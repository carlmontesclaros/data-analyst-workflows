import pytest
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table
from openpyxl.worksheet.filters import AutoFilter, FilterColumn, Filters
from openpyxl.worksheet.datavalidation import DataValidation
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
    # results say which code edition they were screened under
    assert pd.read_excel(path, sheet_name='floor_summary')['code_edition'].tolist() == ['BCBC 2024']

# fake template like 26-09-15 ROOM CAPACITY: factor table on top, header row 10, table allBLDG, per code formula
TEMPLATE_HEADER = ['Property', 'Floor', 'Space', 'Building Number', 'Net Space (sq ft)', 'Net Space (sq m)',
                   'Space Category', 'Space Sub-Category', 'Allocated Group', 'Fund', 'Orgn',
                   'OCCUPANT COUNT (per dept)', 'CAPACITY (per orem records)', 'OCCUPANT LOAD (per code)',
                   'ROOM TYPE (per code)', 'NOTES']
PER_CODE = '=IFERROR(F{r}/XLOOKUP(O{r},$M$3:$M$6,$N$3:$N$6),"")'

def fake_template(path):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Space_Details_Custom_Report2026'
    ws['M2'], ws['N2'] = 'room type', 'area/person (m2)'
    for r, (rt, m2) in enumerate([('classroom', 1.85), ('lab', 4.6), ('non-fixed', 0.95), ('office', 9.3)], 3):
        ws.cell(r, 13, rt)
        ws.cell(r, 14, m2)
    ws.append([])
    ws['E9'] = '=SUBTOTAL(9,E11:E100)'
    for c, name in enumerate(TEMPLATE_HEADER, 1):
        ws.cell(10, c, name)
    # 301 is in the template with group / fund / OREM; 999 is a room the app doesn't have
    rows = [['Fake Hall', 3, 301, 999, 651.754, 60.55, None, None, 'GEOG, Geography', 10000, 2830, None, 30, None, None, None],
            ['Fake Hall', 3, 999, 999, 10, 1, None, None, None, None, None, None, None, None, None, 'old room']]
    for r, row in enumerate(rows, 11):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)
        ws.cell(r, 14, PER_CODE.format(r=r))
    table = Table(displayName='allBLDG', ref='A10:P12')
    table.autoFilter = AutoFilter(ref='A10:P12')
    table.autoFilter.filterColumn.append(FilterColumn(colId=0, filters=Filters(filter=['Somewhere Else'])))
    ws.add_table(table)
    ws.add_data_validation(DataValidation(type='list', formula1='$M$3:$M$6', sqref='O11:O12'))
    wb.create_sheet('TOTAL EXIT CAP')['A1'] = 'BUILDING'
    wb.save(path)

def test_space_report_fills_the_template(tmp_path):
    template, path = tmp_path / 'template.xlsx', tmp_path / 'space_report.xlsx'
    fake_template(template)
    info = exports.write_space_report(result(), path, template)
    assert info['rooms'] == 2 and info['matched_template'] == 1
    df = pd.read_excel(path, header=9)
    assert list(df.columns) == TEMPLATE_HEADER and len(df) == 2
    r301, r302 = df.iloc[0], df.iloc[1]
    # site count -> L, only for visited rooms
    assert r301['OCCUPANT COUNT (per dept)'] == 30 and pd.isna(r302['OCCUPANT COUNT (per dept)'])
    # what the app doesn't store comes from the template's row
    assert r301['Allocated Group'] == 'GEOG, Geography' and r301['Fund'] == 10000
    assert r301['CAPACITY (per orem records)'] == 30
    # no template row -> sq ft from m2
    assert r302['Net Space (sq ft)'] == round(60.55 * exports.SQ_FT_PER_SQ_M, 3)
    wb = load_workbook(path)
    ws = wb['Space_Details_Custom_Report2026']
    assert wb.sheetnames == ['Space_Details_Custom_Report2026', 'TOTAL EXIT CAP']
    assert ws['M3'].value == 'classroom' and ws['E9'].value == '=SUBTOTAL(9,E11:E100)'
    assert ws['N11'].value.startswith('=IFERROR(') and ws['N12'].value.startswith('=IFERROR(')
    # table covers the new rows, old filter gone, dropdown follows
    assert ws.tables['allBLDG'].ref == 'A10:P12' and not ws.tables['allBLDG'].autoFilter.filterColumn
    assert str(ws.data_validations.dataValidation[0].sqref) == 'O11:O12'

def test_space_report_one_floor_and_no_template(tmp_path):
    template = tmp_path / 'template.xlsx'
    fake_template(template)
    info = exports.write_space_report(result(), tmp_path / 'none.xlsx', template, ['Nowhere'])
    # an empty selection still writes a valid table (one blank row)
    assert info['rooms'] == 0
    assert load_workbook(tmp_path / 'none.xlsx')['Space_Details_Custom_Report2026'].tables['allBLDG'].ref == 'A10:P11'
    with pytest.raises(FileNotFoundError):
        exports.find_template(tmp_path / 'empty_folder')
