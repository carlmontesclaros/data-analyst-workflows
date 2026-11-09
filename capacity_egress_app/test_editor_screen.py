# end-to-end: the editor screen driven the way a person uses it -> pick the room, type in the boxes,
# press Save, then check the database, the change log and what the screen shows.
# every save path that changes a floor's result is here: capacity, room note, exits, code factors
import tkinter as tk
from tkinter import ttk
import pytest
import app
import capacity_db as db
import excel_inputs as xi
import widgets
from test_capacity_db import report, CONFIG_DIR

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
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    widgets.use_theme(r)
    yield r
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
