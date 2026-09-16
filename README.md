# UVic Data Analyst Internship Workflows 

A collection of data analytics and automation workflows developed during my data analyst internship at the **University of Victoria (UVic)**. This repository highlights self-directed automation tools and pipelines I built on my own initiative to optimize internal data workflows, replacing tedious manual tasks before anyone even asked me to.

---

## What's in here?

I’m keeping everything modular. Each project or workflow gets its own separate folder so the root directory stays clean:

### Project Overview

### 📁 `facility_folder_automation` (Current project)
* **What it does:**
  1. Reads any input Excel file dropped into the "input/" folder and automatically generates a nested directory tree (`Property Name ➔ Floor Number ➔ Space/Room Number`).
  2. Automatic header detection -> finds the header row wherever it sits, files with slicers, subtotals or loop up tables above the data all work.
  3. Batch processing - every .xlsx in input folder, not one file.
  4. DRY_RUN = True mode which previews counts without creating any folders
  5. ONLY_PROPERTIES = [] which can restrict run to named buildings. "[]" means all -> for full reports.
  6. Safe to rerun: existing folders and their contents are never touched or deleted
* **The Stack:** Python, Pandas, OpenPyXL, built-in `os` and `glob` modules.
* **Why it matters:** Instead of manually building out hundreds of nested folders for campus inventory, you just drag and drop the raw spreadsheet into the "input/" folder, hit run, and output goes to "Campus Space Photos/" folder
* **Limitations:**
    1. Renaming a space in the source file creates a new folder; the old one is not moved or removed.
    2. Excel filters are ignored -> hidden rows will get processed. Copy visible cells to a new sheet before saving!
    3. Currently capitalization matters will be fixed soon -> column headers must be named exactly "Property", "Floor", and "Space".
    4. Characters illegal in paths (/ \ : * ? " < > |) are replaced with - in folder names.
### Tech Stack & Dependencies
* **Python 3**
* **Pandas** (Data structures and analysis)
* **OpenPyXL** (Excel file engine backend)
