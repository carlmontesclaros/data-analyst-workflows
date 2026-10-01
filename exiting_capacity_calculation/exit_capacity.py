import pandas as pd
import os
import glob
import numpy as np
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from exit_calc import occupant_load, exit_persons, capacity_50_rule, people_sent

#configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
OUTPUT_DIR = BASE_DIR
ROOM_TYPE_COL = "Room type (per code m^2 used in capacity)"
COUNT_COL = "Capacity (Occupants)"
AREA_COL = "Net Space (sq m)"
LOAD_BASIS = 'counted'  # 'counted' = site count, blank count falls back to per code; 'area' = per code for every room
ROOM_EXCLUDE = ['14.3', '16']  # sub-category codes left out of the load (16 = all 16.x non-assignable), [] = all rooms
OPEN_STAIRS_COUNT = False  # BCBC 3.4.4.1.(1) exits must be fire separated -> open stairs don't count until confirmed
VERBOSE = True  # True = print the step checkpoints, False = only files read + summary

# checkpoint prints -> only shown when VERBOSE is on
def checkpoint(msg):
    if VERBOSE:
        print(msg)

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

# same room in 2 different space reports -> stop instead of double counting
files_per_room = rooms.groupby(room_keys)['source_file'].nunique()
if (files_per_room > 1).any():
    raise SystemExit(f"the same rooms are in more than one space report: {sorted(rooms['source_file'].unique())}\n"
                     f"keep only one space report in input/ and run again")
checkpoint(f"rooms: {rooms.shape}")

# room type override
override = rooms[ROOM_TYPE_COL].astype(str).str.strip().str.lower() # lower cases everything, makes everything text
override = override.where(rooms[ROOM_TYPE_COL].notna() & (override != '')) # keeps a value where condition is true puts NaN whens its false

# default room type from category map
default = rooms['Space Sub-Category'].map(category_map) # takes each room's sub-category,from category_map.csv. Rooms with no sub-category get NaN

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

# room occupant load = area / m^2 per person, rounded up
if ROUNDING != 'up':
    raise ValueError(f"settings.csv: occupant_load_rounding is '{ROUNDING}', only 'up' is supported")

rooms['area_per_person_m2'] = rooms['room_type'].map(area_factor)
rooms['occupant_load'] = occupant_load(rooms[AREA_COL], rooms['area_per_person_m2']).fillna(0).astype(int)

# combine exits
if exit_frames:
    all_exits = pd.concat(exit_frames, ignore_index=True)
else: # still get an empty row with the correct columns
    all_exits = pd.DataFrame(columns=exit_cols + ['source_file'])

# keep rows with something recorded
has_data = all_exits[['exit_id', 'exit_type', 'clear_width_cm']].notna().any(axis=1)
exits = all_exits[has_data].copy()
checkpoint(f"exits recorded: {len(exits)}")

# clean exit columns
exits['exit_type'] = exits['exit_type'].fillna('').astype(str).str.strip().str.lower()
for col in ['wing', 'into_wing']:
    exits[col] = exits[col].fillna('').astype(str).str.strip().str.upper()
exits['clear_width_cm'] = pd.to_numeric(exits['clear_width_cm'], errors='coerce')

# person per exit = width in mm / mm per person, rounded down
exits['mm_per_person'] = exits['exit_type'].map(width_df['mm_per_person'])
exits['persons'] = exit_persons(exits['clear_width_cm'], exits['mm_per_person']).fillna(0).astype(int)

# min width check (table 3.4.3.2 via BCBC 2024)
exits['width_mm'] = exits['clear_width_cm'] * 10
exits['minimum_mm'] = exits['exit_type'].map(width_df['minimum_mm'])
exits['minimum_mm_low_rise'] = exits['exit_type'].map(width_df['minimum_mm_low_rise'])

exits['width_check'] = 'ok'
exits.loc[exits['width_mm'] < exits['minimum_mm'], 'width_check'] = 'review - depends on storeys served'
exits.loc[exits['width_mm'] < exits['minimum_mm_low_rise'], 'width_check'] = 'fail - below minimum'
exits.loc[exits['minimum_mm'].isna() | exits['width_mm'].isna(), 'width_check'] = 'unknown'

# open stairs -> not fire separated so not an exit (BCBC 3.4.4.1.(1)), found by "open stair" in exit_id
exits['counts_as_exit'] = True
if not OPEN_STAIRS_COUNT:
    open_stair = exits['exit_id'].astype(str).str.lower().str.contains('open stair')
    exits.loc[open_stair, 'counts_as_exit'] = False
    exits.loc[open_stair, 'persons'] = 0
    exits.loc[open_stair, 'width_check'] = 'not an exit - open stair'
    checkpoint(f"open stairs not counted: {open_stair.sum()}")

# exit warnings -> exits with unknown type of missing width (counting it as 0 people)
bad_type = exits[exits['mm_per_person'].isna()]
for _, row in bad_type.iterrows():
    warning_rows.append({'type': 'unknown_exit_type', 'Property': row['Property'], 'Floor': row['Floor'],
                         'detail': f"{row['exit_id']}: exit_type '{row['exit_type']}' not in width_factors.csv - counted as 0 people"})

no_width = exits[exits['clear_width_cm'].isna()]
for _, row in no_width.iterrows():
    warning_rows.append({'type': 'missing_width', 'Property': row['Property'], 'Floor': row['Floor'],
                         'detail': f"{row['exit_id']}: no clear_width_cm - counted as 0 people"})

checkpoint(f"warnings total: {len(warning_rows)}")

# room wing -> leading letter of Space column
rooms['room_wing'] = rooms['Space'].astype(str).str.strip().str.extract(r'^([A-Za-z]+)')[0].fillna('').str.upper()

# floor key -> one text id per floor, same in rooms and exits
rooms['floor_key'] = rooms['Property'] + ' | ' + rooms['Floor']
exits['floor_key'] = exits['Property'] + ' | ' + exits['Floor']

# split floors -> any exit on the floor has a wing
split_floors = set(exits.loc[exits['wing'] != '', 'floor_key'])

# zone wing - > room's wing letter on split floors
rooms['zone_wing'] = rooms['room_wing'].where(rooms['floor_key'].isin(split_floors), '')

# occupant load per zone
zone_keys = ['Property', 'Floor', 'floor_key', 'zone_wing']
zones = rooms.groupby(zone_keys, as_index=False)['occupant_load'].sum()

# exits per zone
exits['zone_wing'] = exits['wing']
exit_count = exits.groupby(zone_keys, as_index=False)['counts_as_exit'].sum()
exit_count = exit_count.rename(columns={'counts_as_exit': 'exit_count'})

#join -> outer keeps zones that only have exits
zones = zones.merge(exit_count, on=zone_keys, how='outer')
zones['occupant_load'] = zones['occupant_load'].fillna(0).astype(int)
zones['exit_count'] = zones['exit_count'].fillna(0).astype(int)

# dropping pseudo zones -> split floor, 0 load, no exits
pseudo = zones['floor_key'].isin(split_floors) & (zones['occupant_load'] == 0) & (zones['exit_count'] == 0)
zones = zones[~pseudo].copy()

checkpoint(f"zones: {len(zones)}")

# room scope -> every room counts except the sub-categories in ROOM_EXCLUDE (a code also covers its children, 16 -> 16.2.1)
rooms['sub_code'] = rooms['Space Sub-Category'].astype(str).str.split(' - ').str[0].str.strip()
rooms['in_scope'] = True
for code in ROOM_EXCLUDE:
    rooms.loc[(rooms['sub_code'] == code) | rooms['sub_code'].str.startswith(code + '.'), 'in_scope'] = False

# load used per room -> count if filled in (0 stays 0), blank = not seen yet so use per code
rooms[COUNT_COL] = pd.to_numeric(rooms[COUNT_COL], errors='coerce')
if LOAD_BASIS == 'counted':
    rooms['load_used'] = rooms[COUNT_COL].fillna(rooms['occupant_load'])
    rooms['load_source'] = np.where(rooms[COUNT_COL].notna(), 'counted', 'per code')
elif LOAD_BASIS == 'area':
    rooms['load_used'] = rooms['occupant_load']
    rooms['load_source'] = 'per code'
else:
    raise ValueError(f"LOAD_BASIS is '{LOAD_BASIS}', must be 'counted' or 'area'")

rooms.loc[~rooms['in_scope'], 'load_used'] = 0
rooms.loc[~rooms['in_scope'], 'load_source'] = 'out of scope'
rooms['load_used'] = rooms['load_used'].astype(int)
rooms['counted'] = rooms['in_scope'] & rooms[COUNT_COL].notna()
rooms['count_in_scope'] = rooms[COUNT_COL].where(rooms['in_scope'])

checkpoint(f"load basis: {LOAD_BASIS}, excluded sub-categories: {ROOM_EXCLUDE}")
checkpoint(f"rooms in scope: {rooms['in_scope'].sum()}, counted: {rooms['counted'].sum()}, "
      f"per code: {(rooms['load_source'] == 'per code').sum()}")

# per zone -> load used, counted capacity, rooms counted
per_zone = rooms.groupby(zone_keys, as_index=False).agg(load_used=('load_used', 'sum'),
                                                        counted_capacity=('count_in_scope', 'sum'),
                                                        rooms_in_scope=('in_scope', 'sum'),
                                                        rooms_counted=('counted', 'sum'))

zones = zones.merge(per_zone, on=zone_keys, how='left')
for col in ['load_used', 'counted_capacity', 'rooms_in_scope', 'rooms_counted']:
    zones[col] = zones[col].fillna(0).astype(int)

checkpoint(f"zone load used total: {zones['load_used'].sum()}")

# exit capacity per zone -> applying the 50% rule on BCBC 3.4.3.2 (7)
cap = exits.groupby(zone_keys, as_index=False)['persons'].agg(total_persons='sum', largest_exit='max')
cap['exit_capacity'] = capacity_50_rule(cap['total_persons'], cap['largest_exit'])

zones = zones.merge(cap[zone_keys + ['exit_capacity']], on=zone_keys, how='left')
zones['exit_capacity'] = zones['exit_capacity'].fillna(0).astype(int)

# link flow -> a door into another wing sends people to that wing BCBC 3.4.3.1(2)
links = exits.loc[exits['into_wing'] != '', zone_keys + ['exit_id', 'into_wing', 'persons']]
links = links.merge(zones[zone_keys + ['load_used', 'exit_count']], on=zone_keys, how='left')

links['people_sent'] = people_sent(links['load_used'], links['exit_count'], links['persons'], LINK_METHOD).astype(int)

# add people sent to the receiving wing
inflow = links.groupby(['floor_key', 'into_wing'], as_index=False)['people_sent'].sum()
inflow = inflow.rename(columns={'into_wing': 'zone_wing', 'people_sent': 'link_inflow'})

zones = zones.merge(inflow, on=['floor_key', 'zone_wing'], how='left')
zones['link_inflow'] = zones['link_inflow'].fillna(0).astype(int)
zones['total_load'] = zones['load_used'] + zones['link_inflow']

# warning -> link into a wing that isnt a zone
zone_ids = set(zones['floor_key'] + ' | ' + zones['zone_wing'])
for _, row in links.iterrows():
    if f"{row['floor_key']} | {row['into_wing']}" not in zone_ids:
        warning_rows.append({'type': 'link_to_missing_wing', 'Property': row['Property'], 'Floor': row['Floor'],
                             'detail': f"{row['exit_id']}: into_wing '{row['into_wing']}' has no zone - {row['people_sent']} people not added"})

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
    if z['total_load'] == 0:
        flags.append("load is 0 - no rooms in scope, or all counted as 0")

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

# output tables -> pick and order the columns for each sheet
status_order = {'REVIEW': 0, 'WITHIN CAPACITY - review before acting': 1, 'NOT SURVEYED - no exit data': 2}
floor_summary = zones.copy()
floor_summary['status_order'] = floor_summary['status'].map(status_order)
floor_summary = floor_summary.sort_values(['status_order', 'Property', 'Floor', 'zone_wing'])
floor_summary['load_basis'] = LOAD_BASIS
floor_summary = floor_summary.rename(columns={'occupant_load': 'area_based_load'})

# total_load (load_used + link inflow) is the number checked against exit_capacity
summary_cols = ['Property', 'Floor', 'zone_wing', 'status', 'flags',
                'total_load', 'exit_capacity', 'load_basis', 'rooms_in_scope', 'rooms_counted',
                'counted_capacity', 'area_based_load', 'link_inflow', 'exit_count', 'floor_key']
exit_detail_cols = ['Property', 'Floor', 'wing', 'exit_id', 'exit_type', 'clear_width_cm', 'counts_as_exit', 'persons',
                    'width_check', 'mm_per_person', 'minimum_mm', 'minimum_mm_low_rise',
                    'into_wing', 'measured_date', 'source_file', 'floor_key']
room_detail_cols = ['Property', 'Floor', 'Space', 'room_wing', 'zone_wing', 'Space Sub-Category',
                    'room_type', 'room_type_source', AREA_COL, 'area_per_person_m2', 'occupant_load',
                    COUNT_COL, 'in_scope', 'load_used', 'load_source', 'source_file', 'floor_key']

floor_summary = floor_summary[summary_cols]
exit_detail = exits[exit_detail_cols]
room_detail = rooms[room_detail_cols]
warnings_df = pd.DataFrame(warning_rows, columns=['type', 'Property', 'Floor', 'detail'])

# pick buildings for the output -> calculation already ran on the whole campus
available = sorted(floor_summary['Property'].unique())
print(f"\n{len(available)} properties found.")

while True:
    choice = input("Type building name(s), comma-separated (blank = all, q = quit): ").strip()
    if choice.lower() == 'q':
        raise SystemExit("Canceled.")

    terms = [t.strip().lower() for t in choice.split(',') if t.strip()]
    if terms:
        matches = [p for p in available if any(t in p.lower() for t in terms)]
        no_match = [t for t in terms if not any(t in p.lower() for p in available)]
        if no_match:
            print(f"no match for: {no_match}")
    else:
        matches = available
    if not matches:
        print("No properties matched. Try again.")
        continue

    print(f"\n{len(matches)} properties matched:")
    if len(matches) <= 20:
        for m in matches:
            print(" -", m)

    confirm = input("\nWrite these? (y/n): ").strip().lower()
    if confirm == 'y':
        break

# pick floors -> only asked when one building matched
selected_floors = []
if terms and len(matches) == 1:
    building_floors = sorted(floor_summary.loc[floor_summary['Property'] == matches[0], 'Floor'].unique())
    print(f"floors: {', '.join(building_floors)}")
    while True:
        floor_choice = input("Floor(s), comma-separated (blank = all): ").strip()
        selected_floors = [f.strip() for f in floor_choice.split(',') if f.strip()]
        unknown = [f for f in selected_floors if f not in building_floors]
        if not unknown:
            break
        print(f"not a floor in {matches[0]}: {unknown}. Try again.")

# filter -> same selection on all 4 tables
def pick(df):
    df = df[df['Property'].isin(matches)]
    if selected_floors:
        df = df[df['Floor'].isin(selected_floors)]
    return df

floor_summary = pick(floor_summary)
exit_detail = pick(exit_detail)
room_detail = pick(room_detail)
warnings_df = pick(warnings_df)

# file name -> blank = campus file, a selection gets its own file
output_name = "exiting_capacity_results.xlsx"
if terms:
    tag = '_'.join(terms)
    if selected_floors:
        tag += '_floor_' + '-'.join(selected_floors)
    tag = ''.join(c if c.isalnum() or c in '_-' else '-' for c in tag)
    output_name = f"exiting_capacity_results_{tag}.xlsx"

# writing the result workbook -> one sheet per table
output_path = os.path.join(OUTPUT_DIR, output_name)
status_fills = {'REVIEW': PatternFill('solid', fgColor='F8CBAD'),
                'WITHIN CAPACITY - review before acting': PatternFill('solid', fgColor='C6EFCE'),
                'NOT SURVEYED - no exit data': PatternFill('solid', fgColor='E7E6E6')}

try:
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        floor_summary.to_excel(writer, sheet_name='floor_summary', index=False)
        exit_detail.to_excel(writer, sheet_name='exit_detail', index=False)
        room_detail.to_excel(writer, sheet_name='room_detail', index=False)
        warnings_df.to_excel(writer, sheet_name='warnings', index=False)

        # formatting -> bold frozen header, filters, column widths
        for ws in writer.sheets.values():
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for col_cells in ws.columns:
                width = max(len(str(c.value)) for c in col_cells if c.value is not None)
                ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(width + 2, 50)

        # status colours -> whole row on floor_summary
        ws = writer.sheets['floor_summary']
        status_idx = summary_cols.index('status')
        for row in ws.iter_rows(min_row=2):
            fill = status_fills.get(row[status_idx].value)
            if fill:
                for cell in row:
                    cell.fill = fill
except PermissionError:
    raise SystemExit(f"can't write {output_path} - it's probably open in Excel. close it and run again")

# terminal summary
print(f"\n--- summary ---")
print(f"zones: {len(floor_summary)}")
for status, n in floor_summary['status'].value_counts().items():
    print(f"  {status}: {n}")
for _, z in floor_summary[floor_summary['status'] == 'REVIEW'].iterrows():
    print(f"  REVIEW {z['floor_key']} {z['zone_wing']}: {z['flags']}")
print(f"warnings: {len(warnings_df)}")
print(f"written: {output_path}")

input("\nDone. Press Enter to close...")