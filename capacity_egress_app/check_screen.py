import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import capacity_db as db
import egress
import code_factors as cf
import exports
import colours
from widgets import (FONTS, BuildingBox, anchor_for, card_section, fit_columns, fit_window, heading_text, initials, open_path,
                     sideways_bar, wrap_to_width)

# configs
POLL_MS = 20000                                                        # check for other people's saves every 20 s
ANY = '(any)'
MAX_RESULTS = 500
MIN_WINDOW = (1280, 720)                                               # smallest window the screens are laid out for
OPEN_WINDOW = (1320, 860)
CHIP_GAP = 10                                                       # between the two verdict chips on one line
TABLE_ASKS_WIDTH = 400                                              # a table asks for no more: it grows with the window and scrolls sideways when the window is smaller

# table columns -> (heading, least width in px). no column is squeezed below its width; the zone Result column also
# grows to the longest fixed zone verdict in the real font, so that verdict is never cut short (a room's may scroll)
FOUND_COLUMNS = [('Room', 65), ('Floor', 50), ('Building', 120)]
CHECK_COLUMNS = [('Room', 100), ('Room type', 90), ('Capacity now', 125), ('Proposed', 85), ('Per code load', 105),
                 ('Result', 300)]
ZONE_COLUMNS = [('Zone', 175), ('Occupant load → with change', 215), ('Exit capacity', 105), ('Result', 340)]
# every verdict a zone can get, from the rule that gives them; over by 9999 stands for the longest overage
ZONE_VERDICTS = [egress.zone_verdict(zone) for zone in [{'status': egress.STATUS_NOT_SURVEYED},
                                                        {'status': egress.STATUS_WITHIN, 'total_load': 0, 'exit_capacity': 0},
                                                        {'status': egress.STATUS_REVIEW, 'total_load': 9999, 'exit_capacity': 0}]]

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


TRIAL_HELP = ("Leave New capacity blank to try only the room type. "
              "To check several rooms, pick another in the same building and press Check again.")

def rooms_found_text(count, shown):
    text = f"{count} room" + ('' if count == 1 else 's')
    return text + (f" (first {shown} shown)" if count > shown else '')


class CheckScreen:
    def __init__(self, root, conn, user_login, open_editor=None, open_editors=None):
        self.root = root
        self.conn = conn
        self.user_login = user_login
        self.editor = db.is_editor(conn, user_login)
        self.open_editor = open_editor
        self.open_editors = open_editors
        self.changes = {}          # room_id -> proposed capacity
        self.check = None
        self.room = None
        self.fonts = FONTS
        root.title("Room capacity check")
        self.build_widgets()
        # an error can wrap to a line more than the help: the smallest window keeps that line on top of what the widgets
        # ask for, so the result tables keep their row
        fit_window(root, OPEN_WINDOW, MIN_WINDOW, int(root.tk.call('font', 'metrics', self.fonts['caption'], '-linespace')))
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
        # narrow margins (8 px at the sides and between the two columns, 6 at the sides inside the cards): the tables ask
        # for no more than TABLE_ASKS_WIDTH and scroll sideways below their full width, so these margins and the find
        # column decide how narrow the screen can go, and how wide a result table is there. small gaps up and down (a few px
        # between and inside the cards, one more under the verdict chips and the tables): at the Windows font the screen and
        # its spare error line just fit the usable height of a 1920x1080 laptop at 150%
        outer = ttk.Frame(self.root, padding=(8, 6, 8, 4))
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        # header
        head = ttk.Frame(outer)
        head.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 4))
        # the name and buttons share the title's line; the subtitle has the whole width under both, so a long name never
        # wraps it onto another line (it wraps only in a window narrower than itself)
        head.columnconfigure(0, weight=1)
        who = ttk.Frame(head)
        who.grid(row=0, column=1, sticky='ne')
        ttk.Label(head, text="Room capacity check", font=self.fonts['title']).grid(row=0, column=0, sticky='w')
        wrap_to_width(ttk.Label(head, text="Try a new capacity: see the code's number for the room, and whether the floor's exits still carry everyone.",
                                foreground=colours.MUTED)).grid(row=1, column=0, columnspan=2, sticky='ew')
        name = db.get_user_name(self.conn, self.user_login) or self.user_login
        role = "Editor" if self.editor else "Viewer"
        ttk.Label(who, text=f"{name}  ·  {role}", font=self.fonts['strong']).pack(side='left', padx=(0, 12))
        if self.editor:
            ttk.Button(who, text="Editors", command=lambda: self.open_editors and self.open_editors()).pack(side='left', padx=4)
            # opens on the room picked here, if there is one
            ttk.Button(who, text="Editor screen",
                       command=lambda: self.open_editor and self.open_editor(self.room)).pack(side='left', padx=4)

        # left: find a room
        left = card_section(outer, "1. Find a room", padding=(6, 8))
        left.master.grid(row=1, column=0, sticky='nsw', padx=(0, 8))
        left.rowconfigure(5, weight=1)
        row = ttk.Frame(left, style='Inner.Card.TFrame')
        row.grid(row=0, column=0, sticky='ew')
        self.search_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.search_var, width=15)
        entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda e: self.search())
        entry.focus_set()
        ttk.Button(row, text="Search", command=self.search).pack(side='left', padx=(8, 0))
        ttk.Label(left, text="e.g.  DTB A120   ·   Turpin   ·   A120", style='Card.TLabel', font=self.fonts['caption'],
                  foreground=colours.MUTED).grid(row=1, column=0, sticky='w', pady=(4, 10))

        pick = ttk.Frame(left, style='Inner.Card.TFrame')
        pick.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(pick, text="Building", style='Card.TLabel').grid(row=0, column=0, sticky='w')
        self.building_var = tk.StringVar(value=ANY)
        self.building = BuildingBox(pick, self.building_var, ANY, self.pick_building, width=22)
        self.building.box.grid(row=1, column=0, sticky='ew', pady=(2, 8))
        ttk.Label(pick, text="Floor", style='Card.TLabel').grid(row=2, column=0, sticky='w')
        self.floor_var = tk.StringVar(value=ANY)
        self.floor_box = ttk.Combobox(pick, textvariable=self.floor_var, width=12, state='readonly', values=[ANY])
        self.floor_box.grid(row=3, column=0, sticky='w', pady=(2, 0))
        self.floor_box.bind('<<ComboboxSelected>>', lambda e: self.search())

        self.found_var = tk.StringVar()
        ttk.Label(left, textvariable=self.found_var, style='Card.TLabel', font=self.fonts['caption'],
                  foreground=colours.MUTED).grid(row=4, column=0, sticky='w')
        self.found_tree = self.make_tree(left, FOUND_COLUMNS, height=8)
        self.found_tree.master.grid(row=5, column=0, sticky='nsew', pady=(4, 0))
        self.found_tree.bind('<<TreeviewSelect>>', lambda e: self.pick_found())

        # right: room, try a number, results
        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        # room card -> the room now, and right under it the room with the change, column by column
        card = card_section(right, "2. Room", padding=(6, 3, 6, 5))
        card.master.grid(row=0, column=0, sticky='ew')
        card.columnconfigure(5, weight=1)
        self.room_title = tk.StringVar(value="Pick a room on the left")
        title = ttk.Frame(card, style='Inner.Card.TFrame')
        title.grid(row=0, column=0, columnspan=6, sticky='w')
        ttk.Label(title, textvariable=self.room_title, style='Card.TLabel', font=self.fonts['subtitle']).pack(side='left')
        self.room_category = tk.StringVar()
        ttk.Label(title, textvariable=self.room_category, style='Card.TLabel', foreground=colours.MUTED).pack(
            side='left', padx=(12, 0))
        ttk.Label(card, text="Now", style='Card.TLabel', font=self.fonts['strong']).grid(row=2, column=0, sticky='w', padx=(0, 24))
        ttk.Label(card, text="With change", style='Card.TLabel', font=self.fonts['strong'], foreground=colours.CHANGED_FG).grid(
            row=3, column=0, sticky='w', padx=(0, 24))
        self.card_vars, self.trial_vars, self.trial_labels = {}, {}, {}
        for i, label in enumerate(["Room type", "Area", "Room capacity", "Per code load"], start=1):
            # small muted captions over large values
            ttk.Label(card, text=label, style='Card.TLabel', font=self.fonts['caption'], foreground=colours.MUTED).grid(
                row=1, column=i, sticky='w', padx=(0, 20), pady=(4, 0))
            self.card_vars[label] = tk.StringVar(value='-')
            ttk.Label(card, textvariable=self.card_vars[label], style='Card.TLabel', font=self.fonts['large']).grid(
                row=2, column=i, sticky='w', padx=(0, 28))
            self.trial_vars[label] = tk.StringVar(value='-')
            self.trial_labels[label] = ttk.Label(card, textvariable=self.trial_vars[label], style='Card.TLabel',
                                                 font=self.fonts['large'])
            self.trial_labels[label].grid(row=3, column=i, sticky='w', padx=(0, 28))
        # the two verdicts as chips -> side by side, one under the other when the card is too narrow for both
        self.chips = ttk.Frame(card, style='Inner.Card.TFrame')
        self.chips.grid(row=4, column=0, columnspan=6, sticky='ew', pady=(4, 0))
        self.badge = tk.Label(self.chips, text="", padx=8, pady=1, anchor='w', compound='left', **colours.NO_CHIP)
        self.badge.grid(row=0, column=0, sticky='w')
        self.trial_badge = tk.Label(self.chips, text="", padx=8, pady=1, anchor='w', compound='left', **colours.NO_CHIP)
        self.trial_badge.grid(row=0, column=1, sticky='w', padx=(CHIP_GAP, 0))
        self.chips.bind('<Configure>', lambda e: self.place_chips())

        trial = card_section(right, "3. Try a new capacity or room type", padding=(6, 3))
        trial.master.grid(row=1, column=0, sticky='ew', pady=(4, 0))
        line = ttk.Frame(trial, style='Inner.Card.TFrame')
        line.pack(fill='x')
        # room type -> changes the m2 per person, so the per code load (and an unvisited room's load) changes
        ttk.Label(line, text="Room type", style='Card.TLabel', font=self.fonts['strong']).pack(side='left')
        self.type_var = tk.StringVar()
        self.type_box = ttk.Combobox(line, textvariable=self.type_var, width=11, state='readonly')
        self.type_box.pack(side='left', padx=(10, 18))
        self.type_box.bind('<<ComboboxSelected>>', lambda e: self.show_trial())
        ttk.Label(line, text="New capacity", style='Card.TLabel', font=self.fonts['strong']).pack(side='left')
        self.new_var = tk.StringVar()
        self.new_var.trace_add('write', lambda *_: self.show_trial())
        new_entry = ttk.Entry(line, textvariable=self.new_var, width=8)
        new_entry.pack(side='left', padx=10)
        new_entry.bind('<Return>', lambda e: self.add_to_check())
        ttk.Button(line, text="Check", style='Accent.TButton', command=self.add_to_check).pack(side='left')
        ttk.Button(line, text="Remove room", command=self.remove_from_check).pack(side='left', padx=(18, 4))
        ttk.Button(line, text="Start over", command=self.start_over).pack(side='left', padx=4)
        # one label: the help, or what's wrong with the number (a long message wraps)
        self.hint = wrap_to_width(ttk.Label(trial, text=TRIAL_HELP, style='Card.TLabel', font=self.fonts['caption'],
                                            foreground=colours.MUTED))
        self.hint.pack(fill='x', pady=(2, 0))
        self.message_var = tk.StringVar()
        self.message_var.trace_add('write', lambda *_: self.show_hint())

        results = card_section(right, "4. Result", padding=(6, 3, 6, 5))
        results.master.grid(row=2, column=0, sticky='nsew', pady=(4, 0))
        results.columnconfigure(0, weight=1)
        # the tables ask for one row and share what the window has: on a small window they scroll, nothing else gives way
        results.rowconfigure(1, weight=1)
        results.rowconfigure(3, weight=2)
        # the summary is this check written down -> saved from the result's first line, not a line of its own
        top = ttk.Frame(results, style='Inner.Card.TFrame')
        top.grid(row=0, column=0, sticky='ew')
        ttk.Label(top, text="Rooms in this check", style='Card.TLabel', font=self.fonts['strong']).pack(side='left')
        ttk.Button(top, text="Save summary (.docx)", command=self.save_summary).pack(side='right')
        ttk.Label(top, text="Attach it to your email to Mark Arrojado.", style='Card.TLabel', foreground=colours.MUTED).pack(
            side='right', padx=10)
        self.check_tree = self.make_tree(results, CHECK_COLUMNS, height=1)
        self.check_tree.master.grid(row=1, column=0, sticky='nsew', pady=(2, 4))
        self.zone_label = tk.StringVar(value="Floor exits: occupant load vs exit capacity")
        ttk.Label(results, textvariable=self.zone_label, style='Card.TLabel', font=self.fonts['strong']).grid(
            row=2, column=0, sticky='w')
        self.zone_tree = self.make_tree(results, ZONE_COLUMNS, height=1)
        self.zone_tree.master.grid(row=3, column=0, sticky='nsew', pady=(2, 0))

        # footer: legend + the screening rule
        foot = ttk.Frame(outer)
        foot.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(4, 0))
        colours.legend(foot).pack(side='left', anchor='n')
        # one line with the legend: the rule asks for no width and wraps into what the legend leaves it
        wrap_to_width(ttk.Label(foot, text="Screening only, not an approval. Nothing on this screen is saved; an editor reviews every change.",
                                font=self.fonts['caption'], foreground=colours.MUTED, width=1)).pack(side='left', fill='x', expand=True, pady=(2, 0))

    # a verdict (colours.chip) or a line without one (colours.NO_CHIP) into its chip
    def show_chip(self, chip, text, look):
        chip.configure(text=text, **look)
        self.place_chips()

    def place_chips(self):
        width = self.chips.winfo_width()                  # 1 until it's drawn: its first <Configure> comes with the real one
        asked = self.badge.winfo_reqwidth() + CHIP_GAP + self.trial_badge.winfo_reqwidth()
        if width <= 1 or asked <= width:
            self.trial_badge.grid_configure(row=0, column=1, padx=(CHIP_GAP, 0), pady=0)
        else:
            self.trial_badge.grid_configure(row=1, column=0, padx=0, pady=(2, 0))

    def show_hint(self):
        message = self.message_var.get()
        self.hint.configure(text=message or TRIAL_HELP, foreground=colours.ERROR_FG if message else colours.MUTED)

    # every column as wide as its heading and values: after each fill. the zone Result column also holds every fixed verdict
    def fit(self, tree, columns=None):
        columns = columns or {self.found_tree: FOUND_COLUMNS, self.check_tree: CHECK_COLUMNS, self.zone_tree: ZONE_COLUMNS}[tree]
        fit_columns(tree, columns, always={'Result': ZONE_VERDICTS} if columns is ZONE_COLUMNS else None)

    def make_tree(self, parent, columns, height):
        frame = ttk.Frame(parent, style='Inner.Card.TFrame')
        tree = ttk.Treeview(frame, columns=[c for c, _ in columns], height=height, selectmode='browse')
        colours.colour_tags(tree)
        for col, width in columns:
            tree.heading(col, text=heading_text(col), anchor=anchor_for(col))
            tree.column(col, width=width, minwidth=width, anchor=anchor_for(col), stretch=col in ('Building', 'Result'))
        # the table asks the window for the room its headings and the fixed zone verdicts need, but never more than
        # TABLE_ASKS_WIDTH: it grows with the window, and where the window is narrower than its columns (a small screen, a
        # long building name) the table scrolls sideways. the sideways bar shows only then, and takes its height from the
        # table's rows: the window keeps the room a wrapped message needs
        self.fit(tree, columns)
        asked = colours.MARK_COLUMN + sum(int(tree.column(col, 'width')) for col, _ in columns)
        ys = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        xs = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=ys.set, xscrollcommand=sideways_bar(xs))
        tree.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        xs.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.configure(width=min(asked + ys.winfo_reqwidth(), TABLE_ASKS_WIDTH), height=tree.winfo_reqheight())
        frame.grid_propagate(False)
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
                                   **colours.row(self.found_tree, colour))
        self.fit(self.found_tree)
        if not len(found) and not (self.search_var.get().strip() or prop):
            self.found_var.set("Type a room or building, or pick a building.")
        else:
            self.found_var.set(rooms_found_text(len(found), MAX_RESULTS))
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
        self.card_vars["Room type"].set(f"{r['room_type'] or '-'}")
        self.room_category.set(r['sub_category'] if pd.notna(r['sub_category']) else '')
        self.card_vars["Area"].set('-' if pd.isna(r['area_m2']) else f"{r['area_m2']:g} m²")
        self.card_vars["Room capacity"].set("not visited" if pd.isna(capacity) else f"{int(capacity)}  ({r['capacity_source']})")
        self.card_vars["Per code load"].set('-' if pd.isna(r['area_per_person_m2'])
                                            else f"{r['per_code_load']}  ({r['area_per_person_m2']:g} m²/person)")
        colour, text = room_status_text(r)
        self.show_chip(self.badge, f"Now: {text}", colours.chip(self.badge, colour))
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
            self.show_chip(self.trial_badge, '', colours.NO_CHIP)
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
            "Per code load": (f"{t['per_code_load']}  ({t['area_per_person_m2']:g} m²/person)" if has_load else 'none',
                              per_changed),
        }
        for label, (value, changed) in cells.items():
            self.trial_vars[label].set(value if changed else 'same')
            self.trial_labels[label].configure(foreground=colours.CHANGED_FG if changed else colours.MUTED)

        if not (type_changed or cap_changed):
            self.show_chip(self.trial_badge, "With change: pick a room type or type a new capacity in 3 below",
                           colours.NO_CHIP)
            return
        verdict = t['verdict'] + ('' if r['in_scope'] else '  ·  out of scope: not counted toward the floor')
        if t['capacity'] is None and per_changed and r['in_scope']:
            verdict += f" ({r['per_code_load']} → {t['per_code_load']} on the floor)"
        self.show_chip(self.trial_badge, f"With change: {verdict}", colours.chip(self.trial_badge, t['colour']))

    def show_floor_now(self, prop, floor):
        zones = self.result['zones']
        zones = zones[(zones['property'] == prop) & (zones['floor'] == floor)].sort_values('zone_wing')
        self.zone_label.set(f"Floor {floor} exits now: occupant load vs exit capacity")
        self.zone_tree.delete(*self.zone_tree.get_children())
        for _, z in zones.iterrows():
            verdict = egress.zone_verdict(z)
            capacity = '-' if verdict == egress.CANT_CHECK else z['exit_capacity']
            name = egress.zone_name(z['floor'], z['zone_wing'])
            self.zone_tree.insert('', 'end', values=[name, z['total_load'], capacity, verdict],
                                  **colours.row(self.zone_tree, egress.zone_colour(z)))
        self.fit(self.zone_tree)

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
                                   now, proposed, per_code, verdict],
                                   **colours.row(self.check_tree, r['colour']))
        self.fit(self.check_tree)
        self.zone_label.set("Floor exits with the change: occupant load vs exit capacity   (★ = your room's zone)")
        self.zone_tree.delete(*self.zone_tree.get_children())
        for z in self.check['zones']:
            name = egress.zone_name(z['floor'], z['zone_wing']) + (' ★' if z['has_checked_room'] else '')
            capacity = '-' if z['verdict'] == egress.CANT_CHECK else z['exit_capacity']
            verdict = z['verdict'] + (f"  (also: {z['other_flags']})" if z['other_flags'] else '')
            self.zone_tree.insert('', 'end', values=[name, f"{z['load_before']} → {z['load_after']}", capacity, verdict],
                                  **colours.row(self.zone_tree, z['colour']))
        self.fit(self.zone_tree)

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
