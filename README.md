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
  2. **Editors and viewers:** the Windows login decides. Editors (Mark, Carl, Carolyn, Karine, and whoever they add in the app) change the numbers; everyone else gets a simple **capacity check** screen: find a room, try a new number, see if it's over the per code load (needs justification) and whether the floor's exits still cover it, then save a one-page .docx summary to email to Mark.
  3. Search a room (`B303`) or pick building -> floor, and see each zone's occupant load vs exit capacity. Rooms, zones and exits are coloured green (within) / amber (needs a look) / red (over exit capacity or a failing width) / grey (not visited or not surveyed), with a legend.
  4. Change capacity -> type the new number, preview the floor result, then save or cancel. Every change is logged: who, when, old value, new value and why.
  5. Add or edit exits with the same checks the Excel exits sheet had (exit type dropdown, width 50-500 cm).
  6. Code factors (m² per person, mm per person, settings) can be edited in the app, but only with a building code clause reference, and it previews how many floors change status first.
  7. Exports -> results workbook (4 sheets, same as the old script) and the space report, filled into Carl's own space report (slicers kept); a one-page .docx summary of a capacity check.
  8. Backs up the database every day it's opened (last 30 kept).
  9. Screening only: results say "review", never "approved".
* **The Stack:** Python, Tkinter, SQLite, Pandas, OpenPyXL, pytest.
* **Why it matters:** Answering "can this room go from 32 to 36?" used to mean opening the Excel files and a hand calculation per floor. Now you just find the room, type 36 and see if the floor's exits still cover it, with a record of who changed it and why.
* **How to run:** from `capacity_egress_app/`, run `build_database.py` once (reads the space report and `floor_exits.xlsx` in `data/input/`), then `app.py` every time after. On Windows use `py` instead of `python3`.
* **Limitations:**
    1. Built for a handful of editors and a few viewers. Two people saving at once is handled (it waits, and refuses to overwrite a change you haven't seen), but it isn't meant for dozens of people at the same time.
    2. Open stairs count as exits (screening; they lead down to an exit door), and a door into a stair counts the smaller of the door and the stair. Doors into the same stair count as one exit.
    3. Ramps have no exit factor yet, so they can't be entered as exits.
    4. Doesn't check travel distance, dead ends, sprinklers, door hardware or fire separations. That's why results say "review", not "approved".
    5. A newer space report is loaded with Refresh in the app, not by rebuilding. Rooms that disappear are kept and flagged, never deleted.
* **Details:** method, decisions and open questions are in `capacity_egress_app/README.md`. It replaced the earlier `exiting_capacity_calculation` terminal script (retired 2026-10-05).

## Test-weakening guard
When a test fails, the fix belongs in the app (or whatever really caused it), not in the test. A Claude Code hook enforces that so a reviewer doesn't have to catch it: `.claude/settings.json` runs `.claude/hooks/guard_tests.py` before every Edit, Write and MultiEdit.
* **What it blocks in a test file** (`test_*.py`, `*_test.py`, `conftest.py`), when the edit would:
  1. add a skip mark: `pytest.mark.skip` / `skipif` / `xfail` (also `pytestmark = ...`), or unittest's skip decorators
  2. add a skip call: `pytest.skip(...)` / `pytest.xfail(...)` / `pytest.importorskip(...)` (also through `import pytest as pt`), the same names imported with `from pytest import ...` and called bare, `self.skipTest(...)`, `raise unittest.SkipTest`, `raise pytest.skip.Exception` / `pytest.xfail.Exception`
  3. add entries to `collect_ignore` / `collect_ignore_glob`
  4. leave fewer test functions, fewer `assert` statements, or fewer `@pytest.mark.parametrize` cases
  5. add an assert that can't fail (`assert True`, `assert 1`, `assert not False`, `assert 1 == 1`, `assert (x, "why")`)

  Strings and comments don't count, so commenting out an assert counts as removing it.
* **What it blocks in pytest's settings and CI** (`pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`, `.github/workflows/*.yml`): adding an option that deselects tests (`-k`, `--deselect`, `--ignore`, `--ignore-glob`, any `-m` marker expression) to `addopts` (continuation lines included) or a line that runs pytest. Every other edit to those files is fine.
* **What it blocks on the guard itself:** any edit to `.claude/hooks/guard_tests.py`, and any edit to `.claude/settings.json` or `.claude/settings.local.json` that removes, changes or switches off (`disableAllHooks`) the hook entry that runs it. Other settings edits are fine. Changing the guard is a human-only edit.
* The agent is told to fix the app code instead.
* **What it lets through:** other files, new tests and extra asserts, rewrites that keep the same tests and asserts, removing a skip or a deselect option, and the screen tests' no-display guard (`except tk.TclError` -> re-raise unless the message mentions the display -> `pytest.skip(f"no display: {e}")`), which only skips on a machine with no screen.
* **Overriding it (humans only):** if a test, or the guard itself, really is wrong or obsolete, edit the file by hand in your editor (outside the agent), or turn the hook off for a while (`/hooks` in Claude Code, or remove the `PreToolUse` entry from `.claude/settings.json` by hand and put it back afterwards).
* **Limits** (what it doesn't catch, so a reviewer still has to):
  1. an early exit that stops a test checking anything, e.g. `if sys.platform == 'win32': return` before the asserts
  2. weaker asserts that can still fail (`assert x == 5` loosened to `assert x > 0`), or deleting a test while adding a different one with as many asserts
  3. shell commands (`sed`, `rm`, `git rm`, a script), including ones that change the guard or its settings: it only sees Claude Code's Edit, Write and MultiEdit
  4. parametrize cases built in code rather than written as a list, a deselect option set through an environment variable (`PYTEST_ADDOPTS`) or a file it doesn't watch, test paths given to pytest on its command line (`python -m pytest test_egress.py` runs only that file), and skips through other helpers or plugins
  5. a test renamed while also losing its asserts is blocked even if that was intended

  It needs `python3` on the PATH. Its own tests are `capacity_egress_app/test_guard_tests.py`.

## Future Ideas
1. A web link for the capacity check screen (OREM and others, nothing to install). Starts with asking UVic IT; no outside hosting.
2. Generalize the hierarchy of `facility_folder_automation` let the user choose which columns become folder levels, instead of hardcoding Property/Floor/Space.
   
### Tech Stack & Dependencies
* **Python 3**
* **Pandas** (Data structures and analysis)
* **OpenPyXL** (Excel file engine backend)
* **Tkinter** (Desktop app window, comes with Python)
* **SQLite** (Database, comes with Python)
* **pytest** (Tests)
