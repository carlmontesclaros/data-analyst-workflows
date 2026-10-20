import os
import pandas as pd

# reading the input workbooks -> the space report and the floor exits file, found by their header row
# (header rows move between exports, so they're detected, never hardcoded). Writing to the database is capacity_db

# header detection
SPACE_REPORT_HEADERS = {'property', 'floor', 'space'}
EXITS_HEADERS = {'property', 'floor', 'exit_type'}

def find_header(excel_file, required):
    raw = pd.read_excel(excel_file, header=None, nrows=50)
    for i in range(len(raw)):
        values = {str(x).strip().lower() for x in raw.iloc[i].tolist()}
        if required.issubset(values):
            return i
    return None

# space report
SPACE_REPORT_COLS = ['Property', 'Floor', 'Space', 'Building Number', 'Net Space (sq m)',
                     'Space Category', 'Space Sub-Category', 'Capacity (Occupants)',
                     'Room type (per code m^2 used in capacity)', 'Note']
ROOM_KEYS = ['Property', 'Floor', 'Space']

def read_space_report(excel_file):
    name = os.path.basename(excel_file)
    header_row = find_header(excel_file, SPACE_REPORT_HEADERS)
    if header_row is None:
        raise ValueError(f"{name}: not a space report (no Property/Floor/Space header in the first 50 rows)")

    df = pd.read_excel(excel_file, header=header_row)
    missing = [c for c in SPACE_REPORT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")

    df = df[SPACE_REPORT_COLS].copy()
    df = df.dropna(subset=ROOM_KEYS)
    for col in ROOM_KEYS:
        df[col] = df[col].astype(str).str.strip().str.removesuffix(".0")
    df = df.drop_duplicates()
    return df

# first import on which building have visited
VISITED_BUILDINGS = ['Engineering Office Wing', 'Engineering Lab Wing',
                     'Engineering / Computer Science Building']
VISITED_FLOORS = [('David Turpin Building', '2', 'B'),
                  ('David Turpin Building', '3', 'B')]   # (property, floor, wing)

def classify_rooms(df):
    df = df.copy()
    count = pd.to_numeric(df['Capacity (Occupants)'], errors='coerce')

    # same room twice, one copy blank -> drop the blank copy (ECS 242A)
    twin = df.duplicated(ROOM_KEYS + ['Net Space (sq m)'], keep=False)
    keep = ~(twin & count.isna())
    df, count = df[keep].copy(), count[keep]

    # visited area mask
    visited_area = df['Property'].isin(VISITED_BUILDINGS)
    for prop, floor, wing in VISITED_FLOORS:
        visited_area = visited_area | ((df['Property'] == prop) & (df['Floor'] == floor)
                                       & df['Space'].str.upper().str.startswith(wing))

    site = visited_area & count.notna()
    df['capacity'] = count.where(site).astype('Int64')
    df['capacity_source'] = 'per code'
    df.loc[site, 'capacity_source'] = 'site count'
    df['visited'] = site.astype(int)
    df['fmis_capacity'] = count.where(~visited_area & (count > 0)).astype('Int64')
    return df

# exits
EXIT_COLS = ['Property', 'Floor', 'wing', 'into_wing', 'exit_id', 'exit_type', 'clear_width_cm',
             'measured_date', 'measured_by', 'narrowest_point', 'photo_ref', 'notes', 'stair_width_cm', 'stair_type']
OPTIONAL_EXIT_COLS = ['wing', 'into_wing', 'measured_date', 'stair_width_cm', 'stair_type']
MEASURED_COLS = ['exit_id', 'exit_type', 'clear_width_cm']

def read_exits(excel_file):
    name = os.path.basename(excel_file)
    header_row = find_header(excel_file, EXITS_HEADERS)
    if header_row is None:
        raise ValueError(f"{name}: not an exits file (no Property/Floor/exit_type header in the first 50 rows)")

    df = pd.read_excel(excel_file, header=header_row)
    for col in OPTIONAL_EXIT_COLS:
        if col not in df.columns:
            df[col] = None
    missing = [c for c in EXIT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns: {missing}")

    df = df[EXIT_COLS].copy()
    df = df.dropna(subset=['Property', 'Floor'])
    df = df[df[MEASURED_COLS].notna().any(axis=1)].copy()
    for col in ['Property', 'Floor']:
        df[col] = df[col].astype(str).str.strip().str.removesuffix(".0")
    for col in ['clear_width_cm', 'stair_width_cm']:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    df['measured_date'] = pd.to_datetime(df['measured_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    return df
