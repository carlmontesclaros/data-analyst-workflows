import os
import glob
import getpass
import capacity_db as db

# configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(db.DATA_DIR, "input")      # space report + floor_exits.xlsx (local, gitignored)
CONFIG_DIR = os.path.join(BASE_DIR, "config")        # code factor csvs, only read on the first import
DB_PATH = db.DB_PATH

# one time only -> never rebuild over a database people have typed into
if os.path.exists(DB_PATH):
    raise SystemExit(f"{DB_PATH} already exists. the first import only runs once.\n"
                     f"to load a newer space report use the app's refresh, not this script")

# find the input files by their header row, names don't matter
space_reports = []
exit_files = []
for excel_file in sorted(glob.glob(os.path.join(INPUT_DIR, "*.xlsx"))):
    name = os.path.basename(excel_file)
    if name.startswith("~$"):
        continue
    if db.find_header(excel_file, db.SPACE_REPORT_HEADERS) is not None:
        space_reports.append(excel_file)
    elif db.find_header(excel_file, db.EXITS_HEADERS) is not None:
        exit_files.append(excel_file)

if len(space_reports) != 1:
    raise SystemExit(f"need exactly one space report in {INPUT_DIR}, found {len(space_reports)}")
report = space_reports[0]
report_name = os.path.basename(report)
print(f"space report: {report_name}")
print(f"exit files: {[os.path.basename(f) for f in exit_files]}")

user_login = getpass.getuser()
os.makedirs(db.DATA_DIR, exist_ok=True)
conn = db.connect(DB_PATH)

try:
    # tables
    db.create_schema(conn)

    # code factors first -> exits are checked against width_factors
    counts = db.import_code_factors(conn, CONFIG_DIR)
    db.insert_extra_settings(conn)
    print(f"code factors: {counts}")

    # rooms
    rooms = db.classify_rooms(db.read_space_report(report))
    n_rooms = db.insert_rooms(conn, rooms, report_name)
    print(f"rooms: {n_rooms}")
    print(f"  {rooms['capacity_source'].value_counts().to_dict()}")

    # exits
    n_exits = 0
    for exit_file in exit_files:
        count, warnings = db.insert_exits(conn, db.read_exits(exit_file))
        n_exits += count
        for w in warnings:
            print(f"  warning: {w}")
    print(f"exits: {n_exits}")

    # first import -> starting capacities in the log
    n_logged = db.insert_first_import_audit(conn, user_login)
    print(f"audit log rows: {n_logged}")

    conn.commit()
except Exception:
    # half built database is worse than none -> remove it
    conn.close()
    os.remove(DB_PATH)
    raise

conn.close()
print(f"\nwritten: {DB_PATH}")
input("\nDone. Press Enter to close...")
