import os
import re
import sys
import sqlite3
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import capacity_db as db
import egress
import code_factors as cf
import exports
import colours

# configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
THEME_FILE = os.path.join(BASE_DIR, "theme", "sun_valley", "sv.tcl")   # Sun Valley ttk theme (MIT), no install
POLL_MS = 20000                                                        # check for other people's saves every 20 s
ANY = '(any)'
MAX_RESULTS = 500

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

def find_rooms(rooms, query, prop=None, floor=None):
    if prop:
        rooms = rooms[rooms['property'] == prop]
        if floor:
            rooms = rooms[rooms['floor'] == floor]
    words = query.lower().split()
    room_words = [w for w in words if any(c.isdigit() for c in w)]
    building_words = [w for w in words if w not in room_words]
    if not words and not prop:
        return rooms.iloc[0:0]
    if building_words:
        names = rooms['property'].drop_duplicates()
        keep = [p for p in names if all(w in p.lower() or w == initials(p) for w in building_words)]
        rooms = rooms[rooms['property'].isin(keep)]
    for w in room_words:
        space = rooms['space'].astype(str).str.lower()
        exact = space == w
        rooms = rooms[exact] if exact.any() else rooms[space.str.contains(w, regex=False)]
    return rooms.sort_values(['property', 'floor', 'space'])

# the card's verdict text -> egress.judge_room decides, this only words it for the badge
def room_status_text(room):
    verdict, colour, _ = egress.judge_room(room, egress.room_capacity(room))
    if not room['in_scope']:
        verdict += "  ·  out of scope: not counted toward the floor"
    return colour, verdict


class CheckScreen:
    def __init__(self, root, conn, user_login, themed, open_editor=None, open_editors=None):
        self.root = root
        self.conn = conn
        self.user_login = user_login
        self.editor = db.is_editor(conn, user_login)
        self.open_editor = open_editor
        self.open_editors = open_editors
        self.changes = {}          # room_id -> proposed capacity
        self.check = None
        self.room = None
        self.fonts = ({'title': 'SunValleyTitleFont', 'subtitle': 'SunValleySubtitleFont', 'strong': 'SunValleyBodyStrongFont',
                       'large': 'SunValleyBodyLargeFont', 'caption': 'SunValleyCaptionFont'} if themed else
                      {'title': ('TkDefaultFont', 20, 'bold'), 'subtitle': ('TkDefaultFont', 15, 'bold'),
                       'strong': ('TkDefaultFont', 10, 'bold'), 'large': ('TkDefaultFont', 12), 'caption': ('TkDefaultFont', 9)})
        root.title("Room capacity check")
        root.geometry("1320x860")
        root.minsize(1100, 720)
        self.build_widgets()
        self.reload()
        self.root.after(POLL_MS, self.poll)

    # data -> whole campus once; the check itself only recalculates the floors involved
    def reload(self):
        self.root.config(cursor='watch')
        self.root.update_idletasks()
        try:
            self.rooms = db.load_rooms(self.conn)
            self.exits = db.load_exits(self.conn)
            self.factors = db.load_code_factors(self.conn)
            self.result = egress.calculate(self.rooms, self.exits, self.factors)
            self.seen_version = db.data_version(self.conn)
            self.building.set_names(sorted(self.rooms['property'].unique()))
            self.room_types = cf.room_types(self.factors)
            self.type_box['values'] = self.room_types
            self.search()
            if self.room is not None:
                self.show_room(self.room['room_id'])
            if self.changes:
                self.run_check()
        finally:
            self.root.config(cursor='')

    def poll(self):
        try:
            if self.root.grab_current() is None and db.data_version(self.conn) != self.seen_version:
                self.reload()
        except sqlite3.Error:
            pass                                      # drive busy or offline -> try again next time
        self.root.after(POLL_MS, self.poll)

    # layout
    def build_widgets(self):
        outer = ttk.Frame(self.root, padding=(24, 18, 24, 12))
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        # header
        head = ttk.Frame(outer)
        head.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 14))
        titles = ttk.Frame(head)
        titles.pack(side='left')
        ttk.Label(titles, text="Room capacity check", font=self.fonts['title']).pack(anchor='w')
        ttk.Label(titles, text="Try a new room capacity: see the building code's number for the room, "
                               "and whether the floor's exits can still carry everyone.",
                  font=self.fonts['large'], foreground='#5A5A5A').pack(anchor='w')
        who = ttk.Frame(head)
        who.pack(side='right', anchor='n')
        name = db.get_user_name(self.conn, self.user_login) or self.user_login
        role = "Editor" if self.editor else "Viewer"
        ttk.Label(who, text=f"{name}  ·  {role}", font=self.fonts['strong']).pack(side='left', padx=(0, 12))
        if self.editor:
            ttk.Button(who, text="Editors", command=lambda: self.open_editors and self.open_editors()).pack(side='left', padx=4)
            # opens on the room picked here, if there is one
            ttk.Button(who, text="Editor screen", style='Accent.TButton',
                       command=lambda: self.open_editor and self.open_editor(self.room)).pack(side='left', padx=4)

        # left: find a room
        left = ttk.LabelFrame(outer, text=" 1. Find a room ", padding=12)
        left.grid(row=1, column=0, sticky='nsw', padx=(0, 18))
        left.rowconfigure(5, weight=1)
        row = ttk.Frame(left)
        row.grid(row=0, column=0, sticky='ew')
        self.search_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.search_var, width=26)
        entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda e: self.search())
        entry.focus_set()
        ttk.Button(row, text="Search", style='Accent.TButton', command=self.search).pack(side='left', padx=(8, 0))
        ttk.Label(left, text="e.g.  DTB A120   ·   Turpin   ·   A120", font=self.fonts['caption'],
                  foreground='#6A6A6A').grid(row=1, column=0, sticky='w', pady=(4, 10))

        pick = ttk.Frame(left)
        pick.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(pick, text="Building").grid(row=0, column=0, sticky='w')
        self.building_var = tk.StringVar(value=ANY)
        self.building = BuildingBox(pick, self.building_var, ANY, self.pick_building, width=30)
        self.building.box.grid(row=1, column=0, sticky='ew', pady=(2, 8))
        ttk.Label(pick, text="Floor").grid(row=2, column=0, sticky='w')
        self.floor_var = tk.StringVar(value=ANY)
        self.floor_box = ttk.Combobox(pick, textvariable=self.floor_var, width=12, state='readonly', values=[ANY])
        self.floor_box.grid(row=3, column=0, sticky='w', pady=(2, 0))
        self.floor_box.bind('<<ComboboxSelected>>', lambda e: self.search())

        self.found_var = tk.StringVar()
        ttk.Label(left, textvariable=self.found_var, font=self.fonts['caption'], foreground='#6A6A6A').grid(
            row=4, column=0, sticky='w')
        self.found_tree = self.make_tree(left, [('Room', 80), ('Floor', 55), ('Building', 230)], height=18)
        self.found_tree.master.grid(row=5, column=0, sticky='nsew', pady=(4, 0))
        self.found_tree.bind('<<TreeviewSelect>>', lambda e: self.pick_found())
        colours.colour_tags(self.found_tree)

        # right: room, try a number, results
        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        # room card -> the room now, and right under it the room with the change, column by column
        card = ttk.LabelFrame(right, text=" 2. Room ", padding=(14, 10))
        card.grid(row=0, column=0, sticky='ew')
        card.columnconfigure(5, weight=1)
        self.room_title = tk.StringVar(value="Pick a room on the left")
        ttk.Label(card, textvariable=self.room_title, font=self.fonts['subtitle']).grid(row=0, column=0, columnspan=6, sticky='w')
        ttk.Label(card, text="Now", font=self.fonts['strong']).grid(row=2, column=0, sticky='w', padx=(0, 24))
        ttk.Label(card, text="With change", font=self.fonts['strong'], foreground=colours.CHANGED_FG).grid(
            row=3, column=0, sticky='w', padx=(0, 24), pady=(2, 0))
        self.card_vars, self.trial_vars, self.trial_labels = {}, {}, {}
        for i, label in enumerate(["Room type", "Area", "Room capacity", "Per code load"], start=1):
            ttk.Label(card, text=label, foreground='#6A6A6A').grid(row=1, column=i, sticky='w', padx=(0, 28), pady=(8, 0))
            self.card_vars[label] = tk.StringVar(value='-')
            ttk.Label(card, textvariable=self.card_vars[label], font=self.fonts['large']).grid(row=2, column=i, sticky='w', padx=(0, 28))
            self.trial_vars[label] = tk.StringVar(value='-')
            self.trial_labels[label] = ttk.Label(card, textvariable=self.trial_vars[label], font=self.fonts['large'])
            self.trial_labels[label].grid(row=3, column=i, sticky='w', padx=(0, 28), pady=(2, 0))
        badges = ttk.Frame(card)
        badges.grid(row=4, column=0, columnspan=6, sticky='w', pady=(10, 0))
        self.badge = tk.Label(badges, text="", padx=10, pady=4, anchor='w', fg=colours.ROW_FG)
        self.badge_bg = self.badge.cget('bg')
        self.badge.pack(side='left')
        self.trial_badge = tk.Label(badges, text="", padx=10, pady=4, anchor='w', fg=colours.ROW_FG)
        self.trial_badge.pack(side='left', padx=(10, 0))

        trial = ttk.LabelFrame(right, text=" 3. Try a new capacity or room type ", padding=(14, 10))
        trial.grid(row=1, column=0, sticky='ew', pady=(14, 0))
        line = ttk.Frame(trial)
        line.pack(fill='x')
        # room type -> changes the m2 per person, so the per code load (and an unvisited room's load) changes
        ttk.Label(line, text="Room type", font=self.fonts['strong']).pack(side='left')
        self.type_var = tk.StringVar()
        self.type_box = ttk.Combobox(line, textvariable=self.type_var, width=11, state='readonly')
        self.type_box.pack(side='left', padx=(10, 18))
        self.type_box.bind('<<ComboboxSelected>>', lambda e: self.show_trial())
        ttk.Label(line, text="New capacity", font=self.fonts['strong']).pack(side='left')
        self.new_var = tk.StringVar()
        self.new_var.trace_add('write', lambda *_: self.show_trial())
        new_entry = ttk.Entry(line, textvariable=self.new_var, width=8)
        new_entry.pack(side='left', padx=10)
        new_entry.bind('<Return>', lambda e: self.add_to_check())
        ttk.Button(line, text="Check", style='Accent.TButton', command=self.add_to_check).pack(side='left')
        ttk.Button(line, text="Remove room", command=self.remove_from_check).pack(side='left', padx=(18, 4))
        ttk.Button(line, text="Start over", command=self.start_over).pack(side='left', padx=4)
        ttk.Label(trial, text="Leave New capacity blank to try only the room type. Check shows the floor exits; "
                              "pick another room in the same building and press Check again to check several together.",
                  font=self.fonts['caption'], foreground='#6A6A6A').pack(anchor='w', pady=(6, 0))
        self.message_var = tk.StringVar()
        ttk.Label(trial, textvariable=self.message_var, foreground='#B00020').pack(anchor='w')

        results = ttk.LabelFrame(right, text=" 4. Result ", padding=(14, 10))
        results.grid(row=2, column=0, sticky='nsew', pady=(14, 0))
        results.columnconfigure(0, weight=1)
        results.rowconfigure(3, weight=1)
        ttk.Label(results, text="Rooms in this check", font=self.fonts['strong']).grid(row=0, column=0, sticky='w')
        self.check_tree = self.make_tree(results, [('Room', 120), ('Room type', 130), ('Capacity now', 140), ('Proposed', 75),
                                                   ('Per code load', 100), ('Result', 300)], height=3)
        self.check_tree.master.grid(row=1, column=0, sticky='ew', pady=(4, 12))
        colours.colour_tags(self.check_tree)
        self.zone_label = tk.StringVar(value="Floor exits: occupant load vs exit capacity")
        ttk.Label(results, textvariable=self.zone_label, font=self.fonts['strong']).grid(row=2, column=0, sticky='w')
        self.zone_tree = self.make_tree(results, [('Zone', 130), ('Occupant load now → with change', 230),
                                                  ('Exit capacity', 100), ('Result', 420)], height=5)
        self.zone_tree.master.grid(row=3, column=0, sticky='nsew', pady=(4, 0))
        colours.colour_tags(self.zone_tree)

        actions = ttk.Frame(right)
        actions.grid(row=3, column=0, sticky='ew', pady=(12, 0))
        ttk.Button(actions, text="Save summary (.docx)", style='Accent.TButton', command=self.save_summary).pack(side='left')
        ttk.Label(actions, text="Attach it to your email to Mark Arrojado.", foreground='#6A6A6A').pack(side='left', padx=10)

        # footer: legend + the screening rule
        foot = ttk.Frame(outer)
        foot.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(14, 0))
        colours.legend(foot).pack(anchor='w')
        ttk.Label(foot, text="Screening only, not an approval. Nothing on this screen is saved; an editor reviews every change.",
                  font=self.fonts['caption'], foreground='#6A6A6A').pack(anchor='w', pady=(4, 0))

    def make_tree(self, parent, columns, height):
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=[c for c, _ in columns], show='headings', height=height, selectmode='browse')
        for col, width in columns:
            tree.heading(col, text=col, anchor='w')
            tree.column(col, width=width, anchor='w', stretch=col in ('Building', 'Result'))
        ys = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        tree.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    # finding rooms
    def pick_building(self):
        prop = self.building.picked()
        floors = sorted(self.rooms.loc[self.rooms['property'] == prop, 'floor'].unique()) if prop else []
        self.floor_box['values'] = [ANY] + floors
        self.floor_var.set(ANY)
        self.search_var.set('')
        self.search()

    def search(self):
        # half-typed building text isn't a filter until it's picked
        prop = self.building.picked()
        floor = None if self.floor_var.get() == ANY else self.floor_var.get()
        found = find_rooms(self.result['rooms'], self.search_var.get(), prop, floor)
        self.found_tree.delete(*self.found_tree.get_children())
        for _, r in found.head(MAX_RESULTS).iterrows():
            colour = egress.room_colour(r)
            self.found_tree.insert('', 'end', iid=f"r{int(r['room_id'])}", values=[r['space'], r['floor'], r['property']],
                                   tags=(colour,) if colour else ())
        if not len(found) and not (self.search_var.get().strip() or prop):
            self.found_var.set("Type a room or building, or pick a building.")
        else:
            self.found_var.set(f"{len(found)} rooms" + (f" (first {MAX_RESULTS} shown)" if len(found) > MAX_RESULTS else ''))
        if len(found) == 1:
            # one match -> show it now, not when the select event gets round to it
            self.found_tree.selection_set(self.found_tree.get_children()[0])
            self.show_room(int(found['room_id'].iloc[0]))

    def pick_found(self):
        sel = self.found_tree.selection()
        if sel:
            self.show_room(int(sel[0][1:]))

    # the room card + the floor as it is now
    def show_room(self, room_id):
        rooms = self.result['rooms'].set_index('room_id')
        if room_id not in rooms.index:
            self.room = None
            self.room_title.set("That room is no longer in the database")
            return
        r = rooms.loc[room_id].to_dict() | {'room_id': room_id}
        self.room = r
        self.room_title.set(f"{r['property']}  ·  Floor {r['floor']}  ·  {r['space']}")
        capacity = pd.to_numeric(r['capacity'], errors='coerce')
        self.card_vars["Room type"].set(f"{r['room_type'] or '-'}" + (f"  ({r['sub_category']})" if pd.notna(r['sub_category']) else ''))
        self.card_vars["Area"].set('-' if pd.isna(r['area_m2']) else f"{r['area_m2']:g} m²")
        self.card_vars["Room capacity"].set("not visited" if pd.isna(capacity) else f"{int(capacity)}  ({r['capacity_source']})")
        self.card_vars["Per code load"].set('-' if pd.isna(r['area_per_person_m2'])
                                            else f"{r['per_code_load']}  ({r['area_per_person_m2']:g} m² per person)")
        colour, text = room_status_text(r)
        self.badge.configure(text=f"Now: {text}", bg=colours.ROW_BG.get(colour, self.badge_bg))
        tried = self.changes.get(room_id, {})
        self.new_var.set('' if tried.get('capacity') is None else str(tried['capacity']))
        self.type_var.set(tried.get('room_type') or self.room_type_now())
        self.show_trial()
        if not self.changes:
            self.show_floor_now(r['property'], r['floor'])

    def room_type_now(self):
        t = self.room['room_type'] if self.room is not None else None
        return '' if t is None or pd.isna(t) else t

    # the room with the change -> updates as you pick a type or type a number, before pressing Check
    def show_trial(self):
        r = self.room
        if r is None:
            for label in self.trial_vars:
                self.trial_vars[label].set('-')
                self.trial_labels[label].configure(foreground='')
            self.trial_badge.configure(text='', bg=self.badge_bg)
            return

        # what's tried: room type from the box, capacity typed (blank or not a number -> as now)
        type_now = self.room_type_now()
        new_type = self.type_var.get() or type_now
        type_changed = new_type != type_now
        cap_now = egress.room_capacity(r)
        text = self.new_var.get().strip()
        cap_typed = int(text) if text.isdigit() else None
        self.message_var.set("Type a whole number (0 or more)." if text and cap_typed is None else '')
        cap_changed = cap_typed is not None and cap_typed != cap_now
        # per code load and verdict -> egress.try_room, the same rule as the check
        t = egress.try_room(r, self.factors, room_type=new_type if type_changed else None,
                            capacity=cap_typed if cap_changed else None)
        has_load = pd.notna(t['area_per_person_m2'])
        per_changed = t['per_code_load'] != int(r['per_code_load'])

        # changed -> the new value in blue; unchanged -> "same" in grey, the Now row above says what it is
        cells = {
            "Room type": (new_type or '-', type_changed),
            "Area": ('', False),
            "Room capacity": (('not visited' if t['capacity'] is None else str(t['capacity'])) + '  (PM change)', cap_changed),
            "Per code load": (f"{t['per_code_load']}  ({t['area_per_person_m2']:g} m² per person)" if has_load else 'none',
                              per_changed),
        }
        for label, (value, changed) in cells.items():
            self.trial_vars[label].set(value if changed else 'same')
            self.trial_labels[label].configure(foreground=colours.CHANGED_FG if changed else '#6A6A6A')

        if not (type_changed or cap_changed):
            self.trial_badge.configure(text="With change: pick a room type or type a new capacity in 3 below",
                                       bg=self.badge_bg)
            return
        verdict = t['verdict'] + ('' if r['in_scope'] else '  ·  out of scope: not counted toward the floor')
        if t['capacity'] is None and per_changed and r['in_scope']:
            verdict += f" ({r['per_code_load']} → {t['per_code_load']} on the floor)"
        self.trial_badge.configure(text=f"With change: {verdict}", bg=colours.ROW_BG.get(t['colour'], self.badge_bg))

    def show_floor_now(self, prop, floor):
        zones = self.result['zones']
        zones = zones[(zones['property'] == prop) & (zones['floor'] == floor)].sort_values('zone_wing')
        self.zone_label.set(f"Floor {floor} exits now: occupant load vs exit capacity")
        self.zone_tree.delete(*self.zone_tree.get_children())
        for _, z in zones.iterrows():
            verdict = egress.zone_verdict(z)
            capacity = '-' if verdict == egress.CANT_CHECK else z['exit_capacity']
            name = f"Floor {z['floor']}" + (f" wing {z['zone_wing']}" if z['zone_wing'] else '')
            self.zone_tree.insert('', 'end', values=[name, z['total_load'], capacity, verdict], tags=(egress.zone_colour(z),))

    # the check -> nothing is saved
    def add_to_check(self):
        self.message_var.set('')
        if self.room is None:
            self.message_var.set("Pick a room first.")
            return
        text = self.new_var.get().strip()
        try:
            new = None if text == '' else int(text)
            if new is not None and new < 0:
                raise ValueError
        except ValueError:
            self.message_var.set("Type a whole number (0 or more).")
            return
        new_type = self.type_var.get()
        new_type = new_type if new_type and new_type != self.room_type_now() else None
        if new is None and new_type is None:
            self.message_var.set("Type a new capacity, or pick another room type.")
            return
        if self.changes:
            building = self.rooms.loc[self.rooms['room_id'] == next(iter(self.changes)), 'property'].iloc[0]
            if building != self.room['property']:
                if not messagebox.askyesno("New check",
                                           f"This check holds rooms in {building}.\nStart a new check for "
                                           f"{self.room['property']}?", parent=self.root):
                    return
                self.changes = {}
        self.changes[self.room['room_id']] = {'capacity': new, 'room_type': new_type}
        self.run_check()

    def remove_from_check(self):
        sel = self.check_tree.selection()
        room_id = int(sel[0][1:]) if sel else (self.room['room_id'] if self.room else None)
        if room_id in self.changes:
            del self.changes[room_id]
            self.run_check()

    def start_over(self):
        self.changes = {}
        self.check = None
        self.new_var.set('')
        self.type_var.set(self.room_type_now())
        self.show_trial()
        self.message_var.set('')
        self.check_tree.delete(*self.check_tree.get_children())
        if self.room is not None:
            self.show_floor_now(self.room['property'], self.room['floor'])
        else:
            self.zone_tree.delete(*self.zone_tree.get_children())

    def run_check(self):
        self.check_tree.delete(*self.check_tree.get_children())
        if not self.changes:
            self.start_over()
            return
        try:
            capacities = {k: v['capacity'] for k, v in self.changes.items() if v['capacity'] is not None}
            room_types = {k: v['room_type'] for k, v in self.changes.items() if v['room_type']}
            self.check = egress.check_capacities(self.rooms, self.exits, self.factors, capacities, room_types)
        except ValueError as err:
            self.message_var.set(str(err))
            self.changes = {}
            self.check = None
            return
        for r in self.check['rooms']:
            now = 'not visited (per code)' if r['current'] is None else f"{r['current']} ({r['current_source']})"
            verdict = r['verdict'] + ('' if r['in_scope'] else '  (out of scope)')
            if r['type_changed']:
                room_type = f"{r['room_type_before'] or '-'} → {r['room_type']}"
                per_code = f"{r['per_code_before']} → {r['per_code_load']}"
            else:
                room_type, per_code = r['room_type'] or '-', r['per_code_load']
            proposed = '-' if r['proposed'] is None else r['proposed']
            self.check_tree.insert('', 'end', iid=f"r{r['room_id']}", values=[f"Floor {r['floor']}  {r['space']}", room_type,
                                   now, proposed, per_code, verdict], tags=(r['colour'],) if r['colour'] else ())
        self.zone_label.set("Floor exits with the change: occupant load vs exit capacity")
        self.zone_tree.delete(*self.zone_tree.get_children())
        for z in self.check['zones']:
            name = f"Floor {z['floor']}" + (f" wing {z['zone_wing']}" if z['zone_wing'] else '') + (' ★' if z['has_checked_room'] else '')
            capacity = '-' if z['verdict'] == egress.CANT_CHECK else z['exit_capacity']
            verdict = z['verdict'] + (f"  (also: {z['other_flags']})" if z['other_flags'] else '')
            self.zone_tree.insert('', 'end', values=[name, f"{z['load_before']} → {z['load_after']}", capacity, verdict],
                                  tags=(z['colour'],))

    def save_summary(self):
        if not self.check or not self.check['rooms']:
            messagebox.showinfo("Nothing to save", "Run a check first: pick a room, type a new capacity, press Check.",
                                parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Save the check summary", defaultextension='.docx',
                                            initialfile=exports.check_file_name(self.check),
                                            filetypes=[("Word document", "*.docx")])
        if not path:
            return
        name = db.get_user_name(self.conn, self.user_login) or self.user_login
        try:
            exports.write_check_summary(self.check, path, name)
        except PermissionError as err:
            messagebox.showerror("Not saved", str(err), parent=self.root)
            return
        if messagebox.askyesno("Saved", f"Saved:\n{path}\n\nOpen it now?", parent=self.root):
            open_path(path)
