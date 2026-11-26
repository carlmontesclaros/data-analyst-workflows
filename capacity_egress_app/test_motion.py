# the app's only motion: the row under the pointer is highlighted on every table, and a zone row whose verdict a check
# changes fades from a stronger tint to its own
import tkinter as tk
from tkinter import ttk

import pytest

import app
import capacity_db as db
import colours
import egress
import excel_inputs as xi
import widgets
import test_screens
from test_capacity_db import report
from test_screens import all_widgets, check_screen, editor_screen

conn, root = test_screens.conn, test_screens.root                # the same fixtures
HOVER = widgets.HOVER_TAG


def wait(window, ms):
    done = tk.BooleanVar(window, False)
    window.after(ms, done.set, True)
    window.wait_variable(done)


def table(root, rows=3):
    tree = ttk.Treeview(root, columns=['a'], show='headings', height=rows)
    tree.heading('a', text='A')
    for i in range(rows):
        tree.insert('', 'end', iid=f'r{i}', values=[i])
    tree.pack()
    widgets.hover_rows(tree)
    root.update()
    return tree


def point_at(tree, item):
    tree.see(item)
    tree.update()
    x, y, width, height = tree.bbox(item)
    tree.event_generate('<Motion>', x=x + 5, y=y + height // 2)


def lit(tree):
    return list(tree.tag_has(HOVER))


def test_hover_follows_the_pointer_from_row_to_row(root):
    tree = table(root)
    point_at(tree, 'r0')
    assert lit(tree) == ['r0']
    point_at(tree, 'r0')
    assert lit(tree) == ['r0']
    point_at(tree, 'r2')
    assert lit(tree) == ['r2']


def test_hover_clears_when_the_pointer_leaves(root):
    tree = table(root)
    point_at(tree, 'r1')
    tree.event_generate('<Leave>')
    assert lit(tree) == []
    point_at(tree, 'r1')                          # and comes back
    assert lit(tree) == ['r1']


def test_hover_clears_over_the_heading_and_below_the_rows(root):
    tree = table(root, rows=2)
    tree.configure(height=6)
    root.update()
    for y in (3, tree.winfo_height() - 3):
        point_at(tree, 'r0')
        tree.event_generate('<Motion>', x=10, y=y)
        assert lit(tree) == []


def test_hover_clears_when_the_wheel_scrolls_the_rows_away(root):
    tree = table(root)
    point_at(tree, 'r1')
    tree.event_generate('<MouseWheel>', x=10, y=40, delta=-1)
    assert lit(tree) == []


# a refresh fills a table again, often with the same ids: the old highlight is gone with the old row
def test_hover_comes_back_on_rows_filled_again(root):
    tree = table(root)
    point_at(tree, 'r1')
    tree.delete(*tree.get_children())
    for i in range(3):
        tree.insert('', 'end', iid=f'r{i}', values=[i])
    point_at(tree, 'r1')
    assert lit(tree) == ['r1']
    tree.delete(*tree.get_children())
    tree.insert('', 'end', iid='new', values=['new'])
    point_at(tree, 'new')                         # the row last lit no longer exists
    assert lit(tree) == ['new']


def test_hover_keeps_the_rows_own_tags_and_the_selection(root):
    tree = table(root)
    colours.colour_tags(tree)
    tree.item('r1', tags=(egress.RED,))
    tree.selection_set('r1')
    point_at(tree, 'r1')
    assert set(tree.item('r1', 'tags')) == {egress.RED, HOVER}
    point_at(tree, 'r0')
    assert list(tree.item('r1', 'tags')) == [egress.RED]
    assert list(tree.selection()) == ['r1']


# of two tags that set the same option Tk takes the one made first, so the hover tag must be made after every tag with a
# background of its own, and the fade's before the status tints it covers
@pytest.fixture
def tags_made(monkeypatch):
    made = {}
    real = ttk.Treeview.tag_configure

    def record(tree, tag, option=None, **kw):
        if option is None:
            made.setdefault(str(tree), []).append(str(tag))
        return real(tree, tag, option, **kw)
    monkeypatch.setattr(ttk.Treeview, 'tag_configure', record)
    return made


def first_rows(screen_root):
    trees = [w for w in all_widgets(screen_root) if isinstance(w, ttk.Treeview)]
    return trees, [t for t in trees if t.winfo_ismapped() and t.get_children()]


def assert_each_table_hovers(trees):
    for tree in trees:
        item = tree.get_children()[0]
        point_at(tree, item)
        assert lit(tree) == [item], str(tree)
        tree.event_generate('<Leave>')
        assert lit(tree) == []


def test_every_check_screen_table_highlights_the_row_under_the_pointer(root, conn, tags_made):
    screen = check_screen(root, conn)
    screen.new_var.set('30')
    screen.add_to_check()
    root.update()
    trees, filled = first_rows(root)
    assert len(trees) == 3 and len(filled) == 3
    assert_each_table_hovers(filled)
    for tree in trees:
        made = tags_made[str(tree)]
        assert made[-1] == HOVER and made.count(HOVER) == 1
    zone = tags_made[str(screen.zone_tree)]
    fades = [i for i, tag in enumerate(zone) if tag.startswith('fade')]
    assert fades and max(fades) < min(zone.index(colour) for colour in colours.ROW_RULES)


def test_every_editor_table_highlights_the_row_under_the_pointer(root, conn, tags_made):
    screen = editor_screen(root, conn)
    screen.building_var.set('Engineering / Computer Science Building')
    screen.pick_building()
    screen.exit_tree.insert('', 'end', iid='e1', values=[''])
    root.update()
    trees = [screen.zone_tree, screen.room_tree, screen.exit_tree]
    assert_each_table_hovers(trees)
    for tree in trees:
        assert tags_made[str(tree)][-1] == HOVER


def newest_dialog(window):
    return [w for w in window.winfo_children() if isinstance(w, tk.Toplevel)][-1]


def test_every_code_factors_table_highlights_the_row_under_the_pointer(root, conn):
    screen = editor_screen(root, conn)
    screen.edit_code_factors()
    root.update()
    win = newest_dialog(root)
    notebook = next(w for w in all_widgets(win) if isinstance(w, ttk.Notebook))
    for tab in notebook.tabs():
        notebook.select(tab)
        root.update()
        assert_each_table_hovers([w for w in all_widgets(notebook.nametowidget(tab)) if isinstance(w, ttk.Treeview)])
    win.destroy()


def test_the_editors_table_highlights_the_row_under_the_pointer(root, conn, monkeypatch):
    # Tk drops a generated pointer event inside a window that holds the grab (plain Tk does too): the box takes none here
    monkeypatch.setattr(tk.Toplevel, 'grab_set', lambda window: None)
    app.editors_dialog(root, conn, 'carl', 'Carl')
    root.update()
    win = newest_dialog(root)
    trees = [w for w in all_widgets(win) if isinstance(w, ttk.Treeview)]
    assert len(trees) == 1
    assert_each_table_hovers(trees)
    win.destroy()


# ---- the zone row's fade

def fading(tree):
    return {item: [t for t in tree.item(item, 'tags') if str(t).startswith('fade')] for item in tree.get_children()
            if any(str(t).startswith('fade') for t in tree.item(item, 'tags'))}


def verdicts(tree):
    return [tree.set(item, 'Result') for item in tree.get_children()]


# until the fade has run out, however slow the machine is
def settle(tree):
    for _ in range(300):
        if not fading(tree):
            return
        wait(tree.winfo_toplevel(), 10)
    raise AssertionError(f"still fading: {fading(tree)}")


def pending(window):
    return set(window.tk.splitlist(window.tk.call('after', 'info')))


# the one zone has no exits measured, so a check can't change its verdict -> measure two doors and its verdict can move
@pytest.fixture
def measured(conn):
    for door in ('S1', 'S2'):
        db.save_exit(conn, {'property': 'Engineering / Computer Science Building', 'floor': '3', 'exit_id': f'{door} - doorway',
                            'exit_type': 'doorway', 'clear_width_cm': '90'}, 'carl', 'Carl')
    return conn


def try_capacity(screen, capacity):
    screen.new_var.set(str(capacity))
    screen.add_to_check()


def test_a_verdict_the_check_changes_fades_to_its_own_tint(root, measured):
    screen = check_screen(root, measured)
    assert verdicts(screen.zone_tree) == ['within exit capacity']
    try_capacity(screen, 5000)
    (item,) = screen.zone_tree.get_children()
    assert fading(screen.zone_tree) == {item: [f'fade0-{egress.RED}']}
    seen = []
    for _ in range(200):
        wait(root, 10)
        step = fading(screen.zone_tree).get(item, [None])
        assert len(step) == 1                      # never two steps at once
        if not seen or seen[-1] != step[0]:
            seen.append(step[0])
        if step[0] is None:
            break
    assert seen[-1] is None and seen[:-1] == sorted(seen[:-1])
    assert list(screen.zone_tree.item(item, 'tags')) == [egress.RED]        # its final tint, and nothing else


def test_the_fade_is_three_timed_steps_of_about_160_ms(root, measured, monkeypatch):
    screen = check_screen(root, measured)
    delays = []
    real = screen.zone_tree.after

    def after(ms, *args):
        delays.append(ms)
        return real(ms, *args)
    monkeypatch.setattr(screen.zone_tree, 'after', after)
    try_capacity(screen, 5000)
    settle(screen.zone_tree)
    assert len(delays) == 3 and 150 <= sum(delays) <= 170


def test_a_change_back_to_within_fades_to_a_white_row(root, measured):
    screen = check_screen(root, measured)
    try_capacity(screen, 5000)
    settle(screen.zone_tree)
    try_capacity(screen, 10)
    (item,) = screen.zone_tree.get_children()
    assert fading(screen.zone_tree) == {item: [f'fade0-{egress.GREEN}']}
    settle(screen.zone_tree)
    assert list(screen.zone_tree.item(item, 'tags')) == [egress.GREEN]


def test_the_same_verdict_never_fades(root, measured):
    screen = check_screen(root, measured)
    try_capacity(screen, 10)                       # within before, within with the change
    assert fading(screen.zone_tree) == {}
    try_capacity(screen, 5000)
    settle(screen.zone_tree)
    try_capacity(screen, 5000)                     # Check again
    assert fading(screen.zone_tree) == {}
    screen.reload()                                # someone else's save redraws the screen
    assert fading(screen.zone_tree) == {}


def test_typing_and_picking_never_fade(root, measured):
    screen = check_screen(root, measured)
    try_capacity(screen, 5000)
    settle(screen.zone_tree)
    before = pending(root)
    for text in ('1', '10', '', '9999'):
        screen.new_var.set(text)
        assert fading(screen.zone_tree) == {}
    screen.search()
    screen.start_over()                            # the floor as it is now, not a check's result
    screen.show_room(screen.room['room_id'])
    assert fading(screen.zone_tree) == {} and pending(root) <= before


# a zone is compared with what its row says now, not with an earlier check's
def test_the_same_change_after_start_over_fades_again(root, measured):
    screen = check_screen(root, measured)
    try_capacity(screen, 5000)
    settle(screen.zone_tree)
    screen.start_over()                            # the row says within again
    try_capacity(screen, 5000)
    assert len(fading(screen.zone_tree)) == 1


# a floor the table wasn't showing is compared with that floor as it is now, and only the zone that changed fades
def test_only_the_zone_whose_verdict_changed_fades(root, measured):
    building = 'Engineering / Computer Science Building'
    db.insert_rooms(measured, xi.classify_rooms(report([(building, '4', 'B200', 60.55, 24)])), 'second.xlsx')
    for door in ('S1', 'S2'):
        db.save_exit(measured, {'property': building, 'floor': '4', 'exit_id': f'{door} - doorway', 'exit_type': 'doorway',
                                'clear_width_cm': '90'}, 'carl', 'Carl')
    screen = check_screen(root, measured)
    try_capacity(screen, 10)                       # floor 3, still within
    upstairs, = measured.execute("SELECT room_id FROM rooms WHERE space = 'B200'").fetchone()
    screen.show_room(upstairs)
    try_capacity(screen, 5000)
    tree = screen.zone_tree
    assert verdicts(tree)[0] == 'within exit capacity' and verdicts(tree)[1].startswith('over exit capacity')
    assert list(fading(tree)) == [tree.get_children()[1]]
    settle(tree)
    screen.show_room(upstairs)
    try_capacity(screen, 10)                       # floor 4 back within, floor 3 as it was
    assert list(fading(tree)) == [tree.get_children()[1]]
    settle(tree)
    screen.check_tree.selection_set(f'r{upstairs}')
    screen.remove_from_check()                     # floor 4 leaves the check: floor 3's verdict is what it was
    assert fading(tree) == {}


def test_a_save_by_someone_else_that_changes_the_verdict_fades(root, measured):
    screen = check_screen(root, measured)
    try_capacity(screen, 10)
    for exit_pk, in measured.execute("SELECT exit_pk FROM exits").fetchall():
        measured.execute("UPDATE exits SET clear_width_cm = 1 WHERE exit_pk = ?", (exit_pk,))
    measured.commit()
    screen.reload()
    assert len(fading(screen.zone_tree)) == 1


def test_a_redraw_mid_fade_cancels_its_steps(root, measured):
    screen = check_screen(root, measured)
    before = pending(root)
    try_capacity(screen, 5000)
    assert pending(root) - before
    try_capacity(screen, 5000)                     # same verdict: the new row starts at its own tint
    assert pending(root) <= before and fading(screen.zone_tree) == {}
    try_capacity(screen, 10)
    screen.start_over()
    assert pending(root) <= before


def background_errors(window):
    errors = []
    window.tk.createcommand('bgerror', lambda message: errors.append(message))
    return errors


@pytest.mark.parametrize('what', ['window', 'table'])
def test_closing_mid_fade_leaves_nothing_to_raise(root, measured, what):
    window = tk.Toplevel(root)
    errors = background_errors(root)
    screen = check_screen(window, measured)
    before = pending(root)
    try_capacity(screen, 5000)
    steps = pending(root) - before
    assert steps
    (window if what == 'window' else screen.zone_tree).destroy()
    assert not steps & pending(root)
    wait(root, widgets.FADE_MS * 2)               # past every step that was due
    assert errors == []
    if what == 'table':
        window.destroy()


# the colours of the fade: three steps from a stronger tint towards the row's own, text readable on every one
@pytest.mark.parametrize('colour', list(colours.ROW_RULES))
def test_fade_shades_step_towards_the_rows_own_tint(colour):
    def luminance(shade):
        parts = [int(shade[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (p / 12.92 if p <= 0.03928 else ((p + 0.055) / 1.055) ** 2.4 for p in parts)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    background, ink = colours.row_look(colour)
    shades = colours.fade_shades(colour)
    steps = [luminance(shade) for shade in [*shades, background]]
    assert len(shades) == 3 and steps == sorted(set(steps))          # lighter at every step, never the same twice
    assert all((step + 0.05) / (luminance(ink) + 0.05) >= 4.5 for step in steps)
