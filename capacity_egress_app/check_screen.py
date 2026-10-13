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

def room_status_text(room):
    colour = egress.room_colour(room)
    if colour == egress.NONE:
        return colour, "Out of scope: not counted toward the floor"
    if colour == egress.GREY:
        return colour, "Not visited yet: uses the per code load"
    if colour == egress.AMBER:
        return colour, "Over the per code load: needs justification"
    return colour, f"Visited ({room['capacity_source']}): within per code"


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
            self.building_box['values'] = [ANY] + sorted(self.rooms['property'].unique())
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
        self.building_box = ttk.Combobox(pick, textvariable=self.building_var, width=30, state='readonly')
        self.building_box.grid(row=1, column=0, sticky='ew', pady=(2, 8))
        self.building_box.bind('<<ComboboxSelected>>', lambda e: self.pick_building())
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

        card = ttk.LabelFrame(right, text=" 2. Room ", padding=(14, 10))
        card.grid(row=0, column=0, sticky='ew')
        card.columnconfigure(5, weight=1)
        self.room_title = tk.StringVar(value="Pick a room on the left")
        ttk.Label(card, textvariable=self.room_title, font=self.fonts['subtitle']).grid(row=0, column=0, columnspan=6, sticky='w')
        self.card_vars = {}
        for i, label in enumerate(["Room type", "Area", "Room capacity now", "Per code load"]):
            ttk.Label(card, text=label, foreground='#6A6A6A').grid(row=1, column=i, sticky='w', padx=(0, 28), pady=(8, 0))
            var = tk.StringVar(value='-')
            ttk.Label(card, textvariable=var, font=self.fonts['large']).grid(row=2, column=i, sticky='w', padx=(0, 28))
            self.card_vars[label] = var
        self.badge = tk.Label(card, text="", padx=10, pady=4, anchor='w', fg=colours.ROW_FG)
        self.badge_bg = self.badge.cget('bg')
        self.badge.grid(row=3, column=0, columnspan=6, sticky='w', pady=(10, 0))

        trial = ttk.LabelFrame(right, text=" 3. Try a new capacity ", padding=(14, 10))
        trial.grid(row=1, column=0, sticky='ew', pady=(14, 0))
        line = ttk.Frame(trial)
        line.pack(fill='x')
        ttk.Label(line, text="New capacity", font=self.fonts['strong']).pack(side='left')
        self.new_var = tk.StringVar()
        new_entry = ttk.Entry(line, textvariable=self.new_var, width=8)
        new_entry.pack(side='left', padx=10)
        new_entry.bind('<Return>', lambda e: self.add_to_check())
        ttk.Button(line, text="Check", style='Accent.TButton', command=self.add_to_check).pack(side='left')
        ttk.Button(line, text="Remove room", command=self.remove_from_check).pack(side='left', padx=(18, 4))
        ttk.Button(line, text="Start over", command=self.start_over).pack(side='left', padx=4)
        ttk.Label(trial, text="To check several rooms together, pick another room in the same building and press Check again.",
                  font=self.fonts['caption'], foreground='#6A6A6A').pack(anchor='w', pady=(6, 0))
        self.message_var = tk.StringVar()
        ttk.Label(trial, textvariable=self.message_var, foreground='#B00020').pack(anchor='w')

        results = ttk.LabelFrame(right, text=" 4. Result ", padding=(14, 10))
        results.grid(row=2, column=0, sticky='nsew', pady=(14, 0))
        results.columnconfigure(0, weight=1)
        results.rowconfigure(3, weight=1)
        ttk.Label(results, text="Rooms in this check", font=self.fonts['strong']).grid(row=0, column=0, sticky='w')
        self.check_tree = self.make_tree(results, [('Room', 130), ('Capacity now', 150), ('Proposed', 80),
                                                   ('Per code load', 100), ('Result', 330)], height=4)
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
        prop = self.building_var.get()
        floors = sorted(self.rooms.loc[self.rooms['property'] == prop, 'floor'].unique()) if prop != ANY else []
        self.floor_box['values'] = [ANY] + floors
        self.floor_var.set(ANY)
        self.search_var.set('')
        self.search()

    def search(self):
        prop = None if self.building_var.get() == ANY else self.building_var.get()
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
        self.card_vars["Room capacity now"].set("not visited" if pd.isna(capacity) else f"{int(capacity)}  ({r['capacity_source']})")
        self.card_vars["Per code load"].set('-' if pd.isna(r['area_per_person_m2'])
                                            else f"{r['per_code_load']}  ({r['area_per_person_m2']:g} m² per person)")
        colour, text = room_status_text(r)
        self.badge.configure(text=text, bg=colours.ROW_BG.get(colour, self.badge_bg))
        self.new_var.set(str(self.changes[room_id]) if room_id in self.changes else '')
        if not self.changes:
            self.show_floor_now(r['property'], r['floor'])

    def show_floor_now(self, prop, floor):
        zones = self.result['zones']
        zones = zones[(zones['property'] == prop) & (zones['floor'] == floor)].sort_values('zone_wing')
        self.zone_label.set(f"Floor {floor} exits now: occupant load vs exit capacity")
        self.zone_tree.delete(*self.zone_tree.get_children())
        for _, z in zones.iterrows():
            if z['status'] == egress.STATUS_NOT_SURVEYED:
                verdict, capacity = egress.CANT_CHECK, '-'
            else:
                over = int(z['total_load']) - int(z['exit_capacity'])
                verdict = f"over exit capacity by {over}" if over > 0 else 'within exit capacity'
                capacity = z['exit_capacity']
            name = f"Floor {z['floor']}" + (f" wing {z['zone_wing']}" if z['zone_wing'] else '')
            self.zone_tree.insert('', 'end', values=[name, z['total_load'], capacity, verdict], tags=(egress.zone_colour(z),))

    # the check -> nothing is saved
    def add_to_check(self):
        self.message_var.set('')
        if self.room is None:
            self.message_var.set("Pick a room first.")
            return
        try:
            new = int(self.new_var.get().strip())
            if new < 0:
                raise ValueError
        except ValueError:
            self.message_var.set("Type a whole number (0 or more).")
            return
        if self.changes:
            building = self.rooms.loc[self.rooms['room_id'] == next(iter(self.changes)), 'property'].iloc[0]
            if building != self.room['property']:
                if not messagebox.askyesno("New check",
                                           f"This check holds rooms in {building}.\nStart a new check for "
                                           f"{self.room['property']}?", parent=self.root):
                    return
                self.changes = {}
        self.changes[self.room['room_id']] = new
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
            self.check = egress.check_capacities(self.rooms, self.exits, self.factors, self.changes)
        except ValueError as err:
            self.message_var.set(str(err))
            self.changes = {}
            self.check = None
            return
        for r in self.check['rooms']:
            now = 'not visited (per code)' if r['current'] is None else f"{r['current']} ({r['current_source']})"
            verdict = r['verdict'] + ('' if r['in_scope'] else '  (out of scope)')
            self.check_tree.insert('', 'end', iid=f"r{r['room_id']}", values=[f"Floor {r['floor']}  {r['space']}", now,
                                   r['proposed'], r['per_code_load'], verdict], tags=(r['colour'],) if r['colour'] else ())
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
