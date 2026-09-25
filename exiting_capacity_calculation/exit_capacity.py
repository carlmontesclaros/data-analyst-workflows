import pandas as pd
import os
import glob

#configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
OUTPUT_DIR = BASE_DIR
ROOM_TYPE_COL = "Room type (per code m^2 used in capacity)"
COUNT_COL = "Capacity (Occupants)"

# file recognition
SPACE_REPORT_HEADERS =  {'property', 'floor', 'space'}
EXITS_HEADERS =  {'property', 'floor', 'exit_type'}

room_keys = ['Property', 'Floor', 'Space']
room_cols = ['Property', 'Floor', 'Space', 'Net Space (sq m)',
                'Space Sub-Category', COUNT_COL, ROOM_TYPE_COL]
exit_keys = ['Property', 'Floor', 'exit_id']
exit_cols = ['Property', 'Floor', 'wing', 'exit_id', 'exit_type', 'clear_width_cm', 'into_wing', 'measured_date']
optional_exit_cols = ['wing', 'into_wing', 'measured_date']
zone_keys = ['Property', 'Floor', 'wing']

# counters
reports_processed = 0
exit_files_processed = 0
room_frames = []
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

print(f"area factors: {len(area_factor)}")
print(f"category mappings: {len(category_map)}")
print(f"width factors: {width_df.shape}")
print(f"settings: {ROUNDING}, {MIN_EXITS}, {LINK_METHOD}")
print(f"min exits + 1: {MIN_EXITS + 1}")


