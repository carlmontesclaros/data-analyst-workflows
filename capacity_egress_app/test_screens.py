import re
import pathlib
import sqlite3
import statistics
import sys
import time
import tkinter as tk
from tkinter import ttk
import pytest
import app
import capacity_db as db
import check_screen as check_screen_module
import colours
import egress
import excel_inputs as xi
import widgets
from check_screen import MIN_WINDOW, CheckScreen, rooms_found_text
from test_capacity_db import report, CONFIG_DIR

# the real one: conftest.py swaps it for a fixed screen in every test
REAL_WORK_AREA = widgets.work_area

LONG_ROOM = ('Engineering / Computer Science Building', '3', 'A120', 60.55, 24)

@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    db.create_schema(c)
    db.import_code_factors(c, CONFIG_DIR)
    db.insert_extra_settings(c)
    db.insert_rooms(c, xi.classify_rooms(report([LONG_ROOM])), 'first.xlsx')
    db.set_editor(c, 'carl', True, 'carl', 'Carl', why='first editor')
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
    widgets.use_theme(r)
    yield r
    r.destroy()

def all_widgets(w):
    for child in w.winfo_children():
        yield child
        yield from all_widgets(child)

def buttons(w):
    return [b for b in all_widgets(w) if isinstance(b, ttk.Button)]

def is_inside_window(w, window):
    return (w.winfo_ismapped() and w.winfo_rootx() + w.winfo_width() <= window.winfo_rootx() + window.winfo_width()
            and w.winfo_rooty() + w.winfo_height() <= window.winfo_rooty() + window.winfo_height())

def check_screen(root, conn):
    screen = CheckScreen(root, conn, 'carl', open_editor=lambda r=None: None, open_editors=lambda: None)
    screen.search_var.set('A120')
    screen.search()
    root.update()
    return screen

# at the size the screen opens, nothing is cut off, including with a long building name on the room card
def test_check_screen_fits_its_window(root, conn):
    check_screen(root, conn)
    assert root.winfo_reqwidth() <= root.winfo_width()
    assert root.winfo_reqheight() <= root.winfo_height()

def test_check_screen_shows_every_button(root, conn):
    check_screen(root, conn)
    texts = {b.cget('text') for b in buttons(root)}
    assert {'Editor screen', 'Editors', 'Search', 'Check', 'Save summary (.docx)'} <= texts
    assert [b.cget('text') for b in buttons(root) if not is_inside_window(b, root)] == []

# one main action per screen: everything blue competes with Check
def test_check_screen_has_one_primary_action(root, conn):
    check_screen(root, conn)
    assert [b.cget('text') for b in buttons(root) if b.cget('style') == 'Accent.TButton'] == ['Check']

def editor_screen(root, conn):
    screen = app.App(root, conn, 'carl', 'Carl', on_back=lambda: None)
    root.update()
    return screen

# the status line is the only feedback an export gives; it can't be pushed off the window
def test_editor_screen_keeps_status_line_and_buttons_visible(root, conn):
    screen = editor_screen(root, conn)
    screen.status_var.set("written")
    root.update()
    status = [w for w in all_widgets(root) if isinstance(w, ttk.Label) and str(w.cget('textvariable')) == str(screen.status_var)]
    assert len(status) == 1 and is_inside_window(status[0], root)
    assert [b.cget('text') for b in buttons(root) if not is_inside_window(b, root)] == []

# a person can shrink either screen to its smallest size: every control still shows in full there,
# and the tables give up rows (they scroll) rather than anything else being cut off
def shrink_to_minimum(window):
    window.geometry('{}x{}'.format(*window.minsize()))
    window.update()
    assert (window.winfo_width(), window.winfo_height()) == window.minsize()

def ancestors(w, window):
    while w is not window:
        w = w.master
        yield w

# drawn smaller than it asks for, or hanging past the edge of anything it sits in
def is_cut_off(w, window):
    return (w.winfo_width() < w.winfo_reqwidth() or w.winfo_height() < w.winfo_reqheight()
            or not all(is_inside_window(w, a) for a in ancestors(w, window)))

CONTAINERS = (ttk.Frame, ttk.Labelframe, ttk.Panedwindow, ttk.Scrollbar, ttk.Treeview)

def cut_off_widgets(window):
    return [f"{w.winfo_class()} {w.cget('text') or w.cget('textvariable')!s}" for w in all_widgets(window)
            if w.winfo_ismapped() and not isinstance(w, CONTAINERS) and is_cut_off(w, window)]

def rows_shown(tree):
    row = int(ttk.Style(tree).lookup('Treeview', 'rowheight'))
    return (tree.winfo_height() - row) // row        # less the heading, about a row tall

def asked_for(window):
    return window.winfo_reqwidth(), window.winfo_reqheight()

def at_least(size, floor):
    return size[0] >= floor[0] and size[1] >= floor[1]

# never smaller than the layout's floor, nor than the widgets ask for in this platform's font once shrunk there
# (a line that wraps asks for the width it was given, so it is only measured at the smallest size)
def stops_shrinking_before_anything_is_cut_off(window):
    shrink_to_minimum(window)
    return at_least(window.minsize(), MIN_WINDOW) and at_least(window.minsize(), asked_for(window))

# what the screen needs must still fit on a common 1366x768 laptop screen
def fits_a_laptop(size):
    return size[0] <= 1366 and size[1] <= 768

def test_check_screen_stops_shrinking_at_its_smallest_size(root, conn):
    check_screen(root, conn)
    assert stops_shrinking_before_anything_is_cut_off(root) and fits_a_laptop(asked_for(root))

# Windows' Segoe UI draws taller and wider than the Mac font (about 20 px a line): the screens grow to what
# their widgets ask for
WINDOWS_FONT = -17
# that 20 px line, for a test of the height a screen has: the Mac font draws it at WINDOWS_FONT, Segoe UI itself at 15 px
# (at 17 px it draws 23 px a line, taller than the 19 px of the 14 px body the app gets from Windows' 9 pt default)
WINDOWS_LINE_FONT = -15 if sys.platform == 'win32' else WINDOWS_FONT

# a platform font of this size (negative px) -> the body and every other size built from it, as use_theme does at startup
def use_font(root, size):
    widgets.set_type_scale(root, -size)

@pytest.fixture
def larger_font_root(root):
    use_font(root, WINDOWS_FONT)
    return root

@pytest.mark.parametrize('open_screen', [check_screen, editor_screen])
def test_screens_fit_a_larger_platform_font(larger_font_root, conn, open_screen):
    root = larger_font_root
    open_screen(root, conn)
    assert at_least((root.winfo_width(), root.winfo_height()), asked_for(root))
    assert stops_shrinking_before_anything_is_cut_off(root)
    shrink_to_minimum(root)
    assert cut_off_widgets(root) == []

# with the larger font the screens still fit a 1366 px laptop: the editor's search line and menu wrap onto more
# lines rather than widening the window, and a menu group (data, exports, people) stays together on one line
@pytest.mark.parametrize('open_screen', [check_screen, editor_screen])
def test_screens_fit_a_laptop_with_a_larger_platform_font(larger_font_root, conn, open_screen):
    root = larger_font_root
    open_screen(root, conn)
    assert fits_a_laptop(root.minsize())
    shrink_to_minimum(root)
    assert [b.cget('text') for b in buttons(root) if not is_inside_window(b, root) or is_cut_off(b, root)] == []

def test_editor_screen_menu_groups_stay_on_one_line_when_it_wraps(larger_font_root, conn):
    root = larger_font_root
    editor_screen(root, conn)
    shrink_to_minimum(root)
    line = {b.cget('text'): b.winfo_rooty() for b in buttons(root)}
    assert len({line[text] for text in ['← Check screen', 'Refresh', 'Export for FMIS', 'Change my name']}) > 1
    for group in [['Refresh', 'Code factors', 'Refresh space report'],
                  ['Export results workbook', 'Export space report', 'Export for FMIS'], ['Editors', 'Change my name']]:
        assert len({line[text] for text in group}) == 1, group

def test_check_screen_fits_its_smallest_window(root, conn):
    screen = check_screen(root, conn)
    screen.new_var.set('30')
    screen.add_to_check()
    shrink_to_minimum(root)
    assert root.winfo_reqwidth() <= root.winfo_width()
    assert root.winfo_reqheight() <= root.winfo_height()
    assert cut_off_widgets(root) == []
    assert {'Editor screen', 'Editors', 'Search', 'Check', 'Remove room', 'Start over',
            'Save summary (.docx)'} <= {b.cget('text') for b in buttons(root) if b.winfo_ismapped()}

# the Result column holds the verdict, the reason for the screen: no column is squeezed to fit the window
def test_check_screen_tables_keep_every_column_at_its_width(root, conn):
    screen = check_screen(root, conn)
    shrink_to_minimum(root)
    for tree, columns in [(screen.found_tree, check_screen_module.FOUND_COLUMNS),
                          (screen.check_tree, check_screen_module.CHECK_COLUMNS),
                          (screen.zone_tree, check_screen_module.ZONE_COLUMNS)]:
        shown = {col: int(tree.column(col, 'width')) for col, _ in columns}
        assert [col for col, width in columns if shown[col] < width] == [], shown
        if tree is not screen.found_tree:
            assert sum(shown.values()) <= tree.winfo_width(), shown
    # a building name longer than its column is shown in full by scrolling the list sideways, not by cutting it
    assert sum(int(screen.found_tree.column(col, 'width')) for col, _ in check_screen_module.FOUND_COLUMNS) > screen.found_tree.winfo_width()
    assert screen.found_tree.xview() != (0.0, 1.0)

# a sideways bar shows only under a table with more to see sideways (Tk's own xview): an empty one would take height
# the window keeps for a wrapped message
def test_check_screen_shows_a_sideways_bar_only_under_a_table_that_scrolls(root, conn):
    screen = check_screen(root, conn)
    shown = {}
    for tree in (screen.found_tree, screen.check_tree, screen.zone_tree):
        bars = [w for w in tree.master.winfo_children() if isinstance(w, ttk.Scrollbar) and str(w.cget('orient')) == 'horizontal']
        assert len(bars) == 1
        shown[tree] = bool(bars[0].winfo_ismapped())
        assert shown[tree] == (tree.xview() != (0.0, 1.0))
    assert shown[screen.found_tree] and not shown[screen.check_tree]

# an error can be longer than the window is wide: it wraps under the fields rather than running off the edge
@pytest.mark.parametrize('font_size', [None, WINDOWS_FONT])
def test_check_screen_long_message_wraps_at_the_smallest_size(root, conn, font_size):
    if font_size:
        use_font(root, font_size)
    screen = check_screen(root, conn)
    shrink_to_minimum(root)
    screen.message_var.set("That room's floor has no exits measured, so " * 6)
    root.update()
    assert cut_off_widgets(root) == []
    assert root.winfo_reqheight() <= root.winfo_height()

def test_check_screen_tables_still_show_rows_at_the_smallest_size(root, conn):
    screen = check_screen(root, conn)
    shrink_to_minimum(root)
    assert rows_shown(screen.check_tree) >= 2 and rows_shown(screen.zone_tree) >= 2
    assert rows_shown(screen.found_tree) >= 8

def test_editor_screen_stops_shrinking_at_its_smallest_size(root, conn):
    editor_screen(root, conn)
    assert at_least((root.winfo_width(), root.winfo_height()), asked_for(root))
    assert stops_shrinking_before_anything_is_cut_off(root) and fits_a_laptop(asked_for(root))

# with the larger font the wrapped menu takes the height of a table row, so the shortest table may show only one
@pytest.mark.parametrize(('font_size', 'rows'), [(None, 2), (WINDOWS_FONT, 1)])
def test_editor_screen_fits_its_smallest_window(root, conn, font_size, rows):
    if font_size:
        use_font(root, font_size)
    screen = editor_screen(root, conn)
    # an export saved on the S: drive: its path alone is wider than the window
    screen.status_var.set(f"written: {app.PHOTOS_DIR_WINDOWS}\\..\\exports\\Capacity results 2026-11-10.xlsx  "
                          "(412 rooms, 96 zones, 230 exits, 17 flagged)")
    shrink_to_minimum(root)
    # the tables are wider than any window and scroll sideways; everything else shows in full
    assert cut_off_widgets(root) == []
    assert [b.cget('text') for b in buttons(root) if not b.winfo_ismapped()] == []
    assert all(rows_shown(tree) >= rows for tree in (screen.zone_tree, screen.room_tree, screen.exit_tree))

def test_editor_screen_has_no_competing_primary_button(root, conn):
    editor_screen(root, conn)
    assert [b.cget('text') for b in buttons(root) if b.cget('style') == 'Accent.TButton'] == []

@pytest.mark.parametrize('columns', [app.ZONE_COLUMNS, app.ROOM_COLUMNS, app.EXIT_COLUMNS])
def test_editor_tables_use_words_not_database_names(columns):
    for key, _ in columns:
        heading = widgets.heading_for(key)
        assert '_' not in heading and heading[0].isupper()

def test_table_vocabulary_matches_the_glossary():
    assert widgets.heading_for('total_load') == 'Occupant load'
    assert widgets.heading_for('exit_capacity') == 'Exit capacity'
    assert widgets.heading_for('per_code_load') == 'Per code load'
    assert widgets.heading_for('capacity') == 'Room capacity'

@pytest.mark.parametrize('key', ['total_load', 'exit_capacity', 'per_code_load', 'capacity', 'area_m2', 'clear_width_cm', 'persons'])
def test_numbers_line_up_on_the_right(key):
    assert widgets.anchor_for(key) == 'e'

@pytest.mark.parametrize('key', ['floor', 'space', 'status', 'flags', 'note', 'exit_id'])
def test_words_line_up_on_the_left(key):
    assert widgets.anchor_for(key) == 'w'

# no exits measured means capacity unknown; a printed 0 reads as "no one can get out"
def test_zone_with_no_exits_shows_a_dash_not_zero():
    assert app.exit_capacity_text({'exit_count': 0, 'exit_capacity': 0}) == '-'

def test_zone_with_exits_shows_its_capacity_even_if_zero():
    assert app.exit_capacity_text({'exit_count': 2, 'exit_capacity': 432}) == 432
    assert app.exit_capacity_text({'exit_count': 1, 'exit_capacity': 0}) == 0

@pytest.mark.parametrize('n, text', [(0, '0 rooms'), (1, '1 room'), (2, '2 rooms')])
def test_rooms_found_counts_read_right(n, text):
    assert rooms_found_text(n, 200) == text

def test_rooms_found_says_when_the_list_is_cut():
    assert rooms_found_text(500, 200) == '500 rooms (first 200 shown)'

# one colour list -> changing a shade means changing one line
@pytest.mark.parametrize('name', ['app.py', 'check_screen.py', 'widgets.py'])
def test_screens_take_colours_from_colours_py(name):
    assert re.findall(r"#[0-9A-Fa-f]{6}\b", pathlib.Path(name).read_text(encoding='utf-8')) == []

def test_legend_fits_on_one_line_each():
    assert all(len(meaning) <= 20 for _, _, meaning in colours.LEGEND)

# a right-aligned heading needs room before the next column, or they read as one word
def test_number_headings_keep_clear_of_the_next_column():
    assert widgets.heading_text('total_load') == 'Occupant load  '
    assert widgets.heading_text('floor') == 'Floor'
    assert widgets.heading_text('Exit capacity') == 'Exit capacity  '

def test_check_screen_says_what_the_star_means(root, conn):
    screen = check_screen(root, conn)
    screen.new_var.set('30')
    screen.add_to_check()
    assert '★' in screen.zone_label.get()

# typing has to feel instant: a redraw of the whole screen, theme included, stays well under what you can notice
def test_typing_stays_quick(root, conn):
    screen = check_screen(root, conn)
    times = []
    for i in range(9):
        start = time.perf_counter()
        screen.search_var.set('x' * (i + 1))
        root.update()
        times.append((time.perf_counter() - start) * 1000)
    assert statistics.median(times) < 60

# Sun Valley drew every widget from images: 167 ms per keystroke on a Mac, against 17 ms without
def test_theme_draws_without_images(root):
    # Tk always loads its own 4 dialog icons
    assert [i for i in root.image_names() if not i.startswith('::tk::icons')] == []

@pytest.mark.parametrize('columns', [app.ZONE_COLUMNS, app.ROOM_COLUMNS, app.EXIT_COLUMNS])
def test_every_heading_fits_its_column(root, columns):
    too_narrow = [key for key, width in columns
                  if root.tk.call('font', 'measure', 'TkDefaultFont', widgets.heading_text(key)) + 8 > width]
    assert too_narrow == []


# a wing group (Clearihue 1: A+C+D) shows whole wherever a zone's wing is shown, not cut to "A+C+"
def text_width(root, text):
    return root.tk.call('font', 'measure', 'TkDefaultFont', text) + 8

def test_a_wing_group_fits_the_editor_columns(root):
    widths = dict(app.ZONE_COLUMNS) | dict(app.EXIT_COLUMNS)
    assert {key: widths[key] for key in ['zone_wing', 'wing', 'into_wing']
            if text_width(root, 'A+C+D') > widths[key]} == {}

def test_a_wing_group_fits_the_check_screen_zone_column(root, conn):
    screen = check_screen(root, conn)
    name = egress.zone_name('1M', 'A+C+D') + ' ★'
    assert text_width(root, name) <= int(screen.zone_tree.column('Zone', 'width'))

# polish: details you only notice when they're wrong
def test_buttons_and_fields_share_one_height(root):
    heights = {type(w).__name__: w.winfo_reqheight() for w in
               [ttk.Button(root, text="Check"), ttk.Entry(root), ttk.Combobox(root)]}
    assert max(heights.values()) - min(heights.values()) <= 1, heights

def test_dropdown_arrow_sits_inside_its_field(root):
    field = ttk.Style(root).layout('TCombobox')[0]
    assert field[0] == 'Entry.field'          # all 4 edges
    assert 'border' not in field[1]           # a border here hides the arrow (seen on screen, 2026-11-06)
    assert any('downarrow' in child[0] for child in field[1]['children'])

def test_dropdown_arrow_can_still_be_clicked(root):
    box = ttk.Combobox(root, width=20)
    box.pack()
    root.update()
    assert 'downarrow' in box.identify(box.winfo_width() - 6, box.winfo_height() // 2)

@pytest.mark.parametrize('bar', ['Vertical.TScrollbar', 'Horizontal.TScrollbar'])
def test_scrollbars_are_a_plain_thumb(root, bar):
    style = ttk.Style(root)
    assert 'arrow' not in str(style.layout(bar))
    assert style.lookup(bar, 'gripcount') == 0

@pytest.mark.parametrize('widget', ['TEntry', 'TCombobox', 'TButton'])
def test_focus_shows_in_blue(root, widget):
    assert ttk.Style(root).lookup(widget, 'bordercolor', ['focus']) == colours.ACCENT

# no dashed box inside a button; the blue border says it has focus
def test_buttons_have_no_dashed_focus_box(root):
    assert 'Button.focus' not in str(ttk.Style(root).layout('TButton'))

# the label moves 1 px when pressed, so the button feels like it heard you
def test_button_gives_way_when_pressed(root):
    style = ttk.Style(root)
    assert str(style.lookup('TButton', 'padding', ['pressed'])) != str(style.lookup('TButton', 'padding'))

def test_legend_swatches_have_no_heavy_black_box(root):
    frame = colours.legend(root)
    assert [w for w in all_widgets(frame) if isinstance(w, tk.Label) and w.cget('relief') == 'solid'] == []

def test_status_line_is_flat(root, conn):
    screen = editor_screen(root, conn)
    status = [w for w in all_widgets(root) if isinstance(w, ttk.Label) and str(w.cget('textvariable')) == str(screen.status_var)]
    assert str(status[0].cget('relief')) != 'sunken'

# one line under the fields: the help, or what's wrong. no empty row saved for an error that isn't there
def test_error_takes_the_place_of_the_help_line(root, conn):
    screen = check_screen(root, conn)
    help_text = screen.hint.cget('text')
    screen.new_var.set('abc')
    assert screen.hint.cget('text') == "Type a whole number (0 or more)."
    assert str(screen.hint.cget('foreground')) == colours.ERROR_FG
    screen.new_var.set('30')
    assert screen.hint.cget('text') == help_text
    assert str(screen.hint.cget('foreground')) == colours.MUTED

# the width a cell gives its text, read off the drawn cell: its padding is the theme's, not a number copied from the code
def text_room(tree, item, col):
    x, y, width, height = tree.bbox(item, col)
    return sum(tree.identify_element(px, y + height // 2) == 'text' for px in range(x, x + width))

# a floor with no exits measured says so in full: its verdict is the longest one and must never be cut short
@pytest.mark.parametrize('font_size', [None, WINDOWS_FONT])
def test_zone_verdict_shows_in_full_at_the_smallest_size(root, conn, font_size):
    if font_size:
        use_font(root, font_size)
    screen = check_screen(root, conn)
    screen.new_var.set('30')
    screen.add_to_check()
    shrink_to_minimum(root)
    zones = screen.zone_tree.get_children()
    assert [screen.zone_tree.set(z, 'Result') for z in zones] == [egress.CANT_CHECK]
    font = ttk.Style(root).lookup('Treeview', 'font')
    assert text_room(screen.zone_tree, zones[0], 'Result') >= int(root.tk.call('font', 'measure', font, egress.CANT_CHECK))
    assert fits_a_laptop(asked_for(root))


# at the Windows font no heading and no value in a check or editor table is cut: every column is as wide as the
# widest of its heading and its values (typed notes may be longer, so they scroll). a heading needs what Tk lays out
# for a label in the theme's heading style, border and padding included; a cell's text fills its whole cell (text_room)
def heading_room(tree, key):
    label = ttk.Label(tree, style='Treeview.Heading', text=tree.heading(key, 'text'))
    need = label.winfo_reqwidth()
    label.destroy()
    return need

def cut_columns(tree, keys):
    font = ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont'
    cut = []
    for key in keys:
        need = heading_room(tree, key)
        if key not in ('note', 'notes'):
            need = max([need] + [int(tree.tk.call('font', 'measure', font, tree.set(item, key))) for item in tree.get_children()])
        if int(tree.column(key, 'width')) < need:
            cut.append((key, int(tree.column(key, 'width')), need))
    return cut

def test_check_screen_tables_show_every_heading_and_room_in_full_at_the_windows_font(larger_font_root, conn):
    screen = check_screen(larger_font_root, conn)
    screen.new_var.set('30')
    screen.add_to_check()
    larger_font_root.update()
    assert screen.check_tree.get_children() and screen.zone_tree.get_children()
    for tree in (screen.found_tree, screen.check_tree, screen.zone_tree):
        assert cut_columns(tree, tree['columns']) == []

def editor_with_rooms(root, conn):
    screen = editor_screen(root, conn)
    screen.search_var.set('A120')
    screen.search()
    root.update()
    return screen

def test_editor_tables_show_every_heading_and_value_in_full_at_the_windows_font(larger_font_root, conn):
    screen = editor_with_rooms(larger_font_root, conn)
    assert screen.zone_tree.get_children() and screen.room_tree.get_children() and not screen.exit_tree.get_children()
    for tree in (screen.zone_tree, screen.room_tree, screen.exit_tree):
        assert cut_columns(tree, tree['columns']) == []

# a user drags a column's right edge in its heading: Tk's own drag, which holds the column to its minwidth
def drag_edge(tree, key, width):
    tree.xview_moveto(0)
    left = sum(int(tree.column(k, 'width')) for k in tree['columns'][:list(tree['columns']).index(key)])
    tree.tk.call(tree, 'drag', key, left + width)
    return int(tree.column(key, 'width'))

# a short column the user widened stays as wide when the lists refill (after a save, or another person's save); the
# descriptive columns give the width back, so the table still needs no sideways bar
def test_editor_keeps_a_column_the_user_widened_after_a_refill(root, conn):
    screen = editor_with_rooms(root, conn)
    tree = screen.room_tree
    widened = {key: drag_edge(tree, key, int(tree.column(key, 'width')) + 150) for key in ('space', 'capacity_source')}
    drag_edge(tree, 'note', int(tree.column('note', 'width')) + 150)
    screen.show()
    root.update()
    assert {key: int(tree.column(key, 'width')) for key in widened} == widened
    assert tree.xview() == (0.0, 1.0)

# a value column can be narrowed by the user, down to its heading in full but no further
def test_editor_column_narrows_to_its_heading(root, conn):
    screen = editor_with_rooms(root, conn)
    tree = screen.room_tree
    font = ttk.Style(root).lookup('Treeview', 'font') or 'TkDefaultFont'
    longest = max(int(root.tk.call('font', 'measure', font, tree.set(item, 'sub_category'))) for item in tree.get_children())
    assert heading_room(tree, 'sub_category') < longest
    assert drag_edge(tree, 'sub_category', 1) == heading_room(tree, 'sub_category')

def test_the_check_screen_still_fits_a_laptop_with_every_column_in_full(larger_font_root, conn):
    screen = check_screen(larger_font_root, conn)
    screen.new_var.set('30')
    screen.add_to_check()
    assert fits_a_laptop(larger_font_root.minsize())
    shrink_to_minimum(larger_font_root)
    assert cut_off_widgets(larger_font_root) == []
    assert cut_columns(screen.check_tree, screen.check_tree['columns']) == []

def open_code_factors(root, conn):
    screen = editor_screen(root, conn)
    screen.edit_code_factors()
    root.update()
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][0]

# the Code factors dialog grows to what its form asks for, so Preview, Save and the Why field are never cut off
@pytest.mark.parametrize('font_size', [None, WINDOWS_FONT])
def test_code_factors_dialog_shows_its_form_in_full(root, conn, font_size):
    if font_size:
        use_font(root, font_size)
    win = open_code_factors(root, conn)
    assert asked_for(win)[0] <= win.winfo_width() and asked_for(win)[1] <= win.winfo_height()
    shown = [b for b in buttons(win) if b.cget('text') in ('Preview', 'Save', 'Close')]
    assert len(shown) == 3 and [b.cget('text') for b in shown if not is_inside_window(b, win)] == []
    whys = [w for w in all_widgets(win) if isinstance(w, ttk.Entry) and w.winfo_reqwidth() > 100]
    assert whys and [w for w in whys if not is_inside_window(w, win)] == []
    assert cut_off_widgets(win) == []

def test_change_dialog_titles_use_the_app_strong_font(root, conn):
    screen = editor_with_rooms(root, conn)
    screen.room_tree.selection_set(screen.room_tree.get_children()[0])
    for open_dialog in (screen.change_capacity, screen.change_room_type):
        before = set(root.winfo_children())
        open_dialog()
        root.update()
        win = next(w for w in root.winfo_children() if w not in before and isinstance(w, tk.Toplevel))
        title = next(w for w in all_widgets(win) if isinstance(w, ttk.Label) and 'floor 3 room A120' in str(w.cget('text')))
        assert str(title.cget('font')) == 'AppStrongFont'
        win.destroy()

# status marks and row rules (README "Colours"): shape and colour both carry the status, a row is tinted only where
# someone has to act. the five fills used to sit within 8 L* of each other, so red and grey looked alike
STATUSES = [egress.GREEN, egress.AMBER, egress.RED, egress.GREY]

def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

def contrast(a, b):
    high, low = sorted([luminance(a), luminance(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)

def shape(image):
    # which of the 12 x 12 pixels the mark fills, as text
    return '\n'.join(''.join('#' if image.transparency_get(x, y) is False else '.' for x in range(image.width()))
                     for y in range(image.height()))

def status_table(root):
    tree = ttk.Treeview(root, columns=['a'])
    colours.colour_tags(tree)
    return tree

def test_each_status_has_a_12_px_mark_of_its_own_shape(root):
    shapes = {colour: shape(colours.marks(root)[colour]) for colour in STATUSES}
    assert all(colours.marks(root)[c].width() == colours.marks(root)[c].height() == 12 for c in STATUSES)
    assert len(set(shapes.values())) == 4
    assert all('#' in s for s in shapes.values())

def test_marks_are_drawn_once_per_window_and_kept(root):
    assert colours.marks(root) is colours.marks(status_table(root))
    assert len([i for i in root.image_names() if not i.startswith('::tk::icons')]) == 4

def test_each_status_row_gets_its_mark_and_rule(root):
    tree = status_table(root)
    for colour in STATUSES:
        item = tree.insert('', 'end', values=['x'], **colours.row(tree, colour))
        assert str(tree.item(item, 'image')[0]) == str(colours.marks(root)[colour])
        assert list(tree.item(item, 'tags')) == [colour]
    configured = {colour: {k: str(tree.tag_configure(colour, k)) for k in ('background', 'foreground')} for colour in STATUSES}
    assert configured[egress.GREEN] == {'background': '', 'foreground': ''}
    assert configured[egress.AMBER] == {'background': colours.STATUS[egress.AMBER][1], 'foreground': ''}
    assert configured[egress.RED] == {'background': colours.STATUS[egress.RED][1], 'foreground': colours.STATUS[egress.RED][0]}
    assert configured[egress.GREY] == {'background': '', 'foreground': colours.MUTED}

def test_a_room_with_no_status_gets_no_mark_and_no_tag(root):
    tree = status_table(root)
    item = tree.insert('', 'end', values=['x'], **colours.row(tree, egress.NONE, 'missing'))
    assert not tree.item(item, 'image')
    assert list(tree.item(item, 'tags')) == ['missing']

def test_red_and_grey_differ_in_shape_and_in_colour_or_text(root):
    marks = colours.marks(root)
    assert shape(marks[egress.RED]) != shape(marks[egress.GREY])
    red, grey = colours.ROW_RULES[egress.RED], colours.ROW_RULES[egress.GREY]
    assert red != grey and red.get('background') and not grey.get('background')
    assert red['foreground'] != grey['foreground']
    # and the marks' own colours are told apart too
    assert contrast(colours.STATUS[egress.RED][2], colours.STATUS[egress.GREY][2]) > 1.2

def test_only_amber_and_red_rows_are_tinted_and_green_stays_white():
    assert [c for c, rule in colours.ROW_RULES.items() if 'background' in rule] == [egress.AMBER, egress.RED]
    assert colours.ROW_RULES[egress.GREEN] == {}
    assert colours.STATUS[egress.AMBER][1] == '#FFF2D1' and colours.STATUS[egress.RED][1] == '#FDE3E3'
    assert colours.STATUS[egress.RED][0] == '#A31919' and colours.ROW_RULES[egress.GREY] == {'foreground': '#5D636B'}

def test_status_colours_are_readable():
    for colour in STATUSES:
        ink, tint, mark = colours.STATUS[colour]
        fill = tint or colours.SURFACE                                # a grey row is muted text on white
        assert contrast(ink, fill) >= 4.5, colour                     # text on its own tint (a verdict chip, a row)
        assert contrast(mark, colours.SURFACE) >= 3, colour           # a shape on white
        assert contrast(mark, fill) >= 3, colour                      # and on its own tint
    assert contrast(colours.MUTED, colours.SURFACE) >= 6
    assert contrast(colours.MUTED, colours.GROUND) >= 4.5

def hue_gap(a, b):
    return max(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) for i in (1, 3, 5))

def test_the_picked_row_stays_distinct_from_every_status(root):
    style = ttk.Style(root)
    picked = dict(style.map('Treeview', 'background'))['selected']
    assert picked == colours.SELECTED
    for colour in STATUSES:
        for fill in (colours.STATUS[colour][1] or colours.SURFACE, colours.SURFACE):
            assert hue_gap(picked, fill) >= 12                         # a different colour, not a slightly paler one
        assert colours.STATUS[colour][1] != picked

# the mark is drawn whole and centred in its 28 px column: no tree indicator takes the left of the cell and clips it
def test_each_mark_is_drawn_whole_and_centred_in_its_column(root):
    tree = status_table(root)
    tree.pack()
    items = [tree.insert('', 'end', values=['x'], **colours.row(tree, colour)) for colour in STATUSES]
    root.update()
    for item in items:
        x, y, width, height = tree.bbox(item, '#0')
        assert width == colours.MARK_COLUMN
        middle = y + height // 2
        image = [px for px in range(x, x + width) if tree.identify_element(px, middle) == 'image']
        assert len(image) == colours.MARK_SIZE
        assert image == list(range(image[0], image[0] + colours.MARK_SIZE))
        assert abs((image[0] - x) - (x + width - 1 - image[-1])) <= 1
        assert colours.MARK_SIZE <= height

# red text only ever means over a hard limit (README "Colours"): a room missing from the report says so in amber
def test_a_missing_room_is_not_written_in_red(root, conn):
    screen = editor_screen(root, conn)
    ink = str(screen.room_tree.tag_configure('missing', 'foreground'))
    assert ink == '#7A4A00'
    assert ink not in (colours.STATUS[egress.RED][0], colours.ERROR_FG)

@pytest.mark.parametrize('open_screen', [check_screen, editor_screen])
def test_every_status_table_has_a_mark_column(root, conn, open_screen):
    screen = open_screen(root, conn)
    trees = [t for t in all_widgets(root) if isinstance(t, ttk.Treeview)]
    assert trees
    for tree in trees:
        assert tuple(str(s) for s in tree.cget('show')) == ('tree', 'headings')
        assert int(tree.column('#0', 'width')) == colours.MARK_COLUMN
        assert not tree.tk.getboolean(tree.column('#0', 'stretch'))
    assert screen

# a table with no statuses (a room's history, the code factors) has no empty mark column in front of its headings
def test_tables_without_statuses_show_only_their_headings(root, conn):
    screen = editor_screen(root, conn)
    changes = db.history(conn, 'rooms', 0)
    changes.loc[0] = ['2026-11-19 09:00', 'Carl', 'carl', 'capacity', '20', '24', 'surveyed', '']
    screen.show_history("History - A120", changes)
    screen.edit_code_factors()
    root.update()
    dialogs = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    trees = [t for w in dialogs for t in all_widgets(w) if isinstance(t, ttk.Treeview)]
    assert len(dialogs) == 2 and len(trees) > 1
    assert all(tuple(str(s) for s in tree.cget('show')) == ('headings',) for tree in trees)

def test_check_screen_rows_carry_their_marks(root, conn):
    screen = check_screen(root, conn)
    screen.new_var.set('30')
    screen.add_to_check()
    root.update()
    marks = {str(m): c for c, m in colours.marks(root).items()}
    rows = [(tree, item) for tree in (screen.found_tree, screen.check_tree, screen.zone_tree) for item in tree.get_children()]
    assert rows
    for tree, item in rows:
        tags = tree.item(item, 'tags')
        assert [marks[str(i)] for i in tree.item(item, 'image')] == list(tags)

def test_editor_rows_carry_their_marks(root, conn):
    screen = editor_with_rooms(root, conn)
    marks = {str(m): c for c, m in colours.marks(root).items()}
    for tree in (screen.zone_tree, screen.room_tree):
        assert tree.get_children()
        for item in tree.get_children():
            colour = [t for t in tree.item(item, 'tags') if t in STATUSES]
            assert [marks[str(i)] for i in tree.item(item, 'image')] == colour

def test_legend_shows_the_same_marks(root):
    frame = colours.legend(root)
    root.update()
    shown = [str(w.cget('image')[0]) for w in all_widgets(frame) if isinstance(w, ttk.Label) and w.cget('image')]
    assert shown == [str(colours.marks(root)[c]) for c in STATUSES]
    assert [w.cget('text') for w in all_widgets(frame) if isinstance(w, ttk.Label) and w.cget('text')] == [
        'Green: within', 'Amber: needs a look', 'Red: over a hard limit', 'Grey: no data yet']

# the only images are the four marks, drawn once: not one per row, and not the theme's (see test_theme_draws_without_images)
def test_a_full_screen_makes_only_the_four_marks(root, conn):
    screen = editor_with_rooms(root, conn)
    assert screen
    assert len([i for i in root.image_names() if not i.startswith('::tk::icons')]) == 4

# type scale -> every size is a step from the body, so the order holds at any platform font
def size_of(root, name):
    # px, as the font was given it ('font actual' reports whole points on Windows: -14 px comes back as 11)
    return -int(root.tk.call('font', 'configure', name, '-size'))

@pytest.mark.parametrize(('body', 'sizes'), [(17, [14, 15, 17, 20, 22, 28]), (14, [11, 12, 14, 17, 19, 25]),
                                             (20, [17, 18, 20, 23, 25, 31])])
def test_type_scale_is_relative_to_the_body(root, body, sizes):
    widgets.set_type_scale(root, body)
    names = ['AppCaptionFont', 'AppSectionFont', 'TkDefaultFont', 'AppLargeFont', 'AppSubtitleFont', 'AppTitleFont']
    assert [size_of(root, n) for n in names] == sizes
    assert size_of(root, 'AppStrongFont') == body
    for bold in ('AppSectionFont', 'AppStrongFont', 'AppSubtitleFont', 'AppTitleFont'):
        assert root.tk.call('font', 'actual', bold, '-weight') == 'bold'
    assert [root.tk.call('font', 'actual', n, '-weight') for n in ('AppCaptionFont', 'AppLargeFont')] == ['normal', 'normal']

def test_card_values_are_larger_than_the_body_at_every_platform_font(root):
    for body in (14, 15, 17, 20):
        widgets.set_type_scale(root, body)
        assert size_of(root, 'AppLargeFont') > size_of(root, 'TkDefaultFont') > size_of(root, 'AppCaptionFont')

@pytest.mark.parametrize(('platform', 'body'), [(-12, 14), (-14, 14), (-17, 17), (-20, 20)])
def test_use_theme_builds_the_scale_from_the_platform_font(platform, body):
    try:
        r = tk.Tk()
    except tk.TclError as e:
        if 'display' not in str(e):
            raise
        pytest.skip(f"no display: {e}")
    # Windows' 96 dpi on every system, where a point is not a pixel. Tk keeps the scaling for the next window, so put it back
    scaling = r.tk.call('tk', 'scaling')
    try:
        r.tk.call('tk', 'scaling', 96 / 72)
        r.tk.call('font', 'configure', 'TkDefaultFont', '-size', platform)
        widgets.use_theme(r)
        assert size_of(r, 'TkDefaultFont') == body
        assert size_of(r, 'AppLargeFont') == body + 3
        assert size_of(r, 'AppCaptionFont') == body - 3
    finally:
        r.tk.call('tk', 'scaling', scaling)
        r.destroy()

# the card, section, tool button and tab styles, as use_theme defines them
def test_card_section_toolbutton_and_notebook_styles_are_defined(root):
    style = ttk.Style(root)
    assert style.lookup('Card.TFrame', 'background') == colours.SURFACE
    assert style.lookup('Card.TFrame', 'bordercolor') == colours.CARD_BORDER
    assert style.lookup('Card.TLabel', 'background') == colours.SURFACE
    assert style.lookup('Section.TLabel', 'font') == 'AppSectionFont'
    assert style.lookup('Section.TLabel', 'foreground') == colours.MUTED
    assert style.lookup('Toolbutton', 'background') == colours.GROUND
    assert style.lookup('Toolbutton', 'relief') == 'flat'
    assert style.lookup('Toolbutton', 'background', ['active']) == colours.HOVER
    assert style.lookup('Toolbutton', 'background', ['pressed']) == colours.PRESSED
    assert style.lookup('TNotebook.Tab', 'background', ['selected']) == colours.SURFACE
    assert style.lookup('TNotebook.Tab', 'background') == colours.GROUND

def test_a_flat_tool_button_is_visible_on_hover_against_the_ground():
    assert contrast(colours.HOVER, colours.GROUND) >= 1.05
    assert colours.HOVER != colours.GROUND != colours.PRESSED

def test_tool_buttons_and_tabs_draw(root):
    frame = ttk.Frame(root)
    frame.pack()
    ttk.Button(frame, text='Refresh', style='Toolbutton').pack(side='left')
    ttk.Separator(frame, orient='vertical').pack(side='left', fill='y', padx=6)
    notebook = ttk.Notebook(frame)
    notebook.add(ttk.Frame(notebook), text='Rooms')
    notebook.pack(side='left')
    root.update()
    assert all(w.winfo_ismapped() for w in all_widgets(frame))


# part 3: the editor at the Windows font -> one menu row, tables that need no sideways bar, a zones pane as tall as its rows
LONG_NOTE = 'tables and chairs moved to the back for the exam week, move them again before the first lecture on Monday morning'

def busy_editor(root, conn, exits=('S1 - doorway',)):
    rid = conn.execute("SELECT room_id FROM rooms").fetchone()[0]
    db.set_note(conn, 'rooms', rid, LONG_NOTE, 'carl', 'Carl')
    for exit_id in exits:
        db.save_exit(conn, {'property': LONG_ROOM[0], 'floor': LONG_ROOM[1], 'exit_id': exit_id, 'exit_type': 'doorway',
                            'clear_width_cm': '88', 'measured_date': '2026-11-10', 'measured_by': 'Carl Montesclaros',
                            'notes': LONG_NOTE}, 'carl', 'Carl')
    screen = editor_screen(root, conn)
    screen.building_var.set(LONG_ROOM[0])
    screen.pick_building()
    root.update()
    return screen

def editor_tables(screen):
    return (screen.zone_tree, screen.room_tree, screen.exit_tree)

def test_editor_menu_is_one_row_at_the_windows_font(larger_font_root, conn):
    editor_screen(larger_font_root, conn)
    menu = [w for w in larger_font_root.winfo_children() if isinstance(w, widgets.FlowRow)][1]
    assert (larger_font_root.winfo_width(), larger_font_root.winfo_height()) == app.OPEN_WINDOW
    assert len({g.winfo_y() for g in menu.groups}) == 1
    assert len({b.winfo_rooty() for b in buttons(menu)}) == 1
    assert [g.winfo_ismapped() for g in menu.lines] == [True] * 3

def test_editor_menu_is_made_of_quiet_tool_buttons(larger_font_root, conn):
    editor_screen(larger_font_root, conn)
    menu = [w for w in larger_font_root.winfo_children() if isinstance(w, widgets.FlowRow)][1]
    assert {b.cget('style') for b in buttons(menu)} == {'Toolbutton'}
    # a line between the four groups: back, data, exports, people
    assert [len(buttons(g)) for g in menu.groups] == [1, 3, 3, 2]
    assert len(menu.lines) == 3

def test_editor_tables_need_no_sideways_bar_at_the_windows_font(larger_font_root, conn):
    screen = busy_editor(larger_font_root, conn)
    assert all(tree.get_children() for tree in editor_tables(screen))
    for tree in editor_tables(screen):
        assert tree.xview() == (0.0, 1.0), tree['columns']

# the exit ids the README documents (README: Measuring exits): a space number plus what was measured, and the outside
# doors' E<floor> ids with a letter. each shows in full and the exits table still needs no sideways bar
@pytest.mark.parametrize('exit_id', ['S5 - open stair', 'E3 - outside exit', 'E2A - outside exit'])
def test_editor_exits_table_needs_no_sideways_bar_with_a_documented_exit_id(larger_font_root, conn, exit_id):
    root = larger_font_root
    screen = busy_editor(root, conn, exits=(exit_id,))
    assert (root.winfo_width(), root.winfo_height()) == app.OPEN_WINDOW
    tree = screen.exit_tree
    assert [tree.set(item, 'exit_id') for item in tree.get_children()] == [exit_id]
    assert cut_columns(tree, [key for key in tree['columns'] if key not in app.EXIT_LONG]) == []
    assert tree.xview() == (0.0, 1.0)
    assert not sideways_bar_of(tree).winfo_ismapped()

# a search across buildings shows the whole campus: the zones' first column then holds the building name and the floor
def test_editor_tables_need_no_sideways_bar_on_a_search_across_buildings(larger_font_root, conn):
    root = larger_font_root
    db.insert_rooms(conn, xi.classify_rooms(report([LONG_ROOM, (LONG_ROOM[0], '4', 'A124', 30.0, 10),
                                                    ('Turpin Hall', '1', 'A121', 30.0, 10)])), 'second.xlsx')
    screen = busy_editor(root, conn)
    screen.building_var.set('')
    screen.search_var.set('a12')
    screen.search()
    root.update()
    assert screen.building_var.get() == ''
    assert {texts['property'] for texts in screen.room_tree.long_columns.full.values()} == {LONG_ROOM[0], 'Turpin Hall'}
    zones = screen.zone_tree
    full = {zones.long_columns.full[item]['floor']: zones.set(item, 'floor') for item in zones.get_children()}
    engineering = [f"{LONG_ROOM[0]} 3", f"{LONG_ROOM[0]} 4"]
    assert set(engineering) <= set(full)
    # the building's name gives way, its floor never does: two floors of one building still read differently
    for name, floor in zip(engineering, ['3', '4'], strict=True):
        assert full[name].endswith(f"{widgets.ELLIPSIS} {floor}") and LONG_ROOM[0].startswith(full[name][:-len(floor) - 2])
    assert full[engineering[0]] != full[engineering[1]]
    item = next(item for item in zones.get_children() if zones.long_columns.full[item]['floor'] == engineering[1])
    point_at(root, zones, item, 'floor')
    assert zones.long_columns.tip_text == engineering[1]
    for tree in editor_tables(screen):
        assert tree.xview() == (0.0, 1.0), tree['columns']
        assert not sideways_bar_of(tree).winfo_ismapped(), tree['columns']

# a search that finds nothing empties the tables; the window can still change size afterwards without an error
def test_editor_window_resizes_after_a_search_that_finds_nothing(larger_font_root, conn):
    root = larger_font_root
    screen = busy_editor(root, conn)
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(value)
    screen.search_var.set('no such room anywhere')
    screen.search()
    root.update()
    assert all(not tree.get_children() for tree in editor_tables(screen))
    root.geometry(f'{root.winfo_width() + 120}x{root.winfo_height()}')
    root.update()
    assert errors == []

# a floor split into named zones (Cornett: WEST, NORTH, SOUTH), a room with no zone flagged: names and flag show in full
# and the tables still need no sideways bar
def test_editor_tables_show_room_zones_at_the_windows_font(larger_font_root, conn):
    root = larger_font_root
    db.insert_rooms(conn, xi.classify_rooms(report([(LONG_ROOM[0], LONG_ROOM[1], 'B130', 30.0, 10)])), 'second.xlsx')
    rid = conn.execute("SELECT room_id FROM rooms WHERE space = 'B130'").fetchone()[0]
    db.change_zone(conn, [rid], 'NORTH', 'carl', 'Carl', 'walked the floor')
    for exit_id in ('E1', 'E2'):
        db.save_exit(conn, {'property': LONG_ROOM[0], 'floor': LONG_ROOM[1], 'wing': 'NORTH', 'into_wing': 'SOUTH',
                            'exit_id': exit_id, 'exit_type': 'doorway', 'clear_width_cm': '88'}, 'carl', 'Carl')
    screen = busy_editor(root, conn)
    assert (root.winfo_width(), root.winfo_height()) == app.OPEN_WINDOW
    rooms = screen.room_tree
    assert sorted(rooms.set(item, 'zone_override') for item in rooms.get_children()) == ['', 'NORTH']
    for tree, long in [(screen.zone_tree, app.ZONE_LONG), (rooms, app.ROOM_LONG), (screen.exit_tree, app.EXIT_LONG)]:
        assert cut_columns(tree, [key for key in tree['columns'] if key not in long]) == []
        assert tree.xview() == (0.0, 1.0), tree['columns']

# a selection across many floors -> the Change zone box names a few and stays short enough for a 150% scaled laptop,
# with Save still on it (its height at the Windows font's line, as the app draws it there)
def test_the_change_zone_box_stays_short_for_a_big_selection(root, conn):
    use_font(root, WINDOWS_LINE_FONT)
    rows = [(LONG_ROOM[0], str(floor), f"{floor}{n:02d}", 30.0, 10) for floor in range(11, 23) for n in range(20)]
    db.insert_rooms(conn, xi.classify_rooms(report(rows)), 'floors.xlsx')
    screen = editor_screen(root, conn)
    screen.building_var.set(LONG_ROOM[0])
    screen.pick_building()
    root.update()
    screen.room_tree.selection_set(screen.room_tree.get_children())
    screen.change_zone()
    root.update()
    win = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith('Change zone'))
    zone = next(w for w in all_widgets(win) if isinstance(w, ttk.Combobox))
    zone.set('WEST')
    root.update()
    text = ' '.join(str(w.cget('text')) for w in all_widgets(win) if isinstance(w, ttk.Label))
    assert 'and 8 more' in text and 'more floors' in text and 'more zones' in text
    assert win.winfo_reqheight() <= 700
    assert [b.cget('text') for b in buttons(win) if not is_inside_window(b, win)] == []

def sideways_bar_of(tree):
    bars = [w for w in tree.master.winfo_children() if isinstance(w, ttk.Scrollbar) and str(w.cget('orient')) == 'horizontal']
    assert len(bars) == 1
    return bars[0]

# no sideways bar is drawn under a table that has nothing to scroll sideways; one that does scroll gets its bar back
def test_editor_tables_draw_no_sideways_bar_at_the_windows_font(larger_font_root, conn):
    root = larger_font_root
    screen = busy_editor(root, conn)
    assert (root.winfo_width(), root.winfo_height()) == app.OPEN_WINDOW
    for tree in editor_tables(screen):
        assert not sideways_bar_of(tree).winfo_ismapped(), tree['columns']
    tree = screen.room_tree
    tree.column('space', width=tree.winfo_width() * 2)
    root.update()
    assert tree.xview() != (0.0, 1.0)
    assert sideways_bar_of(tree).winfo_ismapped()

def test_editor_short_columns_are_never_cut(larger_font_root, conn):
    screen = busy_editor(larger_font_root, conn)
    for tree, long in [(screen.zone_tree, app.ZONE_LONG), (screen.room_tree, app.ROOM_LONG), (screen.exit_tree, app.EXIT_LONG)]:
        assert cut_columns(tree, [key for key in tree['columns'] if key not in long]) == []
        assert not any(widgets.ELLIPSIS in str(tree.set(item, key)) for item in tree.get_children()
                       for key in tree['columns'] if key not in long)

def test_editor_long_columns_cut_with_an_ellipsis_and_keep_their_headings(larger_font_root, conn):
    screen = busy_editor(larger_font_root, conn)
    tree = screen.room_tree
    item = tree.get_children()[0]
    shown = tree.set(item, 'note')
    assert shown.endswith(widgets.ELLIPSIS) and LONG_NOTE.startswith(shown[:-1]) and shown != LONG_NOTE
    assert tree.long_columns.full[item]['note'] == LONG_NOTE
    for tree in editor_tables(screen):
        assert cut_columns(tree, tree['columns']) == []

# where a column's cell is in a table: its first pixel, found the way Tk itself numbers the columns ('#0' is the mark column)
def cell_at(tree, item, key):
    number = f"#{list(tree['columns']).index(key) + 1}"
    left = next(x for x in range(tree.winfo_width()) if tree.identify_column(x) == number)
    _, y, _, height = tree.bbox(item)
    return left + 4, y + height // 2

# the made-up pointer is the only one: the event is handled as it is generated, and only the layout is run after it. a full
# update() would also handle the real mouse's events, so a person moving it over the test window changed the result
def point_at(root, tree, item, key):
    x, y = cell_at(tree, item, key)
    tree.event_generate('<Motion>', x=x, y=y, rootx=tree.winfo_rootx() + x, rooty=tree.winfo_rooty() + y)
    root.update_idletasks()

def test_a_cut_cell_shows_its_full_text_under_the_pointer(larger_font_root, conn):
    root = larger_font_root
    screen = busy_editor(root, conn)
    tree = screen.room_tree
    item = tree.get_children()[0]
    point_at(root, tree, item, 'note')
    assert tree.long_columns.tip_text == LONG_NOTE
    assert tree.long_columns.tip_label.cget('text') == LONG_NOTE
    # a short cell shows nothing, and neither does leaving the table
    point_at(root, tree, item, 'space')
    assert tree.long_columns.tip_text is None
    point_at(root, tree, item, 'note')
    assert tree.long_columns.tip_text == LONG_NOTE
    tree.event_generate('<Leave>')
    assert tree.long_columns.tip_text is None

# the cut notes are the rightmost columns: a pointer near the window's right or bottom edge still shows the whole text,
# inside the app's own window, so it stays on the monitor that window is on
@pytest.mark.parametrize('corner', ['right', 'bottom', 'bottom right'])
def test_the_full_text_stays_inside_the_window(larger_font_root, conn, corner):
    root = larger_font_root
    screen = busy_editor(root, conn)
    tree = screen.room_tree
    item = tree.get_children()[0]
    x, y = cell_at(tree, item, 'note')
    left, top = root.winfo_rootx(), root.winfo_rooty()
    right, bottom = left + root.winfo_width(), top + root.winfo_height()
    pointer_x = right - 5 if 'right' in corner else left + 100
    pointer_y = bottom - 5 if 'bottom' in corner else top + 100
    tree.event_generate('<Motion>', x=x, y=y, rootx=pointer_x, rooty=pointer_y)
    root.update_idletasks()                           # not update(): see point_at
    tip = tree.long_columns.tip
    assert tree.long_columns.tip_text == LONG_NOTE
    assert tip.winfo_width() >= tree.long_columns.tip_label.winfo_reqwidth()
    assert left <= tip.winfo_rootx() and tip.winfo_rootx() + tip.winfo_width() <= right
    assert top <= tip.winfo_rooty() and tip.winfo_rooty() + tip.winfo_height() <= bottom
    # beside the pointer, not moved off to some other edge
    assert tip.winfo_rootx() - 30 <= pointer_x <= tip.winfo_rootx() + tip.winfo_width() + 30
    assert tip.winfo_rooty() - 30 <= pointer_y <= tip.winfo_rooty() + tip.winfo_height() + 30

def test_a_cell_that_fits_shows_no_full_text(larger_font_root, conn):
    root = larger_font_root
    screen = editor_with_rooms(root, conn)
    tree = screen.room_tree
    item = tree.get_children()[0]
    screen.zone_tree.long_columns.layout()
    zone = screen.zone_tree.get_children()[0]
    assert screen.zone_tree.set(zone, 'status') == screen.zone_tree.long_columns.full[zone]['status'] != ''
    point_at(root, screen.zone_tree, zone, 'status')
    assert screen.zone_tree.long_columns.tip_text is None
    assert tree.set(item, 'flag') == tree.long_columns.full[item]['flag']
    point_at(root, tree, item, 'flag')
    assert tree.long_columns.tip_text is None

def test_pane_titles_carry_their_actions_as_tool_buttons(root, conn):
    screen = editor_screen(root, conn)
    for tree, title, actions in [(screen.zone_tree, 'Zones: occupant load vs exit capacity', []),
                                 (screen.room_tree, 'Rooms', ['Change capacity', 'Change room type', 'Change zone', 'Room note', 'Room history',
                                                              'Open photos']),
                                 (screen.exit_tree, 'Exits', ['Add exit', 'Edit exit', 'Delete exit', 'Exit note', 'Exit history'])]:
        pane = tree.master.master
        header = pane.winfo_children()[0]
        labels = [w.cget('text') for w in header.winfo_children() if isinstance(w, ttk.Label)]
        assert labels == [title]
        assert [(b.cget('text'), b.cget('style')) for b in buttons(header)] == [(a, 'Toolbutton') for a in actions]
        assert header.winfo_rooty() < tree.winfo_rooty()
        assert len({w.winfo_rooty() + w.winfo_height() // 2 for w in header.winfo_children()}) <= 2

@pytest.mark.parametrize('zones', [1, 2, 3])
def test_zones_pane_is_only_as_tall_as_its_zones(root, conn, zones):
    for floor in range(1, zones + 1):
        db.insert_rooms(conn, xi.classify_rooms(report([(LONG_ROOM[0], str(floor + 10), 'B1', 30.0, 10)])), f'floor{floor}.xlsx')
    screen = editor_screen(root, conn)
    screen.building_var.set(LONG_ROOM[0])
    screen.pick_building()
    root.update()
    shown = len(screen.zone_tree.get_children())
    assert shown >= zones
    assert screen.zone_tree['height'] == max(shown, app.ZONE_ROWS_LEAST)
    assert abs(screen.panes.sashpos(0) - screen.zone_frame.winfo_reqheight()) <= 2
    assert abs(screen.zone_frame.winfo_height() - screen.zone_frame.winfo_reqheight()) <= 6

def test_zones_pane_gives_the_rest_of_the_window_to_the_tables_below(root, conn):
    screen = editor_screen(root, conn)
    before = screen.zone_frame.winfo_height()
    root.geometry(f'{root.winfo_width()}x{root.winfo_height() + 200}')
    root.update()
    assert screen.zone_frame.winfo_height() == before
    assert screen.room_tree.winfo_height() > 0

# the app is not DPI-aware on Windows: a 1920x1080 laptop at 150% scaling gives it a 1280x720 screen, and the taskbar
# takes some of that. every window opens at the size it is laid out at when the usable screen (the work area: left, top,
# width, height, less its title bar and borders) has room, shrinks to that screen when it has not, is never forced bigger
# than that screen by its minimum size, and can still be dragged bigger
BIG_WORK_AREA = (0, 0, 1920, 1040)
TIGHT_WORK_AREA = (0, 0, 1280, 672)
# a taskbar on the top or left edge moves the work area's corner off the screen's (and keeps it below a Mac's menu bar,
# which no window goes above)
SHIFTED_WORK_AREA = (64, 48, 1280, 672)
# a laid-out size above what the screens ask for at the Windows font, and one any test machine's screen holds
LAID_OUT = (1300, 760)
# the least a Windows title bar and borders add to a window's inside at 96 dpi, the scale a program that is not
# DPI-aware is given: an 8 px resize border on each side, and a 23 px caption above the top one
TITLE_BAR_AND_BORDERS = (16, 39)

def within(size, area):
    return size[0] <= area[0] and size[1] <= area[1]

def inside_of(area):
    return tuple(a - f for a, f in zip(area[2:], TITLE_BAR_AND_BORDERS, strict=True))

@pytest.fixture(params=[BIG_WORK_AREA, TIGHT_WORK_AREA], ids=['roomy_screen', 'tight_screen'])
def work_area(request, larger_font_root, monkeypatch):
    monkeypatch.setattr(widgets, 'work_area', lambda window: request.param)
    return request.param

def open_code_factors_window(root, conn):
    return open_code_factors(root, conn)

def opened_window(root, open_screen, conn):
    open_screen(root, conn)
    win = root
    if open_screen is open_code_factors_window:
        win = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][0]
    win.update()
    return win

@pytest.mark.parametrize('open_screen', [check_screen, editor_screen, open_code_factors_window])
def test_windows_open_inside_the_work_area(larger_font_root, conn, work_area, open_screen):
    win = opened_window(larger_font_root, open_screen, conn)
    assert within((win.winfo_width(), win.winfo_height()), inside_of(work_area))
    assert within(win.minsize(), inside_of(work_area))
    assert win.resizable() == (True, True)

# the system places a new window down and to the right of the last one: one that would reach past the usable screen
# from there moves back inside it, frame and all
@pytest.mark.parametrize('open_screen', [check_screen, editor_screen, open_code_factors_window])
def test_windows_placed_low_and_right_move_inside_the_work_area(larger_font_root, conn, monkeypatch, open_screen):
    monkeypatch.setattr(widgets, 'work_area', lambda window: SHIFTED_WORK_AREA)
    larger_font_root.geometry('+700+300')
    larger_font_root.update()
    win = opened_window(larger_font_root, open_screen, conn)
    left, top, width, height = SHIFTED_WORK_AREA
    x, y = win.winfo_x(), win.winfo_y()
    assert x >= left
    assert y >= top
    assert x + win.winfo_width() + TITLE_BAR_AND_BORDERS[0] <= left + width
    assert y + win.winfo_height() + TITLE_BAR_AND_BORDERS[1] <= top + height

# the app starts with its main window withdrawn and shows it once the check screen is built (app.main): the system
# would pick its place only then, so it opens in the middle of the usable screen instead
def test_main_window_shown_after_it_is_built_opens_in_the_middle_of_the_work_area(larger_font_root, conn, monkeypatch):
    area = (0, 40, 1600, 900)
    monkeypatch.setattr(widgets, 'work_area', lambda window: area)
    monkeypatch.setattr(check_screen_module, 'OPEN_WINDOW', LAID_OUT)      # a size the test machine's own screen holds
    root = larger_font_root
    root.withdraw()
    check_screen(root, conn)
    root.deiconify()
    root.update()
    left, top, width, height = area
    outer = (root.winfo_width() + TITLE_BAR_AND_BORDERS[0], root.winfo_height() + TITLE_BAR_AND_BORDERS[1])
    gaps = (root.winfo_x() - left, left + width - root.winfo_x() - outer[0],
            root.winfo_y() - top, top + height - root.winfo_y() - outer[1])
    assert min(gaps) >= 0
    assert abs(gaps[0] - gaps[1]) <= TITLE_BAR_AND_BORDERS[0]
    assert abs(gaps[2] - gaps[3]) <= TITLE_BAR_AND_BORDERS[1]

# the real work area, as the system reports it, for a window not shown yet: on Windows the main monitor's work area, elsewhere
# the whole screen: from its top left corner, it holds the biggest window Tk lets a window grow to (wm maxsize, the screen
# less any menu bar) and stays within the root window Tk draws on (the virtual root, the screen itself)
def test_work_area_of_a_window_not_shown_yet_is_the_main_monitors(root):
    window = tk.Toplevel(root)
    window.withdraw()
    area = REAL_WORK_AREA(window)
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        assert ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)         # SPI_GETWORKAREA
        assert area == (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    else:
        assert area[:2] == (0, 0)
        assert at_least(area[2:], window.wm_maxsize())
        assert within(area[2:], (window.winfo_vrootwidth(), window.winfo_vrootheight()))

@pytest.mark.parametrize('open_screen', [check_screen, editor_screen])
def test_screens_show_everything_at_their_smallest_size_inside_the_work_area(larger_font_root, conn, work_area, open_screen):
    root = larger_font_root
    open_screen(root, conn)
    shrink_to_minimum(root)
    assert within(root.minsize(), inside_of(work_area))
    assert cut_off_widgets(root) == []
    assert [b.cget('text') for b in buttons(root) if not is_inside_window(b, root) or is_cut_off(b, root)] == []

@pytest.mark.parametrize('open_screen', [check_screen, editor_screen])
def test_screens_can_still_be_dragged_bigger(larger_font_root, conn, monkeypatch, open_screen):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    root = larger_font_root
    open_screen(root, conn)
    root.geometry('1360x760')
    root.update()
    assert (root.winfo_width(), root.winfo_height()) == (1360, 760)
    assert cut_off_widgets(root) == []

# on the tightest screen at the Windows font a long name and the buttons take their room on the title's line: the subtitle
# under them is never cut off at the smallest size
def test_check_screen_subtitle_shows_in_full_beside_a_long_name_on_the_tight_screen(larger_font_root, conn, monkeypatch):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    db.set_user_name(conn, 'carl', 'Carlos Montesclaros-Villanueva')
    root = larger_font_root
    check_screen(root, conn)
    shrink_to_minimum(root)
    assert cut_off_widgets(root) == []

# on the tightest screen with the Windows font's line the check screen opens at its smallest size: both result tables
# still show a row with every column at full width (the zone verdict never scrolls out of sight), also while an error
# wraps under the fields onto a second line
@pytest.mark.parametrize('name', ['Carl', 'Carlos Montesclaros-Villanueva'], ids=['short_name', 'long_name'])
@pytest.mark.parametrize('message', ['', "That room's floor has no exits measured, so " * 4], ids=['no_message', 'two_line_message'])
def test_check_screen_tables_show_a_whole_row_on_the_tight_screen(root, conn, monkeypatch, message, name):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    db.set_user_name(conn, 'carl', name)
    use_font(root, WINDOWS_LINE_FONT)
    screen = check_screen(root, conn)
    shrink_to_minimum(root)
    screen.message_var.set(message)
    root.update()
    for tree, columns in [(screen.check_tree, check_screen_module.CHECK_COLUMNS),
                          (screen.zone_tree, check_screen_module.ZONE_COLUMNS)]:
        assert colours.MARK_COLUMN + sum(int(tree.column(col, 'width')) for col, _ in columns) <= tree.winfo_width()
        assert tree.xview() == (0.0, 1.0)
        assert rows_shown(tree) >= 1
    assert cut_off_widgets(root) == []

# on a screen with room each screen opens at the size it is laid out at, not smaller
@pytest.mark.parametrize('open_screen, module', [(check_screen, check_screen_module), (editor_screen, app)])
def test_screens_open_at_their_laid_out_size_when_the_work_area_has_room(larger_font_root, conn, monkeypatch, open_screen, module):
    monkeypatch.setattr(widgets, 'work_area', lambda window: BIG_WORK_AREA)
    monkeypatch.setattr(module, 'OPEN_WINDOW', LAID_OUT)
    win = opened_window(larger_font_root, open_screen, conn)
    assert (win.winfo_width(), win.winfo_height()) == LAID_OUT
    assert win.resizable() == (True, True)


# part 2: the check screen -> its four sections are white cards under their titles, and each verdict is a chip
SECTIONS = ["1. Find a room", "2. Room", "3. Try a new capacity or room type", "4. Result"]

def styled(window, kind, style):
    return [w for w in all_widgets(window) if isinstance(w, kind) and str(w.cget('style')) == style]

def test_check_screen_sections_are_cards_that_need_no_sideways_scroll(larger_font_root, conn, work_area):
    root = larger_font_root
    use_font(root, WINDOWS_LINE_FONT)
    # the widest row a check usually makes: an unvisited room tried far over its per code load
    conn.execute("UPDATE rooms SET capacity = NULL")
    screen = check_screen(root, conn)
    screen.new_var.set('300')
    screen.add_to_check()
    root.update()
    assert [w for w in all_widgets(root) if isinstance(w, ttk.Labelframe)] == []
    titles, cards = styled(root, ttk.Label, 'Section.TLabel'), styled(root, ttk.Frame, 'Card.TFrame')
    assert [str(t.cget('text')) for t in titles] == SECTIONS
    assert len(cards) == len(SECTIONS)
    for title, card in zip(titles, cards, strict=True):
        assert title.master is card.master
        assert title.winfo_rootx() == card.winfo_rootx()
        assert title.winfo_rooty() + title.winfo_height() <= card.winfo_rooty()
    # at the size it opens at: nothing is cut off and neither result table scrolls sideways. (the room list does, by
    # design, for a building name longer than its column)
    assert at_least((root.winfo_width(), root.winfo_height()), asked_for(root))
    assert cut_off_widgets(root) == []
    assert screen.check_tree.get_children() and screen.zone_tree.get_children()
    assert [tree.xview() for tree in (screen.check_tree, screen.zone_tree)] == [(0.0, 1.0)] * 2

def test_check_screen_cards_have_no_grey_patches(root, conn):
    check_screen(root, conn)
    cards = styled(root, ttk.Frame, 'Card.TFrame')
    assert cards
    style = ttk.Style(root)
    grey = [f"{w.winfo_class()} {w}" for card in cards for w in all_widgets(card) if isinstance(w, (ttk.Label, ttk.Frame))
            and style.lookup(str(w.cget('style')) or w.winfo_class(), 'background') != colours.SURFACE]
    assert grey == []
    # only the section's own card has the 1 px line: the frames that lay out its contents draw no box of their own
    inner = [w for card in cards for w in all_widgets(card) if isinstance(w, ttk.Frame)]
    assert inner
    assert [str(w) for w in inner if str(style.lookup(str(w.cget('style')), 'relief')) != 'flat'] == []

# clam draws a frame's border as two lines. 'solid' paints both in bordercolor (2 px); 'raised' paints the inner one in
# lightcolor (top, left) and darkcolor (bottom, right): in the card's own white that leaves the 1 px line a card has
def test_a_card_has_a_1_px_line(root):
    style = ttk.Style(root)
    assert str(style.lookup('Card.TFrame', 'relief')) == 'raised'
    assert [style.lookup('Card.TFrame', option) for option in ('lightcolor', 'darkcolor')] == [colours.SURFACE] * 2

def test_check_screen_card_values_are_larger_than_their_captions(root, conn):
    screen = check_screen(root, conn)
    captions = [w for w in all_widgets(root) if isinstance(w, ttk.Label) and w.master is screen.badge.master.master
                and str(w.cget('text')) in ('Room type', 'Area', 'Room capacity', 'Per code load')]
    assert [str(w.cget('font')) for w in captions] == [widgets.FONTS['caption']] * 4
    values = [str(v) for v in [*screen.card_vars.values(), *screen.trial_vars.values()]]
    shown = [w for w in all_widgets(root) if isinstance(w, ttk.Label) and str(w.cget('textvariable')) in values]
    assert [str(w.cget('font')) for w in shown] == [widgets.FONTS['large']] * 8

def chip_look(chip):
    return str(chip.cget('image')), str(chip.cget('bg')), str(chip.cget('fg'))

def mark_chip(root, colour, fill):
    return str(colours.marks(root)[colour]), fill, colours.STATUS[colour][0]

PLAIN = ('', colours.SURFACE, colours.TEXT_FG)                   # no verdict: text (or nothing) straight on the card

def test_check_screen_empty_state_shows_no_chip(root, conn):
    screen = CheckScreen(root, conn, 'carl')
    root.update()
    assert screen.room_title.get() == "Pick a room on the left"
    for chip in (screen.badge, screen.trial_badge):
        assert (chip.cget('text'), chip_look(chip)) == ('', PLAIN)

def test_check_screen_verdicts_are_chips_with_their_status_mark(root, conn):
    screen = check_screen(root, conn)
    green = mark_chip(root, egress.GREEN, colours.STATUS[egress.GREEN][1])
    assert (screen.badge.cget('text'), chip_look(screen.badge)) == ("Now: within per code", green)
    assert str(screen.badge.cget('compound')) == str(screen.trial_badge.cget('compound')) == 'left'
    # nothing tried yet -> a line of help, not a verdict
    assert screen.trial_badge.cget('text') == "With change: pick a room type or type a new capacity in 3 below"
    assert chip_look(screen.trial_badge) == PLAIN
    screen.new_var.set('300')
    amber = mark_chip(root, egress.AMBER, colours.STATUS[egress.AMBER][1])
    assert screen.trial_badge.cget('text').startswith("With change: needs justification, +")
    assert chip_look(screen.trial_badge) == amber
    screen.start_over()
    assert chip_look(screen.trial_badge) == PLAIN

# grey (no data) has no tint of its own, and a room out of scope no status: both chips sit on the window's ground colour
@pytest.mark.parametrize(('change', 'status', 'ink'),
                         [('capacity = NULL', egress.GREY, colours.MUTED),
                          ("sub_category = '16.2 - Other Non-Assignable Area'", None, colours.TEXT_FG)])
def test_check_screen_chip_without_a_tint_sits_on_the_ground(root, conn, change, status, ink):
    conn.execute(f"UPDATE rooms SET {change}")    # noqa: S608  (the two fixed texts above)
    screen = check_screen(root, conn)
    mark = str(colours.marks(root)[status]) if status else ''
    assert screen.badge.cget('text').startswith("Now: ")
    assert chip_look(screen.badge) == (mark, colours.GROUND, ink)
    assert contrast(ink, colours.GROUND) >= 4.5
    assert status is None or contrast(colours.STATUS[status][2], colours.GROUND) >= 3

def test_check_screen_picking_no_room_clears_the_chip(root, conn):
    screen = check_screen(root, conn)
    screen.new_var.set('300')
    screen.room = None
    screen.show_trial()
    assert (screen.trial_badge.cget('text'), chip_look(screen.trial_badge)) == ('', PLAIN)

# two long verdicts (a room out of scope says why on each) don't fit one line on the tight screen: the second chip goes
# under the first, and the result tables keep a row
def test_long_verdict_chips_stack_instead_of_being_cut_off(root, conn, monkeypatch):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    use_font(root, WINDOWS_LINE_FONT)
    conn.execute("UPDATE rooms SET sub_category = '16.2 - Other Non-Assignable Area'")
    screen = check_screen(root, conn)
    shrink_to_minimum(root)
    for typed in ('', '30'):                          # the line of help beside the verdict, then both verdicts
        screen.new_var.set(typed)
        root.update()
        assert 'out of scope' in screen.badge.cget('text')
        assert cut_off_widgets(root) == []
        assert screen.trial_badge.winfo_rooty() >= screen.badge.winfo_rooty() + screen.badge.winfo_height()
        assert screen.trial_badge.winfo_rootx() == screen.badge.winfo_rootx()
        assert rows_shown(screen.check_tree) >= 1
        assert rows_shown(screen.zone_tree) >= 1

# short verdicts share a line, also after long ones were stacked
def test_short_verdict_chips_sit_side_by_side(root, conn, monkeypatch):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    use_font(root, WINDOWS_LINE_FONT)
    screen = check_screen(root, conn)
    shrink_to_minimum(root)
    short = screen.badge.cget('text')
    for text in (short + ' and on' * 20, short):
        screen.show_chip(screen.badge, text, colours.NO_CHIP)
        root.update()
        beside = screen.trial_badge.winfo_rooty() == screen.badge.winfo_rooty()
        assert beside == (text == short)
    assert screen.trial_badge.winfo_rootx() >= screen.badge.winfo_rootx() + screen.badge.winfo_width()


# part 4: the dialogs -> save previews as small marked tables, forms on a grid, nothing clipped at the Windows font
ANNEX = 'Engineering / Computer Science Building Annex'

# a campus where every dialog has its longest content: floors with two doors each in two buildings with long names,
# one floor of many rooms, and a wing group
def dialog_campus(conn):
    rows = [(building, str(floor), f"{floor}{n:02d}", 30.0, 10)
            for building in (LONG_ROOM[0], ANNEX) for floor in range(11, 23) for n in range(14)]
    db.insert_rooms(conn, xi.classify_rooms(report(rows)), 'campus.xlsx')
    for floor in range(11, 23):
        wing = 'A+C+D' if floor == 11 else ''
        for exit_id in ('S1 - doorway', 'S2 - doorway'):
            db.save_exit(conn, {'property': LONG_ROOM[0], 'floor': str(floor), 'wing': wing, 'exit_id': exit_id,
                                'exit_type': 'doorway', 'clear_width_cm': '88'}, 'carl', 'Carl')

# the editor screen on the room's floor (one door measured), that room picked
def picked_room(root, conn):
    screen = busy_editor(root, conn)
    screen.room_tree.selection_set(screen.room_tree.get_children()[0])
    return screen

def new_dialog(root, open_it):
    before = set(root.winfo_children())
    open_it()
    root.update()
    return next(w for w in root.winfo_children() if w not in before and isinstance(w, tk.Toplevel))

def boxes(win, kind):
    return [w for w in all_widgets(win) if isinstance(w, kind)]

def plain_entries(win):
    return [w for w in boxes(win, ttk.Entry) if not isinstance(w, ttk.Combobox)]

def type_over(root, entry, text):
    entry.delete(0, 'end')
    entry.insert(0, text)
    root.update()

def open_change_capacity(root, conn, typed=None):
    screen = picked_room(root, conn)
    win = new_dialog(root, screen.change_capacity)
    if typed:
        type_over(root, plain_entries(win)[0], typed)
    return win

def open_change_capacity_over(root, conn):
    return open_change_capacity(root, conn, typed='100000')

def open_change_room_type(root, conn):
    screen = picked_room(root, conn)
    return new_dialog(root, screen.change_room_type)

def pick_zone_name(root, win, name):
    boxes(win, ttk.Combobox)[0].set(name)
    root.update()
    return win

def open_change_zone(root, conn):
    screen = picked_room(root, conn)
    return pick_zone_name(root, new_dialog(root, screen.change_zone), 'WEST')

# the longest the box gets: every room of two buildings with long names, many floors and zones
def open_change_zone_for_two_buildings(root, conn):
    dialog_campus(conn)
    screen = editor_screen(root, conn)
    screen.search_var.set('1')
    screen.search()
    root.update()
    screen.room_tree.selection_set(screen.room_tree.get_children())
    return pick_zone_name(root, new_dialog(root, screen.change_zone), 'NORTH')

# the exit forms wait for the person: don't wait, look at the form while it's open
def open_exit_form(root, conn, which):
    screen = busy_editor(root, conn)
    root.wait_window = lambda window: None
    screen.floor_var.set(LONG_ROOM[1])
    screen.show()
    if which == 'edit_exit':
        screen.exit_tree.selection_set(screen.exit_tree.get_children()[0])
    return new_dialog(root, getattr(screen, which))

def open_add_exit(root, conn):
    return open_exit_form(root, conn, 'add_exit')

def open_edit_exit(root, conn):
    return open_exit_form(root, conn, 'edit_exit')

# the longest preview: more zones changing status and exit capacity than it lists
def open_code_factors_preview(root, conn):
    dialog_campus(conn)
    win = open_code_factors(root, conn)
    notebook = boxes(win, ttk.Notebook)[0]
    notebook.select(list(db.CODE_FACTOR_KEYS).index('width_factors'))
    root.update()
    boxes(notebook.nametowidget(notebook.select()), ttk.Treeview)[0].selection_set('doorway')
    root.update()
    field = boxes(win, ttk.Combobox)[0]
    field.set('mm_per_person')
    field.event_generate('<<ComboboxSelected>>')
    root.update()
    type_over(root, plain_entries(win)[0], '100')
    next(b for b in buttons(win) if b.cget('text') == 'Preview').invoke()
    root.update()
    assert 'zones that change status' in ' '.join(str(w.cget('text') or '') for w in boxes(win, ttk.Label))
    return win

ROOM_DIALOGS = [open_change_capacity, open_change_capacity_over, open_change_room_type, open_change_zone]
DIALOGS = [*ROOM_DIALOGS, open_change_zone_for_two_buildings, open_add_exit, open_edit_exit, open_code_factors,
           open_code_factors_preview]
CONTROLS = (ttk.Button, ttk.Entry, ttk.Radiobutton)

@pytest.mark.parametrize('open_dialog', DIALOGS)
def test_dialogs_show_everything_at_the_windows_font(larger_font_root, conn, monkeypatch, open_dialog):
    monkeypatch.setattr(widgets, 'work_area', lambda window: BIG_WORK_AREA)
    win = open_dialog(larger_font_root, conn)
    assert at_least((win.winfo_width(), win.winfo_height()), asked_for(win))
    assert within((win.winfo_width(), win.winfo_height()), inside_of(BIG_WORK_AREA))
    assert cut_off_widgets(win) == []

# on a 150% scaled laptop a dialog stays inside the usable screen and every field and button is still whole: only a
# preview or a table longer than the room left gives up height, and scrolls
@pytest.mark.parametrize('open_dialog', DIALOGS)
def test_dialogs_keep_their_controls_on_the_tight_screen(root, conn, monkeypatch, open_dialog):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    use_font(root, WINDOWS_LINE_FONT)
    win = open_dialog(root, conn)
    assert within((win.winfo_width(), win.winfo_height()), inside_of(TIGHT_WORK_AREA))
    assert within(win.minsize(), inside_of(TIGHT_WORK_AREA))
    controls = boxes(win, CONTROLS)
    assert controls
    assert [f"{w.winfo_class()} {w}" for w in controls if is_cut_off(w, win)] == []

@pytest.mark.parametrize('open_dialog', DIALOGS)
def test_dialogs_placed_low_and_right_move_inside_the_work_area(larger_font_root, conn, monkeypatch, open_dialog):
    monkeypatch.setattr(widgets, 'work_area', lambda window: SHIFTED_WORK_AREA)
    larger_font_root.geometry('+700+300')
    larger_font_root.update()
    win = open_dialog(larger_font_root, conn)
    left, top, width, height = SHIFTED_WORK_AREA
    assert win.winfo_x() >= left and win.winfo_y() >= top
    assert win.winfo_x() + win.winfo_width() + TITLE_BAR_AND_BORDERS[0] <= left + width
    assert win.winfo_y() + win.winfo_height() + TITLE_BAR_AND_BORDERS[1] <= top + height

# the Code factors tables give up rows to a long preview on the tight screen, but keep their tabs and a row to pick
def test_code_factors_preview_keeps_a_row_to_pick_on_the_tight_screen(root, conn, monkeypatch):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    use_font(root, WINDOWS_LINE_FONT)
    win = open_code_factors_preview(root, conn)
    notebook = boxes(win, ttk.Notebook)[0]
    tree = boxes(notebook.nametowidget(notebook.select()), ttk.Treeview)[0]
    assert rows_shown(tree) >= 1
    assert all(is_inside_window(a, win) for a in [tree, *ancestors(tree, win)])

# a preview longer than the room the screen leaves scrolls to its last line
def test_a_long_preview_scrolls_to_its_end_on_the_tight_screen(root, conn, monkeypatch):
    monkeypatch.setattr(widgets, 'work_area', lambda window: TIGHT_WORK_AREA)
    use_font(root, WINDOWS_LINE_FONT)
    win = open_change_zone_for_two_buildings(root, conn)
    table = boxes(win, widgets.PreviewTable)[0]
    assert table.canvas.yview()[1] < 1 and table.bar.winfo_ismapped()
    last = boxes(table, ttk.Label)[-1]
    assert is_cut_off(last, win)
    for _ in range(100):
        table.canvas.event_generate('<MouseWheel>', delta=-120)
    root.update()
    assert table.canvas.yview()[1] == 1 and not is_cut_off(last, win)

# the table adds its size up from its rows: it must come to what the rows themselves ask for, or a row's end is cut
@pytest.mark.parametrize('font_size', [None, WINDOWS_FONT])
@pytest.mark.parametrize('open_dialog', [*ROOM_DIALOGS, open_change_zone_for_two_buildings])
def test_a_preview_asks_for_the_size_of_its_rows(root, conn, font_size, open_dialog):
    if font_size:
        use_font(root, font_size)
    win = open_dialog(root, conn)
    table = boxes(win, widgets.PreviewTable)[0]
    body = (table.body.winfo_reqwidth() + table.bar.winfo_reqwidth(), table.body.winfo_reqheight())
    assert (int(table.canvas.cget('width')), int(table.canvas.cget('height'))) == body

def test_a_preview_that_fits_shows_no_scrollbar(root, conn):
    win = open_change_capacity(root, conn)
    table = boxes(win, widgets.PreviewTable)[0]
    assert table.canvas.yview() == (0.0, 1.0) and not table.bar.winfo_ismapped()

# the preview's rows -> {text of the row's text cell: (the status of its mark, tint behind it, its status cell)}
def preview_rows(root, win):
    table = boxes(win, widgets.PreviewTable)[0]
    marks = {str(m): c for c, m in colours.marks(root).items()}
    grid = {}
    for label in boxes(table, ttk.Label):
        info = label.grid_info()
        grid.setdefault(int(info['row']), {})[int(info['column'])] = label
    rows = {}
    for cells in grid.values():
        if len(cells) == 3:
            mark, text, status = cells[0], cells[1], cells[2]
            assert len({str(c.cget('background')) for c in cells.values()}) == 1
            shown = marks[str(mark.cget('image')[0])] if mark.cget('image') else ''
            rows[str(text.cget('text'))] = (shown, str(mark.cget('background')), str(status.cget('text')))
    return rows

# two doors -> within; a third that is too narrow -> review; far more people than the doors carry -> over
@pytest.mark.parametrize(('widths', 'typed', 'status', 'words'), [
    (('88', '88'), '24', egress.GREEN, f"[{egress.STATUS_WITHIN}]"),
    (('88', '88', '80'), '24', egress.AMBER, f"[{egress.STATUS_REVIEW}]"),
    (('88', '88'), '100000', egress.RED, f"[{egress.STATUS_REVIEW}]")], ids=['within', 'review', 'over'])
def test_change_capacity_preview_is_a_table_with_status_marks(root, conn, widths, typed, status, words):
    for number, width in enumerate(widths, start=1):
        db.save_exit(conn, {'property': LONG_ROOM[0], 'floor': LONG_ROOM[1], 'exit_id': f'S{number} - doorway',
                            'exit_type': 'doorway', 'clear_width_cm': width}, 'carl', 'Carl')
    screen = editor_with_rooms(root, conn)
    screen.room_tree.selection_set(screen.room_tree.get_children()[0])
    win = new_dialog(root, screen.change_capacity)
    type_over(root, plain_entries(win)[0], typed)
    (text, row), = preview_rows(root, win).items()
    assert text.startswith('floor 3: occupant load') and f'-> {typed} vs exit capacity' in text
    assert row == (status, colours.STATUS[status][1] if status != egress.GREEN else colours.SURFACE, words)

def test_a_zone_with_no_exits_is_a_grey_preview_row(root, conn):
    screen = editor_with_rooms(root, conn)
    screen.room_tree.selection_set(screen.room_tree.get_children()[0])
    win = new_dialog(root, screen.change_capacity)
    (row,) = preview_rows(root, win).values()
    assert row == (egress.GREY, colours.SURFACE, f"[{egress.STATUS_NOT_SURVEYED}]")

def test_change_room_type_preview_marks_the_room_and_its_zones(root, conn):
    win = open_change_room_type(root, conn)
    rows = preview_rows(root, win)
    room = next(v for text, v in rows.items() if text.startswith('room: '))
    assert room[0] in STATUSES and room[2] == ''
    assert [v[2] for text, v in rows.items() if text.startswith('floor ')] == [f"[{egress.STATUS_REVIEW}]"]

def test_change_zone_preview_rows_carry_their_marks(root, conn):
    win = open_change_zone(root, conn)
    rows = preview_rows(root, win)
    assert rows and all(mark in STATUSES and status.startswith('[') for mark, _, status in rows.values())

# the preview keeps the words it had before it was a table
def test_a_preview_keeps_its_wording(root, conn):
    win = open_change_capacity(root, conn, typed='100000')
    shown = [str(w.cget('text')) for w in boxes(boxes(win, widgets.PreviewTable)[0], ttk.Label) if w.cget('text')]
    assert shown[0] == 'Preview (not saved):' and 'occupant load over exiting capacity' in ' '.join(shown)
    type_over(root, plain_entries(win)[0], 'many')
    shown = [str(w.cget('text')) for w in boxes(boxes(win, widgets.PreviewTable)[0], ttk.Label) if w.cget('text')]
    assert shown == ['Type a whole number (0 or more).']

def edges(w):
    return w.winfo_rootx(), w.winfo_rooty(), w.winfo_rootx() + w.winfo_width(), w.winfo_rooty() + w.winfo_height()

@pytest.mark.parametrize('open_dialog', [open_add_exit, open_edit_exit])
@pytest.mark.parametrize('font_size', [None, WINDOWS_FONT])
def test_exit_form_labels_and_controls_line_up(root, conn, open_dialog, font_size):
    if font_size:
        use_font(root, font_size)
    win = open_dialog(root, conn)
    controls = sorted(boxes(win, ttk.Entry), key=lambda w: w.winfo_rooty())
    labels = sorted(boxes(win, ttk.Label), key=lambda w: w.winfo_rooty())
    assert len(controls) == len(labels) == 14
    assert len({edges(w)[0] for w in labels}) == 1
    assert len({(edges(w)[0], edges(w)[2]) for w in controls}) == 1
    for label, control in zip(labels, controls, strict=True):
        assert abs((edges(label)[1] + edges(label)[3]) - (edges(control)[1] + edges(control)[3])) <= 2
        assert edges(label)[2] < edges(control)[0]
    # a gap between one field and the next, so two borders never read as one box
    assert min(edges(b)[1] - edges(a)[3] for a, b in zip(controls, controls[1:], strict=False)) >= 2
    save = next(b for b in buttons(win) if b.cget('text') == 'Cancel')
    assert edges(save)[2] == edges(controls[0])[2]

def overlap(a, b):
    (left, top, right, bottom), (left2, top2, right2, bottom2) = edges(a), edges(b)
    return left < right2 and left2 < right and top < bottom2 and top2 < bottom

@pytest.mark.parametrize('font_size', [None, WINDOWS_FONT])
def test_code_factors_form_is_a_grid_with_no_overlaps(root, conn, font_size):
    if font_size:
        use_font(root, font_size)
    win = open_code_factors(root, conn)
    field = boxes(win, ttk.Combobox)[0]
    form = [w for w in field.master.winfo_children() if isinstance(w, (ttk.Label, ttk.Entry)) and w.winfo_ismapped()]
    assert [f"{a} {b}" for i, a in enumerate(form) for b in form[i + 1:] if overlap(a, b)] == []
    value, clause, why = plain_entries(win)
    assert (edges(field)[0], edges(field)[2]) == (edges(clause)[0], edges(clause)[2])
    assert (edges(value)[0], edges(value)[2]) == (edges(why)[0], edges(why)[2])

# every factor shows in full: keys and numbers always, the free text (source, note) as far as the width goes, with the
# rest under the pointer. no heading is cut and no tab needs a sideways bar
def test_code_factor_tables_cut_no_value_at_the_windows_font(larger_font_root, conn):
    root = larger_font_root
    win = open_code_factors(root, conn)
    notebook = boxes(win, ttk.Notebook)[0]
    for index, table in enumerate(db.CODE_FACTOR_KEYS):
        notebook.select(index)
        root.update()
        tree = boxes(notebook.nametowidget(notebook.select()), ttk.Treeview)[0]
        assert tree.get_children(), table
        assert cut_columns(tree, [key for key in tree['columns'] if key not in app.FACTOR_LONG]) == [], table
        assert tree.xview() == (0.0, 1.0), table
        for item, texts in tree.long_columns.full.items():
            for key, full in texts.items():
                shown = tree.set(item, key)
                assert shown == full or (shown.endswith(widgets.ELLIPSIS) and full.startswith(shown[:-1].rstrip()))
        # a long text gets the width the other columns leave over, up to what it needs
        widths = sum(int(tree.column(key, 'width')) for key in tree['columns'])
        cut = any(tree.set(item, key) != full for item, texts in tree.long_columns.full.items() for key, full in texts.items())
        assert not cut or widths >= tree.winfo_width() - 8, (table, widths, tree.winfo_width())

def test_changing_a_code_factor_still_finds_its_row_when_texts_are_cut(larger_font_root, conn):
    root = larger_font_root
    win = open_code_factors(root, conn)
    notebook = boxes(win, ttk.Notebook)[0]
    notebook.select(list(db.CODE_FACTOR_KEYS).index('category_map'))
    root.update()
    tree = boxes(notebook.nametowidget(notebook.select()), ttk.Treeview)[0]
    tree.selection_set('2.2 - Unscheduled Class Lab Space')
    root.update()
    field = boxes(win, ttk.Combobox)[0]
    field.set('note')
    field.event_generate('<<ComboboxSelected>>')
    root.update()
    assert plain_entries(win)[0].get() == ('Supervisor ruling: class labs count as classroom. '
                                           'Override per room if it is really a lab')
