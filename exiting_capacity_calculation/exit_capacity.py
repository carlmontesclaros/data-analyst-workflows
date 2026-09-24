import pandas as pd
import os
import glob

#configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
OUTPUT_DIR = BASE_DIR
ROOM_TYPE_COL = "Room type (per code m^2 used in capacity)"

# file recognition
SPACE_REPORT_HEADERS =  {'property', 'floor', 'space'}
EXITS_HEADERS =  {'property', 'floor', 'exit_type'}

room_keys = ['Property', 'Floor', 'Space']
room_cols = room_columns = ['Property', 'Floor', 'Space', 'Net Space (sq m)',
                'Space Sub-Category', 'Capacity (Occupants)', ROOM_TYPE_COL]
exit_keys = ['Property', 'Floor', 'exit_id']
exit_cols = ['Property', 'Floor', 'wing', 'exit_id', 'exit_type', 'clear_width_cm']

# counters
reports_processed = 0
exit_files_processed = 0
room_frames = []
exit_frames = []

# glob
glob_pattern = os.path.join(INPUT_DIR, "*.xlsx")
glob_list = sorted(glob.glob(glob_pattern))

# file loop
for excel_file in glob_list:
    name = os.path.basename(excel_file)
    if name.startswith("~$"):
        continue

    # header detection
    raw = pd.read_excel(excel_file, header=None, nrows=50)
    header_row = None
    kind = None

    for i in range(len(raw)):
        values = {str(x).strip().lower() for x in raw.iloc[i].tolist()}
        if SPACE_REPORT_HEADERS.issubset(values):
            header_row, kind = i, "space report"
            break
        if EXITS_HEADERS.issubset(values):
            header_row, kind = i, "exit report"
            break

    if header_row is None:
        raise ValueError(f"{name}: not a space report (Property/Floor/Space)" 
                         f"or an exit report (Property/Floor/exit_id)")



