# Exiting Capacity Calculation

Works out, for every floor (or wing) on campus, the occupant load of the floor and how many people its exits can discharge, using the **BC Building Code 2024**.

It is a **screening tool, not a code determination**. Results say "within capacity, review before acting" or "review", never "approved". Any change to a posted room capacity still needs sign-off from a qualified reviewer.

---

## Folder layout

```
exiting_capacity_calculation/
  exit_capacity.py        the script
  config/                 code factors and decisions (in git)
  input/                  space report + exits file(s) (gitignored)
  README.md
```

The output workbook is written next to the script (`exiting_capacity_results*.xlsx`, gitignored).

## How to run

1. Install Python 3 with `pandas` and `openpyxl`.
2. Put **one** space report and your exits file(s) in `input/`.
3. Run it:
   - Mac: `python3 exit_capacity.py`
   - Windows: `py exit_capacity.py`
4. The script calculates the whole campus, then asks which buildings to write:
   - **Blank** = all buildings → `exiting_capacity_results.xlsx`
   - **Building name(s)**, comma-separated, part of the name is enough (`turpin, engineering`) → `exiting_capacity_results_<names>.xlsx`
   - If exactly one building matches, it also asks for floor(s) (exact names: `2`, `Roof`) → `..._floor_<floors>.xlsx`
   - `q` quits
5. Type `y` to confirm. Press Enter at the end to close the window.

The selection only filters what gets written. The calculation always runs on the whole campus, and a selection never overwrites the campus file.

If the output file is open in Excel, the script stops with "close it and run again".

The script finds its own `input/` and `config/` folders wherever it is run from, so it works the same on a Mac and on the workstation PC.

### Switches at the top of the script

| Switch | Default | What it does |
|---|---|---|
| `LOAD_BASIS` | `'counted'` | `'counted'` = use the site count; a blank count falls back to per code. `'area'` = per code for every room |
| `ROOM_EXCLUDE` | `['14.3', '16']` | Sub-category codes left out of the load. A code covers its children (`16` → `16.2.1`). `[]` = all rooms |
| `OPEN_STAIRS_COUNT` | `False` | `False` = open stairs are not exits (see method step 6). `True` = they count |

---

## Inputs

Every `.xlsx` in `input/` is read. The script works out what each file is from its header row, so file names don't matter. Excel lock files (`~$...`) are skipped.

### Space report (FMIS export)

Recognised by a header row containing **Property, Floor, Space**. The header can be anywhere in the first 50 rows.

Required columns: `Property`, `Floor`, `Space`, `Net Space (sq m)`, `Space Sub-Category`, `Capacity (Occupants)`, `Room type (per code m^2 used in capacity)`.

- `Capacity (Occupants)` holds the counted capacity from site visits. **Leave it blank for rooms not visited yet.** A blank uses the per code load; a `0` means the room was counted as 0 people.
- `Room type (per code m^2 used in capacity)` is the surveyor's room type call. When filled, it overrides the default from the FMIS sub-category.
- The report's own `Capacity (per code)` column is **not used**. Many of its values are formula errors (about 2,200). The script calculates per code itself.
- **Keep only one space report in `input/`.** If the same rooms appear in two reports, the script stops and names the files rather than counting them twice.

### Exits file

Recognised by a header row containing **Property, Floor, exit_type**. Only the first sheet is read, so keep the data sheet first.

| Column | What goes in it |
|---|---|
| Property, Floor | Copied from the space report. **Never retype**; a one-character difference stops the rows from matching. |
| wing | Wing letter (A, B...) for a floor split into wings. Fill it on **every** exit row of that floor. Blank = the floor is one zone. |
| exit_id | Space number from the base drawings + what was measured, e.g. `S4 - doorway`, `S5 - open stair`. Outside doors aren't numbered on the plans: `E<floor> - outside exit`, plus a letter if there are several (`E2`, `E2A`, `E2B`). |
| exit_type | `doorway`, `stairs` or `stairs_steep` (dropdown). `ramp (accesibility)` is in the dropdown but has no factor yet: it counts as 0 people and shows as width `unknown`. |
| clear_width_cm | Clear width in cm at the **narrowest** point. Round down. |
| into_wing | Only for a door that leads into **another wing**: the letter of the wing it leads into. Blank otherwise. |
| measured_date, measured_by | When and who. |
| narrowest_point | What was narrowest and why, e.g. `121 cm at handrail`. |
| photo_ref | Where the photos of this exit are. |
| notes | For stairs: the rise and run measured, e.g. `rise 17 cm, run 29 cm`. |

**One row per exit.** A floor with three exits has three rows with the same Property and Floor. Floors with no exits recorded stay as one blank row and show as not surveyed.

**What to measure:** where a stair has a door in front of it, measure the **door** (it is narrower and controls the flow). Only measure the stair itself when it is an open stair with no door. For open stairs, also measure one riser height and one tread depth, and put `open stair` in the exit_id so the script can recognise it.

---

## Config files

| File | Contents |
|---|---|
| `width_factors.csv` | mm per person and minimum widths by exit type, with the code clause for each |
| `area_factors.csv` | m² per person by room type (Table 3.1.17.1). `excluded` = counts as zero people |
| `category_map.csv` | Every FMIS sub-category → default room type, with a `needs_review` flag and a note |
| `settings.csv` | Code edition, rounding, minimum exits, how people are split between wings |

Change numbers and rulings here, not in the code. Room type names must be spelled identically in all files. Keep them lowercase.

---

## Method

1. **Room type.** Surveyor override if filled (lowercased and trimmed), otherwise the default from `category_map.csv`. Rooms with area but no sub-category count as excluded and are listed in the warnings.
2. **Per code load per room** = net area ÷ m² per person, **rounded up** (3.4.3.1.(1) → Subsection 3.1.17).
3. **Load used per room** (`LOAD_BASIS = 'counted'`):
   - count filled in → the count (0 stays 0)
   - count blank → the per code load from step 2
   - sub-category in `ROOM_EXCLUDE` (lounges 14.3, all non-assignable 16.x) → 0, marked `out of scope`
4. **Wing of each room** = the letter(s) at the start of its Space number (`B303` → B).
5. **Zones.** A floor is one zone, unless any exit on it has a `wing`. Then each wing is its own zone and rooms go to the zone matching their wing letter. On a split floor, zones with no load and no exits (stairwells `S`, landings `L`) are dropped.
6. **Open stairs are not exits** by default. BCBC 3.4.4.1.(1) requires every exit to be fire separated, and an open stair isn't. Any exit_id containing `open stair` gets 0 people and `not an exit - open stair`, and doesn't count toward the number of exits. Pending a ruling (see open questions); `OPEN_STAIRS_COUNT = True` counts them.
7. **Capacity of each exit** = `clear_width_cm × 10 ÷ mm per person`, rounded down.

   | exit_type | mm per person | Clause |
   |---|---|---|
   | doorway | 6.1 | 3.4.3.2.(1)(a) |
   | stairs (rise ≤ 180 mm **and** run ≥ 280 mm) | 8.0 | 3.4.3.2.(1)(b) |
   | stairs_steep (anything else) | 9.2 | 3.4.3.2.(1)(c) |

8. **Exiting capacity of a zone, 50% rule.** No exit can count for more than half the required width (3.4.3.2.(7)).
   - If the largest exit ≤ the sum of the others: exiting capacity = sum of all exits.
   - Otherwise: exiting capacity = 2 × the sum of the others.

   This equals the highest occupant load that passes Sentence (7). A single exit gives an exiting capacity of 0.
9. **Minimum widths**, Table 3.4.3.2.-A:
   - Doorways: under 800 mm fails.
   - Stairs: under 900 mm fails. 900–1099 mm is **review**, because 900 mm is only allowed when the stair serves no more than 2 storeys above the lowest exit level (or no more than 1 below). 1100 mm and over passes.
10. **Stairs across floors are not cumulative** (3.4.3.2.(4)). Each floor is checked on its own.
11. **Doors between wings.** Where exits converge, the required width is cumulative (3.4.3.1.(2)). A door into another wing counts as an exit of the wing it serves, and the people it sends are added to the receiving wing's load:

    > people sent = the smaller of (sending wing load ÷ number of exits in the sending wing) and (the link door's capacity)

    Example: 100 people in B wing with 4 exits → 25 people added to A wing. Only one step is handled. If a wing both receives and sends people, it is flagged.
12. **Total load** = load used (step 3) + people received through link doors. This is the number compared with the exiting capacity.
13. **Status of each zone:**

    | Status | When |
    |---|---|
    | `NOT SURVEYED - no exit data` | no exits recorded for the zone (no flags) |
    | `REVIEW` | one or more flags (below) |
    | `WITHIN CAPACITY - review before acting` | exits recorded and no flags |

    Flags: fewer than 2 exits · occupant load over exiting capacity · exit below minimum width · stair width depends on storeys served · exit type or width unknown · wing sends and receives link traffic · load is 0.

---

## Output

`exiting_capacity_results.xlsx`, four sheets. Every sheet has a bold frozen header and filters.

| Sheet | One row per | Main columns |
|---|---|---|
| `floor_summary` | floor or wing zone | status, flags, **total_load vs exit_capacity**, rooms counted, counted capacity, area based load. Sorted REVIEW → WITHIN → NOT SURVEYED; rows coloured red / green / grey |
| `exit_detail` | exit | type, width, counts_as_exit, persons, width_check |
| `room_detail` | room | room type and where it came from, per code load, count, in_scope, load_used, load_source |
| `warnings` | problem found | type, Property, Floor, detail |

`floor_key` (`Property | Floor`) is in every sheet except warnings, so the sheets can be joined later (e.g. Power BI).

---

## Decisions

| Decision | By | Date |
|---|---|---|
| BCBC 2024 governs | Carl | 2026-09-22 |
| Class labs (2.1, 2.2) count as classroom unless the room type column says otherwise | Supervisors | 2026-09 |
| Where a stair has a door, the door is measured; open stairs are measured directly | Carl | 2026-09-22 |
| Stair factor follows the rise/run test (8.0 or 9.2) | BCBC 3.4.3.2.(1) | 2026-09-23 |
| Stairs are not cumulative across floors | BCBC 3.4.3.2.(4) | 2026-09-23 |
| Wings are calculated separately even when connected; connections are recorded with `into_wing` | Supervisor | 2026-09-24 |
| People sent through a link door = even split across the sending wing's exits (`link_share_method = even_split`) | Supervisor | 2026-09-24 |
| A floor splits into wings only if one of its exits has a wing | Carl | 2026-09-28 |
| Occupant load = site count; blank count = per code; 0 stays 0 (`LOAD_BASIS`) | Carl | 2026-10-01 |
| All rooms count except lounges (14.3) and non-assignable (16.x) (`ROOM_EXCLUDE`) | Carl | 2026-09-29 |
| Open stairs are not exits until confirmed (`OPEN_STAIRS_COUNT`) | BCBC 3.4.4.1.(1), ruling pending | 2026-09-29 |
| Occupant load rounded up | Project default, confirm | 2026-09 |
| Health services (13.1) and day care (19.1) excluded pending a ruling; care occupancies use 18.4 mm/person (3.4.3.2.(2)) | Pending | |
| Residences (17.x) excluded; they use persons per sleeping room, not area | Pending | |

## Open questions

- **Open stairs** (e.g. Turpin S5, curved, not enclosed): do they count as exits? Decides `OPEN_STAIRS_COUNT`.
- **27 sub-category mappings** are marked `needs_review` in `category_map.csv`.
- **Horizontal exits:** if a link door is in a fire-rated wall, the code's horizontal exit rules may apply. Not yet checked.
- **Ramps:** mm per person for ramps (3.4.3.2.(1)) not confirmed yet, so ramps count as 0.
- **Code text:** the clauses were checked against BCBC 2018 Section 3.4. Confirm them in the 2024 text before quoting.
- **Turpin floors 2 and 3:** A and B are not connected on these floors (only on floor 1, through B101A → A101A). A-wing exits are not measured yet, so A shows as not surveyed.
- **Turpin floor 3 B:** hand count about 149 vs the script's 161. The difference is probably the 16 offices not counted yet (per code).

## Out of scope

Travel distance, dead-end corridors, sprinkler status, door swing and hardware, fire separations (other than open stairs), occupancy reclassification, and aisle widths inside rooms. These are all reasons the output says "review", not "approved".

---

## Known data issues (Sept 2026 exports)

- **ECS floor 2, room 242A** appears twice with identical values. The duplicate is dropped.
- **McKinnon floor 0** (14 rooms) and **University House 1 floor 0 room 3** share room numbers with different areas and categories. These are different spaces; both copies are kept.
- **825 rows have no sub-category.** 703 are `_General` placeholders at 0 m². 52 have real area (1,186 m²) and are listed in the warnings.
- The room type column mixes `Office` and `office`. The script lowercases it.
- `Capacity (per code)` has formula errors (about 540 values near 2,200). Not used.

## Test values

Hand-checked numbers for the test file:

| Case | Expected |
|---|---|
| Turpin B303, 60.55 m² classroom ÷ 1.85 | 33 per code (rounded up) |
| 121 cm stair | 151 persons (0 when it's an open stair and `OPEN_STAIRS_COUNT = False`) |
| 88 cm doorway | 144 persons |
| Exits 151, 144, 144 | 439 |
| Exits 151, 144 | 288 |
| Exits 400, 100 | 200 |
| Exits 100, 100 | 200 |
| B wing 100 people, 4 exits, link door → A | 25 added to A |
| Space report as of 22 Sept 2026 | 19,452 rooms, 219 properties, 788 floors |

Results with the current inputs (23 Sept space report, 10 exits recorded, default switches):

| Zone | Total load vs exiting capacity |
|---|---|
| Turpin floor 3, wing B (S4 88 cm + E3 88 cm; S5 open stair not counted) | 161 vs 288 |
| Turpin floor 2, wing B (S4 88, E2 180, E2A 179, E2B 180; S5 open stair not counted) | 62 vs 1027 |
| Engineering Office Wing floor 1 (S1 88, S2 89) | 49 vs 288 |
| Whole campus | 790 zones: 787 not surveyed, 3 within capacity; 52 warnings |
