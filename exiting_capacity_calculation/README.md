# Exiting Capacity Calculation

Works out, for every floor (or wing) on campus, how many people the floor is deemed to hold and how many people its exits can discharge, using the **BC Building Code 2024**.

It is a **screening tool, not a code determination**. Results say "within exiting capacity, review before acting" or "review", never "approved". Any change to a posted room capacity still needs sign-off from a qualified reviewer.

---

## Folder layout

```
exiting_capacity_calculation/
  exiting_capacity.py     the script
  config/                 code factors and decisions (in git)
  input/                  space reports + exits files (gitignored)
  README.md
```

The output spreadsheet is written next to the script. Add its filename to `.gitignore`.

## How to run

1. Install Python 3 with `pandas` and `openpyxl`.
2. Put the newest space report and your exits file(s) in `input/`.
3. Run `exiting_capacity.py`.

The script finds its own `input/` and `config/` folders wherever it is run from, so it works the same on a Mac and on the workstation PC.

---

## Inputs

Every `.xlsx` in `input/` is read. The script works out what each file is from its header row, so file names don't matter. Excel lock files (`~$...`) are skipped.

### Space report (FMIS export)

Recognised by a header row containing **Property, Floor, Space**. The header can be anywhere in the first 50 rows.

Required columns: `Property`, `Floor`, `Space`, `Net Space (sq m)`, `Space Sub-Category`, `Capacity (Occupants)`, `Room type (per code m^2 used in capacity)`.

- `Capacity (Occupants)` holds counted capacity from site visits.
- `Room type (per code m^2 used in capacity)` is the surveyor's room type call. When filled, it overrides the default from the FMIS sub-category.
- **Keep only one pull in `input/` at a time.** If the same rooms appear in two reports, the script stops rather than counting them twice.

### Exits file

Recognised by a header row containing **Property, Floor, exit_type**. Only the first sheet is read.

| Column | What goes in it |
|---|---|
| Property, Floor | Copied from the space report. **Never retype**; a one-character difference stops the rows from matching. |
| wing | Wing letter (A, B...) for buildings with wings. Fill it on **every** row for that building. Blank = the floor is one zone. |
| exit_id | Space number from the base drawings + what was measured, e.g. `S4 - doorway`, `S5 - open stair`. Outside doors: `E1 - outside exit`. |
| exit_type | `doorway`, `stairs` or `stairs_steep` (dropdown). |
| clear_width_cm | Clear width in cm at the **narrowest** point. Round down. |
| into_wing | Only for a door that leads into **another wing**: the letter of the wing it leads into. Blank otherwise. |
| measured_date, measured_by | When and who. |
| narrowest_point | What was narrowest and why, e.g. `121 cm at handrail`. |
| photo_ref | Where the photos of this exit are. |
| notes | For stairs: the rise and run measured, e.g. `rise 17 cm, run 29 cm`. |

**One row per exit.** A floor with three exits has three rows with the same Property and Floor. Floors with no exits recorded stay as one blank row and show as not surveyed.

**What to measure:** where a stair has a door in front of it, measure the **door** (it is narrower and controls the flow). Only measure the stair itself when it is an open stair with no door. For open stairs, also measure one riser height and one tread depth.

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

1. **Room type.** Surveyor override if filled (lowercased and trimmed), otherwise the default from `category_map.csv`. Rooms with no sub-category count as excluded and are listed in the warnings.
2. **Occupant load per room** = net area ÷ m² per person, **rounded up**. Area-based per 3.4.3.1.(1), which points to Subsection 3.1.17. Counted capacity is carried alongside for comparison (see open questions).
3. **Wing of each room** = the letter(s) at the start of its Space number (`B303` → B).
4. **Capacity of each exit** = `clear_width_cm × 10 ÷ mm per person`, rounded down.

   | exit_type | mm per person | Clause |
   |---|---|---|
   | doorway | 6.1 | 3.4.3.2.(1)(a) |
   | stairs (rise ≤ 180 mm **and** run ≥ 280 mm) | 8.0 | 3.4.3.2.(1)(b) |
   | stairs_steep (anything else) | 9.2 | 3.4.3.2.(1)(c) |

5. **Exiting capacity of a floor or wing, 50% rule.** No exit can count for more than half the required width (3.4.3.2.(7)).
   - If the largest exit ≤ the sum of the others: exiting capacity = sum of all exits.
   - Otherwise: exiting capacity = 2 × the sum of the others.

   This equals the highest occupant load that passes Sentence (7).
6. **Minimum widths**, Table 3.4.3.2.-A:
   - Doorways: under 800 mm fails.
   - Stairs: under 900 mm fails. 900–1099 mm is **review**, because 900 mm is only allowed when the stair serves no more than 2 storeys above the lowest exit level (or no more than 1 below). 1100 mm and over passes.
7. **Minimum exits:** fewer than 2 on a floor or wing → review.
8. **Stairs across floors are not cumulative** (3.4.3.2.(4)). Each floor is checked on its own.
9. **Doors between wings.** Where exits converge, the required width is cumulative (3.4.3.1.(2)). A door into another wing counts as an exit of the wing it serves, and the people it sends are added to the receiving wing's load:

   > people sent = the smaller of (sending wing load ÷ number of exits in the sending wing) and (the link door's capacity)

   Example: 100 people in B wing with 4 exits → 25 people added to A wing. The sending wing is calculated first, then the receiving wing. Only one step is handled. If a wing both receives and sends people, it is flagged for manual review.

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
| Occupant load rounded up | Project default, confirm | 2026-09 |
| Health services (13.1) and day care (19.1) excluded pending a ruling; care occupancies use 18.4 mm/person (3.4.3.2.(2)) | Pending | |
| Residences (17.x) excluded; they use persons per sleeping room, not area | Pending | |

## Open questions

- **27 sub-category mappings** are marked `needs_review` in `category_map.csv`.
- **Occupant load basis:** when counted capacity and area-based load differ, which one governs?
- **Horizontal exits:** if a link door is in a fire-rated wall, the code's horizontal exit rules may apply. Not yet checked.
- **Curved stairs** (e.g. Turpin S5): whether they fully count as exits.
- **Turpin floor 3:** A-wing exits S2 and S3 are not measured yet.

## Out of scope

Travel distance, dead-end corridors, sprinkler status, door swing and hardware, fire separations, occupancy reclassification, and aisle widths inside rooms. These are all reasons the output says "review", not "approved".

---

## Known data issues (22 Sept 2026 export)

- **ECS floor 2, room 242A** appears twice with identical values. The duplicate is dropped.
- **McKinnon floor 0** (14 rooms) and **University House 1 floor 0 room 3** share room numbers with different areas and categories. These are different spaces; both copies are kept.
- **825 rows have no sub-category.** 703 are `_General` placeholders at 0 m². 52 have real area (1,186 m²) and are listed in the warnings.
- The room type column mixes `Office` and `office`. The script lowercases it.

## Test values

Hand-checked numbers for the test file:

| Case | Expected |
|---|---|
| Turpin B303, 60.55 m² classroom ÷ 1.85 | 33 (rounded up) |
| 121 cm open stair | 151 persons |
| 88 cm doorway | 144 persons |
| Exits 151, 144, 144 | 439 |
| Exits 151, 144 | 288 |
| Exits 400, 100 | 200 |
| Exits 100, 100 | 200 |
| B wing 100 people, 4 exits, link door → A | 25 added to A |
| Space report as of 22 Sept 2026 | 19,452 rooms, 219 properties, 788 floors |
