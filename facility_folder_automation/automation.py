import pandas as pd
import os
import glob

# glob
glob_pattern = os.path.join("input", "*.xlsx")
glob_list = glob.glob(glob_pattern)
# print(glob_list)

for excel_file in glob_list:

    # read excel file
    df = pd.read_excel(excel_file, header=6)

    # selecting columns
    columns_selected = ['Property', 'Floor', 'Space']
    df_clean = df[columns_selected].copy()

    # cleanup
    df_clean = df_clean.dropna(subset=columns_selected)
    df_clean['Floor'] = df_clean['Floor'].astype(int)

    # loop
    for index, row in df_clean.iterrows():
        prop = row['Property']
        floor = row['Floor']
        space = row['Space']
        folder_path = os.path.join("Campus Space Photos", prop, f"Floor {floor}", space)
        # print(folder_path)
        os.makedirs(folder_path, exist_ok=True)


