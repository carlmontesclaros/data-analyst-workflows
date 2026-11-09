import os
import sqlite3
import pandas as pd
import pytest
import capacity_db as db
import excel_inputs as xi

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

# fake space report rows -> same columns read_space_report gives back
def report(rows):
    cols = xi.SPACE_REPORT_COLS
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
    db.insert_rooms(c, xi.classify_rooms(report(BASE_ROWS)), 'first.xlsx')
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
    for c in xi.EXIT_COLS:
        if c not in exits.columns:
            exits[c] = None
    count, warnings = db.insert_exits(conn, exits[xi.EXIT_COLS])
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

# a 0 nobody counted (FMIS default, first import) -> back to not visited, so the room uses per code again
def test_clear_count_makes_room_not_visited_and_logs_it(conn):
    rid = room_id(conn, '102')
    assert tuple(conn.execute("SELECT capacity, capacity_source, visited FROM rooms WHERE room_id = ?", (rid,)).fetchone()) == (0, 'site count', 1)
    db.clear_count(conn, rid, 'carl', 'Carl', 'nothing written in the space report')
    assert tuple(conn.execute("SELECT capacity, capacity_source, visited FROM rooms WHERE room_id = ?", (rid,)).fetchone()) == (None, 'per code', 0)
    log = [tuple(x) for x in conn.execute("SELECT field, old_value, new_value FROM audit_log "
                                          "WHERE why = 'nothing written in the space report' ORDER BY log_id")]
    assert log == [('capacity', '0', None), ('capacity_source', 'site count', 'per code'), ('visited', '1', '0')]

def test_clear_count_needs_a_reason_and_a_known_room(conn):
    before = conn.execute("SELECT count(*) FROM audit_log").fetchone()[0]
    with pytest.raises(ValueError):
        db.clear_count(conn, room_id(conn, '102'), 'carl', 'Carl', ' ')
    with pytest.raises(ValueError):
        db.clear_count(conn, -1, 'carl', 'Carl', 'x')
    assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == before

def test_clear_count_refuses_a_stale_screen(conn):
    rid = room_id(conn, '102')
    with pytest.raises(db.StaleDataError):
        db.clear_count(conn, rid, 'carl', 'Carl', 'x', expected=(5, 'site count'))

def test_clear_count_is_editors_only(conn):
    db.set_editor(conn, 'carl', True, 'carl', 'Carl', why='first editor')
    with pytest.raises(db.NotEditorError):
        db.clear_count(conn, room_id(conn, '102'), 'viewer1', 'Viewer', 'x')

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

# a factor of 0 or a mistyped setting would stop the calculation, so nobody could open the app -> not saved
@pytest.mark.parametrize('table, key, field, value', [
    ('area_factors', 'classroom', 'area_per_person_m2', 0),
    ('area_factors', 'classroom', 'area_per_person_m2', -1.85),
    ('width_factors', 'doorway', 'mm_per_person', 0),
    ('settings', 'minimum_exits', 'value', 'two'),
    ('settings', 'link_share_method', 'value', 'evensplit'),
])
def test_code_factor_that_breaks_the_calculation_isnt_saved(conn, table, key, field, value):
    key_col = db.CODE_FACTOR_KEYS[table]
    before = conn.execute(f"SELECT {field} FROM {table} WHERE {key_col} = ?", (key,)).fetchone()[0]
    with pytest.raises(ValueError):
        db.change_code_factor(conn, table, key, field, value, 'BCBC 2024 test', 'carl', 'Carl')
    assert conn.execute(f"SELECT {field} FROM {table} WHERE {key_col} = ?", (key,)).fetchone()[0] == before
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0

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

# hand-made backups (capacity_before_...) are kept and don't use up the 30 daily slots
def test_backup_keeps_hand_made_backups_out_of_the_count(conn, tmp_path):
    for day in range(1, 5):
        (tmp_path / f"capacity_2026-01-0{day}.db").write_text('old')
    (tmp_path / "capacity_before_rebuild_2026-01-02.db").write_text('manual')
    db.backup_database(conn, str(tmp_path), keep=3)
    names = sorted(f.name for f in tmp_path.iterdir())
    assert "capacity_before_rebuild_2026-01-02.db" in names
    assert len([n for n in names if not n.startswith('capacity_before')]) == 3

# disaster recovery: a backup only counts once it's complete and passes SQLite's own check
def test_backup_is_a_working_copy(conn, tmp_path):
    path = db.backup_database(conn, str(tmp_path))
    copy = sqlite3.connect(path)
    assert copy.execute("PRAGMA quick_check").fetchone()[0] == 'ok'
    assert copy.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == len(BASE_ROWS)
    copy.close()
    assert [f.name for f in tmp_path.iterdir()] == [os.path.basename(path)]      # no half-written file left behind

# app closed or the S: drive dropped half way -> the next open still makes today's backup
def test_backup_after_a_copy_that_was_cut_off(conn, tmp_path):
    today = f"capacity_{pd.Timestamp.now():%Y-%m-%d}.db"
    (tmp_path / (today + '.part')).write_bytes(b'SQLite format 3\x00' + b'\x00' * 100)
    path = db.backup_database(conn, str(tmp_path))
    assert os.path.basename(path) == today
    assert db.check_database(path) is None
    assert not (tmp_path / (today + '.part')).exists()

# a copy that fails its check never becomes today's backup
def test_bad_copy_is_not_kept_as_a_backup(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'check_database', lambda path: 'database disk image is malformed')
    with pytest.raises(db.BackupError, match='malformed'):
        db.backup_database(conn, str(tmp_path))
    assert list(tmp_path.iterdir()) == []

def damaged_database(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE t (x TEXT)")
    c.executemany("INSERT INTO t VALUES (?)", [('x' * 500,)] * 200)
    c.commit()
    c.close()
    data = bytearray(path.read_bytes())
    data[4096 + 8:4096 + 2000] = b'\xff' * 1992        # scribble over page 2
    path.write_bytes(bytes(data))

# a damaged database is never copied: 30 days of opens would replace every good backup with a broken one
def test_damaged_database_is_not_backed_up(tmp_path):
    live, backups = tmp_path / 'capacity.db', tmp_path / 'backups'
    damaged_database(live)
    backups.mkdir()
    for day in range(1, 5):
        (backups / f"capacity_2026-01-0{day}.db").write_text('good')
    c = sqlite3.connect(live)
    with pytest.raises(db.BackupError, match='failed its check'):
        db.backup_database(c, str(backups), keep=3)
    c.close()
    assert len(list(backups.iterdir())) == 4                  # the good ones are all still there

# one scribbled page -> SQLite reports every bad cell; the editor's warning box shows the first few, not 40+ lines
def test_damage_report_stays_short_enough_for_the_warning(tmp_path):
    live = tmp_path / 'capacity.db'
    c = sqlite3.connect(live)
    c.execute("CREATE TABLE t (x TEXT)")
    c.executemany("INSERT INTO t VALUES (?)", [('row %d' % i,) for i in range(2000)])
    c.commit()
    c.close()
    data = bytearray(live.read_bytes())
    page = len(data) // 4096 // 2 * 4096                       # a leaf page in the middle of t
    data[page + 8:page + 3000] = b'\xff' * 2992                 # its cell pointers now point off the page
    live.write_bytes(bytes(data))
    c = sqlite3.connect(live)
    assert len(c.execute("PRAGMA quick_check").fetchone()[0].splitlines()) > 10     # what SQLite itself says
    with pytest.raises(db.BackupError, match='failed its check') as err:
        db.backup_database(c, str(tmp_path / 'backups'))
    c.close()
    problem = str(err.value)
    assert len(problem.splitlines()) == 4                      # three of SQLite's lines + "... and N more"
    assert '... and ' in problem.splitlines()[-1]

# busy, not damaged: a database locked by someone saving is not called damaged (no "restore" advice)
def test_locked_database_is_not_called_damaged(conn, tmp_path):
    live = tmp_path / 'capacity.db'
    disk = sqlite3.connect(live)
    conn.backup(disk)
    disk.close()
    saver = sqlite3.connect(live)
    saver.execute("BEGIN EXCLUSIVE")
    c = sqlite3.connect(live, timeout=0)
    try:
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            db.backup_database(c, str(tmp_path / 'backups'))
    finally:
        c.close()
        saver.rollback()
        saver.close()
    assert not any((tmp_path / 'backups').iterdir())

# today's backup already made -> the database isn't read again (whole file over the S: drive at every open)
def test_later_opens_dont_check_the_database_again(tmp_path):
    live, backups = tmp_path / 'capacity.db', tmp_path / 'backups'
    damaged_database(live)
    backups.mkdir()
    (backups / f"capacity_{pd.Timestamp.now():%Y-%m-%d}.db").write_text('made earlier today')
    c = sqlite3.connect(live)
    assert db.backup_database(c, str(backups)) is None
    c.close()

# restore drill: back up, lose a change, put the backup back
def test_restore_puts_the_backup_back(conn, tmp_path):
    live = tmp_path / 'capacity.db'
    disk = sqlite3.connect(live)
    conn.backup(disk)
    disk.close()
    c = db.connect(str(live))
    backup = db.backup_database(c, str(tmp_path / 'backups'))
    db.change_capacity(c, room_id(c, 'A201'), 99, 'PM change', 'carl', 'Carl', 'oops')
    c.close()

    kept = db.restore_database(backup, str(live), 'carl')
    c = db.connect(str(live))
    assert c.execute("SELECT capacity FROM rooms WHERE space = 'A201'").fetchone()[0] is None
    assert c.execute("SELECT new_value FROM audit_log WHERE field = 'restored'").fetchone()[0] == os.path.basename(backup)
    c.close()
    # the database as it was before the restore is kept, outside the 30 daily slots
    assert os.path.basename(kept).startswith('capacity_before_restore_')
    old = sqlite3.connect(kept)
    assert old.execute("SELECT capacity FROM rooms WHERE space = 'A201'").fetchone()[0] == 99
    old.close()

# database file lost -> the backup is still put back
def test_restore_when_the_database_file_is_gone(conn, tmp_path):
    live, backup = tmp_path / 'capacity.db', tmp_path / 'capacity_2026-01-01.db'
    disk = sqlite3.connect(backup)
    conn.backup(disk)
    disk.close()
    assert db.restore_database(str(backup), str(live), 'carl') is None
    c = db.connect(str(live))
    assert c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == len(BASE_ROWS)
    assert c.execute("SELECT new_value FROM audit_log WHERE field = 'restored'").fetchone()[0] == backup.name
    c.close()

def test_restore_refuses_a_damaged_backup(conn, tmp_path):
    live, bad = tmp_path / 'capacity.db', tmp_path / 'capacity_2026-01-01.db'
    disk = sqlite3.connect(live)
    conn.backup(disk)
    disk.close()
    damaged_database(bad)
    with pytest.raises(db.BackupError, match='failed its check'):
        db.restore_database(str(bad), str(live), 'carl')
    assert db.check_database(str(live)) is None

# editors and viewers (ADR 0003)
def test_first_editor_then_only_editors_change_the_list(conn):
    db.register_user(conn, 'mark')
    db.register_user(conn, 'viewer1')
    assert db.editor_count(conn) == 0 and not db.is_editor(conn, 'mark')
    # empty list -> the first editor can be set by anyone
    assert db.set_editor(conn, 'carl', True, 'carl', 'Carl', why='first editor')
    assert db.is_editor(conn, 'carl')
    # a viewer can't make themselves an editor
    with pytest.raises(PermissionError):
        db.set_editor(conn, 'viewer1', True, 'viewer1', 'viewer1')
    assert db.set_editor(conn, 'mark', True, 'carl', 'Carl')
    assert not db.set_editor(conn, 'mark', True, 'carl', 'Carl')        # already one -> nothing logged
    log = conn.execute("SELECT user_login, record_key, old_value, new_value FROM audit_log "
                       "WHERE table_name = 'users'").fetchall()
    assert [tuple(r) for r in log] == [('carl', 'carl', '0', '1'), ('carl', 'mark', '0', '1')]

def test_last_editor_cant_be_removed(conn):
    db.set_editor(conn, 'carl', True, 'carl', 'Carl')
    with pytest.raises(ValueError):
        db.set_editor(conn, 'carl', False, 'carl', 'Carl')
    db.set_editor(conn, 'karine', True, 'carl', 'Carl')                  # typed login, never opened the app
    assert db.set_editor(conn, 'carl', False, 'karine', 'karine')
    assert db.editor_count(conn) == 1
    assert db.list_users(conn)['user_login'].tolist()[0] == 'karine'

def test_old_database_gets_the_editor_column():
    c = sqlite3.connect(':memory:')
    c.execute("CREATE TABLE users (user_login TEXT PRIMARY KEY, user_name TEXT NOT NULL)")
    c.execute("INSERT INTO users VALUES ('carl', 'Carl')")
    db.create_schema(c)
    assert not db.is_editor(c, 'carl') and db.editor_count(c) == 0

def test_viewer_cant_save_once_there_are_editors(conn):
    # the screens hide the buttons, but every save also checks for itself
    db.set_editor(conn, 'carl', True, 'carl', 'Carl', why='first editor')
    rid = room_id(conn, 'A201')
    pk = db.save_exit(conn, good_exit(), 'carl', 'Carl')
    tries = [lambda: db.change_capacity(conn, rid, 36, 'PM change', 'viewer1', 'Viewer', 'x'),
             lambda: db.set_note(conn, 'rooms', rid, 'x', 'viewer1', 'Viewer'),
             lambda: db.save_exit(conn, good_exit(exit_id='S2 - doorway'), 'viewer1', 'Viewer'),
             lambda: db.delete_exit(conn, pk, 'viewer1', 'Viewer', 'x'),
             lambda: db.change_code_factor(conn, 'width_factors', 'doorway', 'mm_per_person', 6.0,
                                           'BCBC 2024 3.4.3.2.(1)', 'viewer1', 'Viewer'),
             lambda: db.refresh_space_report(conn, report(BASE_ROWS), 'second.xlsx', 'viewer1')]
    for attempt in tries:
        with pytest.raises(db.NotEditorError):
            attempt()
    assert conn.execute("SELECT count(*) FROM audit_log WHERE user_login = 'viewer1'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM exits").fetchone()[0] == 1
    # an editor still saves
    db.change_capacity(conn, rid, 36, 'PM change', 'carl', 'Carl', 'OREM request')

def test_current_login_ignores_username_variable_on_windows(monkeypatch):
    # off Windows (the mac dev copy) it falls back to getpass; on Windows it never reads USERNAME
    monkeypatch.setenv('USERNAME', 'someone_else')
    if db.sys.platform == 'win32':
        assert db.current_login() != 'someone_else'
    else:
        monkeypatch.delenv('LOGNAME', raising=False)
        monkeypatch.delenv('USER', raising=False)
        monkeypatch.delenv('LNAME', raising=False)
        assert db.current_login() == 'someone_else'

def test_change_room_type_logs_and_can_go_back_to_default(conn):
    rid = room_id(conn, 'A201')
    assert db.change_room_type(conn, rid, 'Lab', 'mark', 'Mark', 'used as a lab now')
    assert conn.execute("SELECT room_type_override FROM rooms WHERE room_id = ?", (rid,)).fetchone()[0] == 'lab'
    assert not db.change_room_type(conn, rid, 'lab', 'mark', 'Mark', 'same again')        # no change, no log row
    assert db.change_room_type(conn, rid, '', 'carl', 'Carl', 'back to classroom')        # blank = sub-category default
    log = [tuple(x) for x in conn.execute("SELECT field, old_value, new_value, why FROM audit_log")]
    assert log == [('room_type_override', None, 'lab', 'used as a lab now'),
                   ('room_type_override', 'lab', None, 'back to classroom')]
    with pytest.raises(ValueError):
        db.change_room_type(conn, rid, 'gym', 'carl', 'Carl', 'x')
    with pytest.raises(ValueError):
        db.change_room_type(conn, rid, 'lab', 'carl', 'Carl', ' ')
    with pytest.raises(db.StaleDataError):
        db.change_room_type(conn, rid, 'office', 'carl', 'Carl', 'x', expected='lab')
    db.set_editor(conn, 'carl', True, 'carl', 'Carl', why='first editor')
    with pytest.raises(db.NotEditorError):
        db.change_room_type(conn, rid, 'office', 'viewer1', 'Viewer', 'x')

def test_visited_means_ever_counted_source_means_current_number(conn):
    # visited = counted on a site visit at some point; capacity_source = where today's number came from
    rid = room_id(conn, '101')                                    # counted 20 on the first import
    assert tuple(conn.execute("SELECT capacity_source, visited FROM rooms WHERE room_id = ?", (rid,)).fetchone()) == ('site count', 1)
    db.change_capacity(conn, rid, 36, 'PM change', 'mark', 'Mark', 'OREM request')
    assert tuple(conn.execute("SELECT capacity, capacity_source, visited FROM rooms WHERE room_id = ?", (rid,)).fetchone()) == \
        (36, 'PM change', 1)                                      # still visited: the room was counted
    rid = room_id(conn, 'A201')                                   # never counted
    db.change_capacity(conn, rid, 30, 'PM change', 'mark', 'Mark', 'OREM request')
    assert conn.execute("SELECT visited FROM rooms WHERE room_id = ?", (rid,)).fetchone()[0] == 0

def test_add_room_type_needs_clause_and_is_logged(conn):
    with pytest.raises(ValueError):
        db.add_room_type(conn, 'dining', 1.2, '', 'carl', 'Carl')
    db.add_room_type(conn, 'dining', 1.2, 'BCBC 2024 Table 3.1.17.1.', 'carl', 'Carl', why='cafeteria')
    m2 = conn.execute("SELECT area_per_person_m2 FROM area_factors WHERE room_type = 'dining'").fetchone()[0]
    log = conn.execute("SELECT table_name, record_key, old_value, new_value, clause_ref FROM audit_log").fetchone()
    assert m2 == 1.2 and tuple(log) == ('area_factors', 'dining', None, '1.2', 'BCBC 2024 Table 3.1.17.1.')
    with pytest.raises(ValueError):                  # already there -> change it with change_code_factor instead
        db.add_room_type(conn, 'dining', 2.0, 'BCBC 2024 Table 3.1.17.1.', 'carl', 'Carl')
    with pytest.raises(ValueError):
        db.add_room_type(conn, 'gym', 0, 'BCBC 2024 Table 3.1.17.1.', 'carl', 'Carl')

def test_save_exit_with_stair_width(conn):
    pk = db.save_exit(conn, good_exit(stair_width_cm='110', stair_type='stairs'), 'carl', 'Carl')
    row = conn.execute("SELECT stair_width_cm, stair_type FROM exits WHERE exit_pk = ?", (pk,)).fetchone()
    assert tuple(row) == (110, 'stairs')
    pk2 = db.save_exit(conn, good_exit(exit_id='S2 - doorway', stair_width_cm='121'), 'carl', 'Carl')
    assert conn.execute("SELECT stair_type FROM exits WHERE exit_pk = ?", (pk2,)).fetchone()[0] == 'stairs'
    for bad in [dict(stair_width_cm='40'), dict(stair_width_cm='110', stair_type='doorway'), dict(stair_width_cm='abc')]:
        with pytest.raises(ValueError):
            db.save_exit(conn, good_exit(exit_id='S3 - doorway', **bad), 'carl', 'Carl')

def test_old_database_gets_the_stair_columns():
    c = sqlite3.connect(':memory:')
    c.execute("CREATE TABLE exits (exit_pk INTEGER PRIMARY KEY, property TEXT NOT NULL, floor TEXT NOT NULL, "
              "exit_id TEXT NOT NULL, exit_type TEXT NOT NULL, clear_width_cm INTEGER)")
    db.create_schema(c)
    cols = [r[1] for r in c.execute("PRAGMA table_info(exits)")]
    assert 'stair_width_cm' in cols and 'stair_type' in cols
