<!-- Moved word for word from CLAUDE.md on 2026-11-12 (context budget cut). Section numbers below are the original CLAUDE.md numbers. -->

# facility_folder_automation and the Excel photo links (from CLAUDE.md sections 7, 8)

Read before touching `facility_folder_automation/automation.py`, the `buildings/` tree, or the Pictures HYPERLINK formula.

## 7. Excel companion workflow: room photo links (not in the repo)

Carl's master spreadsheet gets one clickable link per room, built **in Excel**, not by a script, because pandas would destroy the slicers. In the `Pictures` column, for a row on line 8:

```
=HYPERLINK("<project folder on the S: drive>\buildings\"&SUBSTITUTE(A8,"/","-")&"\Floor "&B8&"\"&C8,"Open")
```

- **`SUBSTITUTE(A8,"/","-")` must mirror `sanitize()`.** The rule lives in two places; change one and the other breaks for the three ` / ` buildings.
- Debugging trick: drop the `HYPERLINK(` wrapper to see the built path as text, then compare it character by character with a path copied from Explorer.
- For exiting capacity, `photo_ref` on an exit row is free text. Exits aren't Spaces, so they have no folder in the `buildings/` tree.

## 8. `facility_folder_automation`

### 8.1 What it does

Reads FMIS space exports and creates `buildings/Property/Floor N/Space` folders for room photos. It's a single script, `automation.py`. Its `input/` and `buildings/` are gitignored.

### 8.2 Pipeline

1. **Config:** `DRY_RUN`, `bad_chars`, `SCRIPT_DIR`, `OUTPUT_DIR`.
2. **Glob** `SCRIPT_DIR/input/*.xlsx`.
3. **File loop:** skip `~$` lock files; detect the header (`header=None, nrows=50`, first row whose lowercased values ⊇ `{'property','floor','space'}`, `break`, `raise ValueError` if none); re-read with that header; select the 3 columns + `.copy()`; `dropna`; `.astype(str).str.strip().str.removesuffix('.0').apply(sanitize)`; append to `all_frames`.
4. **Concat** + `drop_duplicates()`.
5. **Interactive selection** (`while True`): comma-separated, case-insensitive substring search over property names. Blank = all, `q` quits; it lists the matches (the names if there are ≤ 20, otherwise a count), and `y` confirms.
6. **Filter** `combined` by the confirmed matches, **outside** the loop.
7. **Bad-chars check:** reports any illegal characters that survived.
8. **Row loop:** build the path; skip it if already in `planned_paths`; count created vs existing; `os.makedirs(..., exist_ok=True)` unless `DRY_RUN`.
9. **Summary** + dry-run banner + `input()` to hold the console open.

### 8.3 Design decisions (don't reopen)

| Decision | Why |
|---|---|
| Header auto-detection, not a fixed `header=6` | Headers sit on row 7 or 10 depending on the export; slicers and a BCBC table sit above the data. Hardcoding broke immediately |
| `nrows=50` for detection | Cheap; headers are never deeper. The error message names the limit |
| Floor as text, never `astype(int)` | `Roof`, `1M`, `P0`–`P4`, `Roof - A-Wing`… `astype(int)` crashed on the real file |
| `.str.removesuffix('.0')` | NaN-touched Floor columns become float, giving a folder named `Floor 3.0` |
| `sanitize()` replaces `/ \ : * ? " < > \|` with `-` | Three property names contain ` / `; without it `os.path.join` silently builds the wrong tree (exit code 0) |
| `os.path.join` everywhere | Same code on Mac and Windows; verified identical folder counts on both |
| `SCRIPT_DIR` anchoring | Relative `input/` broke when run from VS Code |
| `DRY_RUN = True` by default; commit it as `True` | The full export would create 19,151 folders, including non-buildings. The dry run caught this first |
| Interactive selection, not an `ONLY_PROPERTIES` constant | No editing code to pick a building; case-insensitive matching comes free |
| Filter applied **after** the `while` loop | Inside the loop it was destructive: answering `n` then retyping gave 0 folders while the display showed 5 matches |
| `planned_paths` set | Dedupes across files; otherwise dry-run and real-run counts disagree |
| `exist_ok=True`, never delete | Must be safe to re-run with photos already in the folders. Verified: 388 created / 0 existed, then 0 / 388 |
| `input()` at the end | The Windows console closes instantly otherwise |

### 8.4 Path length (Windows)

Output lives on the S: drive, whose prefix is about 133 characters. The measured longest absolute path is **189** (Turpin). The worst case (`Engineering - Computer Science Building` + `Floor Roof - A-Wing`) is about 220, plus about 23 for a photo filename, so about **242 against the 260 limit**. The output folder was renamed from `Campus Space Photos` to `buildings` to buy those characters. **Don't add a nesting level without re-measuring.** The measurement line, commented out at the bottom of the script:
`print(max(len(os.path.abspath(p)) for p in planned_paths))`

### 8.5 Verified reference numbers

| Input | Expected |
|---|---|
| Full campus export, blank selection | 19,119 unique spaces → 19,119 folders |
| All three test files, blank selection | 19,151 before dedupe across files / 19,119 with `planned_paths` |
| `turpin` | 1 property, **388 folders** |
| `turpin, engineering, maclaurin` | 7 properties, 1,852 folders |
| Second run of any of the above | 0 created, N already existed |
| Longest absolute path, Windows, S: drive, Turpin | 189 characters |

### 8.6 Issues in the committed code (small)

1. `OUTPUT_DIR` is assigned twice: line 8 sets `"buildings"`, line 10 overwrites it with the `SCRIPT_DIR` version. Delete line 8. **Done (PR #25).**
2. `sanitize()` reaches out to the module-level `bad_chars`. Fine at this size; passing it in would be cleaner. **Done (PR #25: `sanitize(name, bad_chars=BAD_CHARS)`).**
3. `columns_selected` is defined inside the file loop but used after it. It belongs in the config block. **Done (PR #25: `COLUMNS_SELECTED`).**
4. `bad_chars` isn't UPPER_CASE like the other constants. **Done (PR #25: `BAD_CHARS`).**

### 8.7 Deferred, by decision (not blocked)

- Move processed files to `input/processed/`.
- Refactor into functions (`find_header`, `clean_data`, `create_folders`). The collect → ask → build split, the hard part, is already done.
- Column-name normalisation (see the case-sensitivity note in section 5).
- Photo counts per folder written to a lookup file ("Open (4)" / "No photos"). Carl: *"no need for complications."* Power Query is the no-code alternative.
- A `.bat` launcher (`@echo off` / `py automation.py` / `pause`). `pause` runs even after a crash; `input()` doesn't.
- PyInstaller: rejected for now. You can't build a Windows `.exe` on a Mac, the output is about 100 MB, antivirus quarantines unsigned binaries, and nobody has asked for it. Whether UVic IT permits unsigned executables matters more than the technical side.
- A generalised folder hierarchy: logged under "Future Ideas" in the root README. Cheap to add later.
