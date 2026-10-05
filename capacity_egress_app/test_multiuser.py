import threading
import time
import multiprocessing as mp
import pytest
import capacity_db as db
from test_capacity_db import report, BASE_ROWS, CONFIG_DIR, good_exit

# two people = two connections to the same file, like two computers on the S: drive

@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / 'capacity.db')
    c = db.connect(path)
    db.create_schema(c)
    db.import_code_factors(c, CONFIG_DIR)
    db.insert_extra_settings(c)
    db.insert_rooms(c, db.classify_rooms(report(BASE_ROWS)), 'first.xlsx')
    c.commit()
    c.close()
    return path

def room_id(c, space):
    return c.execute("SELECT room_id FROM rooms WHERE space = ?", (space,)).fetchone()[0]

def test_stale_capacity_is_refused_not_overwritten(db_path):
    carl, mark = db.connect(db_path), db.connect(db_path)
    rid = room_id(carl, 'A201')
    seen_by_carl = (None, 'per code')                      # what Carl's screen shows
    db.change_capacity(mark, rid, 36, 'PM change', 'mark', 'Mark', 'OREM request')
    with pytest.raises(db.StaleDataError, match='changed to 36 .PM change. by Mark'):
        db.change_capacity(carl, rid, 30, 'site count', 'carl', 'Carl', 'counted', expected=seen_by_carl)
    assert carl.execute("SELECT capacity FROM rooms WHERE room_id = ?", (rid,)).fetchone()[0] == 36
    # after refreshing, Carl's save goes through
    db.change_capacity(carl, rid, 30, 'site count', 'carl', 'Carl', 'counted', expected=(36, 'PM change'))
    assert mark.execute("SELECT capacity FROM rooms WHERE room_id = ?", (rid,)).fetchone()[0] == 30

def test_data_version_tells_the_other_app_to_refresh(db_path):
    carl, mark = db.connect(db_path), db.connect(db_path)
    before = db.data_version(carl)
    db.change_capacity(mark, room_id(mark, 'A201'), 36, 'PM change', 'mark', 'Mark', 'OREM request')
    assert db.data_version(carl) != before
    own = db.data_version(mark)
    db.change_capacity(mark, room_id(mark, 'A202'), 10, 'PM change', 'mark', 'Mark', 'x')
    assert db.data_version(mark) == own                    # own saves don't count

def test_stale_exit_edit_and_delete(db_path):
    carl, mark = db.connect(db_path), db.connect(db_path)
    pk = db.save_exit(carl, good_exit(), 'carl', 'Carl')
    seen = dict(carl.execute("SELECT * FROM exits WHERE exit_pk = ?", (pk,)).fetchone())
    db.save_exit(mark, good_exit(clear_width_cm='90'), 'mark', 'Mark', exit_pk=pk, expected=seen)
    with pytest.raises(db.StaleDataError):
        db.save_exit(carl, good_exit(clear_width_cm='95'), 'carl', 'Carl', exit_pk=pk, expected=seen)
    with pytest.raises(db.StaleDataError):
        db.delete_exit(carl, pk, 'carl', 'Carl', 'wrong door', expected=seen)
    seen = dict(mark.execute("SELECT * FROM exits WHERE exit_pk = ?", (pk,)).fetchone())
    db.delete_exit(mark, pk, 'mark', 'Mark', 'wrong door', expected=seen)
    with pytest.raises(db.StaleDataError, match='deleted'):
        db.save_exit(carl, good_exit(clear_width_cm='95'), 'carl', 'Carl', exit_pk=pk, expected=seen)

def test_stale_exit_check_ignores_how_pandas_loaded_it(db_path):
    # the app loads exits through pandas (88 -> 88.0, None -> NaN); that alone must not look like a change
    carl = db.connect(db_path)
    pk = db.save_exit(carl, good_exit(), 'carl', 'Carl')
    seen = db.load_exits(carl).set_index('exit_pk').loc[pk].to_dict()
    db.save_exit(carl, good_exit(clear_width_cm='90'), 'carl', 'Carl', exit_pk=pk, expected=seen)

def test_stale_code_factor_and_note(db_path):
    carl, mark = db.connect(db_path), db.connect(db_path)
    db.change_code_factor(mark, 'width_factors', 'doorway', 'mm_per_person', 6.0, 'BCBC 2024 3.4.3.2.(1)', 'mark', 'Mark')
    with pytest.raises(db.StaleDataError):
        db.change_code_factor(carl, 'width_factors', 'doorway', 'mm_per_person', 7.0, 'BCBC 2024 3.4.3.2.(1)',
                              'carl', 'Carl', expected=6.1)
    rid = room_id(carl, 'A201')
    db.set_note(mark, 'rooms', rid, 'tables moved', 'mark', 'Mark')
    with pytest.raises(db.StaleDataError):
        db.set_note(carl, 'rooms', rid, 'chairs added', 'carl', 'Carl', expected=None)

def test_save_waits_for_someone_elses_save(db_path):
    carl = db.connect(db_path)
    rid = room_id(carl, 'A201')

    def slow_save():
        mark = db.connect(db_path)                         # a connection belongs to the thread that made it
        with db.write_transaction(mark):
            mark.execute("UPDATE rooms SET note = 'mark was here' WHERE room_id = ?", (rid,))
            time.sleep(1.0)                                # Mark's save holds the lock for a second

    t = threading.Thread(target=slow_save)
    t.start()
    time.sleep(0.2)
    start = time.time()
    db.change_capacity(carl, rid, 30, 'site count', 'carl', 'Carl', 'counted')   # waits, then saves
    t.join()
    assert time.time() - start >= 0.5
    assert carl.execute("SELECT capacity, note FROM rooms WHERE room_id = ?", (rid,)).fetchone()[:] == (30, 'mark was here')

def hammer(path, user, n):
    c = db.connect(path)
    rid = c.execute("SELECT room_id FROM rooms WHERE space = 'A201'").fetchone()[0]
    for i in range(n):
        db.change_capacity(c, rid, i, 'PM change', user, user, f'{user} {i}')
    c.close()

def test_two_apps_saving_at_the_same_time(db_path):
    procs = [mp.get_context('spawn').Process(target=hammer, args=(db_path, u, 25)) for u in ('carl', 'mark')]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    assert [p.exitcode for p in procs] == [0, 0]            # nobody got "database is locked"
    c = db.connect(db_path)
    counts = dict(c.execute("SELECT user_login, count(*) FROM audit_log WHERE field = 'capacity' "
                            "GROUP BY user_login").fetchall())
    assert counts['carl'] >= 24 and counts['mark'] >= 24    # every save logged (a repeat value logs nothing)
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == 'ok'
