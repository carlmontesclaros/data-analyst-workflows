# speed budgets on a campus-size database -> a change that makes the app slow fails here, not on Mark's screen.
# real campus 2026-11: 19,451 rooms, opening the data ~0.2 s and a save ~1 ms on the Mac.
# budgets leave room for slower machines (CI, the workstations, the S: drive) but catch anything 10x slower
import contextlib
import time
import tkinter as tk
from tkinter import ttk
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

# what the check screen does when it opens or refreshes, and the exports: read everything, calculate the whole campus
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
    except tk.TclError as e:
        if 'display' not in str(e):       # only a missing screen is a reason to skip, any other Tk error fails
            raise
        pytest.skip(f"no display: {e}")
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

# the speed of a big table is in how often Python asks Tk for something, which doesn't change from one machine to the
# next -> count those calls on the three editor tables instead of timing them
class TkCalls:
    def __init__(self, tk):
        self.tk, self.calls = tk, []

    def call(self, *args):
        self.calls.append(args)
        return self.tk.call(*args)

    def __getattr__(self, name):
        return getattr(self.tk, name)

@contextlib.contextmanager
def counted(*trees):
    tk_calls = TkCalls(trees[0].tk)
    for tree in trees:
        tree.tk = tk_calls
    try:
        yield tk_calls.calls
    finally:
        for tree in trees:
            tree.tk = tk_calls.tk

# a value read back from a table: Treeview.set(item, column) or Treeview.item(item, 'values')
def cells_read(calls):
    return [c for c in calls if (c[1:2] == ('set',) and (len(c) < 5 or c[4] is None)) or (c[1:2] == ('item',) and c[3:] == ('-values',))]

def cells_written(calls):
    return [c for c in calls if c[1:2] == ('set',) and len(c) == 5 and c[4] is not None]

def texts_measured(calls):
    return [c[-1] for c in calls if c[:2] == ('font', 'measure')]

def shown_texts(trees):
    return {(str(tree), item, key): str(tree.set(item, key)) for tree in trees for item in tree.get_children() for key in tree['columns']}

# the editor screen showing a campus-wide search: 3000 rooms, their zones and exits, in a window just too narrow for
# the rooms table's longest texts, so some are cut (the width is worked out from the columns: fonts differ by system)
@pytest.fixture
def full_editor(conn):
    try:
        root = tk.Tk()
    except tk.TclError as e:
        if 'display' not in str(e):       # only a missing screen is a reason to skip, any other Tk error fails
            raise
        pytest.skip(f"no display: {e}")
    try:
        widgets.use_theme(root)
        screen = app.App(root, conn, 'carl', 'Carl')
        root.minsize(1, 1)
        root.geometry('1900x700')
        screen.search_var.set('building')
        screen.search()
        root.update()
        tree = screen.room_tree
        columns = sum(int(tree.column(key, 'width')) for key in ['#0', *tree['columns']])
        root.geometry(f'{root.winfo_width() - (tree.winfo_width() - columns) - 20}x700')
        root.update()
        assert len(screen.room_tree.get_children()) == 3000
        yield screen
    finally:
        root.destroy()

def editor_trees(screen):
    return (screen.zone_tree, screen.room_tree, screen.exit_tree)

# filling the tables hands the column layout the values it just put in them: nothing is read back cell by cell, and the
# only cells written again are the ones shown cut
def test_filling_the_editor_tables_reads_no_cell_back(full_editor):
    trees = editor_trees(full_editor)
    with counted(*trees) as calls:
        full_editor.show()
    assert cells_read(calls) == []
    full = {(str(tree), item, key): text for tree in trees for item, texts in tree.long_columns.full.items()
            for key, text in texts.items()}
    cut = [cell for cell, shown in shown_texts(trees).items() if cell in full and shown != full[cell]]
    assert cut and len(cells_written(calls)) == len(cut)

# the widths worked out from the handed values are the ones the cells themselves give
def test_columns_fitted_from_handed_values_match_the_cells(full_editor):
    for tree in editor_trees(full_editor):
        short = tree.long_columns.short
        fitted = {key: int(tree.column(key, 'width')) for key, _ in short}
        for key, _ in short:
            tree.column(key, width=1)
        widgets.fit_columns(tree, short)
        assert {key: int(tree.column(key, 'width')) for key, _ in short} == fitted

# one step of dragging the window's edge: only the cells whose cut text changes are touched, and no whole text is
# measured again
def test_a_resize_step_touches_only_the_cells_that_change(full_editor):
    root, tree = full_editor.root, full_editor.room_tree
    before = shown_texts([tree])
    whole = {text for texts in tree.long_columns.full.values() for text in texts.values() if text}
    width, height = tree.winfo_width(), root.winfo_height()
    with counted(tree) as calls:
        root.geometry(f'{root.winfo_width() - 30}x{height}')
        root.update()
    assert tree.winfo_width() < width
    after = shown_texts([tree])
    changed = {cell for cell in after if after[cell] != before[cell]}
    assert changed
    assert cells_read(calls) == []
    assert len(cells_written(calls)) == len(changed)
    assert whole.isdisjoint(texts_measured(calls))

# a campus-wide search fills the rooms table with 3000 rows that share a few long building names and notes: dragging the
# window's edge lays the cut columns out again at every step, so each step must be quick
def test_a_full_rooms_table_follows_the_window_width_quickly():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        if 'display' not in str(e):       # only a missing screen is a reason to skip, any other Tk error fails
            raise
        pytest.skip(f"no display: {e}")
    try:
        widgets.use_theme(root)
        columns = [('property', 60), ('floor', 40), ('space', 50), ('note', 60)]
        tree = ttk.Treeview(root, columns=[key for key, _ in columns], show='headings')
        for key, width in columns:
            tree.heading(key, text=widgets.heading_text(key))
            tree.column(key, width=width, stretch=False)
        tree.pack(fill='both', expand=True)
        long_columns = widgets.LongTextColumns(tree, columns, ('property', 'note'))
        note = 'tables and chairs moved to the back for the exam week, move them again before the first lecture on Monday morning'
        for i in range(3000):
            tree.insert('', 'end', values=[f'Engineering / Computer Science Building {i // 100}', i % 5, f'A{i}', note])
        root.geometry('1300x600')
        root.update()
        filled = seconds(long_columns.refit)
        widths = iter(range(1290, 900, -10))

        def narrower():
            root.geometry(f'{next(widths)}x600')
            root.update()
        resized = seconds(narrower, runs=5)
        cut = tree.set(tree.get_children()[-1], 'note')
    finally:
        root.destroy()
    assert cut.endswith(widgets.ELLIPSIS) and note.startswith(cut[:-1])
    assert filled < 0.3, f"laying out 3000 rows took {filled:.2f} s"
    assert resized < 0.15, f"one step of the window's width took {resized:.2f} s"
