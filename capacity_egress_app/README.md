# Capacity & Egress App

A desktop app for UVic Facilities Management that keeps the record of **room capacities** and checks whether each floor's exits can still carry everyone under the **BC Building Code 2024**.

It replaces editing Excel by hand. A project manager who gets an OREM request ("can B303 go from 32 to 36?") opens the app, finds the room, types 36, sees whether the floor is still within its exit capacity, and saves or cancels. Every change is recorded with who made it, when and why.

**Status: built, not yet installed.** Build steps 1–6 run and are tested (33 pytest tests) on the Mac dev copy. Step 7 (install on Mark's machine) is next. The decision behind this project is in [`docs/adr/0001-sqlite-tkinter-system-of-record.md`](../docs/adr/0001-sqlite-tkinter-system-of-record.md), and the vocabulary is in [`GLOSSARY.md`](../GLOSSARY.md).

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
- **A Tkinter desktop app** installed on each user's Windows machine (Python + `pandas` + `openpyxl`). **Editors** change the numbers; everyone else is a **viewer** and can only look things up and run capacity checks (see [Editors and viewers](#editors-and-viewers)).
- **The FMIS space report is read-only input.** It supplies the list of rooms. The app never writes to it.
- **Excel only comes out as exports:** the space report (Carl's own space report as the template, filled with the app's rooms), and the results workbook (the 4-sheet egress output).

### What a user can do
- Search a room (`B303`) or browse building → floor
- See each zone's occupant load vs exit capacity, and each room's capacity and source
- **Change capacity**: preview the zone result, then save or cancel
- **Change room type** (editors): pick a room type or go back to the sub-category default; previews the per code load and the zone, asks why, logged like a capacity change. A new space report never overwrites it
- Add or edit an exit (same checks as the Excel exits sheet)
- Edit code factors (m² per person, mm per person, settings), with a required building code clause reference
- Keep one note per room and per exit
- Open the room's photo folder
- Export the space report and the results workbook

### Rules the data follows
- **Room capacity** is the accepted number of people for a room. Its **source** is `site count`, `PM change` or `per code` (not visited yet, so the area-based code number is used).
- FMIS shows 0 for most rooms by default, so **a 0 only counts as a real count on a visited room**. Numbers FMIS already holds for unvisited rooms are kept for comparison but not used in the calculation.
- Every change is logged: old value, new value, who, when, why.
- The app's value wins over FMIS. When a new space report disagrees, the room is flagged, never overwritten.
- A room that disappears from the space report is kept and flagged as a **missing room**, never deleted.
- The database is backed up each day the app opens, and the last 30 copies are kept.

## Build roadmap

Steps 1–6 were built by Claude at Carl's request (2026-10-05), each checked against the known numbers before moving on.

| Step | What | Check | Status |
|---|---|---|---|
| 1 | Database schema + first import (space report, exits, code factors, visited rooms) | 19,451 rooms, 1,184 site count, 10 exits, 1,184 audit rows | done |
| 2 | Calculation reads from the database (`egress.py` + `exit_calc.py`) | 790 zones, Turpin 3 B 161 vs 288, Turpin 2 B 62 vs 1027, EOW 1 49 vs 288 | done |
| 3 | Read-only GUI: search, browse, zones + rooms, open photos | | done |
| 4 | Change capacity: preview, audit log, user nickname | | done |
| 5 | Exits + code factors editing | | done |
| 6 | Space report export, results workbook, daily backup | | done |
| 7 | Install on Mark's machine + written instructions | | next |
| 8 | Editors and viewers: editor list by Windows login, Editors screen, change log of adds/removes ([ADR 0003](../docs/adr/0003-editors-by-windows-login.md)) | a viewer can't open the editor screen; the last editor can't be removed | built 2026-10-13, not yet tried by Carl |
| 9 | Capacity check screen for everyone: search, try a number, floor result, summary .docx | DTB A120 → 300: needs justification (+117 over 183), Turpin 1 "can't check egress"; Turpin B303 24 → 160: wing B 161 → 297 vs 288, over by 9 | built 2026-10-13, not yet tried by Carl |
| 10 | Colours on rooms, zones and exits + one legend | campus: zones 787 grey / 3 green; rooms 664 green, 54 amber, 13,734 grey | built 2026-10-13 |

## Editors and viewers

Decided 2026-10-13 from Mark's answers ([ADR 0003](../docs/adr/0003-editors-by-windows-login.md)).

| | Editor | Viewer |
|---|---|---|
| Who | Mark, Carl, Carolyn, Karine, and whoever an editor adds | anyone else who opens the app (planning team; OREM later) |
| Opens on | the capacity check screen | the capacity check screen |
| Editor screen (today's full screen) | yes, with the **Editor screen** button | no |
| Change room capacities, exits, code factors, notes | yes, each logged with why | no |
| Load a space report, exports | yes | no |
| Add or remove editors | yes, on the **Editors** screen | no |

- **Who you are** comes from your Windows login (your own UVic account, on any PC). No password, nothing to type.
- **Adding an editor:** they open the app once (they show up on the Editors screen), then any editor ticks **Editor** beside their name. A login can also be typed in for someone who hasn't opened it yet. Every add and remove goes in the change log. The last editor can't be removed.
- **Never tick a shared or generic Windows account.** Everyone using it would be an editor.
- **First editor:** if the editor list is empty (a new database), the first person to open the app is asked to become the first editor. Carl opens it first after installing.
- **Who you are is asked from Windows**, not read from the `USERNAME` variable, so typing `set USERNAME=<an editor>` before starting the app doesn't work (`capacity_db.current_login`).
- **Every save checks the editor list itself**, not only the screens: change capacity, notes, exits, code factors and a space report refresh refuse a viewer once there is at least one editor (`require_editor`).
- **The lock is still inside the app.** Someone with write access to the S: drive folder could change the database file with other tools, including the change log. To-do list below.

## Capacity check screen

The first screen everyone sees. Built for a quick question like "can DTB A120 go from 250 to 300?" before emailing Mark.

1. **Search** a building, floor or room (`DTB A120`, `Turpin`, `A120`), or pick building → floor → room. The **Building** box takes typing: the list narrows to matching names (`tur`, `dtb`, `comp sci`; names that start with the text come first), **↓** opens it, **Enter** picks the top match (`match_buildings`, added 2026-10-16).
2. **Room card:** two rows of big values, column by column: **Now** (room type, area, room capacity and its source, per code load) and **With change** (what's typed in 3: changed values in blue, the rest say "same"). Each row has its coloured verdict, side by side. It updates as you pick a room type or type a number, before Check.
3. **Room type and/or new capacity → Check.** Picking another room type (supervisor feedback, 2026-10-16) shows that type's per code load next to the box; Check then judges the room against it, and an unvisited room's per code load changes the floor load (a visited room's floor load stays its count). Leave New capacity blank to try only the room type. **Add another room** checks several rooms in the same building together, so three small increases can't each look fine on their own.
4. **Result:**
   - **Room vs per code load:** "within per code", or **"needs justification, +N over"**. Over per code isn't refused: BCBC 2024 3.1.17.1.(1)(c) lets a room be designed for more people than the table, as long as the exits carry them and a sign is posted (3.1.17.1.(2)). Amber is project policy, so an editor looks into it. (It's a count **below** per code that the code says must "be shown".)
   - **Each zone on the floor:** occupant load now → with the change, against exit capacity: **within**, **over by N**, or **"Can't check egress: exits on this floor haven't been measured."** An unmeasured floor is never shown as fine.
5. **Save summary (.docx)**: one page to attach to the email to Mark. It lists, for each room, current capacity and source, proposed number, per code load and verdict; for each zone, occupant load now → after, exit capacity and verdict; the date, who ran it and the code edition. The footer reads "Screening only, not an approval. An editor reviews every change." The request's reason goes in the email. The file is written by the app itself, so nothing extra is installed.

The check screen **never saves**. An editor who wants to apply a change presses **Editor screen**: the check screen is replaced by the editor screen, opened on the room picked (if any), where Change capacity or Change room type previews the floor and asks why. The editor screen's **Building** box takes typing the same way. **← Check screen** on the editor screen switches back, showing anything just saved. One window at a time; closing the editor screen closes the app.

The look uses the Sun Valley ttk theme (MIT licence). Its files sit in the app folder, so there's nothing to install.

## Colours

Same meaning on every table. One legend sits on both screens.

| Colour | Rooms | Zones | Exits |
|---|---|---|---|
| Green | visited, capacity at or under the per code load | within exit capacity | width OK |
| Amber | capacity over the per code load: **needs justification** | REVIEW for any other flag (fewer than 2 exits, width review, link traffic both ways, ...) | width needs review |
| Red | | occupant load **over exit capacity** | width under the minimum |
| Grey | not visited (uses the per code load), or no per code load (excluded or unknown room type) | NOT SURVEYED (no exits measured) | not counted as an exit (open stair, unknown type) |
| No colour | out of scope (lounges, non-assignable) | | |

Red only ever means over a hard limit.

## Future (recorded, not built)

- **A web link for viewers**, so OREM and others don't need anything installed. Starts with asking UVic IT and Mark; Mark's comment on the NFR questions says there will be no outside hosting. `egress.py` already holds the calculation apart from the window, so a web version can reuse it.
- **"Request this change"**: a check saved as a request that editors approve or reject in the app.
- **Security to-do (needs IT or the workstation, can't be fixed in code):**
  - **S: drive folder permissions** from IT: the app folder, the `.db` and `backups/` writable by the editors only, read-only for everyone else. This is the only thing that stops someone editing the database (or the change log) with another SQLite tool, or running a changed copy of the app.
  - **Check the login on Windows** after installing: open the Editors screen and make sure your login there matches the one in the editor list (same spelling). `current_login` has only been tested on the Mac.
  - **Never tick a shared or generic Windows account** as an editor.
- The `.db` stays on the S: drive, not a SharePoint-synced folder (sync can corrupt it mid-save). Exports and the guide can go on SharePoint.

## Folder layout

```
capacity_egress_app/
  README.md
  app.py                   start-up (editor or viewer), the editor screen, the Editors screen
  check_screen.py          the capacity check screen everyone opens on
  colours.py               row colours + legend shared by both screens
  widgets.py               building box you can type in, theme loading, open a file or folder (both screens)
  excel_inputs.py          reads the space report and exits workbooks (header detection, first-import visited rule)
  capacity_db.py           schema, inserts, space report refresh, edits + audit log, editors, backup
  egress.py                occupant load vs exit capacity, read from the database; the one rule for room and zone verdicts
  code_factors.py          the only place that reads the code factor tables (room types, m2 per person, default type)
  exit_calc.py             the four core formulas (occupant load, exit persons, 50% rule, link share)
  exports.py               results workbook, space report export, capacity check summary (.docx)
  theme/sun_valley/        Sun Valley ttk theme files (MIT licence), loaded from the folder, nothing to install
  build_database.py        one-time first import
  test_*.py                pytest (88 tests)
  config/                  code factor CSVs, read once by build_database.py (after that, edit in the app)
  data/                    gitignored, local only
    capacity.db            the database
    backups/               daily copies, last 30
    input/                 space report + floor_exits.xlsx for the first import
    template/              the space report template the export fills (any .xlsx name)
    old_templates/         earlier templates (26-09-15 ROOM CAPACITY)
    old_results/           workbooks from the retired exit_capacity.py script
```

The terminal script `exiting_capacity_calculation/exit_capacity.py` was retired on 2026-10-05; the app replaces it. It's still in git history.

## Running it

From `capacity_egress_app/` (Mac: `python3`, Windows: `py`):

1. **Once:** `python3 build_database.py`. Reads the space report and `floor_exits.xlsx` from `data/input/` and the CSVs from `config/`, and writes `data/capacity.db`. It refuses to run if the database already exists.
2. `python3 app.py`. The first time on a computer, it asks for the name to show in the change log.
3. Tests: `python3 -m pytest`

Load a newer space report with **Refresh space report** in the app, not by rebuilding. It updates area and sub-category, adds new rooms (per code), flags missing rooms and never touches capacities.

### Export space report

**Export space report** fills the template in `data/template/` (Carl's space report, `carl_space_report_23sept.xlsx`) with the app's rooms: the whole campus, or the building / floor picked. The slicers and the BCBC table above the header stay as they are; only the rows of the room table (`Table1`, header on row 7) are replaced. Any saved filter is cleared, so every row shows.

| Column | Comes from |
|---|---|
| Property, Floor, Space, Building Number, Net Space (sq m), Space Category, Space Sub-Category | the app |
| Capacity (Occupants) | the site count, for visited rooms; otherwise whatever the template had |
| Capacity (per code) | the app's per code load (the report's own column had formula errors) |
| Room type (per code m^2 used in capacity), Note | the app if set; otherwise the template |
| Pictures | the table's link formula, pointed at each row; Excel works it out when the file opens |

The template is never opened with pandas or openpyxl (that would delete the slicers): the export copies the file and rewrites only the table's rows. Columns are found by header name, so their order doesn't matter. A new template = drop it in `data/template/` (keep only one there); it needs a table with Property, Floor and Space in its header. The old template (`26-09-15 ROOM CAPACITY`) is in `data/old_templates/`.

## Several people at once

The database is one file on the S: drive that several people use. Built for a handful of people (Carl, Mark, 1–2 PMs), tested with two apps saving at the same moment:

- **A busy database waits instead of failing.** If someone else is saving, the app waits up to 15 seconds for them to finish.
- **Nobody overwrites someone else's change without seeing it.** Every save checks that the room, exit, note or code factor still has the value the person saw when they opened it. If someone else changed it in between, the save is refused ("This room was changed to 45 by Mark at 2:14 pm..."), the screen refreshes, and they try again from the new value.
- **Screens stay current.** The app checks for other people's saves every 20 seconds and refreshes; opening a room always starts from the latest value. There's also a **Refresh** button.
- The database uses SQLite's standard journal mode, not WAL, because WAL doesn't work on network drives.

If many more people ever need to edit at once, the next step is UVic's SQL Server (ADR 0001).

## Settings that used to be constants

`exit_capacity.py` kept `ROOM_EXCLUDE` and `OPEN_STAIRS_COUNT` in its config block. In the app they are rows in the `settings` table (`room_exclude` = `14.3,16`, `open_stairs_count` = `no`), so changing them goes through **Code factors** with a clause reference and is logged. When Mark rules on open stairs, set `open_stairs_count` to `yes` there.

## When the building code changes

BCBC comes out about every 6 years (2012, 2018, 2024). Each rule the app uses is either a **number in the database** or a **formula in the code**.

| Rule | Clause (BCBC 2024) | Where it lives | Who can change it |
|---|---|---|---|
| m² per person by room type | 3.4.3.1.(1) → 3.1.17.1. and Table 3.1.17.1. | `area_factors` table | Anyone, in **Code factors** |
| Which sub-category is which room type | project decision | `category_map` table | Anyone, in **Code factors** |
| mm per person by exit type | 3.4.3.2.(1) | `width_factors` table | Anyone, in **Code factors** |
| Minimum exit widths | 3.4.3.2.(8) and Table 3.4.3.2.-A | `width_factors` table | Anyone, in **Code factors** |
| Minimum number of exits | 3.4.2.1.(1) | `minimum_exits` setting | Anyone, in **Code factors** |
| Rooms left out of scope | project decision | `room_exclude` setting | Anyone, in **Code factors** |
| Open stairs count as exits | 3.4.4.1.(1) | `open_stairs_count` setting | Anyone, in **Code factors** |
| Link door share | supervisor model (closest: 3.4.3.1.(2)) | `link_share_method` setting (even_split / half_load) | Anyone, in **Code factors** |
| Edition the results say | n/a | `code_edition` setting | Anyone, in **Code factors** |
| Occupant load formula (area ÷ m², round up) | 3.4.3.1.(1) → 3.1.17.1.(1)(c) | `occupant_load` in `exit_calc.py` | Someone who can edit Python |
| Persons per exit formula (width ÷ mm, round down) | 3.4.3.2.(1) | `exit_persons` in `exit_calc.py` | Someone who can edit Python |
| 50% rule | 3.4.3.2.(7) | `capacity_50_rule` in `exit_calc.py` | Someone who can edit Python |
| Link door formula | supervisor model (closest: 3.4.3.1.(2)) | `people_sent` in `exit_calc.py` | Someone who can edit Python |
| Stairs not cumulative across floors | 3.4.3.2.(4) | how `build_zones` in `egress.py` groups rooms | Someone who can edit Python |
| Status and flags | project decision | end of `build_zones` in `egress.py` | Someone who can edit Python |

A new exit type (e.g. `ramp`) is just a new `width_factors` row.

**A number changed** (e.g. doorways go from 6.1 to 5.5 mm/person):
1. Open **Code factors**, change the value, enter the new clause, check the preview (how many zones change status), save. It's logged.
2. Change `code_edition` to the new edition (e.g. `BCBC 2030`) the same way.
3. Export a new results workbook. Old workbooks keep the old edition in their `code_edition` column.

**A formula changed, was removed, or a new rule was added** (e.g. the 50% rule is dropped):
1. Copy `data/capacity.db` somewhere safe first.
2. Change the function in `exit_calc.py` (or the step in `egress.py`) and update its comment with the new clause.
3. Hand-check one real floor with the new rule (Turpin floor 3 wing B is the usual one), then update the expected numbers in `test_exit_calc.py` / `test_egress.py` and the **Test values** table below.
4. `py -m pytest` from this folder. Everything must pass before anyone uses it.
5. Update **Method** below, change `code_edition` in **Code factors**, and add a row to **Decisions**.
6. Copy the changed `.py` files to every machine that runs the app.

Clause numbers were checked against the BCBC **2024** text (revision 2) on 2026-10-07. Each formula in `exit_calc.py` and each step in `egress.py` has its clause in a comment.

## Installing on a Windows machine (step 7)

1. Install Python from python.org (tick "Add to PATH"), then `py -m pip install pandas openpyxl`.
2. Copy the `capacity_egress_app/` folder to the machine (`data/` only if you're bringing the database with you).
3. Move `data/capacity.db` to the project folder on the S: drive and set `DB_PATH` at the top of `app.py` to that path. Everyone's app must point at the **same** file.
4. Optional launcher `Capacity app.bat` next to `app.py`: `@echo off` / `cd /d %~dp0` / `py app.py` / `pause`.
5. Check: open the app, search `B303`, and see Turpin floor 3 wing B in the zones list.

## Measuring exits

Enter exits with **Add exit** in the app. One row per exit; a floor with three exits has three.

| Field | What goes in it |
|---|---|
| wing | Wing letter (A, B...) for a floor split into wings. Fill it on **every** exit of that floor. Blank = the floor is one zone. |
| exit_id | Space number from the base drawings + what was measured: `S4 - doorway`, `S5 - open stair`. Outside doors aren't numbered on the plans: `E<floor> - outside exit`, plus a letter if there are several (`E2`, `E2A`, `E2B`). |
| exit_type | `doorway`, `stairs` (rise ≤ 180 mm **and** run ≥ 280 mm) or `stairs_steep` (anything else). |
| clear_width_cm | Clear width in cm at the **narrowest** point, rounded down. Whole number, 50–500. |
| into_wing | Only for a door into **another wing**: that wing's letter. |
| narrowest_point, notes | What was narrowest (`121 cm at handrail`). For stairs, the rise and run. |

Where a stair has a door in front of it, measure the **door**, and write the stair's narrowest width in `notes` (`stair 110 cm`): BCBC 2024 gives doors 6.1 and stairs 8.0 mm/person, so a stair can carry fewer people than its door even when it's wider (88 cm door = 144, 110 cm stair = 137). Using the smaller one is waiting on Mark. Only measure the stair itself when it's an open stair, and put `open stair` in the exit_id so the calculation recognises it.

## Method

**Visited vs capacity source.** Two separate facts about a room: `visited` = it was counted on a site visit at some point (it stays visited after a PM change), `capacity_source` = where today's room capacity came from (`site count`, `PM change`, or `per code` when there's no room capacity). A visited room can have a PM change; a room that was never visited can too. The screens say "not visited" only when a room has no room capacity at all (`test_visited_means_ever_counted_source_means_current_number`).

1. **Room type.** The room's override if set, otherwise the default from the category map. Rooms with area but no sub-category count as excluded and are listed in the warnings.
2. **Per code load** = net area ÷ m² per person, **rounded up** (3.4.3.1.(1) → Subsection 3.1.17).
3. **Load used per room** = the room capacity when there is one (site count or PM change; 0 stays 0), otherwise the per code load. Sub-categories in `room_exclude` (lounges 14.3, all non-assignable 16.x) count as 0, `out of scope`.
4. **Wing of each room** = the letters at the start of its Space number (`B303` → B).
5. **Zones.** A floor is one zone unless any exit on it has a wing; then each wing is its own zone. On a split floor, zones with no load and no exits are dropped.
6. **Open stairs are not exits** while `open_stairs_count` = `no`: BCBC 3.4.4.1.(1) requires exits to be fire separated. They get 0 people and `not an exit - open stair`.
7. **Persons per exit** = `clear_width_cm × 10 ÷ mm per person`, rounded down: doorway 6.1 (3.4.3.2.(1)(a)), stairs 8.0 ((b)), stairs_steep 9.2 ((c)).
8. **50% rule** (3.4.3.2.(7)): exit capacity = the smaller of the total and 2 × (total − largest exit). A single exit gives 0.
9. **Minimum widths** (Table 3.4.3.2.-A): doorway under 850 mm fails; stairs under 900 mm fail, 900–1099 mm is review (depends on storeys served), 1100 mm and over passes.
10. **Stairs are not cumulative across floors** (3.4.3.2.(4)).
11. **Link doors** (supervisor model; no code clause covers a door between wings of one floor area, 3.4.3.1.(2) is the closest): people sent = the smaller of (sending wing load ÷ its exits) and the door's capacity, added to the receiving wing. One step only; a wing that sends and receives is flagged.
12. **Occupant load** = load used + people received through link doors, compared with the exit capacity.
13. **Status:** `NOT SURVEYED - no exit data` (no exits) / `REVIEW` (any flag) / `WITHIN CAPACITY - review before acting`. Flags: fewer than 2 exits, load over capacity, width fail, width review, width unknown, sends and receives link traffic, load is 0. **Never "approved".**

## Decisions

| Decision | By | Date |
|---|---|---|
| BCBC 2024 governs | Carl | 2026-09-22 |
| Class labs (2.1, 2.2) count as classroom unless the room type says otherwise | Supervisors | 2026-09 |
| Where a stair has a door, the door is measured; open stairs are measured directly | Carl | 2026-09-22 |
| Stair factor follows the rise/run test (8.0 or 9.2) | BCBC 3.4.3.2.(1) | 2026-09-23 |
| Stairs are not cumulative across floors | BCBC 3.4.3.2.(4) | 2026-09-23 |
| Wings are calculated separately even when connected; connections recorded with `into_wing` | Supervisor | 2026-09-24 |
| Link door share = even split across the sending wing's exits | Supervisor | 2026-09-24 |
| A floor splits into wings only if one of its exits has a wing | Carl | 2026-09-28 |
| All rooms count except lounges (14.3) and non-assignable (16.x) | Carl | 2026-09-29 |
| Open stairs are not exits until confirmed | BCBC 3.4.4.1.(1), ruling pending | 2026-09-29 |
| Load = room capacity; FMIS's default 0 is not a count, so unvisited rooms use per code | Carl | 2026-10-02 |
| SQLite + Tkinter app is the system of record (ADR 0001) | Carl + Mark | 2026-10-02 |
| Occupant load rounded up | Project default, confirm | 2026-09 |
| Viewers can try a room type on the check screen (not saved); editors change it on the editor screen, logged with why | Supervisor feedback, Carl | 2026-10-16 |
| Space report export: a visited room's PM change goes into `Capacity (Occupants)` (it's the room capacity FMIS gets; the site count stays in the change log) | Carl | 2026-10-16 |
| Health services (13.1) excluded pending a ruling; care occupancies use 18.4 mm/person (3.4.3.2.(2)) | Pending | |
| Day care (19.1) is Group A-2, not care (3.1.2.8.(1)); still excluded until a room type is picked | BCBC 2024 3.1.2.8.(1) | 2026-10-20 |
| Posted signs (3.1.17.1.(2)) not tracked by the app; some rooms already have them | Carl | 2026-10-20 |
| Residences (17.x) excluded; they use persons per sleeping room, not area | Pending | |

## Open questions


- **Open stairs** (e.g. Turpin S5, curved, not enclosed): do they count as exits? Sets `open_stairs_count`.
- **27 sub-category mappings** are marked `needs_review` in the category map.
- **Link doors / firewalls:** with no firewall between two wings they're one floor area (Div A 1.4.1.2.) and the link door isn't an exit; with a firewall it's a horizontal exit (3.4.1.6., 3.4.6.10.: refuge 0.5 m² per person, at most half the exits). Ask Mark about Turpin floor 1 A/B.
- **Door vs stair:** use the smaller of door persons and stair persons (3.4.3.2.(1), (8))? Ask Mark.
- **Interconnected floor space** (3.4.3.2.(6)): floors joined by an open stair or atrium need cumulative stair widths. Does any screened floor have one (Turpin S5)?
- **Lounges (14.3) and kitchens:** Table 3.1.17.1. gives them 1.85 and 9.30, so leaving them out undercounts a little. Carl's call.
- **Ramps:** BCBC 2024 3.4.3.2.(1) gives 6.1 mm/person up to a 1 in 8 slope, 9.2 if steeper; Table 3.4.3.2.-A minimum 1100 mm. Not added as an exit type yet.
- **Turpin floor 3 B:** hand count about 149 vs 161 calculated; probably the 16 offices not counted yet (per code).

## Out of scope

Two egress doors for a room over 60 people (3.3.1.5.), washroom counts (3.7.4.), travel distance, dead-end corridors, sprinklers, door swing and hardware, fire separations (other than open stairs), occupancy reclassification and aisle widths inside rooms. These are why results say "review", not "approved".

## Known data issues (Sept 2026 exports)

- **ECS floor 2, room 242A** appears twice (0 and blank). The blank copy is dropped.
- **McKinnon floor 0** (13 room numbers) and **University House 1 floor 0 room 3** reuse room numbers for different spaces. Both are kept and matched on area when a new space report is loaded.
- **825 rows have no sub-category.** 703 are `_General` placeholders at 0 m²; 52 have real area and are listed in the warnings.
- The space report's `Capacity (per code)` column has formula errors. Not used.

## Test values

| Check | Expected |
|---|---|
| Turpin B303, 60.55 m² classroom ÷ 1.85 | 33 per code |
| 121 cm stair / 88 cm doorway / 121 cm stairs_steep | 151 / 144 / 131 persons |
| 50% rule: 151+144+144 / 151+144 / 400+100 / 144 alone | 439 / 288 / 200 / 0 |
| B wing 100 people, 4 exits, link door → A | 25 added to A |
| First import (23 Sept report) | 19,451 rooms: 1,184 site count, 18,267 per code; 10 exits |
| Turpin floor 3 B / floor 2 B / EOW floor 1 | 161 vs 288 / 62 vs 1027 / 49 vs 288 |
| Whole campus | 790 zones: 787 not surveyed, 3 within; 52 warnings |

## Related projects in this repo

- [`facility_folder_automation`](../facility_folder_automation/): builds the `buildings/Property/Floor/Space` photo folders that the app's **Open photos** button opens.
