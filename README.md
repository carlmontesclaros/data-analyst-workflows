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
    5. Keep the output path short on Windows (260-character limit): don't add a folder level without re-measuring.
* **Details:** this folder has no README of its own. The script is `facility_folder_automation/automation.py`; the design decisions, the Excel formula that links each room to its folder and the path-length numbers are in [`docs/claude/facility-folder-automation.md`](docs/claude/facility-folder-automation.md). The capacity app's **Open photos** button opens these folders.
 
### 📁 `capacity_egress_app` (Current project)
* **What it does: Desktop app that keeps the record of room capacities and checks every floor's exiting capacity under the BC Building Code 2024**
  1. One SQLite database holds the room capacities, measured exits and building code factors. The FMIS space report only supplies the list of rooms and is never written to.
  2. **Editors and viewers:** the Windows login decides. Editors (Mark, Carl, Carolyn, Karine, and whoever they add in the app) change the numbers; everyone else gets a simple **capacity check** screen: find a room, try a new number, see if it's over the per code load (needs justification) and whether the floor's exits still cover it, then save a one-page .docx summary to email to Mark.
  3. Search a room (`B303`) or pick building -> floor, and see each zone's occupant load vs exit capacity. Rooms, zones and exits each carry a status mark (shape and colour), with a row tint only where action is needed: within / needs a look / over a hard limit / no data yet, with a legend. Full meaning: [Colours](capacity_egress_app/README.md#colours).
  4. Change capacity -> type the new number, preview the floor result, then save or cancel. Every change is logged: who, when, old value, new value and why.
  5. Add or edit exits with the same checks the Excel exits sheet had (exit type dropdown, width 50-500 cm).
  6. Code factors (m² per person, mm per person, settings) can be edited in the app, but only with a building code clause reference, and it previews how many floors change status first.
  7. Exports -> results workbook (4 sheets, same as the old script), the space report filled into Carl's own space report (slicers kept), and the FMIS upload (each counted room's capacity against its FMIS ids, for the FMIS systems admin to load); a one-page .docx summary of a capacity check.
  8. Backs up the database every day it's opened (last 30 kept).
  9. Screening only: results say "review", never "approved".
* **The Stack:** Python, Tkinter, SQLite, Pandas, OpenPyXL, pytest.
* **Why it matters:** Answering "can this room go from 32 to 36?" used to mean opening the Excel files and a hand calculation per floor. Now you just find the room, type 36 and see if the floor's exits still cover it, with a record of who changed it and why.
* **How to run:** from `capacity_egress_app/`, run `build_database.py` once (reads the space report and `floor_exits.xlsx` in `data/input/`), then `app.py` every time after. On Windows use `py` instead of `python3`. Tests: `python3 -m pip install -r requirements-dev.txt`, then `python3 -m pytest` and `python3 -m ruff check .`. GitHub Actions runs the lint and the tests on Windows and on the Mac for every pull request.
* **Limitations:**
    1. Built for a handful of editors and a few viewers. Two people saving at once is handled (it waits, and refuses to overwrite a change you haven't seen), but it isn't meant for dozens of people at the same time.
    2. Open stairs count as exits (screening; they lead down to an exit door), and a door into a stair counts the smaller of the door and the stair. Doors into the same stair count as one exit.
    3. Ramps have no exit factor yet, so they can't be entered as exits.
    4. Doesn't check travel distance, dead ends, sprinklers, door hardware or fire separations. That's why results say "review", not "approved".
    5. A newer space report is loaded with Refresh in the app, not by rebuilding. Rooms that disappear are kept and flagged, never deleted.
* **Details:** method, decisions and open questions are in [`capacity_egress_app/README.md`](capacity_egress_app/README.md). It replaced the earlier `exiting_capacity_calculation` terminal script (retired 2026-10-05, see [ADR 0002](docs/adr/0002-retire-terminal-script.md)).

## Documentation
* [`GLOSSARY.md`](GLOSSARY.md): the words the app and the docs use (room capacity, visited room, code factor, zone, ...).
* Decisions ([`docs/adr/`](docs/adr/)):
  * [ADR 0001](docs/adr/0001-sqlite-tkinter-system-of-record.md): an SQLite + Tkinter app replaces Excel as the system of record.
  * [ADR 0002](docs/adr/0002-retire-terminal-script.md): the app is the only egress calculation; the terminal script is retired.
  * [ADR 0003](docs/adr/0003-editors-by-windows-login.md): editors are named by Windows login, everyone else is a viewer.
* [`docs/requirements_and_ui_review.md`](docs/requirements_and_ui_review.md): non-functional requirements questions with the answers, and the UI review against Norman's seven principles.
* [`docs/research/bcbc_2024_factor_check.md`](docs/research/bcbc_2024_factor_check.md): the app's code factors and rulings checked against the BC Building Code 2024, clause by clause.
* Background notes moved out of the project's agent file (`docs/claude/`). They record how things were decided and measured, and parts predate the app:
  * [`egress-method-and-decisions.md`](docs/claude/egress-method-and-decisions.md): the original egress method, settled decisions, test values and field data (historical; the app README wins where they differ).
  * [`fmis-space-exports.md`](docs/claude/fmis-space-exports.md): facts about the FMIS space report exports (header rows, floors as text, slicers).
  * [`facility-folder-automation.md`](docs/claude/facility-folder-automation.md): how `facility_folder_automation` works and why, the Excel photo-link formula and the Windows path-length limit.

## Test-weakening guard
When a test fails, the fix belongs in the app (or whatever really caused it), not in the test. A Claude Code hook enforces that so a reviewer doesn't have to catch it: `.claude/settings.json` runs `.claude/hooks/guard_tests.py` before every Edit, Write and MultiEdit.
* **What it blocks in a test file** (`test_*.py`, `*_test.py`, `conftest.py`), when the edit would:
  1. add a skip mark: `pytest.mark.skip` / `skipif` / `xfail` (also `pytestmark = ...`), or unittest's skip decorators
  2. add a skip call: `pytest.skip(...)` / `pytest.xfail(...)` / `pytest.importorskip(...)` (also through `import pytest as pt`), the same names imported with `from pytest import ...` and called bare, `self.skipTest(...)`, `raise unittest.SkipTest`, `raise pytest.skip.Exception` / `pytest.xfail.Exception`
  3. add entries to `collect_ignore` / `collect_ignore_glob`
  4. leave fewer test functions, fewer `assert` statements, or fewer `@pytest.mark.parametrize` cases
  5. add an assert that can't fail (`assert True`, `assert 1`, `assert not False`, `assert 1 == 1`, `assert (x, "why")`)

  Strings and comments don't count, so commenting out an assert counts as removing it.
* **What it blocks in pytest's settings and CI** (`pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`, `.github/workflows/*.yml`): adding an option that deselects tests (`-k`, `--deselect`, `--ignore`, `--ignore-glob`, any `-m` marker expression) to `addopts` (continuation lines included) or a line that runs pytest. It doesn't judge any other edit to those files (see Limits).
* **What it blocks on the guard itself:** any edit to `.claude/hooks/guard_tests.py`, and any edit to `.claude/settings.json` or `.claude/settings.local.json` that removes, changes or switches off (`disableAllHooks`) the hook entry that runs it. Other settings edits are fine. Changing the guard is a human-only edit.
* The agent is told to fix the app code instead.
* **What it lets through:** other files, new tests and extra asserts, rewrites that keep the same tests and asserts, removing a skip or a deselect option, and the screen tests' no-display guard (`except tk.TclError` -> re-raise unless the message mentions the display -> `pytest.skip(f"no display: {e}")`), meant to skip only on a machine with no screen. The guard checks that the TclError catch, the 'display' check and the re-raise are there, not that the `if` condition is left as it is (see Limits).
* **Overriding it (humans only):** if a test, or the guard itself, really is wrong or obsolete, edit the file by hand in your editor (outside the agent), or turn the hook off for a while (`/hooks` in Claude Code, or remove the `PreToolUse` entry from `.claude/settings.json` by hand and put it back afterwards).
* **Limits** (what it doesn't catch, so a reviewer still has to):
  1. an early exit that stops a test checking anything, e.g. `if sys.platform == 'win32': return` before the asserts
  2. weaker asserts that can still fail (`assert x == 5` loosened to `assert x > 0`), or deleting a test while adding a different one with as many asserts
  3. shell commands (`sed`, `rm`, `git rm`, a script), including ones that change the guard or its settings: it only sees Claude Code's Edit, Write and MultiEdit
  4. parametrize cases built in code rather than written as a list, a deselect option set through an environment variable (`PYTEST_ADDOPTS`) or a file it doesn't watch, test paths given to pytest on its command line (`python -m pytest test_egress.py` runs only that file), and skips through other helpers or plugins
  5. other ways to get CI green while tests still fail: `|| true` on the pytest line, `continue-on-error`, shrinking the OS matrix, deleting the pytest step or adding an `if:` to it, `testpaths` / `python_files` collection settings, swapping a deselect option for a broader one (`-k 'not slow'` to `-k 'not slow and not screens'`), and the short or grouped option forms (`-mfast`, `-knot_screens`, `-qm fast`, `-qk "not screens"`)
  6. widening the no-display guard's condition, e.g. `if 'display' not in str(e) and sys.platform != 'win32':`, which then skips on other Tk errors too
  7. stopping pytest collecting tests without removing them: renaming a test class (`class TestA:` to `class A:`), or `__test__ = False` on a module or class
  8. a test renamed while also losing its asserts is blocked even if that was intended

  It needs `python3` on the PATH. Its own tests are `capacity_egress_app/test_guard_tests.py`.

## Future Ideas
1. A web link for the capacity check screen (OREM and others, nothing to install). Starts with asking UVic IT; no outside hosting.
2. Generalize the hierarchy of `facility_folder_automation` let the user choose which columns become folder levels, instead of hardcoding Property/Floor/Space.
   
### Tech Stack & Dependencies
* **Python 3** (3.13 for the app and CI)
* **Pandas** and **NumPy** (Data structures and analysis)
* **OpenPyXL** (Excel file engine backend)
* **Tkinter** (Desktop app window, comes with Python)
* **SQLite** (Database, comes with Python)
* **pytest** (Tests)
