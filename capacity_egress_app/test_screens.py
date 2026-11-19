import re
import pathlib
import sqlite3
import statistics
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

# a column the user widened stays as wide when the lists refill (after a save, or another person's save)
def test_editor_keeps_a_column_the_user_widened_after_a_refill(root, conn):
    screen = editor_with_rooms(root, conn)
    widened = {key: drag_edge(screen.room_tree, key, int(screen.room_tree.column(key, 'width')) + 150)
               for key in ('sub_category', 'note')}
    screen.show()
    root.update()
    assert {key: int(screen.room_tree.column(key, 'width')) for key in widened} == widened

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
    return abs(int(root.tk.call('font', 'actual', name, '-size')))      # px, whether Tk reports it as -17 or 17

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
    try:
        r.tk.call('font', 'configure', 'TkDefaultFont', '-size', platform)
        widgets.use_theme(r)
        assert size_of(r, 'TkDefaultFont') == body
        assert size_of(r, 'AppLargeFont') == body + 3
        assert size_of(r, 'AppCaptionFont') == body - 3
    finally:
        r.destroy()

# styles the next screens use: defined in use_theme, nothing on today's screens uses them yet
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
