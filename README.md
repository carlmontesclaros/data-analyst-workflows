# UVic Data Analyst Internship Workflows 

A collection of data analytics and automation workflows developed during my data analyst internship at the **University of Victoria (UVic)**. This repository highlights self-directed automation tools and pipelines I built on my own initiative to optimize internal data workflows, replacing tedious manual tasks before anyone even asked me to.

---

## What's in here?

I’m keeping everything modular. Each project or workflow gets its own separate folder so the root directory stays clean:

### Project Overview

### 📁 `facility_folder_automation` (Current project)
* **What it does:** Reads any input Excel file dropped into the folder and automatically generates a nested directory tree (`Property Name ➔ Floor Number ➔ Space/Room Number`).
* **The Stack:** Python, Pandas, OpenPyXL, built-in `os` and `glob` modules.
* **Why it matters:** Instead of manually building out hundreds of nested folders for campus inventory, you just drag and drop the raw spreadsheet into the script directory, hit run, and the pipeline dynamically builds the file architecture instantly.
* **Limitations:** 1. Renaming a space in the source file creates a new folder; the old one is not moved or removed. 2. Excel filters are ignored -> hidden rows will get processed. Copy visible cells to a new sheet before saving! 3. Currently capitalization matters will be fixed soon. Column headers must be named exactly "Property", "Floor", and "Space". 4. Non numeric floors (G, P1, ...) will crash the script. 5. Characters illegal in paths (/ \ : * ? " < > |) are replaced with - in folder names.
  

### Tech Stack & Dependencies
* **Python 3**
* **Pandas** (Data structures and analysis)
* **OpenPyXL** (Excel file engine backend)
