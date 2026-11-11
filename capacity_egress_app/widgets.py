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

BUTTON_PADDING, BUTTON_PRESSED, FIELD_PADDING = (12, 4, 12, 4), (12, 5, 12, 3), (6, 4)

# flat look built on Tk's clam theme: fills and lines, no images. image-based themes (we tried Sun Valley)
# redraw far too slowly: 167 ms per keystroke on a Mac, against 17 ms here. sizes in pixels (negative), same on every screen
def use_theme(root):
    family = root.tk.call('font', 'actual', 'TkDefaultFont', '-family')
    for name in ['TkDefaultFont', 'TkTextFont', 'TkHeadingFont', 'TkMenuFont']:
        root.tk.call('font', 'configure', name, '-family', family, '-size', -14)
    for name, size, weight in [('AppTitleFont', -24, 'bold'), ('AppSubtitleFont', -18, 'bold'), ('AppStrongFont', -14, 'bold'),
                               ('AppLargeFont', -16, 'normal'), ('AppCaptionFont', -12, 'normal')]:
        root.tk.call('font', 'create', name, '-family', family, '-size', size, '-weight', weight)
    row_height = int(root.tk.call('font', 'metrics', 'TkDefaultFont', '-linespace')) + 6

    style = ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=c.BG)
    root.option_add('*Toplevel.background', c.BG)
    root.option_add('*Label.background', c.BG)
    root.option_add('*TCombobox*Listbox.background', c.SURFACE)
    root.option_add('*TCombobox*Listbox.foreground', c.TEXT_FG)
    root.option_add('*TCombobox*Listbox.selectBackground', c.SELECTED)
    root.option_add('*TCombobox*Listbox.selectForeground', c.TEXT_FG)
    root.option_add('*TCombobox*Listbox.font', 'TkDefaultFont')
    root.option_add('*TCombobox*Listbox.relief', 'flat')

    style.configure('.', background=c.BG, foreground=c.TEXT_FG, bordercolor=c.BORDER, lightcolor=c.BG, darkcolor=c.BG,
                    troughcolor=c.BG, focuscolor=c.ACCENT, selectbackground=c.SELECTED, selectforeground=c.TEXT_FG,
                    fieldbackground=c.SURFACE, insertcolor=c.TEXT_FG, font='TkDefaultFont')
    style.configure('TLabelframe.Label', font='AppStrongFont')

    # buttons -> one height with the fields. pressed: the label moves down 1 px. no dashed box, focus is a blue border
    style.layout('TButton', [('Button.border', {'sticky': 'nswe', 'border': '1', 'children': [
        ('Button.padding', {'sticky': 'nswe', 'children': [('Button.label', {'sticky': 'nswe'})]})]})])
    style.configure('TButton', background=c.SURFACE, bordercolor=c.CONTROL_BORDER, lightcolor=c.SURFACE, darkcolor=c.SURFACE,
                    padding=BUTTON_PADDING, width=-1)
    style.map('TButton', background=[('pressed', c.PRESSED), ('active', c.HOVER)], bordercolor=[('focus', c.ACCENT)],
              lightcolor=[('pressed', c.PRESSED), ('active', c.HOVER)], darkcolor=[('pressed', c.PRESSED), ('active', c.HOVER)],
              padding=[('pressed', BUTTON_PRESSED)])
    style.configure('Accent.TButton', background=c.ACCENT, foreground=c.SURFACE, bordercolor=c.ACCENT, lightcolor=c.ACCENT,
                    darkcolor=c.ACCENT)
    style.map('Accent.TButton', background=[('pressed', c.ACCENT_PRESSED), ('active', c.ACCENT_HOVER)],
              bordercolor=[('focus', c.ACCENT_PRESSED)], lightcolor=[('pressed', c.ACCENT_PRESSED), ('active', c.ACCENT_HOVER)],
              darkcolor=[('pressed', c.ACCENT_PRESSED), ('active', c.ACCENT_HOVER)], padding=[('pressed', BUTTON_PRESSED)])

    # fields -> a focused one gets a 2 px blue ring. the dropdown arrow sits inside the field, not in its own box
    if 'Flat.downarrow' not in style.element_names():
        style.element_create('Flat.downarrow', 'from', 'default', 'downarrow')
    # (Entry.field draws all 4 edges, clam's Combobox.field leaves the right one open. a 'border' here hides the arrow)
    style.layout('TCombobox', [('Entry.field', {'sticky': 'nswe', 'children': [
        ('Flat.downarrow', {'side': 'right', 'sticky': 'ns'}),
        ('Combobox.padding', {'sticky': 'nswe', 'children': [('Combobox.textarea', {'sticky': 'nswe'})]})]})])
    for field in ['TEntry', 'TCombobox']:
        style.configure(field, bordercolor=c.CONTROL_BORDER, lightcolor=c.SURFACE, darkcolor=c.SURFACE, padding=FIELD_PADDING,
                        arrowcolor=c.MUTED_FG, arrowsize=14, background=c.SURFACE, relief='flat', borderwidth=0)
        style.map(field, bordercolor=[('focus', c.ACCENT)], lightcolor=[('focus', c.ACCENT)], darkcolor=[('focus', c.ACCENT)],
                  fieldbackground=[('readonly', c.SURFACE)], selectbackground=[('readonly', c.SURFACE)],
                  selectforeground=[('readonly', c.TEXT_FG)], background=[('readonly', c.SURFACE)],
                  arrowcolor=[('active', c.TEXT_FG)])

    # tables -> quiet headings, no lines between rows, the picked row in pale blue
    style.configure('Treeview', background=c.SURFACE, fieldbackground=c.SURFACE, rowheight=row_height, bordercolor=c.BORDER,
                    lightcolor=c.SURFACE, darkcolor=c.SURFACE)
    style.map('Treeview', background=[('selected', c.SELECTED)], foreground=[('selected', c.TEXT_FG)])
    style.configure('Treeview.Heading', background=c.SURFACE, foreground=c.MUTED_FG, relief='flat', padding=(4, 3),
                    lightcolor=c.SURFACE, darkcolor=c.SURFACE, bordercolor=c.SURFACE)
    style.map('Treeview.Heading', background=[('active', c.HOVER)], lightcolor=[('active', c.HOVER)], darkcolor=[('active', c.HOVER)])

    # scrollbars -> just the thumb
    for bar, name, stick in [('Vertical.TScrollbar', 'Vertical', 'ns'), ('Horizontal.TScrollbar', 'Horizontal', 'we')]:
        style.layout(bar, [(f'{name}.Scrollbar.trough', {'sticky': stick, 'children': [
            (f'{name}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure(bar, background=c.PRESSED, troughcolor=c.BG, bordercolor=c.BG, lightcolor=c.PRESSED, darkcolor=c.PRESSED,
                        arrowsize=10, gripcount=0)
        style.map(bar, background=[('active', c.CONTROL_BORDER)], lightcolor=[('active', c.CONTROL_BORDER)],
                  darkcolor=[('active', c.CONTROL_BORDER)])
    style.configure('Sash', sashthickness=6, gripcount=0)

# a platform font can make the widgets ask for more than the size they were laid out at -> grow to fit them
def fit_window(root, size, minimum):
    root.update_idletasks()
    need = (root.winfo_reqwidth(), root.winfo_reqheight())
    root.minsize(*(max(m, n) for m, n in zip(minimum, need, strict=True)))
    root.geometry('{}x{}'.format(*(max(s, n) for s, n in zip(size, need, strict=True))))

# a table column whose words must never be cut short -> at least as wide as its longest text in the table's real font
CELL_PADDING = 8                                                        # the theme's space around a cell's text, and a little more
def fit_column(tree, col, texts):
    font = ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont'
    need = max(int(tree.tk.call('font', 'measure', font, text)) for text in texts) + CELL_PADDING
    width = max(int(tree.column(col, 'minwidth')), need)
    tree.column(col, width=width, minwidth=width)

# a line that can outgrow its window (an export path, an error) wraps onto the next line instead of being cut off
# the label must be packed or gridded to fill the width it is given. its text gets that width less the label's own
# padding and the theme's border, measured off an empty label of the same style and padding
def wrap_to_width(label):
    empty = ttk.Label(label.master, style=label.cget('style'), padding=label.cget('padding'))
    frame = empty.winfo_reqwidth()
    empty.destroy()
    label.bind('<Configure>', lambda e: label.configure(wraplength=max(e.width - frame, 1)), add='+')
    return label

# a line of groups (fields, buttons) that wraps onto more lines when the window is too narrow for one line.
# it asks only for its widest group's width, so it never holds the window wider than that; a group stays on one line
class FlowRow(ttk.Frame):
    def __init__(self, parent, gap):
        super().__init__(parent)
        self.gap, self.groups = gap, []
        self.bind('<Configure>', lambda e: self.flow(e.width))

    # the next group, for the caller to fill
    def group(self):
        if not self.groups:
            self.after_idle(self.ask)
        self.groups.append(ttk.Frame(self))
        return self.groups[-1]

    # once the groups are filled and have their sizes
    def ask(self):
        self.update_idletasks()
        self.flow(self.winfo_width())

    def flow(self, width):
        rows, x = [[]], 0
        for g in self.groups:
            if rows[-1] and x + self.gap + g.winfo_reqwidth() > width:
                rows.append([])
            x = (x + self.gap if rows[-1] else 0) + g.winfo_reqwidth()
            rows[-1].append(g)
        y = 0
        for row in rows:
            height, x = max(g.winfo_reqheight() for g in row), 0
            for g in row:
                g.place(x=x, y=y + (height - g.winfo_reqheight()) // 2)
                x += g.winfo_reqwidth() + self.gap
            y += height
        self.configure(width=max(g.winfo_reqwidth() for g in self.groups), height=y)

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
