---
status: accepted
date: 2026-10-05
---

# The app is the only egress calculation; the terminal script is retired

With build steps 1–6 of the Capacity & Egress app working (ADR 0001), keeping `exiting_capacity_calculation/exit_capacity.py` would mean two calculations that could drift apart, and two places to change a code factor. Carl retired the script on 2026-10-05. Its four core formulas (`exit_calc.py`) and their 15 tests, and the code factor CSVs, moved into `capacity_egress_app/`. The space report and exits file used for the first import moved to `capacity_egress_app/data/input/` (gitignored). The script and its README are deleted; git history keeps them, and the method, decisions and test values were carried into `capacity_egress_app/README.md`. The repo root now holds only `facility_folder_automation/` and `capacity_egress_app/`.

## Decisions made while building the app (2026-10-05)

- **The zeros fix:** load used = room capacity when one exists (a site count or a PM change; 0 stays 0), otherwise the per code load. Before, FMIS's default 0 counted as a real 0, so campus load used was 4,126; now it's 78,006. Turpin 3 B (161 vs 288), Turpin 2 B (62 vs 1027) and EOW 1 (49 vs 288) are unchanged because all their in-scope rooms are visited.
- **`room_exclude` and `open_stairs_count` are settings rows in the database**, not constants in code, so Mark's open-stair ruling is a logged code factor change with a clause reference.
- **Space report refresh** matches rooms on Property + Floor + Space, and on area when a key repeats (McKinnon floor 0, University House 1). It updates only the FMIS columns, adds new rooms as per code, and flags missing rooms. Capacity, source, visited, note and room type are never touched.
- **FMIS capacity** is stored for every room where the report shows a number above 0, and flagged when it disagrees with the app. The app's value wins.
- **Capacity export:** `Capacity (Occupants)` is filled only where a site count or PM change exists; `Capacity (per code)` only for visited rooms. To be checked against the systems admin's FMIS import template.
- **Exits** entered in the app follow the Excel sheet's checks: exit type must have a width factor, clear width is a whole number of cm from 50 to 500, and an exit id is unique per floor. Ramps can't be entered until a ramp factor is confirmed.
- **Users** are identified by Windows login plus a nickname asked once per computer.

## Consequences

- Only the `capacity_egress_app/` folder is copied to a workstation.
- The first import runs once; `build_database.py` refuses to run when the database exists. Newer space reports go through **Refresh space report** in the app.
- The app's code was written by Claude Code at Carl's request and checked against Carl's hand-checked values (48 tests).
