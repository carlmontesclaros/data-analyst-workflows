# UVic Data Analyst Internship Workflows 📊📋

A collection of data analytics and automation workflows developed during my data analyst internship at the **University of Victoria (UVic)**. This repository highlights projects focused on automating operational tasks, managing facilities data, and building cross-platform Python pipelines.

---

## What's in here?

I’m keeping everything modular. Each project or workflow gets its own separate folder so the root directory stays clean:

### Project Overview

### 📁 `01_facility_folder_automation` (Current project)
* **What it does:** Reads any input Excel file dropped into the folder and automatically generates a nested directory tree (`Property Name ➔ Floor Number ➔ Space/Room Number`).
* **The Stack:** Python, Pandas, OpenPyXL, built-in `os` and `glob` modules.
* **Why it matters:** Instead of manually building out hundreds of nested folders for campus inventory, you just drag and drop the raw spreadsheet into the script directory, hit run, and the pipeline dynamically builds the file architecture instantly.

### Tech Stack & Dependencies
* **Python 3**
* **Pandas** (Data structures and analysis)
* **OpenPyXL** (Excel file engine backend)
