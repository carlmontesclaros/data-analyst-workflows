import pandas as pd
import os
import glob
import numpy as np

#configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
OUTPUT_DIR = BASE_DIR
ROOM_TYPE_COL = "Room type (per code m^2 used in capacity)"
COUNT_COL = "Capacity (Occupants)"
AREA_COL = "Net Space (sq m)"

# file recognition
SPACE_REPORT_HEADERS =  {'property', 'floor', 'space'}
EXITS_HEADERS =  {'property', 'floor', 'exit_type'}

room_keys = ['Property', 'Floor', 'Space']
room_cols = ['Property', 'Floor', 'Space', 'Net Space (sq m)',
                'Space Sub-Category', COUNT_COL, ROOM_TYPE_COL]
exit_keys = ['Property', 'Floor', 'exit_id']
exit_cols = ['Property', 'Floor', 'wing', 'exit_id', 'exit_type', 'clear_width_cm', 'into_wing', 'measured_date']
optional_exit_cols = ['wing', 'into_wing', 'measured_date']

# counters
reports_processed = 0
exit_files_processed = 0
room_frames = []
warning_rows = []
exit_frames = []

# glob
glob_pattern = os.path.join(INPUT_DIR, "*.xlsx")
glob_list = sorted(glob.glob(glob_pattern))

# file loop
for excel_file in glob_list:
    name = os.path.basename(excel_file)
    if name.startswith("~$"):
        continue

    # header detection
    raw = pd.read_excel(excel_file, header=None, nrows=50)
    header_row = None
    kind = None

    for i in range(len(raw)):
        values = {str(x).strip().lower() for x in raw.iloc[i].tolist()}
        if SPACE_REPORT_HEADERS.issubset(values):
            header_row, kind = i, "space report"
            break
        if EXITS_HEADERS.issubset(values):
            header_row, kind = i, "exits"
            break

    if header_row is None:
        raise ValueError(f"{name}: not a space report (Property/Floor/Space)" 
                         f" or an exit report (Property/Floor/exit_type)")

    # read excel file -> first sheet
    df = pd.read_excel(excel_file, header=header_row)

    if kind == "space report":
        missing = [c for c in room_cols if c not in df.columns]
        if missing:
            raise ValueError(f"{name}: missing columns: {missing}")

        df_clean = df[room_cols].copy()
        df_clean = df_clean.dropna(subset=room_keys)
        reports_processed += 1
        room_frames.append(df_clean)

    else:
        # optional cols
        for col in optional_exit_cols:
            if col not in df.columns:
                df[col] = None
        missing = [c for c in exit_cols if c not in df.columns]
        if missing:
            raise ValueError(f"{name}: is missing columns: {missing}")

        df_clean = df[exit_cols].copy()
        df_clean = df_clean.dropna(subset=['Property', 'Floor'])
        exit_files_processed += 1
        exit_frames.append(df_clean)

    # clean up
    for col in ['Property', 'Floor']:
        df_clean[col] = df_clean[col].astype(str).str.strip().str.removesuffix(".0")
    df_clean['source_file'] = name
    print(f"{name}: {kind}, {len(df_clean)} rows")

if not room_frames:
    raise ValueError("No space reports found input")

# load config
area_df = pd.read_csv(os.path.join(CONFIG_DIR, "area_factors.csv"))
category_df = pd.read_csv(os.path.join(CONFIG_DIR, "category_map.csv"))
width_df = pd.read_csv(os.path.join(CONFIG_DIR, "width_factors.csv"))
setting_df = pd.read_csv(os.path.join(CONFIG_DIR, "settings.csv"))

# lookups
area_factor = dict(zip(area_df['room_type'], area_df['area_per_person_m2']))
category_map = dict(zip(category_df['space_sub_category'], category_df['room_type']))
settings = dict(zip(setting_df['setting'], setting_df['value']))
width_df = width_df.set_index('exit_type')

# settings
ROUNDING = settings['occupant_load_rounding']
MIN_EXITS = int(settings['minimum_exits'])
LINK_METHOD = settings['link_share_method']

# combine rooms
rooms = pd.concat(room_frames, ignore_index=True) # stacks space report frames into one table
rooms = rooms.drop_duplicates(subset=room_cols) # drops rows that are identical in every col selected
print(f"rooms: {rooms.shape}")

# room type override
override = rooms[ROOM_TYPE_COL].astype(str).str.strip().str.lower() # lower cases everything, makes everything text
override = override.where(rooms[ROOM_TYPE_COL].notna() & (override != '')) # keeps a value where condition is true puts NaN whens its false

print(f"overrides: {override.notna().sum()}")

# default room type from category map
default = rooms['Space Sub-Category'].map(category_map) # takes each room's sub-category,from category_map.csv. Rooms with no sub-category get NaN

print(f"rooms with a category default: {default.notna().sum()}")

# final room type -> override wins, else category default
rooms['room_type'] = override.fillna(default) # keeps override if it exists, else default

# where the rooms came from (goes in room detail)
rooms['room_type_source'] = 'none'
rooms. loc[default.notna(), 'room_type_source'] = 'category'
rooms.loc[override.notna(), 'room_type_source'] = 'override'

# warn -> rooms with area but no room type (counting as 0 occupancy)
no_type = rooms[rooms['room_type'].isna() & (rooms['Net Space (sq m)'] > 0)]
for _, row in no_type.iterrows():
    warning_rows.append({'type': 'no_room_type', 'Property': row['Property'], 'Floor': row['Floor'],
                         'detail': f"{row['Space']}: {row['Net Space (sq m)']} m2, no sub-category or override - counted as 0 people"})

print(f"warnings - no room type: {len(no_type)}")

# room occupant load = area / m^2 per person, rounded up
if ROUNDING != 'up':
    raise ValueError(f"settings.csv: occupant_load_rounding is '{ROUNDING}', only 'up' is supported")

rooms['area_per_person_m2'] = rooms['room_type'].map(area_factor)
raw_load = rooms[AREA_COL] / rooms['area_per_person_m2']
rooms['occupant_load'] = np.ceil(raw_load.round(6)).fillna(0).astype(int)

print(f"rooms with people: {(rooms['occupant_load'] > 0).sum()}")
print(f"total occupant load: {rooms['occupant_load'].sum()}")

# combine exits
if exit_frames:
    all_exits = pd.concat(exit_frames, ignore_index=True)
else: # still get an empty row with the correct columns
    all_exits = pd.DataFrame(columns=exit_cols + ['source_file'])
print(f"exit rows read: {len(all_exits)}")

# keep rows with something recorded
has_data = all_exits[['exit_id', 'exit_type', 'clear_width_cm']].notna().any(axis=1)
exits = all_exits[has_data].copy()
print(f"exits recorded: {len(exits)}")

# clean exit columns
exits['exit_type'] = exits['exit_type'].fillna('').astype(str).str.strip().str.lower()
for col in ['wing', 'into_wing']:
    exits[col] = exits[col].fillna('').astype(str).str.strip().str.upper()
exits['clear_width_cm'] = pd.to_numeric(exits['clear_width_cm'], errors='coerce')

# person per exit = width in mm / mm per person, rounded down
exits['mm_per_person'] = exits['exit_type'].map(width_df['mm_per_person'])
raw_persons = exits['clear_width_cm'] * 10 / exits['mm_per_person']
exits['persons'] = np.floor(raw_persons.round(6)).fillna(0).astype(int)

# min width check (table 3.4.3.2 via BCBC 2024)
exits['width_mm'] = exits['clear_width_cm'] * 10
exits['minimum_mm'] = exits['exit_type'].map(width_df['minimum_mm'])
exits['minimum_mm_low_rise'] = exits['exit_type'].map(width_df['minimum_mm_low_rise'])

exits['width_check'] = 'ok'
exits.loc[exits['width_mm'] < exits['minimum_mm'], 'width_check'] = 'review - depends on storeys served'
exits.loc[exits['width_mm'] < exits['minimum_mm_low_rise'], 'width_check'] = 'fail - below minimum'
exits.loc[exits['minimum_mm'].isna() | exits['width_mm'].isna(), 'width_check'] = 'unknown'

# exit warnings -> exits with unknown type of missing width (counting it as 0 people)
bad_type = exits[exits['mm_per_person'].isna()]
for _, row in bad_type.iterrows():
    warning_rows.append({'type': 'unknown_exit_type', 'Property': row['Property'], 'Floor': row['Floor'],
                         'detail': f"{row['exit_id']}: exit_type '{row['exit_type']}' not in width_factors.csv - counted as 0 people"})

no_width = exits[exits['clear_width_cm'].isna()]
for _, row in no_width.iterrows():
    warning_rows.append({'type': 'missing_width', 'Property': row['Property'], 'Floor': row['Floor'],
                         'detail': f"{row['exit_id']}: no clear_width_cm - counted as 0 people"})

print(f"warnings - unknown exit type: {len(bad_type)}")
print(f"warnings - missing width: {len(no_width)}")
print(f"warnings total: {len(warning_rows)}")

# room wing -> leading letter of Space column
rooms['room_wing'] = rooms['Space'].astype(str).str.strip().str.extract(r'^([A-Za-z]+)')[0].fillna('').str.upper()

print(f"rooms with a wing letter: {(rooms['room_wing'] != '').sum()}")

# floor key -> one text id per floor, same in rooms and exits
rooms['floor_key'] = rooms['Property'] + ' | ' + rooms['Floor']
exits['floor_key'] = exits['Property'] + ' | ' + exits['Floor']

# split floors -> any exit on the floor has a wing
split_floors = set(exits.loc[exits['wing'] != '', 'floor_key'])
print(f"split floors: {len(split_floors)} {sorted(split_floors)}")

# zone wing - > room's wing letter on split floors
rooms['zone_wing'] = rooms['room_wing'].where(rooms['floor_key'].isin(split_floors), '')

# occupant load per zone
zone_keys = ['Property', 'Floor', 'floor_key', 'zone_wing']
zones = rooms.groupby(zone_keys, as_index=False)['occupant_load'].sum()

# exits per zone
exits['zone_wing'] = exits['wing']
exit_count = exits.groupby(zone_keys, as_index=False).size()
exit_count = exit_count.rename(columns={'size': 'exit_count'})

#join -> outer keeps zones that only have exits
zones = zones.merge(exit_count, on=zone_keys, how='outer')
zones['occupant_load'] = zones['occupant_load'].fillna(0).astype(int)
zones['exit_count'] = zones['exit_count'].fillna(0).astype(int)

# dropping pseudo zones -> split floor, 0 load, no exits
pseudo = zones['floor_key'].isin(split_floors) & (zones['occupant_load'] == 0) & (zones['exit_count'] == 0)
zones = zones[~pseudo].copy()

print(f"pseudo-zones dropped: {pseudo.sum()}")
print(f"zones: {len(zones)}")
print(f"zone load total: {zones['occupant_load'].sum()}")

# exit capacity per zone -> applying the 50% rule on BCBC 3.4.3.2 (7)
cap = exits.groupby(zone_keys, as_index=False)['persons'].agg(total_persons='sum', largest_exit='max')
cap['others'] = cap['total_persons'] - cap['largest_exit']
cap['exit_capacity'] = np.minimum(cap['total_persons'], 2 * cap['others'])

zones = zones.merge(cap[zone_keys + ['exit_capacity']], on=zone_keys, how='left')
zones['exit_capacity'] = zones['exit_capacity'].fillna(0).astype(int)

print(zones[zones['exit_count'] > 0])

# link flow -> a door into another wing sends people to that wing BCBC 3.4.3.1(2)
links = exits.loc[exits['into_wing'] != '', zone_keys + ['exit_id', 'into_wing', 'persons']]
links = links.merge(zones[zone_keys + ['occupant_load', 'exit_count']], on=zone_keys, how='left')

if LINK_METHOD == 'even_split':
    share = np.ceil((links['occupant_load'] / links['exit_count']).round(6))
elif LINK_METHOD == 'half_load':
    share = np.ceil((links['occupant_load'] / 2).round(6))
else:
    raise ValueError(f"settings.csv: link_share_method '{LINK_METHOD}' must be even_split or half_load")

links['people_sent'] = np.minimum(share, links['persons']).astype(int)

# add people sent to the receiving wing
inflow = links.groupby(['floor_key', 'into_wing'], as_index=False)['people_sent'].sum()
inflow = inflow.rename(columns={'into_wing': 'zone_wing', 'people_sent': 'link_inflow'})

zones = zones.merge(inflow, on=['floor_key', 'zone_wing'], how='left')
zones['link_inflow'] = zones['link_inflow'].fillna(0).astype(int)
zones['total_load'] = zones['occupant_load'] + zones['link_inflow']

# warning -> link into a wing that isnt a zone
zone_ids = set(zones['floor_key'] + ' | ' + zones['zone_wing'])
for _, row in links.iterrows():
    if f"{row['floor_key']} | {row['into_wing']}" not in zone_ids:
        warning_rows.append({'type': 'link_to_missing_wing', 'Property': row['Property'], 'Floor': row['Floor'],
                             'detail': f"{row['exit_id']}: into_wing '{row['into_wing']}' has no zone - {row['people_sent']} people not added"})

print(f"link doors: {len(links)}, people sent: {links['people_sent'].sum()}")
print(f"warnings total: {len(warning_rows)}")

# width problems per  zone -> true if any exit in the zone has one
exits['width_fail'] = exits['width_check'].str.startswith('fail')
exits['width_review'] = exits['width_check'].str.startswith('review')
exits['width_unknown'] = exits['width_check'] == 'unknown'
width_flags = exits.groupby(zone_keys, as_index=False)[['width_fail', 'width_review', 'width_unknown']].any()

zones = zones.merge(width_flags, on=zone_keys, how='left')
for col in ['width_fail', 'width_review', 'width_unknown']:
    zones[col] = zones[col].eq(True)

# wings that send people through link door
sending = set(links['floor_key'] + ' | ' + links['zone_wing'])
zones['link_sends'] = (zones['floor_key'] + ' | ' + zones['zone_wing']).isin(sending)

# status + flags per zone
statuses = []
flag_texts = []
for _, z in zones.iterrows():
    flags = []
    if z['exit_count'] < MIN_EXITS:
        flags.append(f"fewer than {MIN_EXITS} exits")
    if z['total_load'] > z['exit_capacity']:
        flags.append("occupant load over exiting capacity")
    if z['width_fail']:
        flags.append("exit below minimum width")
    if z['width_review']:
        flags.append("stair width depends on storeys served")
    if z['width_unknown']:
        flags.append("exit type or width unknown")
    if z['link_sends'] and z['link_inflow'] > 0:
        flags.append("wing sends and receives link traffic")

    if z['exit_count'] == 0:
        status = 'NOT SURVEYED - no exit data'
        flags = []
    elif flags:
        status = 'REVIEW'
    else:
        status = 'WITHIN CAPACITY - review before acting'

    statuses.append(status)
    flag_texts.append('; '.join(flags))

zones['status'] = statuses
zones['flags'] = flag_texts

print(zones['status'].value_counts())

# counted capacity per zone -> site counts carried next t the area based load
rooms[COUNT_COL] = pd.to_numeric(rooms[COUNT_COL], errors='coerce').fillna(0).astype(int)
rooms['counted'] = rooms[COUNT_COL] > 0
counted = rooms.groupby(zone_keys, as_index=False).agg(counted_capacity=(COUNT_COL, 'sum'), rooms_counted=('counted', 'sum'))

zones = zones.merge(counted, on=zone_keys, how='left')
for col in ['counted_capacity', 'rooms_counted']:
    zones[col] = zones[col].fillna(0).astype(int)

print(f"rooms counted: {rooms['counted'].sum()}, counted capacity total: {rooms[COUNT_COL].sum()}")
print(f"zone counted total: {zones['counted_capacity'].sum()}, zones with counts: {(zones['rooms_counted'] > 0).sum()}")