import pandas as pd
import os
import glob

# config
DRY_RUN = True
bad_chars = '/\\:*?"<>|'
OUTPUT_DIR = "buildings"

# counters
files_processed = 0
folders_created = 0
folders_existing = 0
planned_paths = set()
all_frames = []

# sanitize name function
def sanitize(name):
    for c in bad_chars:
        name = name.replace(c, '-')
    return name.strip()

# glob
glob_pattern = os.path.join("input", "*.xlsx")
glob_list = glob.glob(glob_pattern)

#file loop
for excel_file in glob_list:

    if os.path.basename(excel_file).startswith('~$'):
        print("Skipping lock file:", excel_file)
        continue

    # header detection
    raw = pd.read_excel(excel_file, header=None, nrows=50)
    header_row = None

    # loop for raw; header detection
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

    all_frames.append(df_clean)


if not all_frames:
    raise ValueError("No excel files found in input")

combined = pd.concat(all_frames, ignore_index=True)
combined = combined.drop_duplicates()

# the list of choices
available = sorted(combined['Property'].unique())
print(f"\n{len(available)} properties found.")

# take input, find matches
while True:
    choice = input("Type building name(s), comma-separated (blank = all, q = quit): ").strip()
    if choice.lower() == 'q':
        raise SystemExit("Canceled.")

    #multi select function
    terms = [t.strip().lower() for t in choice.split(',') if t.strip()]
    if terms:
        matches = [p for p in available if any(t in p.lower() for t in terms)]
    else:
        matches = available
    if not matches:
        print("No properties matched. Try again.")
        continue

    print(f"\n{len(matches)} properties matched:")
    if len(matches) <= 20:
        for m in matches:
            print(" -", m)

    confirm = input("\n Process these? (y/n): ").strip().lower()
    if confirm == 'y':
        break

# filtered outside of loop
combined = combined[combined['Property'].isin(matches)]

# bad chars check
for col in columns_selected:
    for value in combined[col].unique():
        if any(c in value for c in bad_chars):
            print("suspect:", col, repr(value))

# row loop
for index, row in combined.iterrows():
    prop = row['Property']
    floor = row['Floor']
    space = row['Space']
    folder_path = os.path.join(OUTPUT_DIR, prop, f"Floor {floor}", space)
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

if planned_paths:
    print(max(len(os.path.abspath(p)) for p in planned_paths))

if DRY_RUN:
    print("DRY RUN — nothing was actually created")

input("\nDone. Press Enter to close...")



