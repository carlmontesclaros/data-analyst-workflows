import re
import sqlite3
import statistics
import time
import tkinter as tk
from tkinter import ttk
import pandas as pd
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
    return c

@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
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

def use_font(root, size):
    for name in ['TkDefaultFont', 'TkTextFont', 'TkHeadingFont', 'AppStrongFont']:
        root.tk.call('font', 'configure', name, '-size', size)

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
        assert sum(shown.values()) <= tree.winfo_width(), shown

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
    assert re.findall(r"#[0-9A-Fa-f]{6}\b", open(name, encoding='utf-8').read()) == []

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
    assert str(screen.hint.cget('foreground')) == colours.MUTED_FG

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
