import pandas as pd
import os
import glob

# config
DRY_RUN = True
ONLY_PROPERTIES = ['David Turpin Building']
bad_chars = '/\\:*?"<>|'

# with DRY_RUN
files_processed = 0
folders_created = 0
folders_existing = 0
planned_paths = set()

# sanitize name function
def sanitize(name):
    for c in bad_chars:
        name = name.replace(c, '_')
    return name.strip()

# glob
glob_pattern = os.path.join("input", "*.xlsx")
glob_list = glob.glob(glob_pattern)

#file loop
for excel_file in glob_list:

    # header detection
    raw = pd.read_excel(excel_file, header=None, nrows=50)
    header_row = None

    # loop for raw
    for i in range(len(raw)):
        values = [str(x).strip().lower() for x in raw.iloc[i].tolist()]
        if {'property', 'floor', 'space'}.issubset(values):
            header_row = i
            break

    if header_row is None:
        raise ValueError("No header row containing Property/Floor/Space found in the first 50 rows")

    print(excel_file, header_row)
    files_processed += 1

    # read excel file
    df = pd.read_excel(excel_file, header=header_row)

    # selecting columns
    columns_selected = ['Property', 'Floor', 'Space']
    df_clean = df[columns_selected].copy()

    # cleanup
    df_clean = df_clean.dropna(subset=columns_selected)

    for col in columns_selected:
        df_clean[col] = df_clean[col].astype(str).str.strip().str.removesuffix('.0').apply(sanitize)

    before = len(df_clean)
    df_clean = df_clean.drop_duplicates()
    # print(f"{before} rows -> {len(df_clean)} unique spaces")

    if ONLY_PROPERTIES:
        df_clean = df_clean[df_clean['Property'].isin(ONLY_PROPERTIES)]
    # bad chars check
    for col in columns_selected:
        for value in df_clean[col].unique():
            if any(c in value for c in bad_chars):
                print("suspect:", col, repr(value))

    # row loop
    for index, row in df_clean.iterrows():
        prop = row['Property']
        floor = row['Floor']
        space = row['Space']
        folder_path = os.path.join("Campus Space Photos", prop, f"Floor {floor}", space)
        if folder_path in planned_paths:
            continue
        planned_paths.add(folder_path)
        # print(folder_path)
        if os.path.exists(folder_path):
            folders_existing += 1
        else:
            folders_created += 1
        if not DRY_RUN:
            os.makedirs(folder_path, exist_ok=True)

print(f"Files processed: {files_processed}")
print(f"Folders created: {folders_created}")
print(f"Already existed: {folders_existing}")

if DRY_RUN:
    print("DRY RUN — nothing was actually created")


