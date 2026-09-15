import pandas as pd
import os
import glob

# read excel file
df = pd.read_excel('DTB 3rd floor.xlsx', header=6)

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
    folder_path = os.path.join(prop, f"Floor {floor}", space)
    # print(folder_path)
    os.makedirs(folder_path, exist_ok=True)

# print
# print(df_clean.head())
# print(df_clean.shape)
