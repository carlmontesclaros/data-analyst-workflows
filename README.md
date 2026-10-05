# UVic Data Analyst Internship Workflows 

A collection of data analytics and automation workflows developed during my data analyst internship at the **University of Victoria (UVic)**. This repository highlights self-directed automation tools and pipelines I built on my own initiative to optimize internal data workflows, replacing tedious manual tasks before anyone even asked me to.

---

## What's in here?

I’m keeping everything modular. Each project or workflow gets its own separate folder so the root directory stays clean:

### Project Overview

### 📁 `facility_folder_automation` 
* **What it does: Reads facility spreadsheets and builds a nested folder tree**
  1. Reads any input Excel file dropped into the "input/" folder and automatically generates a nested directory tree (`Property Name ➔ Floor Number ➔ Space/Room Number`).
  2. Automatic header detection -> finds the header row wherever it sits, files with slicers, subtotals or look up tables above the data all work.
  3. Batch processing - every .xlsx in input folder, not one file.
  4. DRY_RUN = True mode as default which previews counts without creating any folders. Must be "False" to create the folders
  5. Safe to rerun: existing folders and their contents are never touched or deleted
  6. Safe to run on both Windows and macOS
* **The Stack:** Python, Pandas, OpenPyXL, built-in `os` and `glob` modules.
* **Why it matters:** Instead of manually building out hundreds of nested folders for campus inventory, you just drag and drop the raw spreadsheet into the "input/" folder, asks you which building(s), and output (set by OUTPUT_DIR) goes to "buildings/" folder
* **Limitations:**
    1. Renaming a space in the source file creates a new folder; the old one is not moved or removed.
    2. Excel filters are ignored -> hidden rows will get processed. Copy visible cells to a new sheet before saving!
    3. Column headers must be named exactly "Property", "Floor", and "Space".
    4. Characters illegal in paths (/ \ : * ? " < > |) are replaced with - in folder names.
 
### 📁 `capacity_egress_app` (Current project)
* **What it does: Desktop app that keeps the record of room capacities and checks every floor's exiting capacity under the BC Building Code 2024**
  1. One SQLite database holds the room capacities, measured exits and building code factors. The FMIS space report only supplies the list of rooms and is never written to.
  2. Search a room (`B303`) or pick building -> floor, and see each zone's occupant load vs exit capacity, coloured red (review) / green (within) / grey (not surveyed).
  3. Change capacity -> type the new number, preview the floor result, then save or cancel. Every change is logged: who, when, old value, new value and why.
  4. Add or edit exits with the same checks the Excel exits sheet had (exit type dropdown, width 50-500 cm).
  5. Code factors (m² per person, mm per person, settings) can be edited in the app, but only with a building code clause reference, and it previews how many floors change status first.
  6. Exports -> results workbook (4 sheets, same as the old script) and a capacity file in the space report layout for the FMIS capacity import.
  7. Backs up the database every day it's opened (last 30 kept).
  8. Screening only: results say "review", never "approved".
* **The Stack:** Python, Tkinter, SQLite, Pandas, OpenPyXL, pytest (48 tests).
* **Why it matters:** Answering "can this room go from 32 to 36?" used to mean opening the Excel files and a hand calculation per floor. Now you just find the room, type 36 and see if the floor's exits still cover it, with a record of who changed it and why.
* **How to run:** from `capacity_egress_app/`, run `build_database.py` once (reads the space report and `floor_exits.xlsx` in `data/input/`), then `app.py` every time after. On Windows use `py` instead of `python3`.
* **Limitations:**
    1. Built for a few people editing now and then (Carl, Mark, 1-2 PMs). SQLite on a shared drive isn't meant for many people saving at once.
    2. Open stairs don't count as exits until there's a ruling (BCBC 3.4.4.1.(1) says exits must be fire separated).
    3. Ramps have no exit factor yet, so they can't be entered as exits.
    4. Doesn't check travel distance, dead ends, sprinklers, door hardware or fire separations. That's why results say "review", not "approved".
    5. A newer space report is loaded with Refresh in the app, not by rebuilding. Rooms that disappear are kept and flagged, never deleted.
* **Details:** method, decisions and open questions are in `capacity_egress_app/README.md`. It replaced the earlier `exiting_capacity_calculation` terminal script (retired 2026-10-05).

## Future Ideas
1. Generalize the hierarchy of `facility_folder_automation` let the user choose which columns become folder levels, instead of hardcoding Property/Floor/Space.
   
### Tech Stack & Dependencies
* **Python 3**
* **Pandas** (Data structures and analysis)
* **OpenPyXL** (Excel file engine backend)
* **Tkinter** (Desktop app window, comes with Python)
* **SQLite** (Database, comes with Python)
* **pytest** (Tests)
