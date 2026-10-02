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