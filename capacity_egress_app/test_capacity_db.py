import os
import sqlite3
import pandas as pd
import pytest
import capacity_db as db

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

# fake space report rows -> same columns read_space_report gives back
def report(rows):
    cols = db.SPACE_REPORT_COLS
    df = pd.DataFrame(rows, columns=['Property', 'Floor', 'Space', 'Net Space (sq m)', 'Capacity (Occupants)'])
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df['Space Sub-Category'] = '1.2 - Non-Tiered Classroom'
    return df[cols]

BASE_ROWS = [
    ('Engineering Office Wing', '1', '101', 50.0, 20),     # visited building, counted 20
    ('Engineering Office Wing', '1', '102', 30.0, 0),      # visited building, counted 0 -> stays 0
    ('Clearihue Building', '2', 'A201', 40.0, 0),          # FMIS default 0 -> per code
    ('Clearihue Building', '2', 'A202', 40.0, 35),         # FMIS number -> stored, not used
    ('McKinnon Building', '0', '010', 12.0, 0),            # repeated key, two different rooms
    ('McKinnon Building', '0', '010', 25.0, 0),
]

@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    db.create_schema(c)
    db.import_code_factors(c, CONFIG_DIR)
    db.insert_extra_settings(c)
    db.insert_rooms(c, db.classify_rooms(report(BASE_ROWS)), 'first.xlsx')
    return c

def rooms(c):
    return {(r['space'], r['area_m2']): dict(r) for r in c.execute("SELECT * FROM rooms")}

def test_classify_visited_and_fmis(conn):
    r = rooms(conn)
    assert r[('101', 50.0)]['capacity'] == 20 and r[('101', 50.0)]['capacity_source'] == 'site count'
    assert r[('102', 30.0)]['capacity'] == 0 and r[('102', 30.0)]['visited'] == 1
    assert r[('A201', 40.0)]['capacity'] is None and r[('A201', 40.0)]['capacity_source'] == 'per code'
    assert r[('A202', 40.0)]['capacity'] is None and r[('A202', 40.0)]['fmis_capacity'] == 35

def test_first_import_audit_one_row_per_site_count(conn):
    assert db.insert_first_import_audit(conn, 'carl') == 2
    rows = conn.execute("SELECT field, old_value, new_value, why FROM audit_log ORDER BY new_value").fetchall()
    assert [tuple(r) for r in rows] == [('capacity', None, '0', 'first import'), ('capacity', None, '20', 'first import')]

def test_refresh_same_report_changes_nothing_twice(conn):
    db.refresh_space_report(conn, report(BASE_ROWS), 'second.xlsx')
    result = db.refresh_space_report(conn, report(BASE_ROWS), 'second.xlsx')
    assert (result['matched'], result['changed'], result['new'], result['missing']) == (6, 0, 0, 0)

def test_refresh_never_touches_capacity(conn):
    conn.execute("UPDATE rooms SET capacity = 25, capacity_source = 'PM change', note = 'keep me' WHERE space = '101'")
    rows = [list(r) for r in BASE_ROWS]
    rows[0][3] = 55.0                       # area changed in FMIS
    rows[0][4] = 99                         # FMIS disagrees with the app
    result = db.refresh_space_report(conn, report(rows), 'second.xlsx')
    r = conn.execute("SELECT * FROM rooms WHERE space = '101'").fetchone()
    assert (r['area_m2'], r['capacity'], r['capacity_source'], r['note']) == (55.0, 25, 'PM change', 'keep me')
    assert r['fmis_capacity'] == 99
    assert [d['space'] for d in result['disagree']] == ['101']

def test_refresh_new_and_missing_rooms(conn):
    rows = [r for r in BASE_ROWS if r[2] != 'A201'] + [('Clearihue Building', '2', 'A203', 20.0, 0)]
    result = db.refresh_space_report(conn, report(rows), 'second.xlsx')
    assert (result['new'], result['missing']) == (1, 1)
    gone = conn.execute("SELECT in_latest_report FROM rooms WHERE space = 'A201'").fetchone()
    new = conn.execute("SELECT capacity_source, capacity FROM rooms WHERE space = 'A203'").fetchone()
    assert gone[0] == 0                      # kept, flagged
    assert tuple(new) == ('per code', None)

def test_refresh_repeated_key_matches_on_area(conn):
    rows = [r for r in BASE_ROWS if not (r[2] == '010' and r[3] == 12.0)]
    result = db.refresh_space_report(conn, report(rows), 'second.xlsx')
    assert (result['new'], result['missing']) == (0, 1)
    flags = {r['area_m2']: r['in_latest_report'] for r in conn.execute("SELECT * FROM rooms WHERE space = '010'")}
    assert flags == {12.0: 0, 25.0: 1}

def test_insert_exits_warnings(conn):
    exits = pd.DataFrame([
        {'Property': 'Engineering Office Wing', 'Floor': '1', 'exit_id': 'S1 - doorway', 'exit_type': 'doorway', 'clear_width_cm': 88},
        {'Property': 'Fake Hall', 'Floor': '1', 'exit_id': 'S1', 'exit_type': 'ramp', 'clear_width_cm': None},
        {'Property': 'Engineering Office Wing', 'Floor': '1', 'exit_id': None, 'exit_type': 'doorway', 'clear_width_cm': 90},
    ])
    for c in db.EXIT_COLS:
        if c not in exits.columns:
            exits[c] = None
    count, warnings = db.insert_exits(conn, exits[db.EXIT_COLS])
    assert count == 2
    assert len(warnings) == 4               # skipped, floor unknown, ramp, no width

# editing -> every change logged, bad input refused

def room_id(c, space):
    return c.execute("SELECT room_id FROM rooms WHERE space = ?", (space,)).fetchone()[0]

def test_change_capacity_logs_and_marks_visited(conn):
    rid = room_id(conn, 'A201')
    db.change_capacity(conn, rid, 36, 'PM change', 'mark', 'Mark', 'OREM request')
    r = conn.execute("SELECT capacity, capacity_source, visited FROM rooms WHERE room_id = ?", (rid,)).fetchone()
    assert tuple(r) == (36, 'PM change', 0)
    log = [tuple(x) for x in conn.execute("SELECT field, old_value, new_value, why, user_name FROM audit_log")]
    assert log == [('capacity', None, '36', 'OREM request', 'Mark'),
                   ('capacity_source', 'per code', 'PM change', 'OREM request', 'Mark')]
    db.change_capacity(conn, rid, 30, 'site count', 'carl', 'Carl', 'counted on visit')
    assert conn.execute("SELECT visited FROM rooms WHERE room_id = ?", (rid,)).fetchone()[0] == 1

@pytest.mark.parametrize('cap, source, why', [(-1, 'PM change', 'x'), (5, 'per code', 'x'), (5, 'PM change', ' ')])
def test_change_capacity_refuses_bad_input(conn, cap, source, why):
    with pytest.raises(ValueError):
        db.change_capacity(conn, room_id(conn, 'A201'), cap, source, 'carl', 'Carl', why)
    assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 0

def good_exit(**kw):
    v = {'property': 'Engineering Office Wing', 'floor': '1', 'exit_id': 'S1 - doorway',
         'exit_type': 'doorway', 'clear_width_cm': '88', 'measured_date': '2026-10-05'}
    v.update(kw)
    return v

def test_save_exit_add_edit_delete(conn):
    pk = db.save_exit(conn, good_exit(), 'carl', 'Carl')
    db.save_exit(conn, good_exit(clear_width_cm='90', wing='b'), 'carl', 'Carl', exit_pk=pk)
    r = conn.execute("SELECT clear_width_cm, wing FROM exits WHERE exit_pk = ?", (pk,)).fetchone()
    assert tuple(r) == (90, 'B')
    fields = [x[0] for x in conn.execute("SELECT field FROM audit_log WHERE table_name = 'exits'")]
    assert fields == ['exit', 'wing', 'clear_width_cm']
    db.delete_exit(conn, pk, 'carl', 'Carl', 'measured the wrong door')
    assert conn.execute("SELECT count(*) FROM exits").fetchone()[0] == 0

@pytest.mark.parametrize('bad', [{'clear_width_cm': '40'}, {'clear_width_cm': '88.5'}, {'exit_type': 'ramp'},
                                 {'exit_id': ''}, {'property': 'Fake Hall'}, {'measured_date': '05/10/2026'},
                                 {'into_wing': 'A'}])
def test_save_exit_refuses_what_the_excel_sheet_refused(conn, bad):
    with pytest.raises(ValueError):
        db.save_exit(conn, good_exit(**bad), 'carl', 'Carl')

def test_save_exit_refuses_duplicate_id(conn):
    db.save_exit(conn, good_exit(), 'carl', 'Carl')
    with pytest.raises(ValueError):
        db.save_exit(conn, good_exit(), 'carl', 'Carl')

def test_code_factor_needs_clause(conn):
    with pytest.raises(ValueError):
        db.change_code_factor(conn, 'width_factors', 'doorway', 'mm_per_person', 6.0, '', 'carl', 'Carl')
    db.change_code_factor(conn, 'width_factors', 'doorway', 'mm_per_person', 6.0, 'BCBC 2024 3.4.3.2.(1)', 'carl', 'Carl')
    log = conn.execute("SELECT old_value, new_value, clause_ref FROM audit_log").fetchone()
    assert tuple(log) == ('6.1', '6.0', 'BCBC 2024 3.4.3.2.(1)')

def test_notes_and_users(conn):
    rid = room_id(conn, 'A201')
    assert db.set_note(conn, 'rooms', rid, 'tables moved', 'carl', 'Carl')
    assert not db.set_note(conn, 'rooms', rid, 'tables moved', 'carl', 'Carl')
    db.set_user_name(conn, 'cmontesclaros', 'Carl')
    db.set_user_name(conn, 'cmontesclaros', 'Carl M')
    assert db.get_user_name(conn, 'cmontesclaros') == 'Carl M'

def test_backup_once_a_day_keeps_last(conn, tmp_path):
    for day in range(1, 5):
        (tmp_path / f"capacity_2026-01-0{day}.db").write_text('old')
    assert db.backup_database(conn, str(tmp_path), keep=3) is not None
    assert db.backup_database(conn, str(tmp_path), keep=3) is None
    assert len(list(tmp_path.iterdir())) == 3
