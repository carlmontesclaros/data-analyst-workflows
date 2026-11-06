import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import ttk
import colours as c

# widgets and helpers shared by the check screen and the editor screen
FONTS = {'title': 'AppTitleFont', 'subtitle': 'AppSubtitleFont', 'strong': 'AppStrongFont',
         'large': 'AppLargeFont', 'caption': 'AppCaptionFont'}

def open_path(path):
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])

# flat look built on Tk's clam theme: fills and lines, no images. image-based themes (we tried Sun Valley)
# redraw far too slowly: 167 ms per keystroke on a Mac, against 17 ms here. sizes in pixels (negative), same on every screen
def use_theme(root):
    family = root.tk.call('font', 'actual', 'TkDefaultFont', '-family')
    for name in ['TkDefaultFont', 'TkTextFont', 'TkHeadingFont', 'TkMenuFont']:
        root.tk.call('font', 'configure', name, '-family', family, '-size', -14)
    for name, size, weight in [('AppTitleFont', -28, 'bold'), ('AppSubtitleFont', -20, 'bold'), ('AppStrongFont', -14, 'bold'),
                               ('AppLargeFont', -18, 'normal'), ('AppCaptionFont', -12, 'normal')]:
        root.tk.call('font', 'create', name, '-family', family, '-size', size, '-weight', weight)
    row_height = int(root.tk.call('font', 'metrics', 'TkDefaultFont', '-linespace')) + 4

    style = ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=c.BG)
    root.option_add('*Toplevel.background', c.BG)
    root.option_add('*Label.background', c.BG)
    root.option_add('*TCombobox*Listbox.background', c.SURFACE)
    root.option_add('*TCombobox*Listbox.foreground', c.TEXT_FG)
    root.option_add('*TCombobox*Listbox.selectBackground', c.SELECTED)
    root.option_add('*TCombobox*Listbox.selectForeground', c.TEXT_FG)

    style.configure('.', background=c.BG, foreground=c.TEXT_FG, bordercolor=c.BORDER, lightcolor=c.BG, darkcolor=c.BG,
                    troughcolor=c.BG, focuscolor=c.ACCENT, selectbackground=c.SELECTED, selectforeground=c.TEXT_FG,
                    fieldbackground=c.SURFACE, insertcolor=c.TEXT_FG, font='TkDefaultFont')
    style.configure('TLabelframe.Label', foreground=c.MUTED_FG)
    style.configure('TButton', background=c.SURFACE, bordercolor=c.CONTROL_BORDER, lightcolor=c.SURFACE, darkcolor=c.SURFACE,
                    padding=(10, 3), width=-1, focusthickness=1, focuscolor=c.CONTROL_BORDER)
    style.map('TButton', background=[('pressed', c.PRESSED), ('active', c.HOVER)],
              lightcolor=[('pressed', c.PRESSED), ('active', c.HOVER)], darkcolor=[('pressed', c.PRESSED), ('active', c.HOVER)])
    style.configure('Accent.TButton', background=c.ACCENT, foreground=c.SURFACE, bordercolor=c.ACCENT, lightcolor=c.ACCENT,
                    darkcolor=c.ACCENT, focuscolor=c.SURFACE)
    style.map('Accent.TButton', background=[('pressed', c.ACCENT_PRESSED), ('active', c.ACCENT_HOVER)],
              lightcolor=[('pressed', c.ACCENT_PRESSED), ('active', c.ACCENT_HOVER)],
              darkcolor=[('pressed', c.ACCENT_PRESSED), ('active', c.ACCENT_HOVER)])
    for field in ['TEntry', 'TCombobox']:
        style.configure(field, bordercolor=c.CONTROL_BORDER, lightcolor=c.SURFACE, darkcolor=c.SURFACE, padding=(6, 2),
                        arrowcolor=c.MUTED_FG, background=c.SURFACE)
        style.map(field, bordercolor=[('focus', c.ACCENT)], lightcolor=[('focus', c.ACCENT)],
                  fieldbackground=[('readonly', c.SURFACE)], selectbackground=[('readonly', c.SURFACE)],
                  selectforeground=[('readonly', c.TEXT_FG)], background=[('active', c.HOVER), ('readonly', c.SURFACE)])
    style.configure('Treeview', background=c.SURFACE, fieldbackground=c.SURFACE, rowheight=row_height, bordercolor=c.BORDER)
    style.map('Treeview', background=[('selected', c.SELECTED)], foreground=[('selected', c.TEXT_FG)])
    style.configure('Treeview.Heading', background=c.BG, foreground=c.MUTED_FG, relief='flat', padding=(4, 2),
                    lightcolor=c.BG, darkcolor=c.BG, bordercolor=c.BORDER)
    style.map('Treeview.Heading', background=[('active', c.HOVER)])
    for bar in ['Vertical.TScrollbar', 'Horizontal.TScrollbar']:
        style.configure(bar, background=c.PRESSED, troughcolor=c.BG, bordercolor=c.BG, lightcolor=c.PRESSED, darkcolor=c.PRESSED,
                        arrowcolor=c.MUTED_FG)
        style.map(bar, background=[('active', c.CONTROL_BORDER)])
    style.configure('Sash', sashthickness=6)

# search -> 'DTB A120', 'Turpin', 'A120'. words with a digit are room numbers, the rest name the building
def initials(name):
    return ''.join(word[0] for word in re.findall(r'[A-Za-z]+', name) if word[0].isupper()).lower()

# typing in the building box -> 'tur', 'dtb', 'comp sci'. names starting with the text come first
def match_buildings(names, text):
    words = text.lower().split()
    if not words:
        return list(names)
    hits = [p for p in names if all(w in p.lower() or w == initials(p) for w in words)]
    return sorted(hits, key=lambda p: not p.lower().startswith(text.lower().strip()))

NO_MATCH = "(no building matches)"

# table headings -> the words in GLOSSARY.md, never the database's column names
HEADINGS = {'floor': 'Floor', 'zone_wing': 'Wing', 'status': 'Status', 'total_load': 'Occupant load',
            'exit_capacity': 'Exit capacity', 'exit_count': 'Exits', 'rooms_counted': 'Rooms counted',
            'rooms_in_scope': 'Rooms in scope', 'link_inflow': 'From link door', 'flags': 'Flags',
            'property': 'Building', 'space': 'Room', 'sub_category': 'Sub-category', 'area_m2': 'Area (m²)',
            'room_type': 'Room type', 'per_code_load': 'Per code load', 'capacity': 'Room capacity',
            'capacity_source': 'Capacity source', 'load_used': 'Load used', 'in_scope': 'In scope', 'flag': 'Flag',
            'note': 'Note', 'wing': 'Wing', 'exit_id': 'Exit', 'exit_type': 'Type', 'clear_width_cm': 'Door (cm)',
            'stair_width_cm': 'Stair (cm)', 'persons': 'Persons', 'limited_by': 'Limited by',
            'counts_as_exit': 'Counts as exit', 'shares_stair': 'Shares stair', 'width_check': 'Width check',
            'into_wing': 'Into wing', 'measured_date': 'Measured', 'measured_by': 'Measured by', 'notes': 'Notes'}
# numbers line up on the right, so they can be compared down the column; headings sit over their values
NUMBER_COLUMNS = {'total_load', 'exit_capacity', 'exit_count', 'rooms_counted', 'rooms_in_scope', 'link_inflow', 'area_m2',
                  'per_code_load', 'capacity', 'load_used', 'clear_width_cm', 'stair_width_cm', 'persons',
                  'Proposed', 'Per code load', 'Exit capacity'}

def heading_for(key):
    return HEADINGS.get(key, key)

def heading_text(key):
    return heading_for(key) + ('  ' if key in NUMBER_COLUMNS else '')

def anchor_for(key):
    return 'e' if key in NUMBER_COLUMNS else 'w'

# building box you can type in -> the list narrows as you type, Down arrow opens it, Enter picks the top match
# used by the check screen and the editor screen
class BuildingBox:
    def __init__(self, parent, var, blank, on_pick, width):
        self.var, self.blank, self.on_pick = var, blank, on_pick
        self.names = []
        self.box = ttk.Combobox(parent, textvariable=var, width=width)
        self.box.bind('<<ComboboxSelected>>', lambda e: self.pick())
        self.box.bind('<KeyRelease>', self.narrow)
        self.box.bind('<Return>', lambda e: self.type_in())
        self.box.bind('<FocusIn>', lambda e: self.box.select_range(0, 'end'))

    def set_names(self, names):
        self.names = list(names)
        self.show_all()

    def show_all(self):
        self.box['values'] = ([self.blank] if self.blank else []) + self.names

    def narrow(self, event):
        if event.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
            return
        text = self.var.get()
        if text.strip() in ('', self.blank):
            self.show_all()
        else:
            self.box['values'] = match_buildings(self.names, text) or [NO_MATCH]

    def type_in(self):
        text = self.var.get().strip()
        exact = [p for p in self.names if p.lower() == text.lower()]
        hits = exact or match_buildings(self.names, text)
        if text in ('', self.blank):
            self.var.set(self.blank)
        elif hits:
            self.var.set(hits[0])
        else:
            self.box['values'] = [NO_MATCH]
            self.box.event_generate('<Down>')         # open the list so the no-match line shows
            return
        self.pick()

    def pick(self):
        if self.var.get() not in self.names:          # half-typed text or the no-match line -> nothing picked
            self.var.set(self.blank)
        self.show_all()
        self.box.icursor('end')
        self.on_pick()

    # the building picked, or None while the text is half typed
    def picked(self):
        return self.var.get() if self.var.get() in self.names else None
