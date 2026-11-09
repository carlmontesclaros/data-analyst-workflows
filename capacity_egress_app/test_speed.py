# speed budgets on a campus-size database -> a change that makes the app slow fails here, not on Mark's screen.
# real campus 2026-11: 19,451 rooms, opening the data ~0.2 s and a save ~1 ms on the Mac.
# budgets leave room for slower machines (CI, the workstations, the S: drive) but catch anything 10x slower
import time
import tkinter as tk
import pytest
import app
import capacity_db as db
import egress
import excel_inputs as xi
import widgets
from test_capacity_db import report, CONFIG_DIR
from test_editor_screen import dialog, entries, press, type_into

BUILDINGS, FLOORS, ROOMS_PER_FLOOR = 200, 4, 25          # 20,000 rooms
LOG_ROWS = 100_000                                       # years of changes; the log is kept forever

def campus_rooms():
    rows = [(f"Building {b:03d}", str(f), f"{f}{r:02d}", 20.0 + r, 0 if r % 3 else None)
            for b in range(BUILDINGS) for f in range(1, FLOORS + 1) for r in range(ROOMS_PER_FLOOR)]
    return report(rows)

@pytest.fixture(scope='module')
def campus(tmp_path_factory):
    path = str(tmp_path_factory.mktemp('campus') / 'capacity.db')
    c = db.connect(path)
    db.create_schema(c)
    db.import_code_factors(c, CONFIG_DIR)
    db.insert_extra_settings(c)
    db.insert_rooms(c, xi.classify_rooms(campus_rooms()), 'campus.xlsx')
    for b in range(0, BUILDINGS, 10):                    # exits measured on every 10th building
        for f in range(1, FLOORS + 1):
            for door in ('S1', 'S2'):
                db.save_exit(c, {'property': f"Building {b:03d}", 'floor': str(f), 'exit_id': f"{door} - doorway",
                                 'exit_type': 'doorway', 'clear_width_cm': '88'}, 'carl', 'Carl')
    with c:
        c.executemany("INSERT INTO audit_log (changed_at, user_login, table_name, record_key, field, old_value, new_value) "
                      "VALUES ('2026-01-01 00:00:00', 'carl', 'rooms', ?, 'capacity', '1', '2')",
                      [(str(i % 20_000 + 1),) for i in range(LOG_ROWS)])
    db.set_editor(c, 'carl', True, 'carl', 'Carl', why='first editor')
    c.close()
    return path

@pytest.fixture
def conn(campus):
    c = db.connect(campus)
    yield c
    c.close()

# fastest of a few runs -> one slow moment on a busy machine doesn't fail the test
def seconds(f, runs=3):
    best = float('inf')
    for _ in range(runs):
        start = time.perf_counter()
        f()
        best = min(best, time.perf_counter() - start)
    return best

def test_campus_is_campus_size(conn):
    assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == BUILDINGS * FLOORS * ROOMS_PER_FLOOR
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] > LOG_ROWS

# what every screen does when it opens or refreshes: read everything, calculate the whole campus
def test_opening_the_data_is_quick(conn):
    def open_data():
        egress.calculate(db.load_rooms(conn), db.load_exits(conn), db.load_code_factors(conn))
    assert seconds(open_data) < 2.0

def test_a_save_is_instant(conn):
    rid = conn.execute("SELECT room_id FROM rooms WHERE space = '101' LIMIT 1").fetchone()[0]
    count = iter(range(1, 100))
    assert seconds(lambda: db.change_capacity(conn, rid, next(count), 'PM change', 'carl', 'Carl', 'speed'), runs=5) < 0.2

# "changed by Mark at 2:14" and Room history -> looked up in the change log, inside the save's lock.
# without an index that reads the whole log, and the log only grows
def test_change_log_lookups_use_the_index(conn):
    plan = ' '.join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN SELECT changed_at FROM audit_log "
                                               "WHERE table_name = 'rooms' AND record_key = '5' ORDER BY log_id DESC LIMIT 1"))
    assert 'USING INDEX' in plan
    assert seconds(lambda: db.history(conn, 'rooms', 5)) < 0.05

# what a person feels: open the editor screen, press Save -> the screen shows the new numbers
def test_editor_screen_open_and_save(conn):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.withdraw()
        widgets.use_theme(root)
        start = time.perf_counter()
        screen = app.App(tk.Toplevel(root), conn, 'carl', 'Carl')
        screen.root.update()
        opened = time.perf_counter() - start

        r = dict(conn.execute("SELECT * FROM rooms WHERE property = 'Building 000' AND space = '101'").fetchone())
        screen.focus_room(r)
        screen.root.update()
        screen.change_capacity()
        win = dialog(screen, 'Change capacity')
        capacity, why = entries(win)
        type_into(capacity, '77')
        type_into(why, 'speed')
        start = time.perf_counter()
        press(win, 'Save')
        screen.root.update()
        saved = time.perf_counter() - start
        shown = screen.room_tree.item(f"r{r['room_id']}", 'values')[7]
    finally:
        root.destroy()
    assert shown == '77'
    assert opened < 3.0, f"editor screen took {opened:.2f} s to open"
    assert saved < 2.0, f"Save took {saved:.2f} s to show the new numbers"
