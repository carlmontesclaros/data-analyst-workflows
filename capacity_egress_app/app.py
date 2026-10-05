import os
import sys
import getpass
import sqlite3
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import pandas as pd
import capacity_db as db
import egress
import exports

# configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = db.DB_PATH                                   # step 7: point this at the S: drive copy
BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")
PHOTOS_DIR_WINDOWS = (r"S:\_Buildings and Properties\BP065 - Capital Projects\Project Planning Services"
                      r"\Space Allocation Process\2026 - Room capacity project\buildings")
PHOTOS_DIR_DEV = os.path.join(BASE_DIR, "..", "facility_folder_automation", "buildings")
PHOTOS_DIR = PHOTOS_DIR_WINDOWS if sys.platform == 'win32' else PHOTOS_DIR_DEV
BAD_CHARS = '/\\:*?"<>|'                               # same as automation.py sanitize()
POLL_MS = 20000                                        # check for other people's saves every 20 s
ALL = '(all)'

STATUS_TAGS = {egress.STATUS_REVIEW: 'review', egress.STATUS_WITHIN: 'within', egress.STATUS_NOT_SURVEYED: 'not_surveyed'}

def sanitize(name):
    for c in BAD_CHARS:
        name = name.replace(c, '-')
    return name.strip()

def text_or_blank(v):
    return '' if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

def open_path(path):
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])


class App:
    def __init__(self, root, conn, user_login, user_name):
        self.root = root
        self.conn = conn
        self.user_login = user_login
        self.user_name = user_name
        root.title(f"Capacity & Egress - {user_name}")
        root.geometry("1400x820")
        self.build_widgets()
        self.reload()
        self.root.after(POLL_MS, self.poll)

    # data -> whole campus once, then only the floor that changed
    def reload(self):
        self.root.config(cursor='watch')
        self.root.update_idletasks()
        try:
            self.rooms = db.load_rooms(self.conn)
            self.exits = db.load_exits(self.conn)
            self.factors = db.load_code_factors(self.conn)
            self.result = egress.calculate(self.rooms, self.exits, self.factors)
            self.seen_version = db.data_version(self.conn)
            self.properties = sorted(self.rooms['property'].unique())
            self.building_box['values'] = self.properties
            self.show()
        finally:
            self.root.config(cursor='')

    # other people's saves -> reload when the database changed since this app last looked
    def refresh_if_changed(self):
        if db.data_version(self.conn) != self.seen_version:
            self.reload()
            self.status_var.set("Updated with changes someone else saved")
            return True
        return False

    def poll(self):
        try:
            if self.root.grab_current() is None:      # not while a dialog is open
                self.refresh_if_changed()
        except sqlite3.Error:
            pass                                      # drive busy or offline -> try again next time
        self.root.after(POLL_MS, self.poll)

    def manual_refresh(self):
        self.reload()
        self.status_var.set(f"Refreshed at {pd.Timestamp.now():%H:%M:%S}")

    # one place for every failed save
    def save_failed(self, err, parent=None):
        if isinstance(err, db.StaleDataError):
            messagebox.showwarning("Changed by someone else", str(err), parent=parent)
            self.reload()
        elif isinstance(err, sqlite3.Error):
            messagebox.showerror("Not saved", "The database is busy or the S: drive can't be reached. "
                                 f"Nothing was saved; try again in a moment.\n\n({err})", parent=parent)
        else:
            messagebox.showerror("Not saved", str(err), parent=parent)

    def floor_result(self, prop, floor, rooms=None):
        return egress.calculate_floor(self.rooms if rooms is None else rooms, self.exits, self.factors, prop, floor)

    # layout
    def build_widgets(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill='x')
        ttk.Label(top, text="Search room / building:").pack(side='left')
        self.search_var = tk.StringVar()
        search = ttk.Entry(top, textvariable=self.search_var, width=28)
        search.pack(side='left', padx=4)
        search.bind('<Return>', lambda e: self.search())
        ttk.Button(top, text="Search", command=self.search).pack(side='left')
        ttk.Label(top, text="   Building:").pack(side='left')
        self.building_var = tk.StringVar()
        self.building_box = ttk.Combobox(top, textvariable=self.building_var, width=45, state='readonly')
        self.building_box.pack(side='left', padx=4)
        self.building_box.bind('<<ComboboxSelected>>', lambda e: self.pick_building())
        ttk.Label(top, text="Floor:").pack(side='left')
        self.floor_var = tk.StringVar(value=ALL)
        self.floor_box = ttk.Combobox(top, textvariable=self.floor_var, width=14, state='readonly')
        self.floor_box.pack(side='left', padx=4)
        self.floor_box.bind('<<ComboboxSelected>>', lambda e: self.show())

        menu = ttk.Frame(self.root, padding=(6, 0))
        menu.pack(fill='x')
        for text, cmd in [("Refresh", self.manual_refresh),
                          ("Code factors", self.edit_code_factors), ("Refresh space report", self.refresh_report),
                          ("Export results workbook", self.export_results), ("Export capacity file", self.export_capacity),
                          ("Change my name", self.change_name)]:
            ttk.Button(menu, text=text, command=cmd).pack(side='left', padx=2)

        panes = ttk.PanedWindow(self.root, orient='vertical')
        panes.pack(fill='both', expand=True, padx=6, pady=6)

        # zones
        zone_frame = ttk.LabelFrame(panes, text="Zones: occupant load vs exit capacity")
        self.zone_tree = self.make_tree(zone_frame, [
            ('floor', 70), ('zone_wing', 60), ('status', 260), ('total_load', 90), ('exit_capacity', 100),
            ('exit_count', 70), ('rooms_counted', 100), ('rooms_in_scope', 100), ('link_inflow', 80), ('flags', 420)], height=7)
        self.zone_tree.tag_configure('review', background='#F8CBAD')
        self.zone_tree.tag_configure('within', background='#C6EFCE')
        self.zone_tree.tag_configure('not_surveyed', background='#E7E6E6')
        self.zone_tree.bind('<<TreeviewSelect>>', lambda e: self.pick_zone())
        panes.add(zone_frame, weight=2)

        # rooms
        room_frame = ttk.LabelFrame(panes, text="Rooms")
        buttons = ttk.Frame(room_frame)
        buttons.pack(fill='x')
        for text, cmd in [("Change capacity", self.change_capacity), ("Room note", self.room_note),
                          ("Room history", self.room_history), ("Open photos", self.open_photos)]:
            ttk.Button(buttons, text=text, command=cmd).pack(side='left', padx=2, pady=2)
        self.room_tree = self.make_tree(room_frame, [
            ('property', 200), ('floor', 50), ('space', 70), ('sub_category', 220), ('area_m2', 70), ('room_type', 80),
            ('per_code_load', 90), ('capacity', 70), ('capacity_source', 90), ('load_used', 75), ('in_scope', 65),
            ('flag', 180), ('note', 250)], height=12)
        self.room_tree.tag_configure('missing', foreground='#A00000')
        self.room_tree.bind('<Double-1>', lambda e: self.change_capacity())
        panes.add(room_frame, weight=4)

        # exits
        exit_frame = ttk.LabelFrame(panes, text="Exits")
        buttons = ttk.Frame(exit_frame)
        buttons.pack(fill='x')
        for text, cmd in [("Add exit", self.add_exit), ("Edit exit", self.edit_exit), ("Delete exit", self.delete_exit),
                          ("Exit note", self.exit_note), ("Exit history", self.exit_history)]:
            ttk.Button(buttons, text=text, command=cmd).pack(side='left', padx=2, pady=2)
        self.exit_tree = self.make_tree(exit_frame, [
            ('floor', 50), ('wing', 45), ('exit_id', 180), ('exit_type', 90), ('clear_width_cm', 100), ('persons', 70),
            ('counts_as_exit', 100), ('width_check', 220), ('into_wing', 70), ('measured_date', 100),
            ('measured_by', 90), ('notes', 250)], height=5)
        self.exit_tree.bind('<Double-1>', lambda e: self.edit_exit())
        panes.add(exit_frame, weight=2)

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, padding=4, relief='sunken').pack(fill='x', side='bottom')

    def make_tree(self, parent, columns, height):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=[c for c, _ in columns], show='headings', height=height)
        for col, width in columns:
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor='w', stretch=False)
        ys = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        xs = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        tree.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        xs.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    # browsing
    def pick_building(self):
        prop = self.building_var.get()
        floors = sorted(self.rooms.loc[self.rooms['property'] == prop, 'floor'].unique())
        self.floor_box['values'] = [ALL] + floors
        self.floor_var.set(ALL)
        self.search_var.set('')
        self.show()

    def search(self):
        term = self.search_var.get().strip().lower()
        if not term:
            return
        props = [p for p in self.properties if term in p.lower()]
        if len(props) == 1:
            self.building_var.set(props[0])
            self.pick_building()
            return
        self.building_var.set('')
        self.floor_box['values'] = []
        self.floor_var.set(ALL)
        self.show()

    def selected_rooms(self):
        rooms = self.result['rooms']
        prop, floor, term = self.building_var.get(), self.floor_var.get(), self.search_var.get().strip().lower()
        if prop:
            rooms = rooms[rooms['property'] == prop]
            if floor and floor != ALL:
                rooms = rooms[rooms['floor'] == floor]
        elif term:
            rooms = rooms[rooms['space'].str.lower().str.contains(term, regex=False)
                          | rooms['property'].str.lower().str.contains(term, regex=False)]
        else:
            rooms = rooms.iloc[0:0]
        return rooms

    def show(self):
        keep = {tree: tree.selection() for tree in (self.room_tree, self.exit_tree)}
        self.fill_lists()
        # same room / exit still selected after a refresh
        for tree, sel in keep.items():
            still = [i for i in sel if tree.exists(i)]
            if still:
                tree.selection_set(still)
                tree.see(still[0])

    def fill_lists(self):
        rooms = self.selected_rooms()
        keys = set(zip(rooms['property'], rooms['floor']))
        zones = self.result['zones']
        zones = zones[[k in keys for k in zip(zones['property'], zones['floor'])]]
        exits = self.result['exits']
        exits = exits[[k in keys for k in zip(exits['property'], exits['floor'])]]

        self.zone_tree.delete(*self.zone_tree.get_children())
        for i, z in zones.sort_values(['property', 'floor', 'zone_wing']).iterrows():
            values = [z['floor'] if self.building_var.get() else f"{z['property']} {z['floor']}"] + \
                     [z[c] for c in ['zone_wing', 'status', 'total_load', 'exit_capacity', 'exit_count',
                                     'rooms_counted', 'rooms_in_scope', 'link_inflow', 'flags']]
            self.zone_tree.insert('', 'end', iid=f"z{i}", values=values, tags=(STATUS_TAGS.get(z['status'], ''),))

        self.room_tree.delete(*self.room_tree.get_children())
        for _, r in rooms.sort_values(['property', 'floor', 'space']).head(3000).iterrows():
            flag = []
            if r['in_latest_report'] == 0:
                flag.append('missing room')
            if pd.notna(r['fmis_capacity']) and pd.notna(r['capacity']) and int(r['fmis_capacity']) != int(r['capacity']):
                flag.append(f"FMIS says {int(r['fmis_capacity'])}")
            cap = '' if pd.isna(r['capacity']) else int(r['capacity'])
            values = [r['property'], r['floor'], r['space'], text_or_blank(r['sub_category']), r['area_m2'], text_or_blank(r['room_type']),
                      r['per_code_load'], cap, r['capacity_source'], r['load_used'], 'yes' if r['in_scope'] else 'no',
                      '; '.join(flag), text_or_blank(r['note'])]
            self.room_tree.insert('', 'end', iid=f"r{int(r['room_id'])}", values=values,
                                  tags=('missing',) if r['in_latest_report'] == 0 else ())

        self.exit_tree.delete(*self.exit_tree.get_children())
        for _, e in exits.sort_values(['floor', 'wing', 'exit_id']).iterrows():
            width = '' if pd.isna(e['clear_width_cm']) else int(e['clear_width_cm'])
            values = [e['floor'], e['wing'], e['exit_id'], e['exit_type'], width, e['persons'],
                      'yes' if e['counts_as_exit'] else 'no', e['width_check'], e['into_wing'],
                      text_or_blank(e['measured_date']), text_or_blank(e['measured_by']), text_or_blank(e['notes'])]
            self.exit_tree.insert('', 'end', iid=f"e{int(e['exit_pk'])}", values=values)

        shown = f"{len(rooms)} rooms" + (" (first 3000 shown)" if len(rooms) > 3000 else '')
        self.status_var.set(f"{shown}, {len(zones)} zones, {len(exits)} exits   |   database: {DB_PATH}")

    def pick_zone(self):
        sel = self.zone_tree.selection()
        if not sel or not self.building_var.get():
            return
        floor = self.zone_tree.item(sel[0], 'values')[0]
        if self.floor_var.get() != floor:
            self.floor_var.set(floor)
            self.show()

    def current_room(self):
        sel = self.room_tree.selection()
        if not sel:
            messagebox.showinfo("Pick a room", "Select a room in the Rooms list first.")
            return None
        rid = int(sel[0][1:])
        self.refresh_if_changed()                     # start from the latest values
        rooms = self.result['rooms'].set_index('room_id')
        if rid not in rooms.index:
            messagebox.showinfo("Room not found", "That room is no longer in the database.")
            return None
        return rooms.loc[rid].to_dict() | {'room_id': rid}

    def current_exit_pk(self):
        sel = self.exit_tree.selection()
        if not sel:
            messagebox.showinfo("Pick an exit", "Select an exit in the Exits list first.")
            return None
        pk = int(sel[0][1:])
        self.refresh_if_changed()
        if pk not in set(self.exits['exit_pk']):
            messagebox.showinfo("Exit not found", "Someone else deleted that exit. The list has been refreshed.")
            return None
        return pk

    def after_change(self, message):
        self.reload()
        self.status_var.set(message)

    # change capacity -> preview the zone, then save or cancel
    def change_capacity(self):
        room = self.current_room()
        if room is None:
            return
        win = tk.Toplevel(self.root)
        win.title(f"Change capacity - {room['property']} {room['space']}")
        win.transient(self.root)
        win.grab_set()
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill='both', expand=True)

        current = '' if pd.isna(room['capacity']) else str(int(room['capacity']))
        ttk.Label(frame, text=f"{room['property']} floor {room['floor']} room {room['space']}",
                  font=('TkDefaultFont', 11, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(frame, text=f"Room capacity now: {current or '-'} ({room['capacity_source']}),  "
                              f"per code load: {room['per_code_load']}").grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 8))

        ttk.Label(frame, text="New capacity:").grid(row=2, column=0, sticky='w')
        cap_var = tk.StringVar(value=current)
        cap_entry = ttk.Entry(frame, textvariable=cap_var, width=10)
        cap_entry.grid(row=2, column=1, sticky='w')
        cap_entry.focus_set()
        # undo while typing -> back to the value the box opened with
        cap_entry.bind('<Control-z>', lambda e: cap_var.set(current))
        cap_entry.bind('<Command-z>', lambda e: cap_var.set(current))

        ttk.Label(frame, text="Source:").grid(row=3, column=0, sticky='w')
        source_var = tk.StringVar(value='PM change')
        src = ttk.Frame(frame)
        src.grid(row=3, column=1, columnspan=2, sticky='w')
        for s in db.CAPACITY_SOURCES:
            ttk.Radiobutton(src, text=s, value=s, variable=source_var).pack(side='left')

        ttk.Label(frame, text="Why:").grid(row=4, column=0, sticky='w')
        why_var = tk.StringVar()
        why_entry = ttk.Entry(frame, textvariable=why_var, width=50)
        why_entry.grid(row=4, column=1, columnspan=2, sticky='w')
        why_entry.bind('<Control-z>', lambda e: why_var.set(''))

        preview_var = tk.StringVar()
        ttk.Label(frame, textvariable=preview_var, justify='left', wraplength=560).grid(
            row=5, column=0, columnspan=3, sticky='w', pady=8)

        before = self.floor_result(room['property'], room['floor'])['zones']

        def preview(*_):
            try:
                new = int(cap_var.get())
                if new < 0:
                    raise ValueError
            except ValueError:
                preview_var.set("Type a whole number (0 or more).")
                return None
            rooms = self.rooms.copy()
            mask = rooms['room_id'] == room['room_id']
            rooms.loc[mask, 'capacity'] = new
            rooms.loc[mask, 'capacity_source'] = source_var.get()
            after = self.floor_result(room['property'], room['floor'], rooms=rooms)['zones']
            lines = ["Preview (not saved):"]
            for _, z in after.iterrows():
                b = before[before['zone_wing'] == z['zone_wing']]
                was = f"{b.iloc[0]['total_load']} -> " if len(b) else ''
                lines.append(f"  floor {z['floor']}{' wing ' + z['zone_wing'] if z['zone_wing'] else ''}: "
                             f"occupant load {was}{z['total_load']} vs exit capacity {z['exit_capacity']}  [{z['status']}]")
                if z['flags']:
                    lines.append(f"     {z['flags']}")
            preview_var.set('\n'.join(lines))
            return new

        cap_var.trace_add('write', preview)
        source_var.trace_add('write', preview)
        preview()

        def save():
            new = preview()
            if new is None:
                return
            try:
                db.change_capacity(self.conn, room['room_id'], new, source_var.get(),
                                   self.user_login, self.user_name, why_var.get(),
                                   expected=(room['capacity'], room['capacity_source']))
            except (ValueError, sqlite3.Error) as err:
                if isinstance(err, db.StaleDataError):
                    win.destroy()
                    self.save_failed(err)
                else:
                    self.save_failed(err, parent=win)
                return
            win.destroy()
            self.after_change(f"saved: {room['property']} {room['space']} capacity {current or '-'} -> {new}")

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky='e')
        ttk.Button(buttons, text="Save", command=save).pack(side='left', padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side='left')
        win.bind('<Escape>', lambda e: win.destroy())

    # notes -> one per room, one per exit
    def ask_text(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        box = tk.Text(win, width=60, height=8, wrap='word', undo=True)
        box.insert('1.0', text)
        box.pack(padx=8, pady=8)
        result = {'text': None}

        def ok():
            result['text'] = box.get('1.0', 'end').strip()
            win.destroy()
        buttons = ttk.Frame(win)
        buttons.pack(fill='x', padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Save", command=ok).pack(side='right')
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side='right', padx=4)
        self.root.wait_window(win)
        return result['text']

    def room_note(self):
        room = self.current_room()
        if room is None:
            return
        note = self.ask_text(f"Note - {room['property']} {room['space']}", text_or_blank(room['note']))
        if note is None:
            return
        try:
            if db.set_note(self.conn, 'rooms', room['room_id'], note, self.user_login, self.user_name,
                           expected=room['note']):
                self.after_change(f"note saved: {room['space']}")
        except (ValueError, sqlite3.Error) as err:
            self.save_failed(err)

    def exit_note(self):
        pk = self.current_exit_pk()
        if pk is None:
            return
        e = self.exits.set_index('exit_pk').loc[pk]
        note = self.ask_text(f"Note - {e['exit_id']}", text_or_blank(e['notes']))
        if note is None:
            return
        try:
            if db.set_note(self.conn, 'exits', pk, note, self.user_login, self.user_name, expected=e['notes']):
                self.after_change(f"note saved: {e['exit_id']}")
        except (ValueError, sqlite3.Error) as err:
            self.save_failed(err)

    def show_history(self, title, df):
        win = tk.Toplevel(self.root)
        win.title(title)
        if df.empty:
            ttk.Label(win, text="No changes recorded.", padding=12).pack()
            return
        tree = self.make_tree(win, [(c, 130 if c != 'why' else 220) for c in df.columns], height=12)
        for _, row in df.iterrows():
            tree.insert('', 'end', values=['' if pd.isna(v) else v for v in row])

    def room_history(self):
        room = self.current_room()
        if room is not None:
            self.show_history(f"History - {room['property']} {room['space']}", db.history(self.conn, 'rooms', room['room_id']))

    def exit_history(self):
        pk = self.current_exit_pk()
        if pk is not None:
            self.show_history("Exit history", db.history(self.conn, 'exits', pk))

    def open_photos(self):
        room = self.current_room()
        if room is None:
            return
        path = os.path.join(PHOTOS_DIR, sanitize(room['property']), f"Floor {sanitize(room['floor'])}", sanitize(room['space']))
        if not os.path.isdir(path):
            messagebox.showinfo("No photo folder", f"No folder yet:\n{path}")
            return
        open_path(path)

    # exits -> same checks as the excel sheet
    def exit_form(self, title, values):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        frame = ttk.Frame(win, padding=10)
        frame.pack()
        types = sorted(self.factors['width_factors']['exit_type'])
        fields = [('property', 'Property', None), ('floor', 'Floor', None), ('wing', 'Wing (A, B... blank = one zone)', None),
                  ('into_wing', 'Into wing (link door only)', None), ('exit_id', 'Exit id (e.g. S4 - doorway)', None),
                  ('exit_type', 'Exit type', types), ('clear_width_cm', 'Clear width (cm, narrowest, round down)', None),
                  ('measured_date', 'Measured date (YYYY-MM-DD)', None), ('measured_by', 'Measured by', None),
                  ('narrowest_point', 'Narrowest point', None), ('photo_ref', 'Photo ref', None), ('notes', 'Notes', None)]
        vars_ = {}
        for i, (key, label, choices) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky='w', pady=1)
            value = values.get(key)
            v = tk.StringVar(value='' if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value))
            if choices:
                w = ttk.Combobox(frame, textvariable=v, values=choices, state='readonly', width=40)
            else:
                w = ttk.Entry(frame, textvariable=v, width=43)
            if key in ('property', 'floor'):
                w.configure(state='readonly')
            w.grid(row=i, column=1, sticky='w')
            vars_[key] = v
        result = {'values': None}

        def ok():
            result['values'] = {k: v.get() for k, v in vars_.items()}
            win.destroy()
        buttons = ttk.Frame(frame)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky='e', pady=(8, 0))
        ttk.Button(buttons, text="Save", command=ok).pack(side='left', padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side='left')
        self.root.wait_window(win)
        return result['values']

    def save_exit_loop(self, title, values, exit_pk=None):
        expected = dict(values) if exit_pk is not None else db.NO_CHECK    # the exit as it was when the form opened
        while True:
            entered = self.exit_form(title, values)
            if entered is None:
                return
            try:
                db.save_exit(self.conn, entered, self.user_login, self.user_name, exit_pk=exit_pk, expected=expected)
            except db.StaleDataError as err:
                self.save_failed(err)
                return
            except (ValueError, sqlite3.Error) as err:
                self.save_failed(err)
                values = entered
                continue
            self.after_change(f"exit saved: {entered['property']} floor {entered['floor']} {entered['exit_id']}")
            return

    def add_exit(self):
        prop, floor = self.building_var.get(), self.floor_var.get()
        if not prop or floor in ('', ALL):
            messagebox.showinfo("Pick a floor", "Pick a building and a floor first.")
            return
        self.save_exit_loop("Add exit", {'property': prop, 'floor': floor,
                                         'measured_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                                         'measured_by': self.user_name})

    def edit_exit(self):
        pk = self.current_exit_pk()
        if pk is None:
            return
        values = self.exits.set_index('exit_pk').loc[pk].to_dict()
        self.save_exit_loop("Edit exit", values, exit_pk=pk)

    def delete_exit(self):
        pk = self.current_exit_pk()
        if pk is None:
            return
        e = self.exits.set_index('exit_pk').loc[pk]
        why = simpledialog.askstring("Delete exit", f"Delete {e['exit_id']} on {e['property']} floor {e['floor']}?\nWhy:",
                                     parent=self.root)
        if why is None:
            return
        try:
            db.delete_exit(self.conn, pk, self.user_login, self.user_name, why, expected=e.to_dict())
        except (ValueError, sqlite3.Error) as err:
            self.save_failed(err)
            return
        self.after_change(f"exit deleted: {e['exit_id']}")

    # code factors -> clause reference required, preview zones that change status
    def edit_code_factors(self):
        win = tk.Toplevel(self.root)
        win.title("Code factors")
        win.geometry("900x560")
        notebook = ttk.Notebook(win)
        notebook.pack(fill='both', expand=True, padx=6, pady=6)
        trees = {}
        for table in db.CODE_FACTOR_KEYS:
            df = self.factors[table]
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=table)
            tree = self.make_tree(tab, [(c, 160) for c in df.columns], height=14)
            for _, row in df.iterrows():
                tree.insert('', 'end', iid=str(row[db.CODE_FACTOR_KEYS[table]]),
                            values=['' if pd.isna(v) else v for v in row])
            trees[table] = tree

        form = ttk.Frame(win, padding=6)
        form.pack(fill='x')
        field_var, value_var, clause_var, why_var, info_var = (tk.StringVar() for _ in range(5))
        ttk.Label(form, text="Field:").grid(row=0, column=0, sticky='w')
        field_box = ttk.Combobox(form, textvariable=field_var, state='readonly', width=24)
        field_box.grid(row=0, column=1, sticky='w')
        ttk.Label(form, text="New value:").grid(row=0, column=2, sticky='w', padx=(10, 0))
        ttk.Entry(form, textvariable=value_var, width=24).grid(row=0, column=3, sticky='w')
        ttk.Label(form, text="Clause (required):").grid(row=1, column=0, sticky='w')
        ttk.Entry(form, textvariable=clause_var, width=40).grid(row=1, column=1, columnspan=2, sticky='w')
        ttk.Label(form, text="Why:").grid(row=1, column=2, sticky='e')
        ttk.Entry(form, textvariable=why_var, width=40).grid(row=1, column=3, sticky='w')
        ttk.Label(form, textvariable=info_var, wraplength=860, justify='left').grid(row=2, column=0, columnspan=5, sticky='w', pady=6)

        def selection():
            table = notebook.tab(notebook.select(), 'text')
            sel = trees[table].selection()
            return table, (sel[0] if sel else None)

        def on_select(*_):
            table, key = selection()
            cols = [c for c in self.factors[table].columns if c != db.CODE_FACTOR_KEYS[table]]
            field_box['values'] = cols
            if field_var.get() not in cols:
                field_var.set(cols[0])
            if key:
                row = self.factors[table].set_index(db.CODE_FACTOR_KEYS[table]).loc[key]
                value_var.set('' if pd.isna(row[field_var.get()]) else row[field_var.get()])
        for tree in trees.values():
            tree.bind('<<TreeviewSelect>>', on_select)
        notebook.bind('<<NotebookTabChanged>>', on_select)
        field_box.bind('<<ComboboxSelected>>', on_select)

        def converted(table, field, value):
            current = self.factors[table][field]
            if pd.api.types.is_numeric_dtype(current) and value.strip() != '':
                return float(value) if '.' in value else int(value)
            return value.strip() or None

        def changed_factors():
            table, key = selection()
            if not key or not field_var.get():
                raise ValueError("pick a row and a field")
            value = converted(table, field_var.get(), value_var.get())
            factors = {t: df.copy() for t, df in self.factors.items()}
            k = db.CODE_FACTOR_KEYS[table]
            factors[table][field_var.get()] = factors[table][field_var.get()].astype(object)
            factors[table].loc[factors[table][k] == key, field_var.get()] = value
            if pd.api.types.is_numeric_dtype(self.factors[table][field_var.get()]):
                factors[table][field_var.get()] = pd.to_numeric(factors[table][field_var.get()])
            return table, key, value, factors

        def preview():
            try:
                table, key, value, factors = changed_factors()
                after = egress.calculate(self.rooms, self.exits, factors)['zones']
            except (ValueError, KeyError) as err:
                info_var.set(f"can't preview: {err}")
                return
            before = self.result['zones']
            keys = ['floor_key', 'zone_wing']
            cols = ['status', 'total_load', 'exit_capacity']
            both = before[keys + cols].merge(after[keys + cols], on=keys, how='outer', suffixes=('_before', '_after'))
            status_changes = both[both['status_before'] != both['status_after']]
            load_changes = both[both['total_load_before'] != both['total_load_after']]
            cap_changes = both[both['exit_capacity_before'] != both['exit_capacity_after']]
            lines = [f"Preview: {table} {key} {field_var.get()} -> {value}",
                     f"  zones that change status: {len(status_changes)}   occupant load changes: {len(load_changes)}"
                     f"   exit capacity changes: {len(cap_changes)}"]
            for _, z in status_changes.head(10).iterrows():
                lines.append(f"  {z['floor_key']} {z['zone_wing']}: {z['status_before']} -> {z['status_after']}")
            for _, z in cap_changes.head(5).iterrows():
                lines.append(f"  {z['floor_key']} {z['zone_wing']}: load {z['total_load_after']}, "
                             f"exit capacity {z['exit_capacity_before']} -> {z['exit_capacity_after']}")
            info_var.set('\n'.join(lines))

        def save():
            try:
                table, key, value, _ = changed_factors()
                seen = self.factors[table].set_index(db.CODE_FACTOR_KEYS[table]).loc[key, field_var.get()]
                db.change_code_factor(self.conn, table, key, field_var.get(), value, clause_var.get(),
                                      self.user_login, self.user_name, why_var.get() or None, expected=seen)
            except (ValueError, sqlite3.Error) as err:
                if isinstance(err, db.StaleDataError):
                    win.destroy()
                    self.save_failed(err)
                else:
                    self.save_failed(err, parent=win)
                return
            win.destroy()
            self.after_change(f"code factor saved: {table} {key} {field_var.get()} = {value}")

        buttons = ttk.Frame(form)
        buttons.grid(row=3, column=0, columnspan=5, sticky='e')
        ttk.Button(buttons, text="Preview", command=preview).pack(side='left', padx=4)
        ttk.Button(buttons, text="Save", command=save).pack(side='left', padx=4)
        ttk.Button(buttons, text="Close", command=win.destroy).pack(side='left')

    # space report refresh -> room list only, capacities never touched
    def refresh_report(self):
        path = filedialog.askopenfilename(title="Pick the new space report", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            df = db.read_space_report(path)
        except ValueError as err:
            messagebox.showerror("Not a space report", str(err))
            return
        if not messagebox.askyesno("Refresh rooms", f"{len(df)} rows in {os.path.basename(path)}.\n"
                                   "Room capacities, sources, notes and room types are not changed.\nContinue?"):
            return
        try:
            # one transaction -> nobody sees a half-refreshed room list
            with db.write_transaction(self.conn):
                result = db.refresh_space_report(self.conn, df, os.path.basename(path))
                db.log_change(self.conn, self.user_login, self.user_name, 'rooms', 'all', 'space report', None,
                              os.path.basename(path), f"refresh: {result['matched']} matched, {result['new']} new, "
                              f"{result['missing']} missing")
        except sqlite3.Error as err:
            self.save_failed(err)
            return
        self.after_change("space report refreshed")
        messagebox.showinfo("Refreshed", f"matched: {result['matched']} (changed {result['changed']})\n"
                                         f"new rooms (per code): {result['new']}\nmissing rooms (kept, flagged): "
                                         f"{result['missing']}\nFMIS capacity disagrees with the app: {len(result['disagree'])}")

    # exports -> whole campus, or the building / floor picked
    def export_scope(self):
        prop, floor = self.building_var.get(), self.floor_var.get()
        props = [prop] if prop else None
        floors = [floor] if prop and floor not in ('', ALL) else None
        tag = '' if not prop else '_' + ''.join(c if c.isalnum() else '-' for c in prop) + (f"_floor_{floor}" if floors else '')
        return props, floors, tag

    def export_results(self):
        props, floors, tag = self.export_scope()
        path = filedialog.asksaveasfilename(title="Save results workbook", defaultextension='.xlsx',
                                            initialfile=f"exiting_capacity_results{tag}.xlsx")
        if not path:
            return
        try:
            counts = exports.write_results_workbook(self.result, path, props, floors)
        except PermissionError as err:
            messagebox.showerror("Not written", str(err))
            return
        self.status_var.set(f"written: {path}  {counts}")

    def export_capacity(self):
        props, floors, tag = self.export_scope()
        path = filedialog.asksaveasfilename(title="Save capacity file", defaultextension='.xlsx',
                                            initialfile=f"room_capacity_export{tag}.xlsx")
        if not path:
            return
        try:
            n = exports.write_capacity_export(self.result, path, props, floors)
        except PermissionError as err:
            messagebox.showerror("Not written", str(err))
            return
        self.status_var.set(f"written: {path}  ({n} rooms)")

    def change_name(self):
        name = simpledialog.askstring("Your name", "Name shown in the change log:", initialvalue=self.user_name,
                                      parent=self.root)
        if name and name.strip():
            db.set_user_name(self.conn, self.user_login, name.strip())
            self.user_name = name.strip()
            self.root.title(f"Capacity & Egress - {self.user_name}")


def main():
    root = tk.Tk()
    if not os.path.exists(DB_PATH):
        root.withdraw()
        messagebox.showerror("No database", f"{DB_PATH} doesn't exist.\nRun build_database.py once first.")
        return
    conn = db.connect(DB_PATH)
    db.create_schema(conn)                       # adds any table a newer version needs
    db.backup_database(conn, BACKUP_DIR)

    user_login = getpass.getuser()
    user_name = db.get_user_name(conn, user_login)
    if not user_name:
        root.withdraw()
        user_name = simpledialog.askstring("Your name", f"First time on this computer ({user_login}).\n"
                                           "Name to show in the change log:", parent=root)
        if not user_name or not user_name.strip():
            return
        user_name = user_name.strip()
        db.set_user_name(conn, user_login, user_name)
        root.deiconify()

    App(root, conn, user_login, user_name)
    root.mainloop()
    conn.close()


if __name__ == '__main__':
    main()
