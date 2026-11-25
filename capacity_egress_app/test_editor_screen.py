# end-to-end: the editor screen driven the way a person uses it -> pick the room, type in the boxes,
# press Save, then check the database, the change log and what the screen shows.
# every save path that changes a floor's result is here: capacity, room note, exits, code factors
import tkinter as tk
from tkinter import ttk
import pytest
import app
import capacity_db as db
import egress
import excel_inputs as xi
import widgets
from test_capacity_db import report, CONFIG_DIR
from test_egress import assert_same_frame, assert_same_result, building_rows, renumbered

EOW = 'Engineering Office Wing'
ROOMS = [(EOW, '1', '101', 50.0, 20),      # counted 20 on a site visit
         (EOW, '1', '102', 30.0, 0)]       # counted 0

def doorway(exit_id, cm):
    return {'property': EOW, 'floor': '1', 'exit_id': exit_id, 'exit_type': 'doorway',
            'clear_width_cm': str(cm), 'measured_date': '2026-10-05'}

# a real database file, like the one on the S: drive: 2 rooms, 2 doors of 88 cm (144 people each -> 288)
@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / 'capacity.db')
    c = db.connect(path)
    db.create_schema(c)
    db.import_code_factors(c, CONFIG_DIR)
    db.insert_extra_settings(c)
    db.insert_rooms(c, xi.classify_rooms(report(ROOMS)), 'first.xlsx')
    db.save_exit(c, doorway('S1 - doorway', 88), 'carl', 'Carl')
    db.save_exit(c, doorway('S2 - doorway', 88), 'carl', 'Carl')
    db.set_editor(c, 'carl', True, 'carl', 'Carl', why='first editor')
    db.register_user(c, 'viewer')
    c.close()
    return path

@pytest.fixture
def conn(db_path):
    c = db.connect(db_path)
    yield c
    c.close()

@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        if 'display' not in str(e):       # only a missing screen is a reason to skip, any other Tk error fails
            raise
        pytest.skip(f"no display: {e}")
    r.withdraw()
    widgets.use_theme(r)
    yield r
    # a box a test left open (a refused Save keeps it up) holds the grab -> close it, innermost first
    for w in reversed(list(all_widgets(r))):
        if isinstance(w, tk.Toplevel):
            w.destroy()
    r.destroy()

# message boxes would stop the test until someone clicks OK -> write down what they said instead
@pytest.fixture
def said(monkeypatch):
    messages = []
    for kind in ('showinfo', 'showwarning', 'showerror'):
        monkeypatch.setattr(app.messagebox, kind,
                            lambda title, text, kind=kind, **kw: messages.append((kind, title, text)))
    return messages

def editor_screen(root, conn, user='carl'):
    screen = app.App(tk.Toplevel(root), conn, user, user.title())
    screen.root.update()
    return screen

def all_widgets(w):
    for child in w.winfo_children():
        yield child
        yield from all_widgets(child)

def dialog(screen, title):
    screen.root.update()
    wins = [w for w in screen.root.winfo_children()
            if isinstance(w, tk.Toplevel) and w.winfo_exists() and w.title().startswith(title)]
    return wins[-1] if wins else None

def press(win, text):
    [b for b in all_widgets(win) if isinstance(b, ttk.Button) and b.cget('text') == text][0].invoke()

def type_into(entry, text):
    entry.delete(0, 'end')
    entry.insert(0, text)

def entries(win):
    return [w for w in all_widgets(win) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]

def label_text(win):
    return ' '.join(str(w.cget('text')) for w in all_widgets(win) if isinstance(w, ttk.Label))

# a form that waits for the person (Add exit, notes) -> fill it in once it shows up, like a person would
def when_open(screen, title, *actions):
    actions, problems = list(actions), []
    def look(tries=0):
        win = dialog(screen, title)
        if not actions:                          # all done -> a form still open or back again would wait forever
            if win is not None:
                problems.append(f"{title} still open after the last action")
                win.destroy()
            elif tries < 25:
                screen.root.after(20, look, tries + 1)
            return
        if win is None:
            if tries > 100:
                problems.append(f"{title} never opened")
            else:
                screen.root.after(20, look, tries + 1)
            return
        try:
            actions.pop(0)(win)
        except Exception as err:                 # don't leave the test stuck on an open form
            problems.append(err)
            win.destroy()
            return
        screen.root.after(20, look)
    screen.root.after(20, look)
    return problems

# the form's boxes by their label -> {'Exit type': combobox, ...}
def form_fields(win):
    rows = {}
    for w in all_widgets(win):
        if w.winfo_manager() == 'grid':
            info = w.grid_info()
            rows.setdefault(int(info['row']), {})[int(info['column'])] = w
    return {r[0].cget('text'): r[1] for r in rows.values() if 0 in r and 1 in r and isinstance(r[0], ttk.Label)}

def fill_exit(win, values):
    fields = form_fields(win)
    for label, value in values.items():
        box = next(w for text, w in fields.items() if text.startswith(label))
        if isinstance(box, ttk.Combobox):
            box.set(value)
        else:
            type_into(box, value)

NEW_EXIT = {'Exit id': 'E1 - outside exit', 'Exit type': 'doorway', 'Clear width': '100'}

def room(conn, space):
    return dict(conn.execute("SELECT * FROM rooms WHERE space = ?", (space,)).fetchone())

def zone_row(screen):
    rows = [screen.zone_tree.item(i, 'values') for i in screen.zone_tree.get_children()]
    assert len(rows) == 1
    return dict(zip(['floor', 'wing', 'status', 'load', 'capacity'], rows[0][:5], strict=True))

def open_floor(screen, conn, space='101'):
    screen.focus_room(room(conn, space))
    screen.root.update()

# change capacity: type, see the preview, save -> saved, logged, and the floor's numbers move on screen
def test_change_capacity(root, conn, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    assert (zone_row(screen)['load'], zone_row(screen)['capacity']) == ('20', '288')

    screen.change_capacity()
    win = dialog(screen, 'Change capacity')
    capacity, why = entries(win)
    type_into(capacity, '40')
    type_into(why, 'OREM request')
    assert 'occupant load 20 -> 40 vs exit capacity 288' in label_text(win)
    press(win, 'Save')

    assert not win.winfo_exists() and said == []
    r = room(conn, '101')
    assert (r['capacity'], r['capacity_source']) == (40, 'PM change')
    logged = db.history(conn, 'rooms', r['room_id'])[['field', 'old_value', 'new_value', 'why']].values.tolist()
    assert ['capacity', '20', '40', 'OREM request'] in logged
    assert ['capacity_source', 'site count', 'PM change', 'OREM request'] in logged
    assert zone_row(screen)['load'] == '40'
    assert screen.room_tree.item(f"r{r['room_id']}", 'values')[7] == '40'
    assert 'capacity 20 -> 40' in screen.status_var.get()

# no reason -> told why, nothing saved, the box stays open with what was typed
def test_change_capacity_needs_a_reason(root, conn, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    screen.change_capacity()
    win = dialog(screen, 'Change capacity')
    type_into(entries(win)[0], '40')
    press(win, 'Save')
    assert said == [('showerror', 'Not saved', 'say why the capacity changed')]
    assert win.winfo_exists() and entries(win)[0].get() == '40'
    assert room(conn, '101')['capacity'] == 20

# someone else saved while the box was open -> refused, not overwritten, the screen shows their number
def test_change_capacity_after_someone_else_saved(root, conn, db_path, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    screen.change_capacity()
    win = dialog(screen, 'Change capacity')

    mark = db.connect(db_path)
    db.change_capacity(mark, room(mark, '101')['room_id'], 50, 'site count', 'carl', 'Mark', 'recounted')
    mark.close()

    capacity, why = entries(win)
    type_into(capacity, '40')
    type_into(why, 'OREM request')
    press(win, 'Save')
    assert [s[1] for s in said] == ['Changed by someone else']
    assert room(conn, '101')['capacity'] == 50
    assert zone_row(screen)['load'] == '50'

# a viewer who gets to the editor screen still can't save: every save checks for itself
def test_viewer_cant_save(root, conn, said):
    screen = editor_screen(root, conn, user='viewer')
    open_floor(screen, conn)
    screen.change_capacity()
    win = dialog(screen, 'Change capacity')
    capacity, why = entries(win)
    type_into(capacity, '40')
    type_into(why, 'trying')
    press(win, 'Save')
    assert said[0][0] == 'showerror' and 'not an editor' in said[0][2]
    assert room(conn, '101')['capacity'] == 20

def test_room_note(root, conn, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    def write(win):
        next(w for w in all_widgets(win) if isinstance(w, tk.Text)).insert('1.0', 'tables moved to the back')
        press(win, 'Save')
    problems = when_open(screen, 'Note', write)
    screen.room_note()
    assert problems == [] and said == []
    assert room(conn, '101')['note'] == 'tables moved to the back'

# add an exit through the form -> 100 cm door = 163 people, exit capacity 288 -> 451 on screen, logged
def test_add_exit(root, conn, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    problems = when_open(screen, 'Add exit', lambda win: (fill_exit(win, NEW_EXIT), press(win, 'Save')))
    screen.add_exit()
    assert problems == [] and said == []
    assert 'E1 - outside exit' in [screen.exit_tree.item(i, 'values')[2] for i in screen.exit_tree.get_children()]
    assert zone_row(screen)['capacity'] == '451'
    assert conn.execute("SELECT why FROM audit_log WHERE table_name = 'exits' ORDER BY log_id DESC").fetchone()[0] == 'exit added'

# a width the code can't use -> told what's wrong, the form comes back with what was typed, cancel saves nothing
def test_add_exit_with_a_bad_width(root, conn, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    typed_again = {}
    def bad(win):
        fill_exit(win, NEW_EXIT | {'Clear width': '20'})
        press(win, 'Save')
    def look_then_cancel(win):
        typed_again.update({label: box.get() for label, box in form_fields(win).items()})
        press(win, 'Cancel')
    problems = when_open(screen, 'Add exit', bad, look_then_cancel)
    screen.add_exit()
    assert problems == []
    assert said[0][0] == 'showerror' and 'between 50 and 500' in said[0][2]
    assert next(v for label, v in typed_again.items() if label.startswith('Clear width')) == '20'
    assert conn.execute("SELECT COUNT(*) FROM exits").fetchone()[0] == 2

# a wing group typed in the form -> saved one way (A+C+D) and shown so; a wing already in another group is refused
def test_add_exit_with_a_wing_group(root, conn, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    problems = when_open(screen, 'Add exit', lambda win: (fill_exit(win, NEW_EXIT | {'Wing': 'd + a+c'}), press(win, 'Save')))
    screen.add_exit()
    assert problems == [] and said == []
    rows = {screen.exit_tree.item(i, 'values')[2]: screen.exit_tree.item(i, 'values')[1] for i in screen.exit_tree.get_children()}
    assert rows['E1 - outside exit'] == 'A+C+D'

    clash = NEW_EXIT | {'Exit id': 'E1A - outside exit', 'Wing': 'C'}
    problems = when_open(screen, 'Add exit', lambda win: (fill_exit(win, clash), press(win, 'Save')),
                         lambda win: press(win, 'Cancel'))
    screen.add_exit()
    assert problems == []
    assert said[0][0] == 'showerror' and 'wing C is already in A+C+D (E1 - outside exit)' in said[0][2]
    assert conn.execute("SELECT COUNT(*) FROM exits").fetchone()[0] == 3

# delete one of two doors -> one exit left, the 50% rule gives 0 and the floor goes to review
def test_delete_exit(root, conn, said, monkeypatch):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    s2 = conn.execute("SELECT exit_pk FROM exits WHERE exit_id = 'S2 - doorway'").fetchone()[0]
    screen.exit_tree.selection_set(f"e{s2}")
    monkeypatch.setattr(app.simpledialog, 'askstring', lambda *a, **kw: 'measured the wrong door')
    screen.delete_exit()
    assert said == []
    assert conn.execute("SELECT COUNT(*) FROM exits").fetchone()[0] == 1
    assert zone_row(screen)['capacity'] == '0'
    assert 'REVIEW' in zone_row(screen)['status']

# code factors: pick the row and field, preview how many zones change, save only with a clause
def test_change_code_factor(root, conn, said):
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    screen.edit_code_factors()
    win = dialog(screen, 'Code factors')
    notebook = next(w for w in all_widgets(win) if isinstance(w, ttk.Notebook))
    notebook.select(list(db.CODE_FACTOR_KEYS).index('width_factors'))
    win.update()
    tree = next(w for w in all_widgets(notebook.nametowidget(notebook.select())) if isinstance(w, ttk.Treeview))
    tree.selection_set('doorway')
    win.update()
    field = next(w for w in all_widgets(win) if isinstance(w, ttk.Combobox))
    field.set('mm_per_person')
    field.event_generate('<<ComboboxSelected>>')
    win.update()
    value, clause, why = entries(win)
    assert value.get() == '6.1'
    type_into(value, '8.0')                     # 880 mm / 8.0 = 110 people a door -> 220

    press(win, 'Preview')
    assert 'exit capacity changes: 1' in label_text(win) and '288 -> 220' in label_text(win)

    press(win, 'Save')                          # no clause -> refused, box stays open
    assert 'clause reference is required' in said[0][2] and win.winfo_exists()

    type_into(clause, 'BCBC 2024 3.4.3.2.(1)')
    type_into(why, 'testing')
    press(win, 'Save')
    assert not win.winfo_exists()
    assert conn.execute("SELECT mm_per_person FROM width_factors WHERE exit_type = 'doorway'").fetchone()[0] == 8.0
    assert db.history(conn, 'width_factors', 'doorway').iloc[0]['clause_ref'] == 'BCBC 2024 3.4.3.2.(1)'
    assert zone_row(screen)['capacity'] == '220'


# --- a save redoes its own floor, not the campus -------------------------------------------------------------------
# a save on one floor -> only that floor is read and calculated again; every other floor stays as it was. the screen must
# still show exactly what a whole reload would (same rooms, exits, zones), whichever way the floor was saved

OTHER = 'Clearihue Building'

# 3 floors in 2 buildings: the one the tests save on (2 rooms, 2 doors), a floor where no room has a count yet
# and no door was measured, and another building's floor with one door
@pytest.fixture
def campus_path(tmp_path):
    path = str(tmp_path / 'campus.db')
    c = db.connect(path)
    db.create_schema(c)
    db.import_code_factors(c, CONFIG_DIR)
    db.insert_extra_settings(c)
    db.insert_rooms(c, xi.classify_rooms(report(ROOMS + [(EOW, '2', '201', 40.0, None), (EOW, '2', '202', 45.0, None),
                                                         (OTHER, '1', 'A101', 60.0, 35), (OTHER, '1', 'A102', 25.0, None)])), 'first.xlsx')
    db.save_exit(c, doorway('S1 - doorway', 88), 'carl', 'Carl')
    db.save_exit(c, doorway('S2 - doorway', 88), 'carl', 'Carl')
    db.save_exit(c, doorway('S1 - doorway', 90) | {'property': OTHER}, 'carl', 'Carl')
    db.set_editor(c, 'carl', True, 'carl', 'Carl', why='first editor')
    c.close()
    return path

@pytest.fixture
def calculated(monkeypatch):
    # how many rooms each calculation was given
    sizes = []
    real = egress.calculate
    def spy(rooms, exits, factors):
        sizes.append(len(rooms))
        return real(rooms, exits, factors)
    monkeypatch.setattr(egress, 'calculate', spy)
    return sizes

def assert_shows_what_the_database_holds(screen, conn):
    rooms, exits = db.load_rooms(conn), db.load_exits(conn)
    assert_same_frame(screen.rooms, rooms, 'rooms')
    assert_same_frame(screen.exits, exits, 'exits')
    want = egress.calculate(rooms, exits, db.load_code_factors(conn))
    # the building on screen -> its rows of a whole-campus calculation; a search across buildings -> the whole campus
    prop = screen.building.picked()
    if prop:
        assert_same_result(renumbered(screen.campus.building(prop)), renumbered(building_rows(want, prop)))
    else:
        assert_same_result(screen.campus.whole(), want)
    assert_same_result(screen.export_result(), want)
    assert screen.seen_version == db.data_version(conn)

def test_change_capacity_redoes_only_its_floor(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        open_floor(screen, conn)
        screen.change_capacity()
        win = dialog(screen, 'Change capacity')
        capacity, why = entries(win)
        type_into(capacity, '40')
        type_into(why, 'OREM request')
        calculated.clear()
        press(win, 'Save')
        assert said == [] and zone_row(screen)['load'] == '40'
        assert max(calculated) < 6, calculated
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

def test_change_capacity_on_a_floor_nobody_has_counted(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        screen.focus_room(room(conn, '201'))
        screen.root.update()
        screen.change_capacity()
        win = dialog(screen, 'Change capacity')
        capacity, why = entries(win)
        type_into(capacity, '12')
        type_into(why, 'first count')
        calculated.clear()
        press(win, 'Save')
        assert said == [] and max(calculated) < 6, calculated
        assert screen.room_tree.item(f"r{room(conn, '201')['room_id']}", 'values')[7] == '12'
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

def test_change_room_type_redoes_only_its_floor(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        open_floor(screen, conn)
        screen.change_room_type()
        win = dialog(screen, 'Change room type')
        combo = next(w for w in all_widgets(win) if isinstance(w, ttk.Combobox))
        combo.set('office')
        combo.event_generate('<<ComboboxSelected>>')
        type_into(entries(win)[0], 'it is an office')
        calculated.clear()
        press(win, 'Save')
        assert said == [] and max(calculated) < 6, calculated
        assert room(conn, '101')['room_type_override'] == 'office'
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

def test_room_note_redoes_only_its_floor(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        open_floor(screen, conn)
        def write(win):
            next(w for w in all_widgets(win) if isinstance(w, tk.Text)).insert('1.0', 'tables moved to the back')
            calculated.clear()
            press(win, 'Save')
        problems = when_open(screen, 'Note', write)
        screen.room_note()
        assert problems == [] and said == [] and max(calculated) < 6, calculated
        # the note column shares the width with the others and cuts a long text with an ellipsis: the full text is what it holds
        assert screen.room_tree.long_columns.full[f"r{room(conn, '101')['room_id']}"]['note'] == 'tables moved to the back'
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

def test_exit_saves_redo_only_their_floor(root, campus_path, said, calculated, monkeypatch):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        open_floor(screen, conn)
        def forget_then_save(win, values):
            fill_exit(win, values)
            calculated.clear()
            press(win, 'Save')

        problems = when_open(screen, 'Add exit', lambda win: forget_then_save(win, NEW_EXIT))
        screen.add_exit()
        assert problems == [] and said == [] and max(calculated) < 6, calculated
        assert zone_row(screen)['capacity'] == '451'
        assert_shows_what_the_database_holds(screen, conn)

        s2 = conn.execute("SELECT exit_pk FROM exits WHERE exit_id = 'S2 - doorway' AND property = ?", (EOW,)).fetchone()[0]
        screen.exit_tree.selection_set(f"e{s2}")
        problems = when_open(screen, 'Edit exit', lambda win: forget_then_save(win, {'Clear width': '95'}))
        screen.edit_exit()
        assert problems == [] and said == [] and max(calculated) < 6, calculated
        assert_shows_what_the_database_holds(screen, conn)

        screen.exit_tree.selection_set(f"e{s2}")
        def write_note(win):
            next(w for w in all_widgets(win) if isinstance(w, tk.Text)).insert('1.0', 'door sticks')
            calculated.clear()
            press(win, 'Save')
        problems = when_open(screen, 'Note', write_note)
        screen.exit_note()
        assert problems == [] and said == [] and max(calculated) < 6, calculated
        assert_shows_what_the_database_holds(screen, conn)

        monkeypatch.setattr(app.simpledialog, 'askstring', lambda *a, **kw: 'measured the wrong door')
        screen.exit_tree.selection_set(f"e{s2}")
        calculated.clear()
        screen.delete_exit()
        assert said == [] and max(calculated) < 6, calculated
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

# every door saved so far has a stair behind it -> a plain doorway added with the stair width left blank still shows
def test_add_a_doorway_with_no_stair_when_every_other_door_has_one(root, campus_path, said):
    c = db.connect(campus_path)
    c.execute("UPDATE exits SET stair_width_cm = 110, stair_type = 'stairs'")
    c.commit()
    c.close()
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        open_floor(screen, conn)
        problems = when_open(screen, 'Add exit', lambda win: (fill_exit(win, NEW_EXIT), press(win, 'Save')))
        screen.add_exit()
        assert problems == [] and said == []
        pk = conn.execute("SELECT exit_pk FROM exits WHERE exit_id = ?", (NEW_EXIT['Exit id'],)).fetchone()[0]
        assert screen.exit_tree.exists(f"e{pk}")
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

# the last door on a floor deleted -> the floor has no exits, like the floor nobody measured
def test_deleting_the_last_exit_on_a_floor(root, campus_path, said, calculated, monkeypatch):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        screen.focus_room(room(conn, 'A101'))
        screen.root.update()
        pk = conn.execute("SELECT exit_pk FROM exits WHERE property = ?", (OTHER,)).fetchone()[0]
        screen.exit_tree.selection_set(f"e{pk}")
        monkeypatch.setattr(app.simpledialog, 'askstring', lambda *a, **kw: 'not a door')
        calculated.clear()
        screen.delete_exit()
        assert said == [] and max(calculated) < 6, calculated
        assert screen.exit_tree.get_children() == ()
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

# someone else saved on another floor while this screen was open -> this save shows their change too, not only its own
def test_a_save_also_shows_what_someone_else_saved_on_another_floor(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        open_floor(screen, conn)
        screen.change_capacity()
        win = dialog(screen, 'Change capacity')
        mark = db.connect(campus_path)
        db.change_capacity(mark, room(mark, 'A101')['room_id'], 50, 'site count', 'carl', 'Mark', 'recounted')
        mark.close()
        capacity, why = entries(win)
        type_into(capacity, '40')
        type_into(why, 'OREM request')
        press(win, 'Save')
        assert said == []
        assert_shows_what_the_database_holds(screen, conn)
        assert screen.campus.building(OTHER)['rooms'].set_index('room_id').loc[room(conn, 'A101')['room_id'], 'capacity'] == 50
    finally:
        conn.close()

# the exports read the result. after a one-floor save it must be the whole-campus result row for row, warnings in
# the order a restart would give them, so the files don't depend on what was saved before
def test_exports_after_a_floor_save_are_the_whole_campus_result(root, campus_path, said):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        open_floor(screen, conn)
        screen.change_capacity()
        win = dialog(screen, 'Change capacity')
        capacity, why = entries(win)
        type_into(capacity, '40')
        type_into(why, 'OREM request')
        press(win, 'Save')
        want = egress.calculate(db.load_rooms(conn), db.load_exits(conn), db.load_code_factors(conn))
        got = screen.export_result()
        for table in ('rooms', 'exits', 'zones', 'warnings'):
            assert_same_frame(got[table], want[table], table)
    finally:
        conn.close()

# --- the editor screen calculates a building when it shows it, not the campus when it opens ---------------------------
# it opens on no building, so calculating the whole campus (19,451 rooms) only to show empty lists was most of the wait
# on a busy machine. whatever it shows must still be exactly what one whole-campus calculation gives

def test_opening_the_editor_screen_calculates_no_rooms(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        assert calculated == []
        assert screen.zone_tree.get_children() == () and screen.room_tree.get_children() == ()
        assert screen.status_var.get().startswith('0 rooms, 0 zones, 0 exits')
        assert screen.building.names == [OTHER, EOW]
        open_floor(screen, conn, 'A101')         # Clearihue: 2 rooms
        open_floor(screen, conn, '201')          # Engineering Office Wing: 4 rooms
        open_floor(screen, conn, '101')          # the same building again -> already calculated
        assert calculated == [2, 4]
        assert said == []
    finally:
        conn.close()

# the screen as it was: every building shown from one whole-campus calculation
class WholeCampus(egress.Campus):
    def building(self, prop):
        return building_rows(self.whole(), prop)

def lists(screen):
    zones = [(t.item(i, 'values'), t.item(i, 'tags')) for t in [screen.zone_tree] for i in t.get_children()]
    rooms, exits = ([(i, t.item(i, 'values'), t.item(i, 'tags')) for i in t.get_children()]
                    for t in (screen.room_tree, screen.exit_tree))
    return zones, rooms, exits, screen.status_var.get()

def shown_both_ways(screen):
    screen.show()
    got, calculated = lists(screen), screen.campus
    screen.campus = WholeCampus(calculated.rooms, calculated.exits, calculated.factors)
    screen.show()
    want = lists(screen)
    screen.campus = calculated
    return got, want

def test_every_building_and_search_shows_what_a_whole_campus_calculation_gives(root, campus_path, said):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        for space in ('101', '201', 'A101'):
            open_floor(screen, conn, space)                      # its floor
            got, want = shown_both_ways(screen)
            assert got == want and got[1], space
            screen.floor_var.set(app.ALL)                        # the whole building
            got, want = shown_both_ways(screen)
            assert got == want and got[1], space
        for term in ('0', '20'):                                 # rooms in both buildings, rooms in one
            screen.building_var.set('')
            screen.search_var.set(term)
            screen.search()
            got, want = shown_both_ways(screen)
            assert got == want and got[1], term
        assert {r[1][0] for r in lists(screen)[1]} == {EOW}
        assert said == []
    finally:
        conn.close()

# a search across buildings calculates the whole campus; a save after it -> the search shows the saved number, and
# only the saved floor is calculated again, not the whole campus
def test_a_search_across_buildings_after_a_save_shows_the_saved_number(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        screen.search_var.set('0')
        screen.search()
        rid = room(conn, '101')['room_id']
        assert screen.room_tree.item(f"r{rid}", 'values')[7] == '20'
        assert {r[1][0] for r in lists(screen)[1]} == {EOW, OTHER}
        open_floor(screen, conn)
        screen.change_capacity()
        win = dialog(screen, 'Change capacity')
        capacity, why = entries(win)
        type_into(capacity, '40')
        type_into(why, 'OREM request')
        calculated.clear()
        press(win, 'Save')
        screen.building_var.set('')
        screen.search_var.set('0')
        screen.search()
        assert said == [] and screen.room_tree.item(f"r{rid}", 'values')[7] == '40'
        assert {r[1][0] for r in lists(screen)[1]} == {EOW, OTHER}
        assert max(calculated) < 6, calculated
        got, want = shown_both_ways(screen)
        assert got == want
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

# refresh space report -> a file carrying the app's own counts: the app asks before FMIS capacities are kept or replaced
def refresh_with(root, conn, said, monkeypatch, rows, keep_answer):
    questions = []
    def askyesno(title, text, **kw):
        questions.append(text)
        return keep_answer if text.startswith('The counts') else True
    monkeypatch.setattr(app.filedialog, 'askopenfilename', lambda **kw: '/x/carl_space_report.xlsx')
    monkeypatch.setattr(app.xi, 'read_space_report', lambda path: report(rows))
    monkeypatch.setattr(app.messagebox, 'askyesno', askyesno)
    editor_screen(root, conn).refresh_report()
    return questions

def fmis_of(conn, space):
    return conn.execute("SELECT fmis_capacity FROM rooms WHERE space = ?", (space,)).fetchone()[0]

@pytest.mark.parametrize('answer, expected', [(True, 31), (False, 20)])
def test_refresh_with_the_apps_own_counts_asks_then_keeps_or_replaces_fmis_capacity(root, conn, said, monkeypatch, answer, expected):
    conn.execute("UPDATE rooms SET fmis_capacity = 31 WHERE space = '101'")
    conn.commit()
    questions = refresh_with(root, conn, said, monkeypatch, ROOMS, answer)
    assert questions[-1] == "The counts in this file match the app's own counts.\nKeep the FMIS capacities as they are?"
    assert fmis_of(conn, '101') == expected

def test_refresh_from_a_raw_fmis_export_does_not_ask(root, conn, said, monkeypatch):
    rows = [(EOW, '1', '101', 50.0, 33), (EOW, '1', '102', 30.0, 0)]
    questions = refresh_with(root, conn, said, monkeypatch, rows, False)
    assert len(questions) == 1 and questions[0].startswith('2 rows in')
    assert fmis_of(conn, '101') == 33

# --- room zones: the Change zone box ---------------------------------------------------------------------------------

# the floor in two parts: two doors named WEST (144 each) and two named SOUTH (163 each)
def two_parts(conn):
    for pk, zone in [(1, 'WEST'), (2, 'WEST')]:
        conn.execute("UPDATE exits SET wing = ? WHERE exit_pk = ?", (zone, pk))
    conn.commit()
    for exit_id in ('E1', 'E2'):
        db.save_exit(conn, doorway(exit_id, 100) | {'wing': 'SOUTH'}, 'carl', 'Carl')

def pick_rooms(screen, conn, *spaces):
    open_floor(screen, conn, spaces[0])
    screen.room_tree.selection_set([f"r{room(conn, s)['room_id']}" for s in spaces])
    screen.change_zone()
    win = dialog(screen, 'Change zone')
    zone = next(w for w in all_widgets(win) if isinstance(w, ttk.Combobox))
    why = entries(win)[0]
    return win, zone, why

def zones_shown(screen):
    return {v[1]: (v[3], v[4]) for v in (screen.zone_tree.item(i, 'values') for i in screen.zone_tree.get_children())}

def shown(screen, conn, space, column):
    return screen.room_tree.set(f"r{room(conn, space)['room_id']}", column)

# one room: preview the zones, save -> saved, logged, and its zone and the floor's zones show on screen
def test_change_zone_for_one_room(root, conn, said):
    two_parts(conn)
    screen = editor_screen(root, conn)
    win, zone, why = pick_rooms(screen, conn, '101')
    assert zone.get() == app.NO_ZONE and list(zone['values']) == [app.NO_ZONE, 'SOUTH', 'WEST']
    zone.set('south')
    type_into(why, 'walked the floor')
    assert 'wing SOUTH: occupant load 0 -> 20 vs exit capacity 326' in label_text(win)
    press(win, 'Save')

    assert not win.winfo_exists() and said == []
    r = room(conn, '101')
    assert r['zone_override'] == 'SOUTH'
    assert db.history(conn, 'rooms', r['room_id'])[['field', 'new_value', 'why']].values.tolist()[0] == \
        ['zone_override', 'SOUTH', 'walked the floor']
    assert shown(screen, conn, '101', 'zone_override') == 'SOUTH'
    assert zones_shown(screen)['SOUTH'] == ('20', '326')
    assert screen.status_var.get() == 'saved: Engineering Office Wing 101 zone - -> SOUTH'
    assert shown(screen, conn, '102', 'flag') == ''                  # counted 0 -> nobody to put in the wrong zone

# a room with people and no zone, on a floor where another room has one -> flagged in its row, as the warnings list it
def test_a_room_with_no_zone_on_a_floor_with_zones_is_flagged(root, conn, said):
    two_parts(conn)
    db.change_zone(conn, [room(conn, '102')['room_id']], 'WEST', 'carl', 'Carl', 'set')
    screen = editor_screen(root, conn)
    open_floor(screen, conn)
    assert (shown(screen, conn, '101', 'flag'), shown(screen, conn, '102', 'flag')) == ('no zone set', '')
    assert screen.export_result()['warnings']['type'].tolist().count('room_without_zone') == 1

# a selection of rooms at once -> one save, one log row each, the rooms stay selected
def test_change_zone_for_a_selection_of_rooms(root, conn, said):
    two_parts(conn)
    screen = editor_screen(root, conn)
    win, zone, why = pick_rooms(screen, conn, '101', '102')
    assert win.title() == 'Change zone - 2 rooms'
    assert 'Engineering Office Wing floor 1: 101, 102' in label_text(win)
    zone.set('WEST')
    type_into(why, 'west part')
    press(win, 'Save')

    assert not win.winfo_exists() and said == []
    assert [room(conn, s)['zone_override'] for s in ('101', '102')] == ['WEST', 'WEST']
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE field = 'zone_override' AND why = 'west part'").fetchone()[0] == 2
    assert zones_shown(screen)['WEST'] == ('20', '288')
    assert [shown(screen, conn, s, 'flag') for s in ('101', '102')] == ['', '']
    assert len(screen.room_tree.selection()) == 2
    assert screen.status_var.get() == 'saved: zone WEST on 2 rooms'

# clearing is its own choice in the list -> back to the room number, logged
def test_change_zone_back_to_the_room_number(root, conn, said):
    two_parts(conn)
    db.change_zone(conn, [room(conn, s)['room_id'] for s in ('101', '102')], 'WEST', 'carl', 'Carl', 'set')
    screen = editor_screen(root, conn)
    win, zone, why = pick_rooms(screen, conn, '101', '102')
    assert zone.get() == 'WEST' and 'Zone now: WEST (2 rooms)' in label_text(win)
    zone.set(app.NO_ZONE)
    type_into(why, 'wrong part')
    press(win, 'Save')
    assert said == [] and [room(conn, s)['zone_override'] for s in ('101', '102')] == [None, None]
    assert screen.status_var.get() == 'saved: zone (by room number) on 2 rooms'

# rooms in different zones -> the box starts empty, and an empty box saves nothing: clearing has to be picked
def test_change_zone_for_rooms_in_different_zones_needs_a_choice(root, conn, said):
    db.change_zone(conn, [room(conn, '101')['room_id']], 'WEST', 'carl', 'Carl', 'set')
    screen = editor_screen(root, conn)
    win, zone, why = pick_rooms(screen, conn, '101', '102')
    assert zone.get() == '' and 'Zone now: by room number (1 room), WEST (1 room)' in label_text(win)
    type_into(why, 'x')
    press(win, 'Save')
    assert said == [('showerror', 'Not saved', f'type a zone, or pick {app.NO_ZONE} to clear it')]
    assert win.winfo_exists()
    assert [room(conn, s)['zone_override'] for s in ('101', '102')] == ['WEST', None]

@pytest.mark.parametrize('typed, reason, message', [('SOUTH', '', 'say why the zone changed'),
                                                    ('A+B', 'x', 'letters only')])
def test_change_zone_refused_keeps_the_box_open(root, conn, said, typed, reason, message):
    screen = editor_screen(root, conn)
    win, zone, why = pick_rooms(screen, conn, '101')
    zone.set(typed)
    type_into(why, reason)
    press(win, 'Save')
    assert said[0][:2] == ('showerror', 'Not saved') and message in said[0][2]
    assert win.winfo_exists() and zone.get() == typed
    assert room(conn, '101')['zone_override'] is None

# zones typed before the exits name them -> the preview says the floor is still one zone
def test_change_zone_preview_on_a_floor_whose_exits_have_no_wing(root, conn, said):
    screen = editor_screen(root, conn)
    win, zone, _ = pick_rooms(screen, conn, '101')
    zone.set('WEST')
    text = label_text(win)
    assert 'floor 1: no exit has a wing yet, so it is still one zone' in text
    assert 'occupant load 20 -> 20 vs exit capacity 288' in text
    zone.set(app.NO_ZONE)
    assert 'no exit has a wing yet' not in label_text(win)

def test_change_zone_after_someone_else_saved(root, conn, db_path, said):
    screen = editor_screen(root, conn)
    win, zone, why = pick_rooms(screen, conn, '101', '102')
    mark = db.connect(db_path)
    db.change_zone(mark, [room(mark, '102')['room_id']], 'SOUTH', 'carl', 'Mark', 'mine')
    mark.close()
    zone.set('WEST')
    type_into(why, 'x')
    press(win, 'Save')
    assert [s[1] for s in said] == ['Changed by someone else'] and not win.winfo_exists()
    assert [room(conn, s)['zone_override'] for s in ('101', '102')] == [None, 'SOUTH']
    assert shown(screen, conn, '102', 'zone_override') == 'SOUTH'

def test_change_zone_with_no_room_picked(root, conn, said):
    screen = editor_screen(root, conn)
    screen.change_zone()
    assert said == [('showinfo', 'Pick a room', 'Select a room in the Rooms list first.')]
    assert dialog(screen, 'Change zone') is None

# a zone on one floor -> only that floor is calculated again
def test_change_zone_redoes_only_its_floor(root, campus_path, said, calculated):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        win, zone, why = pick_rooms(screen, conn, '101')
        zone.set('WEST')
        type_into(why, 'x')
        calculated.clear()
        press(win, 'Save')
        assert said == [] and max(calculated) < 6, calculated
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()

# rooms on two floors picked from a search -> saved together, both floors shown right
def test_change_zone_across_two_floors(root, campus_path, said):
    conn = db.connect(campus_path)
    try:
        screen = editor_screen(root, conn)
        screen.search_var.set('01')
        screen.search()
        root.update()
        ids = [room(conn, s)['room_id'] for s in ('101', '201')]
        screen.room_tree.selection_set([f"r{i}" for i in ids])
        screen.change_zone()
        win = dialog(screen, 'Change zone')
        next(w for w in all_widgets(win) if isinstance(w, ttk.Combobox)).set('WEST')
        type_into(entries(win)[0], 'x')
        press(win, 'Save')
        assert said == []
        assert [room(conn, s)['zone_override'] for s in ('101', '201')] == ['WEST', 'WEST']
        assert_shows_what_the_database_holds(screen, conn)
    finally:
        conn.close()
