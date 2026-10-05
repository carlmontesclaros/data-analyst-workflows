import os
import sqlite3
import pandas as pd

# configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "capacity.db")

# tables

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    setting TEXT PRIMARY KEY,
    value TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS area_factors (
    room_type TEXT PRIMARY KEY,
    area_per_person_m2 REAL
);
    
CREATE TABLE IF NOT EXISTS width_factors (
    exit_type TEXT PRIMARY KEY,
    mm_per_person REAL,
    minimum_mm INTEGER,
    minimum_mm_low_rise INTEGER,
    source TEXT
);
    
CREATE TABLE IF NOT EXISTS category_map (
    space_sub_category TEXT PRIMARY KEY,
    room_type TEXT,
    needs_review TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS rooms (
    room_id INTEGER PRIMARY KEY,
    property TEXT NOT NULL,
    floor TEXT NOT NULL,
    space TEXT NOT NULL,
    building_number TEXT,
    area_m2 REAL,
    space_category TEXT,
    sub_category TEXT,
    capacity INTEGER,
    capacity_source TEXT NOT NULL DEFAULT 'per code',
    visited INTEGER NOT NULL DEFAULT 0,
    room_type_override TEXT,
    note TEXT,
    fmis_capacity INTEGER,
    in_latest_report INTEGER NOT NULL DEFAULT 1,
    last_report TEXT
);
    
CREATE TABLE IF NOT EXISTS exits (
    exit_pk INTEGER PRIMARY KEY,
    property TEXT NOT NULL,
    floor TEXT NOT NULL,
    wing TEXT,
    into_wing TEXT,
    exit_id TEXT NOT NULL,
    exit_type TEXT NOT NULL,
    clear_width_cm INTEGER,
    measured_date TEXT,
    measured_by TEXT,
    narrowest_point TEXT,
    photo_ref TEXT,
    notes TEXT,
    UNIQUE (property, floor, exit_id)
);
    
CREATE TABLE IF NOT EXISTS audit_log (
    log_id INTEGER PRIMARY KEY,
    changed_at TEXT NOT NULL,
    user_login TEXT NOT NULL,
    user_name TEXT,
    table_name TEXT NOT NULL,
    record_key TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    why TEXT,
    clause_ref TEXT
);
"""

def create_schema(conn):
    conn.executescript(SCHEMA)

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

# space report col -> rooms table col
ROOM_COLUMN_NAMES = {
'Property': 'property',
    'Floor': 'floor',
    'Space': 'space',
    'Building Number': 'building_number',
    'Net Space (sq m)': 'area_m2',
    'Space Category': 'space_category',
    'Space Sub-Category': 'sub_category',
    'Room type (per code m^2 used in capacity)': 'room_type_override',
    'Note': 'note',
}

def insert_rooms(conn, df, report_name):
    rooms = df.rename(columns=ROOM_COLUMN_NAMES)
    rooms = rooms.drop(columns=['Capacity (Occupants)'])

    # building number 237.0 -> 237 and blank stays blank
    has_number = rooms['building_number'].notna()
    rooms.loc[has_number, 'building_number'] = (rooms.loc[has_number, 'building_number']
                                                .astype(str).str.removesuffix('.0'))

    # Office and office are the same room type
    rooms['room_type_override'] = rooms['room_type_override'].str.strip().str.lower()

    rooms['in_latest_report'] = 1
    rooms['last_report'] = report_name
    rooms.to_sql('rooms', conn, if_exists='append', index=False)
    return len(rooms)

# code factors: csv file -> table of the same name
CODE_FACTOR_TABLES = ['area_factors', 'width_factors', 'category_map', 'settings']

def import_code_factors(conn, config_dir):
    counts = {}
    for table in CODE_FACTOR_TABLES:
        csv_path = os.path.join(config_dir, f'{table}.csv')
        df = pd.read_csv(csv_path)
        df.to_sql(table, conn, if_exists='append', index=False)
        counts[table] = len(df)
    return counts

# exits
EXIT_COLS = ['Property', 'Floor', 'wing', 'into_wing', 'exit_id', 'exit_type', 'clear_width_cm',
             'measured_date', 'measured_by', 'narrowest_point', 'photo_ref', 'notes']
OPTIONAL_EXIT_COLS = ['wing', 'into_wing', 'measured_date']
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
    df['clear_width_cm'] = pd.to_numeric(df['clear_width_cm'], errors='coerce').astype('Int64')
    df['measured_date'] = pd.to_datetime(df['measured_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    return df

def insert_exits(conn, df):
    exits = df.rename(columns={'Property': 'property', 'Floor': 'floor'})
    warnings = []

    # exit_id and exit_type cant be empty in the table -> skip and say so
    no_id = exits['exit_id'].isna() | exits['exit_type'].isna()
    for _, row in exits[no_id].iterrows():
        warnings.append(f"{row['property']} floor {row['floor']}: exit skipped, missing exit_id or exit_type")
    exits = exits[~no_id].copy()

    # floors and exit types the database doesn't know
    known_floors = set(conn.execute("SELECT DISTINCT property, floor FROM rooms").fetchall())
    known_types = {r[0] for r in conn.execute("SELECT exit_type FROM width_factors").fetchall()}
    for _, row in exits.iterrows():
        label = f"{row['property']} floor {row['floor']} {row['exit_id']}"
        if (row['property'], row['floor']) not in known_floors:
            warnings.append(f"{label}: floor not in the rooms table")
        if row['exit_type'] not in known_types:
            warnings.append(f"{label}: exit type '{row['exit_type']}' has no width factor")
        if pd.isna(row['clear_width_cm']):
            warnings.append(f"{label}: no width")

    exits.to_sql('exits', conn, if_exists='append', index=False)
    return len(exits), warnings