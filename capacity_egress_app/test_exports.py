import pandas as pd
from openpyxl import load_workbook
import exports
import test_egress as t

def result():
    rooms = pd.DataFrame([t.room('301', 60.55, 30, 'site count'), t.room('302', 60.55)])
    for col, val in [('building_number', '999'), ('space_category', None), ('note', None),
                     ('fmis_capacity', None), ('in_latest_report', 1)]:
        rooms[col] = val
    rooms['visited'] = [1, 0]
    return t.egress.calculate(rooms, pd.DataFrame(t.TWO_DOORS, columns=t.EXIT_COLUMNS), t.factors())

def test_results_workbook_has_4_formatted_sheets(tmp_path):
    path = tmp_path / 'results.xlsx'
    counts = exports.write_results_workbook(result(), path)
    assert counts == {'floor_summary': 1, 'exit_detail': 2, 'room_detail': 2, 'warnings': 0}
    wb = load_workbook(path)
    assert wb.sheetnames == ['floor_summary', 'exit_detail', 'room_detail', 'warnings']
    ws = wb['floor_summary']
    assert ws.freeze_panes == 'A2' and ws['A1'].font.bold
    assert ws['A2'].fill.fgColor.rgb.endswith('C6EFCE')

def test_capacity_export_per_code_only_for_visited(tmp_path):
    path = tmp_path / 'capacity.xlsx'
    assert exports.write_capacity_export(result(), path) == 2
    df = pd.read_excel(path)
    assert list(df.columns) == exports.CAPACITY_EXPORT_COLS
    assert df['Capacity (Occupants)'].tolist()[0] == 30 and pd.isna(df['Capacity (Occupants)'].tolist()[1])
    assert df['Capacity (per code)'].tolist()[0] == 33 and pd.isna(df['Capacity (per code)'].tolist()[1])
