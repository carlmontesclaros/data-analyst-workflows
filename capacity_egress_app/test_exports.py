import re
import pytest
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table, TableFormula
from openpyxl.worksheet.filters import AutoFilter, FilterColumn, Filters
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
    # S1 / S2 doors with no stair width -> 2 stair_not_measured warnings
    assert counts == {'floor_summary': 1, 'exit_detail': 2, 'room_detail': 2, 'warnings': 2}
    wb = load_workbook(path)
    assert wb.sheetnames == ['floor_summary', 'exit_detail', 'room_detail', 'warnings']
    ws = wb['floor_summary']
    assert ws.freeze_panes == 'A2' and ws['A1'].font.bold
    assert ws['A2'].fill.fgColor.rgb.endswith('C6EFCE')
    # results say which code edition they were screened under
    assert pd.read_excel(path, sheet_name='floor_summary')['code_edition'].tolist() == ['BCBC 2024']

# a note typed as '=...' stays text -> Excel never runs it as a formula
def test_results_workbook_writes_formula_like_text_as_text(tmp_path):
    res = result()
    res['exits'].loc[res['exits'].index[0], 'notes'] = '=HYPERLINK("http://example.com","x")'
    path = tmp_path / 'results.xlsx'
    exports.write_results_workbook(res, path)
    ws = load_workbook(path)['exit_detail']
    cells = [c for row in ws.iter_rows() for c in row if c.value == '=HYPERLINK("http://example.com","x")']
    assert cells and all(c.data_type == 's' for c in cells)

# fake template like carl_space_report: BCBC factor table on top, header row 7, Table1 A-L, Pictures link formula
TEMPLATE_HEADER = ['Property', 'Floor', 'Space', 'Building Number', 'Net Space (sq m)', 'Space Category',
                   'Space Sub-Category', 'Capacity (Occupants)', 'Capacity (per code)',
                   'Room type (per code m^2 used in capacity)', 'Note', 'Pictures']
PICTURES = 'HYPERLINK("S:\\buildings\\"&SUBSTITUTE(A{r},"/","-")&"\\Floor "&B{r}&"\\"&C{r},"Open")'

def fake_template(path):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Sheet1'
    ws['H1'], ws['H2'] = 'BCBC 2024 (per Table 3.1.17.1)', 'room type'
    for r, (rt, m2) in enumerate([('classroom', 1.85), ('lab', 4.6), ('non-fixed', 0.95), ('office', 9.3)], 3):
        ws.cell(r, 8, rt)
        ws.cell(r, 9, m2)
    for c, name in enumerate(TEMPLATE_HEADER, 1):
        ws.cell(7, c, name)
    # 301 is in the template with an FMIS count + note; 302 has a count but isn't visited; 999 the app doesn't have
    rows = [['Fake Hall', 3, 301, 999, 60.55, None, None, 0, 2230, None, 'by window', None],
            ['Fake Hall', 3, 302, 999, 60.55, None, None, 12, 2230, None, None, None],
            ['Fake Hall', 3, 999, 999, 1, None, None, None, None, None, 'old room', None]]
    for r, row in enumerate(rows, 8):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)
        ws.cell(r, 12, '=' + PICTURES.format(r=r))
    table = Table(displayName='Table1', ref='A7:L10')
    table.autoFilter = AutoFilter(ref='A7:L10')
    table.autoFilter.filterColumn.append(FilterColumn(colId=0, filters=Filters(filter=['Somewhere Else'])))
    table._initialise_columns()
    for column, name in zip(table.tableColumns, TEMPLATE_HEADER):
        column.name = name
    table.tableColumns[11].calculatedColumnFormula = TableFormula(attr_text=PICTURES.format(r=8))
    ws.add_table(table)
    wb.save(path)

def test_space_report_fills_the_template(tmp_path):
    template, path = tmp_path / 'template.xlsx', tmp_path / 'space_report.xlsx'
    fake_template(template)
    info = exports.write_space_report(result(), path, template)
    assert info['rooms'] == 2 and info['matched_template'] == 2
    df = pd.read_excel(path, header=6)
    assert list(df.columns) == TEMPLATE_HEADER and len(df) == 2
    r301, r302 = df.iloc[0], df.iloc[1]
    # site count for visited rooms; a room not visited keeps the template's count
    assert r301['Capacity (Occupants)'] == 30 and r302['Capacity (Occupants)'] == 12
    # per code = the app's load (60.55 m2 classroom -> 33), not the template's broken 2230
    assert r301['Capacity (per code)'] == 33 and r302['Capacity (per code)'] == 33
    # what the app doesn't store comes from the template's row
    assert r301['Note'] == 'by window'
    wb = load_workbook(path)
    ws = wb['Sheet1']
    assert ws['H3'].value == 'classroom' and ws['I6'].value == 9.3
    # Pictures link points at its own row
    assert ws['L8'].value == '=' + PICTURES.format(r=8) and ws['L9'].value == '=' + PICTURES.format(r=9)
    # table covers the new rows, old filter gone
    assert ws.tables['Table1'].ref == 'A7:L9' and not ws.tables['Table1'].autoFilter.filterColumn

def test_space_report_one_floor_and_no_template(tmp_path):
    template = tmp_path / 'template.xlsx'
    fake_template(template)
    info = exports.write_space_report(result(), tmp_path / 'none.xlsx', template, ['Nowhere'])
    # an empty selection still writes a valid table (one blank row)
    assert info['rooms'] == 0
    assert load_workbook(tmp_path / 'none.xlsx')['Sheet1'].tables['Table1'].ref == 'A7:L8'
    with pytest.raises(FileNotFoundError):
        exports.find_template(tmp_path / 'empty_folder')

def test_formula_for_row_leaves_text_alone():
    f = 'HYPERLINK("S:\\A8 photos\\"&amp;A8&amp;$B$8&amp;Table1[[#This Row],[Space]],"Open")'
    assert exports.formula_for_row(f, 8, 15) == 'HYPERLINK("S:\\A8 photos\\"&amp;A15&amp;$B$8&amp;Table1[[#This Row],[Space]],"Open")'

# capacity check summary .docx
def test_check_summary_docx(tmp_path):
    import zipfile
    from xml.dom.minidom import parseString
    rooms = pd.DataFrame([t.room('301', 60.55, 30, 'site count')])
    rooms['room_id'] = [7]
    check = t.egress.check_capacities(rooms, pd.DataFrame(t.TWO_DOORS, columns=t.EXIT_COLUMNS), t.factors(), {7: 40})
    when = pd.Timestamp('2026-10-13 10:30')
    name = exports.check_file_name(check, when)
    assert name == 'capacity_check_FH_301_2026-10-13.docx'
    path = exports.write_check_summary(check, tmp_path / name, 'Carl & co', when)
    with zipfile.ZipFile(path) as z:
        assert sorted(z.namelist()) == ['[Content_Types].xml', '_rels/.rels', 'word/_rels/document.xml.rels',
                                        'word/document.xml', 'word/styles.xml']
        doc = z.read('word/document.xml').decode('utf-8')
        for part in z.namelist():
            parseString(z.read(part))
    text = ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', doc))
    for expected in ['Fake Hall', 'Carl &amp; co', 'needs justification, +7 over per code', '30 (site count)',
                     'within exit capacity', 'Screening only, not an approval']:
        assert expected in text
    assert 'w:fill="FFEB9C"' in doc          # amber room row

def test_results_workbook_zone_colours(tmp_path):
    path = tmp_path / 'results.xlsx'
    exports.write_results_workbook(result(), path)
    assert load_workbook(path)['floor_summary']['A2'].fill.fgColor.rgb.endswith('C6EFCE')

def test_check_summary_shows_room_type_tried(tmp_path):
    import zipfile
    rooms = pd.DataFrame([t.room('301', 60.55)])
    rooms['room_id'] = [7]
    check = t.egress.check_capacities(rooms, pd.DataFrame(t.TWO_DOORS, columns=t.EXIT_COLUMNS), t.factors(), {}, {7: 'lab'})
    path = exports.write_check_summary(check, tmp_path / 'c.docx', 'Carl', pd.Timestamp('2026-10-16 10:00'))
    with zipfile.ZipFile(path) as z:
        text = ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', z.read('word/document.xml').decode('utf-8')))
    for expected in ['classroom -&gt; lab', '33 -&gt; 14', 'uses the per code load']:
        assert expected in text

def test_space_report_pm_change_on_a_visited_room_goes_into_capacity_occupants(tmp_path):
    # Carl, 2026-10-16: Capacity (Occupants) is the room capacity FMIS gets, so a PM change after the visit goes in
    rooms = pd.DataFrame([t.room('301', 60.55, 36, 'PM change'), t.room('302', 60.55)])
    for col, val in [('building_number', '999'), ('space_category', None), ('note', None),
                     ('fmis_capacity', None), ('in_latest_report', 1)]:
        rooms[col] = val
    rooms['visited'] = [1, 0]
    res = t.egress.calculate(rooms, pd.DataFrame(t.TWO_DOORS, columns=t.EXIT_COLUMNS), t.factors())
    template, path = tmp_path / 'template.xlsx', tmp_path / 'space_report.xlsx'
    fake_template(template)
    exports.write_space_report(res, path, template)
    assert pd.read_excel(path, header=6).iloc[0]['Capacity (Occupants)'] == 36

# fmis upload -> small copies of the 3 admin files (properties, floors, spaces) in a temp folder
def fmis_folder(tmp_path, spaces=None):
    pd.DataFrame({'Id': [1, 2], 'ExternalId': [237, None], 'Name': ['Turpin', 'Bus Loop']}).to_excel(
        tmp_path / 'Properties.xlsx', sheet_name='properties', index=False)
    pd.DataFrame({'FloorId': [10, 11, 20], 'PropertyId': [1, 1, 2], 'Description': ['3', '4', '0']}).to_excel(
        tmp_path / 'Floors.xlsx', sheet_name='floors', index=False)
    rows = spaces or [(100, 'B303', 1, 10, True), (101, 'B304', 1, 10, True), (102, 'B305', 1, 10, True),
                      (200, '4A', 1, 11, True), (300, 'Stop', 2, 20, True)]
    pd.DataFrame(rows, columns=['Id', 'Name', 'PropertyId', 'FloorId', 'ActiveFlag']).to_excel(
        tmp_path / 'Spaces.xlsx', sheet_name='spaces', index=False)
    return tmp_path

def fmis_rooms(*rooms):
    df = pd.DataFrame(rooms, columns=['property', 'floor', 'space', 'capacity'])
    df['building_number'] = df['property'].map({'Turpin': '237'})
    df['capacity_source'] = df['capacity'].map(lambda c: 'per code' if pd.isna(c) else 'site count')
    return {'rooms': df}

def upload_sheets(tmp_path, res, spaces=None, **kwargs):
    path = tmp_path / 'fmis_upload.xlsx'
    info = exports.write_fmis_upload(res, path, fmis_folder(tmp_path, spaces), **kwargs)
    return info, pd.read_excel(path, sheet_name=None, dtype={'Space': str, 'Space (FMIS)': str})

def test_fmis_upload_sends_counted_rooms_only_with_all_3_ids(tmp_path):
    res = fmis_rooms(('Turpin', '3', 'B303', 33), ('Turpin', '3', 'B304', 0), ('Turpin', '3', 'B305', None))
    info, sheets = upload_sheets(tmp_path, res)
    assert list(sheets) == ['upload', 'review', 'not_matched', 'all_spaces', 'readme']
    up = sheets['upload'].sort_values('Id')
    assert up.columns.tolist() == ['Id', 'PropertyId', 'FloorId', 'OccupantsDay', 'OccupantsNight', 'OccupantsTotal']
    # 0 is a count and gets sent; B305 has no count, a blank might clear FMIS -> left out
    assert up[['Id', 'PropertyId', 'FloorId', 'OccupantsDay']].values.tolist() == [[100, 1, 10, 33], [101, 1, 10, 0]]
    assert up['OccupantsNight'].tolist() == [33, 0] and up['OccupantsTotal'].tolist() == [33, 0]
    assert info == {'upload': 2, 'not_matched': 0}
    assert len(sheets['review']) == 2 and len(sheets['all_spaces']) == 5

def test_fmis_upload_matches_a_property_with_no_building_number_by_name(tmp_path):
    info, sheets = upload_sheets(tmp_path, fmis_rooms(('Bus  loop', '0', 'Stop', 2)))
    assert sheets['upload']['Id'].tolist() == [300]

def test_fmis_upload_matches_lost_leading_zeros_and_marks_them(tmp_path):
    spaces = [(100, '040', 1, 10, True)]
    info, sheets = upload_sheets(tmp_path, fmis_rooms(('Turpin', '3', '40', 5)), spaces)
    assert sheets['upload']['Id'].tolist() == [100]
    assert sheets['review']['Match'].tolist() == ['leading zeros']
    assert sheets['review']['Space (FMIS)'].tolist() == ['040']

def test_fmis_upload_lists_counted_room_with_no_match_and_skips_blank_ones(tmp_path):
    res = fmis_rooms(('Turpin', '3', 'Z1', 7), ('Turpin', '3', 'Z2', None))
    info, sheets = upload_sheets(tmp_path, res)
    assert info == {'upload': 0, 'not_matched': 1}
    assert sheets['upload'].empty
    assert sheets['not_matched'][['Space', 'Match']].values.tolist() == [['Z1', 'no match']]

# two of our rooms on one FMIS space -> can't tell which is right, even if only one has a count
def test_fmis_upload_holds_back_two_rooms_on_one_fmis_space(tmp_path):
    spaces = [(100, '01', 1, 10, True)]
    res = fmis_rooms(('Turpin', '3', '01', 4), ('Turpin', '3', '1', None))
    info, sheets = upload_sheets(tmp_path, res, spaces)
    assert info == {'upload': 0, 'not_matched': 1}
    assert sheets['not_matched']['Match'].tolist() == ['two rooms, one FMIS space']

# one room fits 2 FMIS spaces -> its count must not land on both
@pytest.mark.parametrize('names, space', [(['B303', 'B303'], 'B303'), (['040', '0040'], '40')])
def test_fmis_upload_holds_back_a_room_that_fits_two_fmis_spaces(tmp_path, names, space):
    spaces = [(100, names[0], 1, 10, True), (101, names[1], 1, 10, True)]
    info, sheets = upload_sheets(tmp_path, fmis_rooms(('Turpin', '3', space, 4)), spaces)
    assert info == {'upload': 0, 'not_matched': 1}
    assert sheets['not_matched']['Match'].tolist() == ['ambiguous']

# inactive spaces and a floor that belongs to another property are never upload targets
@pytest.mark.parametrize('space', [(100, 'B303', 1, 10, False), (100, 'B303', 1, 20, True)])
def test_fmis_upload_skips_inactive_and_wrong_property_spaces(tmp_path, space):
    info, sheets = upload_sheets(tmp_path, fmis_rooms(('Turpin', '0', 'B303', 4), ('Turpin', '3', 'B303', 4)), [space])
    assert info['upload'] == 0

def test_fmis_upload_keeps_to_the_building_and_floor_picked(tmp_path):
    res = fmis_rooms(('Turpin', '3', 'B303', 33), ('Turpin', '4', '4A', 8), ('Bus Loop', '0', 'Stop', 2),
                     ('Turpin', '4', 'Z9', 1))
    info, sheets = upload_sheets(tmp_path, res, properties=['Turpin'], floors=['3'])
    assert sheets['upload']['Id'].tolist() == [100]
    assert info == {'upload': 1, 'not_matched': 0}

def test_fmis_upload_says_which_admin_file_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match='Spaces.xlsx'):
        exports.write_fmis_upload(fmis_rooms(), tmp_path / 'x.xlsx', tmp_path)
