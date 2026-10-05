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

CREATE TABLE IF NOT EXISTS users (
    user_login TEXT PRIMARY KEY,
    user_name TEXT NOT NULL
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
    known_floors = {tuple(r) for r in conn.execute("SELECT DISTINCT property, floor FROM rooms").fetchall()}
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
# connection -> rows come back like dicts (row['space'])
def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')

# audit log -> one row per changed field
def log_change(conn, user_login, user_name, table_name, record_key, field, old_value, new_value,
               why=None, clause_ref=None, changed_at=None):
    conn.execute("""INSERT INTO audit_log (changed_at, user_login, user_name, table_name, record_key,
                    field, old_value, new_value, why, clause_ref) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (changed_at or now(), user_login, user_name, table_name, str(record_key), field,
                  None if old_value is None else str(old_value),
                  None if new_value is None else str(new_value), why, clause_ref))

# first import -> every site count room gets its starting capacity in the log
def insert_first_import_audit(conn, user_login, user_name=None):
    changed_at = now()
    rows = conn.execute("SELECT room_id, capacity FROM rooms WHERE capacity_source = 'site count'").fetchall()
    for room_id, capacity in rows:
        log_change(conn, user_login, user_name, 'rooms', room_id, 'capacity', None, capacity,
                   why='first import', changed_at=changed_at)
    return len(rows)

# extra settings the terminal script kept as constants -> now code factors in the database
EXTRA_SETTINGS = [
    ('room_exclude', '14.3,16', 'Sub-category codes left out of the load (16 = all 16.x non-assignable). Carl 2026-09-29'),
    ('open_stairs_count', 'no', 'BCBC 3.4.4.1.(1) exits must be fire separated -> open stairs not counted until Mark rules'),
]

def insert_extra_settings(conn):
    conn.executemany("INSERT INTO settings (setting, value, note) VALUES (?,?,?)", EXTRA_SETTINGS)
    return len(EXTRA_SETTINGS)

# space report refresh -> match rooms on Property + Floor + Space (+ area when a key repeats)
# only FMIS columns change, capacity / source / visited / note / override are never touched
FMIS_COLS = ['building_number', 'area_m2', 'space_category', 'sub_category']

def refresh_space_report(conn, df, report_name):
    report = df.rename(columns=ROOM_COLUMN_NAMES).copy()
    report['fmis_count'] = pd.to_numeric(report['Capacity (Occupants)'], errors='coerce')
    # same room twice, one copy blank -> keep one (ECS 242A)
    report = report.sort_values('fmis_count').drop_duplicates(['property', 'floor', 'space', 'area_m2'])
    has_number = report['building_number'].notna()
    report.loc[has_number, 'building_number'] = (report.loc[has_number, 'building_number']
                                                 .astype(str).str.removesuffix('.0'))

    db = pd.read_sql("SELECT room_id, property, floor, space, area_m2, capacity, in_latest_report FROM rooms", conn)
    keys = ['property', 'floor', 'space']

    # keys found once on both sides -> match on the key alone (area can change)
    report_n = report.groupby(keys)['space'].transform('size')
    db_n = db.groupby(keys)['space'].transform('size')
    single = report[report_n == 1].merge(db[db_n == 1][keys + ['room_id']], on=keys, how='inner')

    # repeated keys -> match on key + area
    matched_report_idx = set(report[report_n == 1].reset_index().merge(
        db[db_n == 1][keys], on=keys)['index'])
    rest_report = report[~report.index.isin(matched_report_idx)].copy()
    rest_db = db[~db['room_id'].isin(single['room_id'])].copy()
    rest_report['area_key'] = rest_report['area_m2'].round(2)
    rest_db['area_key'] = rest_db['area_m2'].round(2)
    by_area = rest_report.reset_index().merge(rest_db[keys + ['area_key', 'room_id']],
                                              on=keys + ['area_key'], how='inner')
    by_area = by_area.drop_duplicates('index').drop_duplicates('room_id')

    matched = pd.concat([single, by_area.set_index('index')], ignore_index=False)
    new_rooms = report[~report.index.isin(set(matched_report_idx) | set(by_area['index']))]
    missing_ids = set(db['room_id']) - set(matched['room_id'])

    # matched rooms -> update FMIS columns, remember FMIS capacity when it's a real number
    changed = 0
    for _, row in matched.iterrows():
        values = [None if pd.isna(row[c]) else row[c] for c in FMIS_COLS]
        fmis = int(row['fmis_count']) if pd.notna(row['fmis_count']) and row['fmis_count'] > 0 else None
        cur = conn.execute(f"""UPDATE rooms SET {', '.join(c + ' = ?' for c in FMIS_COLS)},
                               fmis_capacity = ?, in_latest_report = 1, last_report = ?
                               WHERE room_id = ? AND NOT ({' AND '.join(f'{c} IS ?' for c in FMIS_COLS)}
                               AND fmis_capacity IS ? AND in_latest_report = 1)""",
                           values + [fmis, report_name, int(row['room_id'])] + values + [fmis])
        changed += cur.rowcount
    conn.execute("UPDATE rooms SET last_report = ? WHERE in_latest_report = 1", (report_name,))

    # new rooms -> per code until someone counts them
    if len(new_rooms):
        insert = new_rooms[keys + FMIS_COLS + ['room_type_override', 'note']].copy()
        insert['room_type_override'] = insert['room_type_override'].str.strip().str.lower()
        insert['fmis_capacity'] = new_rooms['fmis_count'].where(new_rooms['fmis_count'] > 0).astype('Int64')
        insert['in_latest_report'] = 1
        insert['last_report'] = report_name
        insert.to_sql('rooms', conn, if_exists='append', index=False)

    # missing rooms -> kept and flagged, never deleted
    if missing_ids:
        conn.executemany("UPDATE rooms SET in_latest_report = 0 WHERE room_id = ?",
                         [(int(i),) for i in missing_ids])

    # disagreements -> app capacity vs FMIS capacity (app value wins, only flagged)
    disagree = conn.execute("""SELECT room_id, property, floor, space, capacity, fmis_capacity FROM rooms
                               WHERE capacity IS NOT NULL AND fmis_capacity IS NOT NULL
                               AND capacity != fmis_capacity""").fetchall()
    return {'matched': len(matched), 'changed': changed, 'new': len(new_rooms),
            'missing': len(missing_ids), 'disagree': [dict(r) for r in disagree]}

# reading tables back for the calculation and the app
def load_rooms(conn):
    return pd.read_sql("SELECT * FROM rooms", conn)

def load_exits(conn):
    return pd.read_sql("SELECT * FROM exits", conn)

def load_code_factors(conn):
    return {
        'area_factors': pd.read_sql("SELECT * FROM area_factors", conn),
        'width_factors': pd.read_sql("SELECT * FROM width_factors", conn),
        'category_map': pd.read_sql("SELECT * FROM category_map", conn),
        'settings': pd.read_sql("SELECT * FROM settings", conn),
    }

# users -> windows login + the nickname people know them by
def get_user_name(conn, user_login):
    row = conn.execute("SELECT user_name FROM users WHERE user_login = ?", (user_login,)).fetchone()
    return row[0] if row else None

def set_user_name(conn, user_login, user_name):
    conn.execute("INSERT INTO users (user_login, user_name) VALUES (?, ?) "
                 "ON CONFLICT(user_login) DO UPDATE SET user_name = excluded.user_name", (user_login, user_name))
    conn.commit()

# change capacity -> site count (counted on a visit) or PM change, always with a reason
CAPACITY_SOURCES = ['site count', 'PM change']

def change_capacity(conn, room_id, new_capacity, source, user_login, user_name, why):
    if source not in CAPACITY_SOURCES:
        raise ValueError(f"capacity source must be one of {CAPACITY_SOURCES}")
    if not str(why or '').strip():
        raise ValueError("say why the capacity changed")
    new_capacity = int(new_capacity)
    if new_capacity < 0:
        raise ValueError("capacity can't be negative")

    old = conn.execute("SELECT capacity, capacity_source, visited FROM rooms WHERE room_id = ?", (room_id,)).fetchone()
    if old is None:
        raise ValueError(f"no room with room_id {room_id}")
    visited = 1 if source == 'site count' else old[2]
    changed_at = now()
    with conn:
        conn.execute("UPDATE rooms SET capacity = ?, capacity_source = ?, visited = ? WHERE room_id = ?",
                     (new_capacity, source, visited, room_id))
        if old[0] != new_capacity:
            log_change(conn, user_login, user_name, 'rooms', room_id, 'capacity', old[0], new_capacity, why, changed_at=changed_at)
        if old[1] != source:
            log_change(conn, user_login, user_name, 'rooms', room_id, 'capacity_source', old[1], source, why, changed_at=changed_at)
        if old[2] != visited:
            log_change(conn, user_login, user_name, 'rooms', room_id, 'visited', old[2], visited, why, changed_at=changed_at)

# notes -> one per room, one per exit
def set_note(conn, table_name, record_id, note, user_login, user_name):
    column, key = {'rooms': ('note', 'room_id'), 'exits': ('notes', 'exit_pk')}[table_name]
    note = str(note or '').strip() or None
    old = conn.execute(f"SELECT {column} FROM {table_name} WHERE {key} = ?", (record_id,)).fetchone()
    if old is None or old[0] == note:
        return False
    with conn:
        conn.execute(f"UPDATE {table_name} SET {column} = ? WHERE {key} = ?", (note, record_id))
        log_change(conn, user_login, user_name, table_name, record_id, column, old[0], note, 'note edited')
    return True

# exits -> same checks as the excel exits sheet
EXIT_EDIT_COLS = ['property', 'floor', 'wing', 'into_wing', 'exit_id', 'exit_type', 'clear_width_cm',
                  'measured_date', 'measured_by', 'narrowest_point', 'photo_ref', 'notes']

def check_exit(conn, values):
    problems = []
    if not values.get('exit_id'):
        problems.append("exit_id is required (e.g. 'S4 - doorway', 'E3 - outside exit')")
    known_types = {r[0] for r in conn.execute("SELECT exit_type FROM width_factors")}
    if values.get('exit_type') not in known_types:
        problems.append(f"exit type must be one of {sorted(known_types)}")
    width = values.get('clear_width_cm')
    if width is None or str(width).strip() == '':
        problems.append("clear width is required")
    else:
        try:
            w = int(str(width).strip())
            if not 50 <= w <= 500:
                problems.append("clear width must be a whole number of cm between 50 and 500")
        except ValueError:
            problems.append("clear width must be a whole number of cm between 50 and 500")
    floor_known = conn.execute("SELECT 1 FROM rooms WHERE property = ? AND floor = ? LIMIT 1",
                               (values.get('property'), values.get('floor'))).fetchone()
    if not floor_known:
        problems.append(f"{values.get('property')} floor {values.get('floor')} is not in the rooms table")
    for col in ['wing', 'into_wing']:
        v = values.get(col) or ''
        if v and not v.isalpha():
            problems.append(f"{col} must be letters only (A, B, ...)")
    if values.get('into_wing') and not values.get('wing'):
        problems.append("a link door (into_wing) needs the wing it leaves from")
    date = values.get('measured_date')
    if date:
        try:
            pd.to_datetime(date, format='%Y-%m-%d')
        except ValueError:
            problems.append("measured date must be YYYY-MM-DD")
    return problems

def clean_exit(values):
    out = {}
    for col in EXIT_EDIT_COLS:
        v = values.get(col)
        v = None if v is None or str(v).strip() == '' else str(v).strip()
        out[col] = v
    for col in ['wing', 'into_wing']:
        if out[col]:
            out[col] = out[col].upper()
    if out['exit_type']:
        out['exit_type'] = out['exit_type'].lower()
    if out['clear_width_cm'] is not None:
        try:
            out['clear_width_cm'] = int(out['clear_width_cm'])
        except ValueError:
            pass
    return out

def save_exit(conn, values, user_login, user_name, exit_pk=None):
    values = clean_exit(values)
    problems = check_exit(conn, values)
    if problems:
        raise ValueError('\n'.join(problems))
    same = conn.execute("SELECT exit_pk FROM exits WHERE property = ? AND floor = ? AND exit_id = ?",
                        (values['property'], values['floor'], values['exit_id'])).fetchone()
    if same and same[0] != exit_pk:
        raise ValueError(f"{values['exit_id']} already exists on {values['property']} floor {values['floor']}")
    changed_at = now()
    with conn:
        if exit_pk is None:
            cur = conn.execute(f"INSERT INTO exits ({', '.join(EXIT_EDIT_COLS)}) VALUES ({', '.join('?' * len(EXIT_EDIT_COLS))})",
                               [values[c] for c in EXIT_EDIT_COLS])
            exit_pk = cur.lastrowid
            log_change(conn, user_login, user_name, 'exits', exit_pk, 'exit', None,
                       f"{values['exit_id']} {values['exit_type']} {values['clear_width_cm']} cm", 'exit added', changed_at=changed_at)
        else:
            old = conn.execute("SELECT * FROM exits WHERE exit_pk = ?", (exit_pk,)).fetchone()
            if old is None:
                raise ValueError(f"no exit with exit_pk {exit_pk}")
            conn.execute(f"UPDATE exits SET {', '.join(c + ' = ?' for c in EXIT_EDIT_COLS)} WHERE exit_pk = ?",
                         [values[c] for c in EXIT_EDIT_COLS] + [exit_pk])
            for c in EXIT_EDIT_COLS:
                if old[c] != values[c]:
                    log_change(conn, user_login, user_name, 'exits', exit_pk, c, old[c], values[c], 'exit edited', changed_at=changed_at)
    return exit_pk

def delete_exit(conn, exit_pk, user_login, user_name, why):
    if not str(why or '').strip():
        raise ValueError("say why the exit is deleted")
    old = conn.execute("SELECT * FROM exits WHERE exit_pk = ?", (exit_pk,)).fetchone()
    if old is None:
        raise ValueError(f"no exit with exit_pk {exit_pk}")
    with conn:
        conn.execute("DELETE FROM exits WHERE exit_pk = ?", (exit_pk,))
        log_change(conn, user_login, user_name, 'exits', exit_pk, 'exit',
                   f"{old['property']} floor {old['floor']} {old['exit_id']} {old['exit_type']} {old['clear_width_cm']} cm",
                   None, why)

# code factors -> every change needs a building code clause
CODE_FACTOR_KEYS = {'area_factors': 'room_type', 'width_factors': 'exit_type',
                    'category_map': 'space_sub_category', 'settings': 'setting'}

def change_code_factor(conn, table_name, key_value, field, new_value, clause_ref, user_login, user_name, why=None):
    if table_name not in CODE_FACTOR_KEYS:
        raise ValueError(f"{table_name} is not a code factor table")
    if not str(clause_ref or '').strip():
        raise ValueError("a building code clause reference is required (e.g. BCBC 2024 3.4.3.2.(1))")
    key = CODE_FACTOR_KEYS[table_name]
    columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table_name})")]
    if field not in columns or field == key:
        raise ValueError(f"{field} is not an editable column of {table_name}")
    old = conn.execute(f"SELECT {field} FROM {table_name} WHERE {key} = ?", (key_value,)).fetchone()
    if old is None:
        raise ValueError(f"no row '{key_value}' in {table_name}")
    with conn:
        conn.execute(f"UPDATE {table_name} SET {field} = ? WHERE {key} = ?", (new_value, key_value))
        log_change(conn, user_login, user_name, table_name, key_value, field, old[0], new_value, why, clause_ref)

# history for one record, newest first
def history(conn, table_name, record_key):
    return pd.read_sql("SELECT changed_at, user_name, user_login, field, old_value, new_value, why, clause_ref "
                       "FROM audit_log WHERE table_name = ? AND record_key = ? ORDER BY log_id DESC",
                       conn, params=(table_name, str(record_key)))

# backup -> one copy per day the app opens, last 30 kept
BACKUP_KEEP = 30

def backup_database(conn, backup_dir, keep=BACKUP_KEEP):
    os.makedirs(backup_dir, exist_ok=True)
    path = os.path.join(backup_dir, f"capacity_{pd.Timestamp.now().strftime('%Y-%m-%d')}.db")
    made = False
    if not os.path.exists(path):
        dest = sqlite3.connect(path)
        with dest:
            conn.backup(dest)
        dest.close()
        made = True
    backups = sorted(f for f in os.listdir(backup_dir) if f.startswith('capacity_') and f.endswith('.db'))
    for old in backups[:-keep]:
        os.remove(os.path.join(backup_dir, old))
    return path if made else None
