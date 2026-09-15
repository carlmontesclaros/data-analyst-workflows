import pandas as pd
import os

# read excel file
df = pd.read_excel('DTB 3rd floor.xlsx', header=6)
print(df.shape)

# selecting columns
columns_selected = ['Property', 'Floor', 'Space']
df_filtered_columns = df[columns_selected]

# cleanup
df_filtered_columns = df_filtered_columns.dropna(subset=columns_selected)
df_filtered_columns['Floor'] = df_filtered_columns['Floor'].astype(int)

# print
print(df_filtered_columns.head())
print(df_filtered_columns.shape)
