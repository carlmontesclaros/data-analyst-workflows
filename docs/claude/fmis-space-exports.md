<!-- Moved word for word from CLAUDE.md on 2026-11-12 (context budget cut). Section numbers below are the original CLAUDE.md numbers. -->

# FMIS space exports: data facts (from CLAUDE.md section 5)

Read before reading, parsing or writing a space report / FMIS export workbook.

## 5. The data: FMIS space exports (shared by both projects)

Facts established by inspection. Don't re-derive them.

**Two different exports have been measured. Always say which one a number comes from.**

| Export | Header row | Data rows | Properties | Notes |
|---|---|---|---|---|
| Older / teammate's export (folder-automation chat) | row 10 | 19,134 (reconciled: Excel last row 19,144 minus header) | 217 | `drop_duplicates` removes about 15 |
| `carl space report 22sept.xlsx` (exiting-capacity chat) | row 7 | 19,453 | 219 | after dropping exact duplicates: 19,452 rooms, 788 Property+Floor pairs. Property/Floor/Space in A/B/C; Carl's `Pictures` column is last (L) |

Header rows move between exports because of slicers and a leftover BCBC factor table above the data. **Always detect the header; never hardcode it.**

**Values**
- Many "properties" aren't buildings: `Bowker Creek`, `Bus Loop`, `West Woods`, `Ziggurat`, `Parking Lot 1..16`, `Playing Field 1..8`, `Tennis Court - ISC`.
- `Select a Property` appears as a property value: a dropdown placeholder leaked into the data.
- `_General` and `General` appear in both Floor and Space. `_General` looks like a slicer artifact (703 rows in the 22 Sept export, all 0 m²). `General` may be a real building-level record. **Unresolved; Carl was going to ask the export owner.**
- Typos and inconsistencies upstream: `Garry Oak Meadow Resoration`; `Roof - A-Wing` vs `Roof - A Wing`.
- **Floor is text, never int:** real values include `Roof`, `1M`, `3M`, `P0`–`P4`, `A`, `C`, `Roof - A-Wing` alongside `0`, `1`, `3`, `_General`. `astype(int)` crashes. Some floor names carry wing information (`Roof - A-Wing`), which matters for the exiting-capacity wing logic.
- A Floor column that ever held NaN becomes float, so `astype(str)` gives `"3.0"`. Fix with `.str.removesuffix('.0')`, a string-level patch documented as such.
- Three properties contain ` / `: `Engineering / Computer Science Building`, `Jam Factory / Water Tower`, `Mearns Centre / McPherson Library`.
- 22 Sept export: ECS floor 2 room 242A is an **exact duplicate** row (drop it). McKinnon floor 0 (14 room numbers) and University House 1 floor 0 room 3 reuse numbers for **different** spaces with different areas (keep both). 825 rows have no Space Sub-Category: 703 `_General`, and 52 with real area (1,186 m²).
- The Space Sub-Category column has 53 distinct values. The room-type column Carl fills (`Room type (per code m^2 used in capacity)`) mixes `Office`/`office`; lowercase it.

**Workbook handling**
- The workbooks contain **slicers**. openpyxl warns `Unknown extension is not supported and will be removed` on read. That's harmless when reading, but **never save the master file through pandas or openpyxl**: slicers and formatting get destroyed.
  - Known casualty: the exiting-capacity session moved Carl's counts from `Capacity` into `Capacity (Occupants)` and deleted the `Capacity` column with openpyxl on a copy of the 18 Sep workbook. That copy lost its slicers. If a master is missing slicers, check whether it descends from that file.
- **pandas ignores Excel filters.** Hidden rows are still read. If someone filters with a slicer and saves, the whole campus gets processed. Copy visible cells to a new sheet first.
- Detection is case-insensitive but column selection (`df[cols]`) is not. A file with `PROPERTY` detects fine, then raises `KeyError`. This applies to both scripts.
