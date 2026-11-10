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
import colours
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

# layout tests measure widgets against the real window, so the screen must hold the smallest window the app supports
# (CI runners have a 1024x768 display, where the window manager squeezes every window)
def skip_if_screen_too_small(root):
    if any(have < need for have, need in zip(root.wm_maxsize(), MIN_WINDOW, strict=True)):
        pytest.skip(f"screen {root.wm_maxsize()} is smaller than the {MIN_WINDOW} window the app supports")

def check_screen(root, conn):
    screen = CheckScreen(root, conn, 'carl', open_editor=lambda r=None: None, open_editors=lambda: None)
    screen.search_var.set('A120')
    screen.search()
    root.update()
    return screen

# at the size the screen opens, nothing is cut off, including with a long building name on the room card
def test_check_screen_fits_its_window(root, conn):
    skip_if_screen_too_small(root)
    check_screen(root, conn)
    assert root.winfo_reqwidth() <= root.winfo_width()
    assert root.winfo_reqheight() <= root.winfo_height()

def test_check_screen_shows_every_button(root, conn):
    skip_if_screen_too_small(root)
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
    skip_if_screen_too_small(root)
    screen = editor_screen(root, conn)
    screen.status_var.set("written")
    root.update()
    status = [w for w in all_widgets(root) if isinstance(w, ttk.Label) and str(w.cget('textvariable')) == str(screen.status_var)]
    assert len(status) == 1 and is_inside_window(status[0], root)
    assert [b.cget('text') for b in buttons(root) if not is_inside_window(b, root)] == []

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
