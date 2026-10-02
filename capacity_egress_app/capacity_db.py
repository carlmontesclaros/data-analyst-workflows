import os
import sqlite3

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

