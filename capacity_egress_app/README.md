# Capacity & Egress App

A desktop app for UVic Facilities Management that keeps the record of **room capacities** and checks whether each floor's exits can still carry everyone under the **BC Building Code 2024**.

It replaces editing Excel by hand. A project manager who gets an OREM request ("can B303 go from 32 to 36?") opens the app, finds the room, types 36, sees whether the floor is still within its exit capacity, and saves or cancels. Every change is recorded with who made it, when and why.

**Status: in design.** Nothing runs yet. Build step 1 (database + first import) is next. The decision behind this project is in [`docs/adr/0001-sqlite-tkinter-system-of-record.md`](../docs/adr/0001-sqlite-tkinter-system-of-record.md), and the vocabulary is in [`GLOSSARY.md`](../GLOSSARY.md).

It's still a **screening tool, not a code determination**. Results say "within capacity, review before acting" or "review", never "approved".

---

## Why an app

Until now the data lived in Excel: the space report exported from FMIS (with Carl's counts added) and `floor_exits.xlsx`. That stopped working once other people needed to change it:

- saving the space report from Python destroys its slicers
- a file open in Excel blocks everyone else's save
- there is no record of who changed a number, or why
- a second, hand-kept copy of the counts drifts from the first

Mark asked for a way to change a room's capacity without opening the Excel files. This is that.

## How it will work

- **One SQLite database file** in the project folder on the S: drive. It's the only place anyone types.
- **A Tkinter desktop app** installed on each user's Windows machine (Python + `pandas` + `openpyxl`). Everyone who has it can edit everything.
- **The FMIS space report is read-only input.** It supplies the list of rooms. The app never writes to it.
- **Excel only comes out as exports:** a capacity export in the space report layout (for the FMIS capacity import), and the results workbook (the 4-sheet egress output).

### What a user can do
- Search a room (`B303`) or browse building → floor
- See each zone's occupant load vs exit capacity, and each room's capacity and source
- **Change capacity**: preview the zone result, then save or cancel
- Add or edit an exit (same checks as the Excel exits sheet)
- Edit code factors (m² per person, mm per person, settings), with a required building code clause reference
- Keep one note per room and per exit
- Open the room's photo folder
- Export the capacity file and the results workbook

### Rules the data follows
- **Room capacity** is the accepted number of people for a room. Its **source** is `site count`, `PM change` or `per code` (not visited yet, so the area-based code number is used).
- FMIS shows 0 for most rooms by default, so **a 0 only counts as a real count on a visited room**. Numbers FMIS already holds for unvisited rooms are kept for comparison but not used in the calculation.
- Every change is logged: old value, new value, who, when, why.
- The app's value wins over FMIS. When a new space report disagrees, the room is flagged, never overwritten.
- A room that disappears from the space report is kept and flagged as a **missing room**, never deleted.
- The database is backed up each day the app opens, and the last 30 copies are kept.

## Build roadmap

Each step is written by Carl and checked against known numbers before moving on.

| Step | What | Check | Status |
|---|---|---|---|
| 1 | Database schema + first import (space report, exits, code factors, visited rooms) | 19,451 rooms, 10 exits | next |
| 2 | Calculation reads from the database (shared with the terminal script) | 15 tests pass, Turpin 3 B ≈ 161 vs 288 | |
| 3 | Read-only GUI: search, browse, zones + rooms, open photos | | |
| 4 | Change capacity: preview, audit log, user nickname | | |
| 5 | Exits + code factors editing | | |
| 6 | Capacity export, results workbook, daily backup | | |
| 7 | Install on Mark's machine + written instructions | | |

## Folder layout (planned)

```
capacity_egress_app/
  README.md
  capacity_db.py           database schema, imports, space report refresh
  build_database.py        one-time first import
  test_capacity_db.py      pytest
  data/                    capacity.db while developing (gitignored)
```

## Related projects in this repo

- [`exiting_capacity_calculation`](../exiting_capacity_calculation/): the egress calculation this app builds on. Its config CSVs seed the code factors, and its `floor_exits.xlsx` seeds the exits.
- [`facility_folder_automation`](../facility_folder_automation/): builds the `buildings/Property/Floor/Space` photo folders that the app's **Open photos** button opens.
