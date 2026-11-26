import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import ttk
import colours as c

# widgets and helpers shared by the check screen and the editor screen
FONTS = {'title': 'AppTitleFont', 'subtitle': 'AppSubtitleFont', 'strong': 'AppStrongFont', 'section': 'AppSectionFont',
         'large': 'AppLargeFont', 'caption': 'AppCaptionFont'}

def open_path(path):
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])

BUTTON_PADDING, BUTTON_PRESSED, FIELD_PADDING = (12, 4, 12, 4), (12, 5, 12, 3), (6, 4)

# every size is a step from the body size (pixels, negative like Tk's own), so a larger platform font grows them all together
# and a bigger body never ends up under a "large" one. at the Windows font (-17): caption -14, section title -15, card
# values -20, subtitle -22, title -28
TYPE_STEPS = {'AppCaptionFont': (-3, 'normal'), 'AppSectionFont': (-2, 'bold'), 'AppStrongFont': (0, 'bold'),
              'AppLargeFont': (3, 'normal'), 'AppSubtitleFont': (5, 'bold'), 'AppTitleFont': (11, 'bold')}
LEAST_BODY = 14

# the platform's own default font size, in pixels. never smaller than the 14 px the app has always used. read as configured:
# 'font actual' reports a size in whole points on Windows, so -14 px would come back as 11 pt and turn into 15 px
def platform_body(root):
    size = int(root.tk.call('font', 'configure', 'TkDefaultFont', '-size'))
    pixels = -size if size < 0 else round(size * root.winfo_fpixels('1p'))
    return max(pixels, LEAST_BODY)

def set_type_scale(root, body):
    family = root.tk.call('font', 'actual', 'TkDefaultFont', '-family')
    for name in ['TkDefaultFont', 'TkTextFont', 'TkHeadingFont', 'TkMenuFont']:
        root.tk.call('font', 'configure', name, '-family', family, '-size', -body)
    existing = root.tk.splitlist(root.tk.call('font', 'names'))
    for name, (step, weight) in TYPE_STEPS.items():
        action = 'configure' if name in existing else 'create'
        root.tk.call('font', action, name, '-family', family, '-size', -(body + step), '-weight', weight)

# flat look built on Tk's clam theme: fills and lines, no images in the theme itself. image-based themes (we tried Sun
# Valley) redraw far too slowly: 167 ms per keystroke on a Mac, against 17 ms here. the only images are the four 12 px
# status marks (colours.py), drawn once. sizes in pixels (negative), same on every screen
def use_theme(root):
    set_type_scale(root, platform_body(root))
    row_height = int(root.tk.call('font', 'metrics', 'TkDefaultFont', '-linespace')) + 6

    style = ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=c.GROUND)
    root.option_add('*Toplevel.background', c.GROUND)
    root.option_add('*Label.background', c.GROUND)
    root.option_add('*TCombobox*Listbox.background', c.SURFACE)
    root.option_add('*TCombobox*Listbox.foreground', c.TEXT_FG)
    root.option_add('*TCombobox*Listbox.selectBackground', c.SELECTED)
    root.option_add('*TCombobox*Listbox.selectForeground', c.TEXT_FG)
    root.option_add('*TCombobox*Listbox.font', 'TkDefaultFont')
    root.option_add('*TCombobox*Listbox.relief', 'flat')

    style.configure('.', background=c.GROUND, foreground=c.TEXT_FG, bordercolor=c.BORDER, lightcolor=c.GROUND, darkcolor=c.GROUND,
                    troughcolor=c.GROUND, focuscolor=c.ACCENT, selectbackground=c.SELECTED, selectforeground=c.TEXT_FG,
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
                        arrowcolor=c.MUTED, arrowsize=14, background=c.SURFACE, relief='flat', borderwidth=0)
        style.map(field, bordercolor=[('focus', c.ACCENT)], lightcolor=[('focus', c.ACCENT)], darkcolor=[('focus', c.ACCENT)],
                  fieldbackground=[('readonly', c.SURFACE)], selectbackground=[('readonly', c.SURFACE)],
                  selectforeground=[('readonly', c.TEXT_FG)], background=[('readonly', c.SURFACE)],
                  arrowcolor=[('active', c.TEXT_FG)])

    # tables -> quiet headings, no lines between rows, the picked row in pale blue. every table is flat, so a row's first
    # column holds only its status mark, centred, with no tree indicator beside it
    style.configure('Treeview', background=c.SURFACE, fieldbackground=c.SURFACE, rowheight=row_height, bordercolor=c.BORDER,
                    lightcolor=c.SURFACE, darkcolor=c.SURFACE)
    style.map('Treeview', background=[('selected', c.SELECTED)], foreground=[('selected', c.TEXT_FG)])
    style.layout('Item', [('Treeitem.padding', {'sticky': 'nswe', 'children': [('Treeitem.image', {'sticky': ''})]})])
    style.configure('Treeview.Heading', background=c.SURFACE, foreground=c.MUTED, relief='flat', padding=(3, 3),
                    lightcolor=c.SURFACE, darkcolor=c.SURFACE, bordercolor=c.SURFACE)
    style.map('Treeview.Heading', background=[('active', c.HOVER)], lightcolor=[('active', c.HOVER)], darkcolor=[('active', c.HOVER)])

    # cards -> white on the ground with a 1 px line, a section title above each one in small bold muted type (card_section).
    # a frame that only lays out a card's contents is white with no line of its own. (clam draws a border as two lines:
    # 'raised' paints the inner one in lightcolor and darkcolor, white here, where 'solid' would make the line 2 px)
    style.configure('Card.TFrame', background=c.SURFACE, bordercolor=c.CARD_BORDER, lightcolor=c.SURFACE,
                    darkcolor=c.SURFACE, relief='raised', borderwidth=1)
    style.configure('Inner.Card.TFrame', relief='flat', borderwidth=0)
    style.configure('Card.TLabel', background=c.SURFACE)
    style.configure('Section.TLabel', font='AppSectionFont', foreground=c.MUTED)

    # tool buttons -> flat until the pointer is over them, no border, the same height as a button. primary actions keep Accent.TButton
    style.layout('Toolbutton', [('Toolbutton.border', {'sticky': 'nswe', 'border': '1', 'children': [
        ('Toolbutton.padding', {'sticky': 'nswe', 'children': [('Toolbutton.label', {'sticky': 'nswe'})]})]})])
    style.configure('Toolbutton', background=c.GROUND, bordercolor=c.GROUND, lightcolor=c.GROUND, darkcolor=c.GROUND,
                    relief='flat', padding=BUTTON_PADDING)
    style.map('Toolbutton', background=[('pressed', c.PRESSED), ('active', c.HOVER)], bordercolor=[('focus', c.ACCENT)],
              lightcolor=[('pressed', c.PRESSED), ('active', c.HOVER)], darkcolor=[('pressed', c.PRESSED), ('active', c.HOVER)],
              padding=[('pressed', BUTTON_PRESSED)])
    style.configure('TSeparator', background=c.CARD_BORDER)

    # tabs -> flat, the picked one in white like the card under it, the others on the ground in muted type
    style.configure('TNotebook', background=c.GROUND, bordercolor=c.CARD_BORDER, lightcolor=c.GROUND, darkcolor=c.GROUND,
                    tabmargins=(0, 0, 0, 0), borderwidth=1)
    style.configure('TNotebook.Tab', background=c.GROUND, foreground=c.MUTED, bordercolor=c.GROUND, lightcolor=c.GROUND,
                    darkcolor=c.GROUND, padding=(14, 6))
    style.map('TNotebook.Tab', background=[('selected', c.SURFACE), ('active', c.HOVER)], foreground=[('selected', c.TEXT_FG)],
              bordercolor=[('selected', c.CARD_BORDER)], lightcolor=[('selected', c.SURFACE)], darkcolor=[('selected', c.SURFACE)],
              padding=[('selected', (14, 6))])

    # scrollbars -> just the thumb
    for bar, name, stick in [('Vertical.TScrollbar', 'Vertical', 'ns'), ('Horizontal.TScrollbar', 'Horizontal', 'we')]:
        style.layout(bar, [(f'{name}.Scrollbar.trough', {'sticky': stick, 'children': [
            (f'{name}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure(bar, background=c.PRESSED, troughcolor=c.GROUND, bordercolor=c.GROUND, lightcolor=c.PRESSED, darkcolor=c.PRESSED,
                        arrowsize=10, gripcount=0)
        style.map(bar, background=[('active', c.CONTROL_BORDER)], lightcolor=[('active', c.CONTROL_BORDER)],
                  darkcolor=[('active', c.CONTROL_BORDER)])
    style.configure('Sash', sashthickness=6, gripcount=0)

# the part of the screen a window can use -> (left, top, width, height) without the taskbar, which can sit on any edge.
# on Windows that is the work area of the monitor the window is on (the main monitor for a window not shown yet);
# elsewhere the whole screen. the app is not DPI-aware, so these are the pixels the app itself sees
def work_area(window):
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT),
                        ('dwFlags', wintypes.DWORD)]

        user32 = ctypes.WinDLL('user32')
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        monitor = user32.MonitorFromWindow(int(window.wm_frame(), 16), 1)                     # MONITOR_DEFAULTTOPRIMARY
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.rcWork
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight()

# room a window's own frame takes (title bar, borders) that the geometry does not count, kept off the work area
FRAME = (16, 48)

# a platform font can make the widgets ask for more than the size they were laid out at -> grow to fit them, and keep
# spare_height on top for a line that can wrap longer later. neither the opening size nor the smallest size goes past
# the usable screen: a window bigger than that has its bottom under the taskbar, so the smallest size gives way (the
# screens wrap and scroll what no longer fits) and the window can still be dragged bigger. a window opens at the size it
# is laid out at when the usable screen has room for it, and shrinks to the usable screen when it has not. the system places a new
# window down and to the right of the last one, so a window that would reach past the usable screen there moves back in.
# a window not shown yet (withdrawn) has no place until the system picks one, so it opens in the middle of the usable screen
def fit_window(root, size, minimum, spare_height=0):
    root.update_idletasks()
    need = (root.winfo_reqwidth(), root.winfo_reqheight() + spare_height)
    left, top, *area = work_area(root)
    usable = tuple(max(a - f, 1) for a, f in zip(area, FRAME, strict=True))
    smallest = tuple(min(max(m, n), u) for m, n, u in zip(minimum, need, usable, strict=True))
    root.minsize(*smallest)
    opened = tuple(min(max(s, m), u) for s, m, u in zip(size, smallest, usable, strict=True))
    shown = root.winfo_ismapped()
    placed = ((root.winfo_x(), root.winfo_y()) if shown else
              tuple(o + (u - w) // 2 for o, u, w in zip((left, top), usable, opened, strict=True)))
    inside = tuple(min(max(p, o), o + u - w) for p, o, u, w in zip(placed, (left, top), usable, opened, strict=True))
    root.geometry('{}x{}'.format(*opened) + ('' if shown and inside == placed else '+{}+{}'.format(*inside)))

# a table cell -> its text in the table's real font, and a little room either side
CELL_PADDING = 8

# a whole table -> every column at least as wide as its heading and its values in the table's real font, and never
# narrower than its least width. columns: [(key, least width)]. a heading needs its text and the theme's heading border
# and padding round it, measured off a label drawn in the heading style. refit after every fill: a column only grows, so
# a column the user widened stays wide. the user can narrow a column down to its heading, but a column that stretches
# with the table keeps every value, or the table would squeeze it. always: {key: texts} a column holds while empty too.
# held: {key: texts} the columns hold now, from a caller that has just filled the table; without it every cell is read
# back from the table, which is slow on a long one
def fit_columns(tree, columns, always=None, held=None):
    cell_font = ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont'
    heading = ttk.Label(tree, style='Treeview.Heading')
    items = tree.get_children()
    for key, least in columns:
        heading.configure(text=tree.heading(key, 'text'))
        head = heading.winfo_reqwidth()
        texts = held[key] if held is not None else {str(tree.set(item, key)) for item in items}
        texts = texts | set((always or {}).get(key, ()))
        fitted = max([least, head] + [int(tree.tk.call('font', 'measure', cell_font, text)) + CELL_PADDING for text in texts])
        stretch = tree.tk.getboolean(tree.column(key, 'stretch'))
        tree.column(key, width=max(int(tree.column(key, 'width')), fitted), minwidth=fitted if stretch else head)
    heading.destroy()

HOVER_TAG = 'hover'

# the row under the pointer is highlighted: one tag moves with it, at once, and comes off when the pointer leaves or the
# wheel scrolls the rows away. of two tags that set the same option Tk takes the one made first, so the tag is made at
# the first highlight, after every tag the table was built with: a status tint wins over it, as does the picked row
def hover_rows(tree):
    lit, made = '', False

    def light(row):
        nonlocal lit, made
        if lit and tree.exists(lit):                  # a refill may have taken the row away, or reused its id
            if lit == row and tree.tag_has(HOVER_TAG, row):
                return
            tree.tk.call(tree, 'tag', 'remove', HOVER_TAG, (lit,))
        if row:
            if not made:
                tree.tag_configure(HOVER_TAG, background=c.HOVER)
                made = True
            tree.tk.call(tree, 'tag', 'add', HOVER_TAG, (row,))      # a tuple: an id with spaces is one row
        lit = row

    tree.bind('<Motion>', lambda e: light(tree.identify_row(e.y)), add='+')
    for sequence in ('<Leave>', '<MouseWheel>'):
        tree.bind(sequence, lambda e: light(''), add='+')

FADE_MS = 160

# a row whose status just changed fades from a stronger step of its colour to its own look, so the eye finds it. make it
# before the table's status tags (colours.colour_tags): the tag made first wins, and the fade covers the row's tint
class RowFade:
    def __init__(self, tree):
        self.tree, self.waiting = tree, {}               # row -> its next step's after() id
        for colour in c.FADE_FROM:
            for tag, shade in zip(self.tags(colour), c.fade_shades(colour), strict=True):
                tree.tag_configure(tag, background=shade)
        tree.bind('<Destroy>', lambda e: self.cancel(), add='+')

    @staticmethod
    def tags(colour):
        return [f'fade{step}-{colour}' for step in range(c.FADE_STEPS)]

    def start(self, row, colour):
        self.step(row, '', self.tags(colour))

    # the step shown comes off, the next goes on. after the last, the row is left with its own tags
    def step(self, row, shown, ahead):
        if shown:
            self.tree.tk.call(self.tree, 'tag', 'remove', shown, (row,))
        if not ahead:
            del self.waiting[row]
            return
        self.tree.tk.call(self.tree, 'tag', 'add', ahead[0], (row,))
        self.waiting[row] = self.tree.after(FADE_MS // c.FADE_STEPS, self.step, row, ahead[0], ahead[1:])

    # before the rows are filled again, and when the table closes
    def cancel(self):
        for job in self.waiting.values():
            self.tree.after_cancel(job)
        self.waiting.clear()

# a scrollbar that comes and goes -> the widget's xscrollcommand (or yscrollcommand): the bar shows only while there is
# more to see that way, so an unneeded sideways bar takes no height. the bar must be gridded, so grid() puts it back
def sideways_bar(bar):
    def scroll_sideways(first, last):
        if float(first) <= 0 and float(last) >= 1:
            bar.grid_remove()
        else:
            bar.grid()
        bar.set(first, last)
    return scroll_sideways

ELLIPSIS = '…'

# a text -> itself when it measures within width, else its start with an ellipsis, as long as still fits. keep: the
# words the text ends with that are never cut (a floor after its building's name), shown whole after the ellipsis
def cut_to_width(measure, text, width, keep=''):
    if measure(text) <= width:
        return text
    body = text[:len(text) - len(keep)]
    if not body.strip():
        return text
    end = ELLIPSIS + (' ' + keep if keep else '')
    low, high = 0, len(body)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(body[:mid].rstrip() + end) <= width:
            low = mid
        else:
            high = mid - 1
    return body[:low].rstrip() + end

# a table whose descriptive columns (status, flags, building, notes ...) share the width the short columns leave over, and
# show a cut text with an ellipsis; resting the pointer on a cut cell shows its full text. the short columns (numbers, ids,
# dates) are fitted to their values by fit_columns and never cut. so the table never needs a sideways bar unless the short
# columns and the headings alone are wider than the window
class LongTextColumns:
    def __init__(self, tree, columns, long_keys):
        self.tree = tree
        self.long = [key for key, _ in columns if key in long_keys]
        self.short = [(key, least) for key, least in columns if key not in long_keys]
        self.font = ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont'
        # per row, the long columns' whole texts and the ones the table shows; the width in pixels of each text measured
        # since the last fill, so dragging the window's edge doesn't ask Tk for them again
        self.full, self.shown, self.measured = {}, {}, {}
        self.ends, self.shown_width = {}, None
        self.tip, self.tip_label, self.tip_text, self.tip_cell = None, None, None, None
        tree.bind('<Configure>', lambda e: self.layout(on_resize=True), add='+')
        tree.bind('<Motion>', self.point_at, add='+')
        for sequence in ('<Leave>', '<ButtonPress>', '<MouseWheel>', '<KeyPress>'):
            tree.bind(sequence, self.hide_tip, add='+')

    # after every fill: the rows hold their full texts. rows: {item: the values it was just inserted with, one per
    # column} -> a long table is filled without reading it back; without rows the cells are read from the table.
    # ends: {item: {key: the words its text ends with, never cut}}
    def refit(self, ends=None, rows=None):
        tree = self.tree
        columns = tree['columns']
        if rows is None:
            rows = {item: [tree.set(item, key) for key in columns] for item in tree.get_children()}
        texts = {item: dict(zip(columns, map(str, values), strict=True)) for item, values in rows.items()}   # as Tk shows them
        self.full = {item: {key: row[key] for key in self.long} for item, row in texts.items()}
        self.shown = {item: dict(row) for item, row in self.full.items()}
        self.measured = {}
        self.ends = ends or {}
        fit_columns(tree, self.short, held={key: {row[key] for row in texts.values()} for key, _ in self.short})
        self.layout()

    def measure(self, text):
        return int(self.tree.tk.call('font', 'measure', self.font, text))

    # a whole text's width is measured once per fill; the trial cuts of a text are not kept
    def width_of(self, text):
        return self.measured[text] if text in self.measured else self.measure(text)

    # the width the columns share is the table's: a change of height alone leaves them as they are
    def layout(self, on_resize=False):
        tree = self.tree
        if tree.winfo_width() <= 1 or (on_resize and tree.winfo_width() == self.shown_width):
            return                                       # not drawn yet: its first <Configure> comes with the real width
        self.shown_width = tree.winfo_width()
        taken = sum(int(tree.column(key, 'width')) for key in ['#0', *tree['columns']] if key not in self.long)
        heading = ttk.Label(tree, style='Treeview.Heading')
        head = {}
        for key in self.long:
            heading.configure(text=tree.heading(key, 'text'))
            head[key] = heading.winfo_reqwidth()
        heading.destroy()
        measured = self.measured
        for key in self.long:
            for texts in self.full.values():
                if texts[key] not in measured:
                    measured[texts[key]] = self.measure(texts[key])
        natural = {key: max([head[key]] + [measured[t[key]] + CELL_PADDING for t in self.full.values()]) for key in self.long}
        # the longest texts give way first: every column up to one common width, as wide as the room allows, never under its
        # heading and never past what its longest text needs
        room = tree.winfo_width() - 4 - taken
        low, high = 0, max(natural.values(), default=0)
        while low < high:
            cap = (low + high + 1) // 2
            if sum(max(head[key], min(natural[key], cap)) for key in self.long) <= room:
                low = cap
            else:
                high = cap - 1
        rooms = {}
        for key in self.long:
            width = max(head[key], min(natural[key], low))
            tree.column(key, width=width, minwidth=head[key])
            rooms[key] = width - CELL_PADDING
        cut = {}
        for item, texts in self.full.items():
            for key in self.long:
                text, keep = texts[key], self.ends.get(item, {}).get(key, '')
                if measured[text] <= rooms[key]:
                    shown = text
                elif (text, keep, rooms[key]) in cut:
                    shown = cut[text, keep, rooms[key]]
                else:
                    shown = cut[text, keep, rooms[key]] = cut_to_width(self.width_of, text, rooms[key], keep)
                if self.shown[item][key] != shown:
                    tree.set(item, key, shown)
                    self.shown[item][key] = shown

    # the pointer rests on a cell whose text was cut -> a small window with the whole text beside it
    def point_at(self, event):
        tree = self.tree
        item, column = tree.identify_row(event.y), tree.identify_column(event.x)
        keys = [None, *tree['columns']]
        key = keys[int(column[1:])] if column.startswith('#') and int(column[1:]) < len(keys) else None
        if item not in self.full or key not in self.long or self.full[item][key] == tree.set(item, key):
            self.hide_tip()
            return
        if self.tip_cell != (item, key):
            self.hide_tip()
            self.show_tip(self.full[item][key], event.x_root, event.y_root)
            self.tip_cell = (item, key)

    def show_tip(self, text, x, y):
        self.tip = tk.Toplevel(self.tree)
        self.tip.withdraw()
        self.tip.wm_overrideredirect(True)
        self.tip.configure(background=c.CONTROL_BORDER)
        self.tip_label = ttk.Label(self.tip, text=text, background=c.SURFACE, padding=(8, 4), wraplength=600)
        self.tip_label.pack(padx=1, pady=1)
        self.tip.update_idletasks()
        width, height = self.tip.winfo_reqwidth(), self.tip.winfo_reqheight()
        window = self.tree.winfo_toplevel()
        right, bottom = window.winfo_rootx() + window.winfo_width(), window.winfo_rooty() + window.winfo_height()
        left = max(window.winfo_rootx(), min(x + 12, right - width))
        top = y + 18 if y + 18 + height <= bottom else max(window.winfo_rooty(), y - 6 - height)
        self.tip.wm_geometry(f'+{left}+{top}')
        self.tip.deiconify()
        self.tip_text = text

    def hide_tip(self, event=None):
        if self.tip is not None:
            self.tip.destroy()
        self.tip, self.tip_label, self.tip_text, self.tip_cell = None, None, None, None

# a dialog -> as big as what it holds asks for, never past the usable screen (fit_window). again whenever what it holds
# changes: an open dialog only grows, so it never jumps smaller under the person typing in it
def fit_dialog(window):
    size = (window.winfo_width(), window.winfo_height()) if window.winfo_ismapped() else (0, 0)
    fit_window(window, size, (0, 0))

# the widest a preview's words and statuses get before they wrap, so the dialog stays well inside a small screen
PREVIEW_WRAP, STATUS_WRAP = 580, 360

# a save preview -> a small white table: a status mark, what changes, the status. it asks for the size of its rows; given
# less height (a long preview on a small screen) it scrolls
class PreviewTable(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style='Card.TFrame', padding=2)
        self.canvas = tk.Canvas(self, background=c.SURFACE, highlightthickness=0, borderwidth=0, width=1, height=1)
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sideways_bar(self.bar))
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.bar.grid(row=0, column=1, sticky='ns')
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.body = ttk.Frame(self.canvas, style='Inner.Card.TFrame')
        self.body.columnconfigure(1, weight=1)
        window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(window, width=e.width))

    # rows, top to bottom: a text -> a line across the table; (colour, text, status) -> a row with the status mark, tinted
    # where someone has to act; (colour, text, None) -> a line under that row, on the same tint
    def show(self, rows):
        for old in self.body.winfo_children():
            old.destroy()
        shapes = c.marks(self)
        gap = (c.MARK_COLUMN - c.MARK_SIZE) // 2
        columns, across, height = [0, 0, 0], 0, 0              # the size the rows ask for
        for i, row in enumerate(rows):
            cells = []                                        # (label, first column, columns it spans)
            if isinstance(row, str):
                cells.append((ttk.Label(self.body, text=row, style='Card.TLabel', padding=(8, 1), justify='left',
                                        wraplength=PREVIEW_WRAP + STATUS_WRAP), 0, 3))
            else:
                colour, text, status = row
                background, foreground = c.row_look(colour)
                look = {'background': background, 'foreground': foreground, 'padding': (8, 1), 'justify': 'left', 'anchor': 'nw'}
                words = ttk.Label(self.body, text=text, wraplength=PREVIEW_WRAP, **look)
                if status is None:
                    cells += [(ttk.Label(self.body, background=background), 0, 1), (words, 1, 2)]
                else:
                    # the mark sits level with the row's first line, in a column as wide as a table's mark column
                    mark = ttk.Label(self.body, image=shapes.get(colour, ''), background=background, anchor='n',
                                     padding=(gap, 6, gap, 0))
                    cells += [(mark, 0, 1), (words, 1, 1),
                              (ttk.Label(self.body, text=status, wraplength=STATUS_WRAP, **look), 2, 1)]
            for label, column, span in cells:
                label.grid(row=i, column=column, columnspan=span, sticky='nsew')
                if span == 1:
                    columns[column] = max(columns[column], label.winfo_reqwidth())
            across = max([across] + [sum(columns[:column]) + label.winfo_reqwidth() for label, column, span in cells if span > 1])
            height += max(label.winfo_reqheight() for label, _, _ in cells)
        # added up from the labels, which know their size at once: an update here would draw the dialog half built
        width = max(sum(columns), across)
        line = int(self.tk.call('font', 'metrics', 'TkDefaultFont', '-linespace'))
        # room for the scrollbar on top of the rows' own width: the rows fill it while there is no bar, and a bar takes it
        # without cutting a row's end
        self.canvas.configure(width=width + self.bar.winfo_reqwidth(), height=height, scrollregion=(0, 0, width, height),
                              yscrollincrement=line)

    # the mouse wheel anywhere in the dialog -> the rows scroll, when there is more of them than shows
    def wheel(self, event):
        if event.delta and self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

# a section of a screen -> its title above a card. returns the card to fill; its .master holds both, and is what to place
def card_section(parent, title, padding):
    section = ttk.Frame(parent)
    ttk.Label(section, text=title, style='Section.TLabel').pack(anchor='w')
    card = ttk.Frame(section, style='Card.TFrame', padding=padding)
    card.pack(fill='both', expand=True)
    return card

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
# separators=True draws a thin vertical line in the gap between two groups on the same line
class FlowRow(ttk.Frame):
    def __init__(self, parent, gap, separators=False):
        super().__init__(parent)
        self.gap, self.groups, self.separators, self.lines = gap, [], separators, []
        self.bind('<Configure>', lambda e: self.flow(e.width))

    # the next group, for the caller to fill
    def group(self):
        if not self.groups:
            self.after_idle(self.ask)
        self.groups.append(ttk.Frame(self))
        if self.separators and len(self.groups) > 1:
            self.lines.append(ttk.Separator(self, orient='vertical'))       # lines[i] sits before groups[i + 1]
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
            for i, g in enumerate(row):
                if self.lines and self.groups.index(g):
                    line = self.lines[self.groups.index(g) - 1]
                    if i:
                        line.place(x=x - self.gap // 2, y=y + 2, height=height - 4)
                    else:
                        line.place_forget()                 # a line never starts a row
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
            'note': 'Note', 'zone_override': 'Zone', 'wing': 'Wing', 'exit_id': 'Exit', 'exit_type': 'Type', 'clear_width_cm': 'Door (cm)',
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
