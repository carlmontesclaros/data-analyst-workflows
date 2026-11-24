<!-- Moved word for word from CLAUDE.md on 2026-11-12 (context budget cut). Section numbers below are the original CLAUDE.md numbers. -->

# Exiting capacity: method, settled decisions, test values, field data (from CLAUDE.md sections 4, 6, 9, 10)

> **Historical.** This is a snapshot of how the retired terminal script `exiting_capacity_calculation/exit_capacity.py` worked (retired 2026-10-05, see [ADR 0002](../adr/0002-retire-terminal-script.md)) plus the decisions made while it was the only calculation. The app in `capacity_egress_app/` replaced it, and where this file disagrees with `capacity_egress_app/README.md` or the code, the README and the code win. Known differences: open stairs now count as exits and `open_stairs_count` is `yes` by default; lounges (14.3) and kitchens (7.2) count at their per code load, and only 16.x is excluded by default; a door into a stair counts the smaller of the door and the stair; the doorway minimum width is 850 mm, not 800; a floor's zone can be a group of wings (`A+C+D`); the editor list and the Windows login decide who can edit; the app has 496 tests, not 15. The repo map in section 4 and the `exit_capacity.py` flags in 6.2 and 6.3 no longer exist.

Read before changing the egress calculation, quoting a BCBC clause, re-checking a number, or proposing something that may already be decided (6.5 is settled: don't re-argue). Sections 4 and 6 describe the retired `exiting_capacity_calculation/` layout; where they disagree with docs/claude/status-log.md (section 11), section 11 wins.

## 4. Repo map

```
data-analyst-workflows/
  README.md                          overview of both projects, for humans
  GLOSSARY.md                        domain vocabulary (room capacity, visited room, code factor, ...)
  docs/adr/0001-sqlite-tkinter-system-of-record.md   why the app replaces Excel
  capacity_egress_app/               NEW: SQLite + Tkinter app (README only so far; data/ for the dev .db)
  CLAUDE.md                         this file, for Claude
  ARCHITECTURE_PLAN.md               PM delivery plan rev 3 (local, gitignored)
  .gitignore                         .idea/, .DS_Store, __pycache__, venvs, ~$*.xlsx,
                                     input/, buildings/, output/, CLAUDE.md, ARCHITECTURE_PLAN.md,
                                     carl_space_report_23sept.xlsx, floor_exits.xlsx,
                                     exiting_capacity_results*.xlsx, bcbc_2018dbp3s34.pdf,
                                     .pytest_cache/, coop/
  facility_folder_automation/
    automation.py                    finished
    input/        (local)            FMIS export(s)
    buildings/    (local)            generated folder tree
  exiting_capacity_calculation/
    exit_capacity.py                 Carl's script, M1–M5 done (procedural; imports exit_calc)
    exit_calc.py                     occupant_load, exit_persons, capacity_50_rule, people_sent
    test_exit_calc.py                15 pytest tests
    README.md                        how to run, method, output, decisions, open questions, test values (authoritative)
    config/
      area_factors.csv               m2/person by room type
      width_factors.csv              mm/person + minimum widths by exit type, with clause refs
      category_map.csv               53 FMIS sub-categories -> room type (+ needs_review, note)
      settings.csv                   code_edition, occupant_load_rounding, minimum_exits, link_share_method
    input/        (local)            space report + exits file(s)
```

Each project has its own `input/`. The exiting-capacity output `exiting_capacity_results.xlsx` is written next to its script (gitignored). `CLAUDE.md` itself is gitignored, so edits to it aren't committed.

## 6. `exiting_capacity_calculation`

### 6.1 Inputs

All `.xlsx` files in `input/` are read, recognised by their header row, so names don't matter; `~$` lock files are skipped. Only the first sheet is read.

**Space report:** the header contains Property/Floor/Space. Columns used: `Property, Floor, Space, Net Space (sq m), Space Sub-Category, Capacity (Occupants), Room type (per code m^2 used in capacity)`.
- `Capacity (Occupants)` = Carl's counted capacity from site visits. **Blank = not visited yet** (uses per code); `0` = counted as 0 people.
- `Room type (per code m^2 used in capacity)` = Carl's room-type call, which **overrides** the category default.
- Keep only one pull in `input/` at a time. If the same room appears in two reports, stop rather than double-count.

**Exits file(s):** the header contains Property/Floor/exit_type. One row per exit; floors repeat.

| column | rule |
|---|---|
| Property, Floor | copied from the space report, never retyped. No `sanitize()`: names must match the report exactly |
| wing | A/B... on **every** row of a multi-wing building; blank = the floor is one zone |
| exit_id | the drawing's space number + what was measured: `S4 - doorway`, `S5 - open stair`. Same label on every floor for the same stair. Exterior exits aren't numbered on the plans, so Carl names them `E<floor>` (+ letter if several): `E3 - outside exit` on floor 3, `E2`/`E2A`/`E2B` on floor 2 |
| exit_type | `doorway`, `stairs`, `stairs_steep`, plus `ramp (accesibility)` in the dropdown (no factor in width_factors.csv yet; a ramp gets width_check `unknown`, 0 persons, and a warning) |
| clear_width_cm | cm, narrowest point, round down |
| into_wing | only on a door leading into another wing: that wing's letter |
| measured_date, measured_by, narrowest_point, photo_ref, notes | records; for stairs, rise/run go in notes |

`wing`, `into_wing` and `measured_date` are optional in code (created blank if missing). An open stair must have `open stair` in its exit_id; that's how the script recognises it.

**Carl's `floor_exits.xlsx` as of 2026-10-01:** 795 rows (788 placeholders, one per Property+Floor, plus measured rows), **10 exits recorded**:
- Turpin floor 2, wing B: S5 open stair 110, S4 doorway 88, E2/E2A/E2B doorways 180/179/180
- Turpin floor 3, wing B: S4 doorway 88, S5 stairs 121, E3 doorway 88
- Engineering Office Wing floor 1: S1 88, S2 89

The sheet has a `wing` column, and data validation that blocks bad entries (exit_type dropdown; width is a whole number 50–500). The input/ copy must be re-copied after every master edit. Both files must be in `exiting_capacity_calculation/input/`; the copies at the repo root aren't read.

### 6.2 Method (full version with clause numbers in the project README)

1. Room type = override, else `category_map.csv`. Rooms with no sub-category count as excluded, with a warning if the room has area.
2. Per code load = `occupant_load(area, m²pp)` = `ceil(round(area / m²pp, 6))`.
3. **Load used** (`LOAD_BASIS = 'counted'`, settled by Carl 2026-10-01): the count if filled in (0 stays 0); blank → per code. Rooms whose sub-category code is in `ROOM_EXCLUDE = ['14.3', '16']` (lounges, all 16.x non-assignable; a code covers its children) → 0, `out of scope`. `'area'` = per code for every room.
4. Room wing = the leading letters of Space (`B303` → B).
5. Zone = the floor, or floor + wing if any exit on that floor has a wing. On split floors, drop pseudo-zones with zero load and no exits.
6. **Open stairs** (`OPEN_STAIRS_COUNT = False`): exit_id containing "open stair" → `counts_as_exit` False, persons 0, width_check `not an exit - open stair`, not in exit_count. Reason: 3.4.4.1.(1) requires exits to be fire separated. Pending Mark; `True` restores them. **SUPERSEDED 2026-10-20 (Carl): open stairs count, `OPEN_STAIRS_COUNT=True` (PR #11); see status-log.**
7. Exit persons = `exit_persons(cm, mm_pp)` = `floor(round(cm × 10 / mm_pp, 6))`. Doorway 6.1; stairs 8.0 (rise ≤ 180 mm and run ≥ 280 mm); stairs_steep 9.2.
8. **50% rule** (3.4.3.2.(7)) = `capacity_50_rule(total, largest)` = `min(total, 2 × (total − largest))`. One exit → 0.
9. Minimum widths (Table 3.4.3.2.-A): doorway < 800 mm fails; stairs < 900 fails, 900–1099 = review, ≥ 1100 ok.
10. Fewer than 2 exits → review.
11. **Wing links** (3.4.3.1.(2)) = `people_sent(load_used, exit_count, door_persons, LINK_METHOD)` = `min(ceil(load / exits), door persons)` (`even_split`) or `ceil(load / 2)` (`half_load`); any other method raises ValueError. Added to the receiving wing's load. One step only; a wing that sends and receives is flagged.
12. Stairs are **not** cumulative across floors (3.4.3.2.(4)).
13. `total_load` = load used + link inflow, compared with `exit_capacity`. Status: `NOT SURVEYED - no exit data` (no exits, no flags) / `REVIEW` / `WITHIN CAPACITY - review before acting`. Flags: fewer than MIN_EXITS exits, load over capacity, width fail, width review, width unknown, sends and receives link traffic, load is 0. **Never "approved".**

**Output:** after the whole campus is calculated, a building/floor picker (like automation.py) chooses what to write. Blank = campus → `exiting_capacity_results.xlsx`; a selection → `exiting_capacity_results_<terms>[_floor_<floors>].xlsx` (the campus file is never overwritten by a subset). Floors are asked only when one building matched, with exact names. Sheets:
- `floor_summary`: one row per zone, sorted REVIEW → WITHIN → NOT SURVEYED, rows coloured F8CBAD / C6EFCE / E7E6E6; columns include status, flags, total_load, exit_capacity, load_basis, rooms_in_scope, rooms_counted, counted_capacity, area_based_load, link_inflow, exit_count, floor_key
- `exit_detail`, `room_detail` (in_scope, load_used, load_source), `warnings`

All sheets: bold frozen header, autofilter, column widths ≤ 50. `PermissionError` → "close it and run again". Then a terminal summary and `input()` to hold the window. The same room in two space reports → `SystemExit` naming the files.

### 6.3 State of the code (HEAD `5c8f850`, refreshed 2026-11-17)

| File | Contents |
|---|---|
| `exit_capacity.py` | one procedural script: M1 read + header detection, M2 room types + per code load, M3 exits + width check + open stairs, M4 zones / load used / capacity / links / status, M5 picker + workbook + summary |
| `exit_calc.py` | the four functions above. numpy, so they work on single numbers and on whole columns |
| `test_exit_calc.py` | 15 tests (values in 6.6) |

- Run tests from `exiting_capacity_calculation/`: `python3 -m pytest` (Windows: `py -m pytest`; pytest isn't installed on the workstation yet).
- The picker's `input()` is still at module level, so `exit_capacity.py` can't be imported; tests only import `exit_calc.py`. Put new calculations in `exit_calc.py` with a test.
- `VERBOSE = True` (config block) routes the step checkpoints through `checkpoint(msg)`; `False` leaves only the file lines, picker and summary. Added 2026-10-01.
- Checkpoint prints (trimmed 2026-10-01): file lines, `rooms: (19452, 8)`, `exits recorded: 10`, `open stairs not counted: 2`, `warnings total: 52`, `zones: 790`, the load basis line, `rooms in scope: 14452, counted: 14322, per code: 130`, `zone load used total: 4126`, then the picker and summary.
- Scratch testing: copy the script, sed `BASE_DIR` to the real folder and `OUTPUT_DIR` to the scratchpad, copy `exit_calc.py` next to it, then `printf '\ny\n\n' | python3 ec.py`. For a fake exits file, cast `into_wing` to object before writing a letter (an all-blank column is float).

### 6.4 Remaining work

- **SUPERSEDED 2026-10-20 (Carl decided open stairs count; see status-log):** **Mark:** does Turpin S5 (curved open stair, not enclosed) count as an exit? Sets `OPEN_STAIRS_COUNT`. The only open question for him on this tool.
- **Fieldwork:** Turpin wing A exits on floors 2 and 3; Turpin floor 1, including the link door B101A → A101A (row: wing B, into_wing A; every floor 1 exit row needs a wing); then the next teaching buildings. Co-op target: 5 buildings by Oct 30, 10 by Dec 18 (SUPERSEDED 2026-10-26: Carl has no building-count goal).
- **PM walkthrough** (co-op competency 4) and feedback; revise README / output from it.
- Windows workstation run: **done, works** (Carl, 2026-10-01).
- Optional: an end-to-end test on a small fake floor. Moving the picker under `if __name__ == '__main__'` was skipped on purpose: the whole calculation runs at module level, so it would need the script wrapped in a function, and tests already import `exit_calc.py`.
- Parked: Power Apps option A. Supabase/Netlify: not in use for now (Carl, 2026-11-17). Earlier reason (2026-09-29): UVic data outside UVic systems, nobody to maintain it after the co-op.

### 6.5 Decisions (settled)

| Decision | By |
|---|---|
| BCBC 2024 governs | Carl |
| Only exits count: doors to outside, doors into stairwells, open stairs. Where a stair has a door, measure the door | Carl |
| Class labs 2.1/2.2 count as classroom unless the room-type column says otherwise | supervisors |
| Stair factor follows the rise/run test (8.0 vs 9.2) | code text |
| Stairs not cumulative across floors | 3.4.3.2.(4) |
| Wings calculated separately even when connected; connections recorded via `into_wing` | supervisor |
| Link share = even split across the sending wing's exits | supervisor |
| A floor splits into wings only if an exit on it has a wing; room wing = leading letters of Space; pseudo-zones (split floor, 0 load, 0 exits) dropped | Carl + Claude, 2026-09-28 |
| Zones compare `total_load` (own + link inflow) vs `exit_capacity`; a single exit gives capacity 0 and is flagged | 2026-09-28 |
| **Load = room capacity** (`LOAD_BASIS='counted'`): a visited room uses its count (0 stays 0); an unvisited room uses per code. FMIS shows 0 by default (19,054 of 19,453 rooms), so **0 alone doesn't mean visited**. **SUPERSEDED 2026-11-05/2026-11-17: visited = the room has a count.** Visited at first import = all rooms in EOW, ELW, ECS + Turpin floors 2 and 3 wing B; other numbers above 0 (30 rooms, e.g. High Bay 20, Elliott 5) are **FMIS capacity**: stored for comparison, **not used** in the calculation (those rooms use per code). ECS 242A appears twice (0 and blank): keep the 0 row, drop the blank one. Fix lands in build step 2, not in the current script. Amends the 2026-10-01 "0 stays 0" rule | Carl, 2026-10-02 |
| Scope = all rooms except 14.3 lounges and 16.x non-assignable (`ROOM_EXCLUDE`) | Carl, 2026-09-29 |
| **SUPERSEDED 2026-10-20 (Carl: open stairs count, `OPEN_STAIRS_COUNT=True`):** Open stairs not exits until Mark rules (`OPEN_STAIRS_COUNT=False`) | 3.4.4.1.(1), 2026-09-29 |
| 4 output sheets; picker filters output only; a selection writes its own file | Carl, 2026-09-29 |
| Calculations live in `exit_calc.py` and are tested with pytest | Carl, 2026-10-01 |
| ~~Excel for exit capture, no SharePoint List/Power Apps~~ **Superseded 2026-10-02 by ADR 0001** | Carl, 2026-09-25 |
| **SQLite + Tkinter desktop app is the system of record** (`docs/adr/0001-sqlite-tkinter-system-of-record.md`). One `.db` on the S: drive; the app is installed on each user's Windows machine; every user can edit everything (Carl, Mark, maybe 1–2 PMs) [SUPERSEDED by ADR 0003, 2026-10-13: editors by Windows login, everyone else views]. Space report = read-only room-list input, never written to; Excel only as exports | Carl + Mark's request, 2026-10-02 |
| Every capacity / exit / code factor change is logged: old, new, who (Windows login + nickname), when, why; code factor changes **require a clause reference** and preview how many zones change status | Carl, 2026-10-02 |
| App value wins over FMIS; a disagreement on a new space report is flagged, never overwritten. A room that disappears from the space report is kept and flagged (missing room), never dropped | Carl, 2026-10-02 |
| Change capacity = preview the zone result, then Save/Cancel. Undo = Ctrl+Z while typing only; a saved change is fixed by changing it again | Carl, 2026-10-02 |
| Two exports: **capacity export** (space report layout, no Pictures column, per code only for visited rooms [SUPERSEDED 2026-10-13: per code for every room, see status-log]; feeds Carl's FMIS capacity import, whose template comes from the systems admin) and the **results workbook** (4 sheets, as now) | Carl, 2026-10-02 |
| Power Apps rejected for now (too much setup; the calculation can't run inside it). Supabase/Netlify: not in use for now (Carl, 2026-11-17; earlier reason: UVic data outside UVic) | Carl, 2026-10-02 |
| Vocabulary lives in the root `GLOSSARY.md`: room capacity, capacity source, visited room, code factor, etc. | Carl, 2026-10-02 |
| Exterior exits named `E<floor>[letter]` since the plans don't number them | Carl |
| ~~Two input sources only: the space report (with Carl's columns in it) + exits file(s)~~ Until the app exists. After build step 1, the space report supplies the room list, and capacities, exits and code factors live in SQLite | Carl |
| Everything dynamic: no hardcoded input filenames | Carl |
| Output next to the script, not in an `output/` folder | Carl |
| Commits under Carl's git identity, no Claude attribution | Carl |

### 6.6 Test values (hand-checked)

In `test_exit_calc.py` (15 tests):

| Case | Expected |
|---|---|
| Turpin B303: 60.55 m², classroom 1.85 | **33** |
| Lab 13.8 m² at 4.6 (float noise: 13.8/4.6 = 3.0000000000000004) | **3** |
| 121 cm stairs / 88 cm doorway / 121 cm stairs_steep | **151** / **144** / **131** persons |
| 50% rule: [151,144,144] / [151,144] / [400,100] / [100,100] / [144] | **439 / 288 / 200 / 200 / 0** |
| Link: 100 people, 4 exits, door 144 / 101 people / door 20 / half_load / bad method | **25 / 26 / 20 / 50 / ValueError** |

Real inputs (23 Sept report as re-saved by Carl, 10 exits, default switches), 2026-10-01:

| Check | Expected |
|---|---|
| Rooms | 19,453 read → **19,452**, 197 overrides, 52 "no room type" warnings |
| Per code (area) load, whole campus | 83,572 (5,934 rooms with people) |
| Load used | rooms in scope 14,452, counted 14,322, per code 130; zone load used **4,126** |
| Zones | **790**: 787 NOT SURVEYED + 3 WITHIN; split floors Turpin 2 and 3; 6 pseudo-zones dropped |
| Turpin 3 B | **161 vs 288** (S4 + E3; S5 open stair not counted) |
| Turpin 2 B | **62 vs 1027** |
| EOW 1 | **49 vs 288** |
| Fake link (E3 on Turpin 3 B, into_wing A) | **81** into A (ceil(161/2)) |
| `LOAD_BASIS='area'`, `ROOM_EXCLUDE=[]`, `OPEN_STAIRS_COUNT=True` | Turpin 3 B = 439 vs 224 (the original method) |
| No exits measured | all zones NOT SURVEYED, 52 warnings |

### 6.7 Pitfalls already hit

- Don't use `sanitize()` here; it breaks name matching between files.
- Normalise keys identically in every file: `astype(str).str.strip().str.removesuffix('.0')`.
- pandas: `series & [python list]` raises TypeError. Build masks as `pd.Series(..., index=df.index, dtype=bool)`.
- pandas: `df[[bools]]` with an **empty** list selects zero *columns* and wipes the frame. This crashed the script when there were no exits.
- Use `ceil(round(x, 6))`, not `ceil(x)`.
- Keep the data sheet first in the exits file; it also has EXAMPLE/README sheets.
- `.where(cond)` without a second argument gives NaN, and groupby **silently drops NaN keys** (step 3 got 4 zones instead of 789). Blank = `''`, always.
- Filter exits with `.any(axis=1)`, not `.all`. `.all` silently drops an exit that's missing a width, so its warning never fires.
- Type exact names: `settings.csv` (not settings_map), `link_share_method`, `Net Space (sq m)` (use `AREA_COL`). `(override != '')`, not `' '`.
- Reading the `Pictures` column with pandas gives "Open" (a HYPERLINK formula); rebuild the paths from Property/Floor/Space.
- The space report's `Capacity (per code)` column is broken (about 540 values ≈ 2200, a formula error). Use the script's `occupant_load`, and keep that column out of the outputs.
- `exit_capacity.py` has no trailing newline. When appending to a scratch copy, start with a blank line.
- `warning_rows`, not `warnings` (that's the Python module name).

### 6.8 Open questions (waiting on supervisors)

- 27 `needs_review` rows in `category_map.csv`.
- Horizontal-exit rules if a link door sits in a fire-rated wall. Not checked.
- Open stairs (Turpin S5, curved, not enclosed): do they count as exits at all? Code text says exits must be fire separated (3.4.4.1.(1)). Ask Mark. (2026-10-19: Carl remembered "295" for Turpin 3 B with S5; that's S4 144 + S5 151 before the 50% rule, which gives 288. With S4 + E3 + S5 it'd be 439. Still not asked; Carl unsure.)
- Clauses were checked against `bcbc_2018dbp3s34.pdf` (BCBC **2018**). Confirm in the 2024 text before quoting. **Done 2026-10-07: every clause was checked against BCBC 2024; see status-log and `docs/research/bcbc_2024_factor_check.md`.**
- Turpin 3 B: Carl's hand count about 149 vs the script's 161; probably the 16 offices not counted yet (per code). Unconfirmed.
- Care occupancies (13.1 health, 19.1 day care) use 18.4 mm/person (3.4.3.2.(2)); currently excluded.
- The article number "3.4.3.1" for "Exit Width Based on Occupant Load" was inferred. Confirm it in Carl's BCBC PDF.
- Ramp mm/person (3.4.3.2.(1)), likely 6.1 like doorways but not verified. After confirming, rename the dropdown value to `ramp` and add a row to width_factors.csv.
- 9 rooms have a blank area and count as 0 people, with no warning yet.
- 69 rooms have Space = `General` (wing `GENERAL`). On a split floor they'd form a no-exit zone (NOT SURVEYED).

### 6.9 Field data

- **David Turpin Building (#237)**
  - Floor 3: separate A (north) and B (south) blocks. B exits: S4, an enclosed stair (doorway 88 cm); S5, a curved open stair (121 cm); E3, an exterior exit at the east end by B303A (88 cm). A's exits S2 and S3 are not measured yet.
  - Floor 2: split A/B like floor 3. B exits: S5 open stair 110, S4 doorway 88, E2/E2A/E2B doorways 180/179/180. A's exits not measured yet. **Skipped for now (Carl, 2026-10-08): wing A floors 2 and 3 are all offices**; floor 1 A + B measured 2026-10-08, going into floor_exits.xlsx and built into the DB on the workstation. A and B are **not connected** on floors 2 and 3 (only on floor 1), so no `into_wing` there.
  - Floor 1: A and B are connected by the double door B101A → A101A, which swings into A; that's the link. B's exterior doors are at S4, by S5/L61, and at B101C. A has the large lecture halls (A102/A104/A110/A120). No floor 1 widths measured yet.
  - The hand-marked 147 cm and 150 cm "stairs" on the early plan are **wrong**. Don't use them.
- 22 properties / 64 floors have multiple wing prefixes (Clearihue A–D, MacLaurin A/B/D, Cornett, Engineering Lab Wing, HSD, …). A prefix means wings, not necessarily separate zones; Carl decides per floor on site.
- Teaching space: 720 rooms (categories 1+2) across 31 properties / 71 floors; the top 15 buildings account for 47 floors. 151 rooms verified so far (ECS, Engineering Lab Wing, Engineering Office Wing, one in Turpin).
- Carl is not working over the December break (2026-11-09), so no break-time measuring.

## 9. Not in the repo

- Data files (space reports, exits file, Turpin floor plan PDFs DTB1/DTB3): local only.
- BCBC 2024 excerpt Carl supplied: 3.4.3.1 Sentences (1)–(2), 3.4.3.2 Sentences (1)–(8), and Tables 3.4.3.2.-A/-B. The rest of the code hasn't been read.

## 10. Out of scope for exiting capacity (why the output says "review")

Travel distance, dead ends, sprinklers, door swing and hardware, fire separations, occupancy reclassification, in-room aisles. The tool screens; a qualified reviewer approves.
