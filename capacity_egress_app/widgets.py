import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import ttk

# widgets and helpers shared by the check screen and the editor screen
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
THEME_FILE = os.path.join(BASE_DIR, "theme", "sun_valley", "sv.tcl")   # Sun Valley ttk theme (MIT), no install

def open_path(path):
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])

def use_theme(root):
    # theme files missing or broken -> plain look, everything still works
    try:
        root.tk.call('source', THEME_FILE)
        ttk.Style(root).theme_use('sun-valley-light')
        return True
    except tk.TclError:
        return False

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
