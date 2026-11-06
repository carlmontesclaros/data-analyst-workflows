import re
import sqlite3
import tkinter as tk
from tkinter import ttk
import pandas as pd
import pytest
import app
import capacity_db as db
import colours
import excel_inputs as xi
import widgets
from check_screen import CheckScreen, rooms_found_text
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
    screen = CheckScreen(root, conn, 'carl', True, open_editor=lambda r=None: None, open_editors=lambda: None)
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
