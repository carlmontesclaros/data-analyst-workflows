import os
import re
import glob
import zipfile
from collections import Counter
from xml.sax.saxutils import escape, unescape
import numpy as np
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter, column_index_from_string
import capacity_db as db
import egress

# results workbook -> same 4 sheets as exit_capacity.py, column names people already know
SUMMARY_COLS = {'property': 'Property', 'floor': 'Floor', 'zone_wing': 'zone_wing', 'status': 'status',
                'flags': 'flags', 'total_load': 'total_load', 'exit_capacity': 'exit_capacity',
                'rooms_in_scope': 'rooms_in_scope', 'rooms_counted': 'rooms_counted',
                'counted_capacity': 'counted_capacity', 'area_based_load': 'area_based_load',
                'link_inflow': 'link_inflow', 'exit_count': 'exit_count', 'code_edition': 'code_edition',
                'floor_key': 'floor_key'}
EXIT_COLS = {'property': 'Property', 'floor': 'Floor', 'wing': 'wing', 'exit_id': 'exit_id',
             'exit_type': 'exit_type', 'clear_width_cm': 'clear_width_cm', 'counts_as_exit': 'counts_as_exit',
             'persons': 'persons', 'width_check': 'width_check', 'mm_per_person': 'mm_per_person',
             'minimum_mm': 'minimum_mm', 'minimum_mm_low_rise': 'minimum_mm_low_rise', 'into_wing': 'into_wing',
             'measured_date': 'measured_date', 'measured_by': 'measured_by', 'notes': 'notes', 'floor_key': 'floor_key'}
ROOM_COLS = {'property': 'Property', 'floor': 'Floor', 'space': 'Space', 'room_wing': 'room_wing',
             'zone_wing': 'zone_wing', 'sub_category': 'Space Sub-Category', 'room_type': 'room_type',
             'room_type_source': 'room_type_source', 'area_m2': 'Net Space (sq m)',
             'area_per_person_m2': 'area_per_person_m2', 'per_code_load': 'per_code_load',
             'capacity': 'room_capacity', 'capacity_source': 'capacity_source', 'fmis_capacity': 'fmis_capacity',
             'in_scope': 'in_scope', 'load_used': 'load_used', 'load_source': 'load_source',
             'in_latest_report': 'in_latest_report', 'floor_key': 'floor_key'}
WARNING_COLS = {'type': 'type', 'property': 'Property', 'floor': 'Floor', 'detail': 'detail'}

STATUS_FILLS = {egress.STATUS_REVIEW: PatternFill('solid', fgColor='F8CBAD'),
                egress.STATUS_WITHIN: PatternFill('solid', fgColor='C6EFCE'),
                egress.STATUS_NOT_SURVEYED: PatternFill('solid', fgColor='E7E6E6')}

def pick(df, properties=None, floors=None):
    if properties:
        df = df[df['property'].isin(properties)]
    if floors:
        df = df[df['floor'].isin(floors)]
    return df

def sheet(df, cols):
    return df[[c for c in cols if c in df.columns]].rename(columns=cols)

# formatting -> bold frozen header, filters, column widths <= 50
def format_sheets(writer):
    for ws in writer.sheets.values():
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col_cells in ws.columns:
            values = [len(str(c.value)) for c in col_cells if c.value is not None]
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(values, default=8) + 2, 50)

def write_results_workbook(result, path, properties=None, floors=None):
    summary = sheet(pick(result['zones'], properties, floors), SUMMARY_COLS)
    tables = {'floor_summary': summary,
              'exit_detail': sheet(pick(result['exits'], properties, floors), EXIT_COLS),
              'room_detail': sheet(pick(result['rooms'], properties, floors), ROOM_COLS),
              'warnings': sheet(pick(result['warnings'], properties, floors), WARNING_COLS)}
    try:
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            for name, df in tables.items():
                df.to_excel(writer, sheet_name=name, index=False)
            format_sheets(writer)
            # status colours -> whole row on floor_summary
            ws = writer.sheets['floor_summary']
            status_idx = list(summary.columns).index('status')
            for row in ws.iter_rows(min_row=2):
                fill = STATUS_FILLS.get(row[status_idx].value)
                if fill:
                    for cell in row:
                        cell.fill = fill
    except PermissionError:
        raise PermissionError(f"can't write {path} - it's probably open in Excel. close it and try again")
    return {name: len(df) for name, df in tables.items()}

# space report export -> Carl's baseline template (26-09-15 ROOM CAPACITY), filled with the app's rooms
# the template has slicers + pivots that openpyxl would destroy, so we never open it with openpyxl:
# copy the zip, rewrite only the allBLDG table's rows, keep every other file as is
TEMPLATE_DIR = os.path.join(db.DATA_DIR, "template")
TEMPLATE_TABLE = 'allBLDG'
SQ_FT_PER_SQ_M = 10.7639

# template columns A-P, by position. the app fills these; the rest come from the template's own row for that room
# L = site count (visited rooms), O = room type override, P = note. M (OREM) and I/J/K are only in the template
APP_COLS = {0: 'property', 1: 'floor', 2: 'space', 3: 'building_number', 5: 'area_m2', 6: 'space_category',
            7: 'sub_category'}
SQ_FT_COL, SITE_COUNT_COL, PER_CODE_COL, ROOM_TYPE_COL, NOTES_COL = 4, 11, 13, 14, 15

def find_template(folder=TEMPLATE_DIR):
    # whatever .xlsx is in data/template/ -> no hardcoded filename
    files = sorted(f for f in glob.glob(os.path.join(folder, '*.xlsx')) if not os.path.basename(f).startswith('~$'))
    if not files:
        raise FileNotFoundError(f"no template in {folder} - put the space report template (.xlsx) there")
    return files[0]

def blank(value):
    return value is None or (isinstance(value, float) and pd.isna(value)) or (isinstance(value, str) and value.strip() == '')

def key(value):
    # same normalising as the import -> '3.0' and 3 both become '3'
    return '' if blank(value) else str(value).strip().removesuffix('.0')

def cell(ref, style, value):
    s = f' s="{style}"' if style else ''
    if blank(value):
        return f'<c r="{ref}"{s}/>'
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        # pandas reads a column with blanks as float -> fund 10000.0 goes back as 10000
        return f'<c r="{ref}"{s}><v>{int(value) if float(value).is_integer() else value}</v></c>'
    text = str(value)
    # floor / space / building number like the FMIS export: 245 is a number, 'B303' or '0014' stays text
    if text.isdigit() and (text == '0' or not text.startswith('0')):
        return f'<c r="{ref}"{s}><v>{int(text)}</v></c>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'

def template_parts(z):
    # the sheet holding the allBLDG table -> (table xml path, sheet xml path)
    table_path = next((n for n in z.namelist() if n.startswith('xl/tables/')
                       and f'name="{TEMPLATE_TABLE}"' in z.read(n).decode('utf-8')), None)
    if table_path is None:
        raise ValueError(f"template has no table called {TEMPLATE_TABLE}")
    # Excel writes Target="../tables/table1.xml", openpyxl writes Target="/xl/tables/table1.xml"
    target = re.compile(r'Target="[^"]*tables/' + re.escape(os.path.basename(table_path)) + '"')
    for name in z.namelist():
        if name.startswith('xl/worksheets/_rels/') and target.search(z.read(name).decode('utf-8')):
            return table_path, 'xl/worksheets/' + os.path.basename(name).removesuffix('.rels')
    raise ValueError(f"can't find the sheet for table {TEMPLATE_TABLE}")

def sheet_name(z, sheet_path):
    # xl/worksheets/sheet1.xml -> its tab name, via workbook.xml.rels (r:id) and workbook.xml (name)
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    rel_id = re.search(r'<Relationship [^>]*Id="(\w+)"[^>]*Target="[^"]*' + re.escape(os.path.basename(sheet_path)) + '"', rels)
    if rel_id is None:
        rel_id = re.search(r'<Relationship [^>]*Target="[^"]*' + re.escape(os.path.basename(sheet_path)) + r'"[^>]*Id="(\w+)"', rels)
    sheet = re.search(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="' + rel_id.group(1) + '"', z.read('xl/workbook.xml').decode('utf-8'))
    return unescape(sheet.group(1))

def row_styles_and_formula(data_rows):
    # most common style per column + the per code formula, from the template's first 50 data rows
    styles = [Counter() for _ in range(16)]
    formulas = Counter()
    for row in data_rows[:50]:
        for c in re.finditer(r'<c r="([A-Z]+)\d+"(?: s="(\d+)")?[^>]*?(?:/>|>(.*?)</c>)', row, re.S):
            col = column_index_from_string(c.group(1)) - 1
            if col < 16:
                styles[col][c.group(2)] += 1
            f = re.search(r'<f>(.*?)</f>', c.group(3) or '', re.S)
            if f and col == PER_CODE_COL:
                formulas[f.group(1)] += 1
    return [s.most_common(1)[0][0] if s else None for s in styles], (formulas.most_common(1)[0][0] if formulas else None)

def write_space_report(result, path, template_path=None, properties=None, floors=None):
    template_path = template_path or find_template()
    rooms = pick(result['rooms'], properties, floors)
    rooms = rooms[rooms['in_latest_report'] == 1].sort_values(['property', 'floor', 'space'])

    with zipfile.ZipFile(template_path) as z:
        table_path, sheet_path = template_parts(z)
        table_xml = z.read(table_path).decode('utf-8')
        sheet_xml = z.read(sheet_path).decode('utf-8')
        header_row = int(re.search(r'<table [^>]*ref="[A-Z]+(\d+):', table_xml).group(1))

        # the template's own rows -> baseline for what the app doesn't store (sq ft, group, fund, orgn, OREM)
        baseline = pd.read_excel(template_path, sheet_name=sheet_name(z, sheet_path), header=header_row - 1)
        baseline_rows = {}
        for values in baseline.iloc[:, :16].itertuples(index=False):
            baseline_rows.setdefault((key(values[0]), key(values[1]), key(values[2])), list(values))

        start, end = sheet_xml.index('<sheetData>') + len('<sheetData>'), sheet_xml.index('</sheetData>')
        all_rows = re.findall(r'<row [^>]*/>|<row [^>]*>.*?</row>', sheet_xml[start:end], re.S)
        row_number = lambda row: int(re.search(r' r="(\d+)"', row).group(1))
        top_rows = [row for row in all_rows if row_number(row) <= header_row]
        styles, formula = row_styles_and_formula([row for row in all_rows if row_number(row) > header_row])

        # new rows -> app values over the template's row for the same room
        first = header_row + 1
        new_rows = []
        matched = 0
        for i, room in enumerate(rooms.itertuples(index=False)):
            r = first + i
            k = (key(room.property), key(room.floor), key(room.space))
            values = list(baseline_rows.get(k, [None] * 16))
            matched += k in baseline_rows
            for col, field in APP_COLS.items():
                values[col] = getattr(room, field)
            if blank(values[SQ_FT_COL]) and not blank(room.area_m2):
                values[SQ_FT_COL] = round(room.area_m2 * SQ_FT_PER_SQ_M, 3)
            if room.visited == 1 and not blank(room.capacity):
                values[SITE_COUNT_COL] = int(room.capacity)
            if not blank(room.room_type_override):
                values[ROOM_TYPE_COL] = room.room_type_override
            if not blank(room.note):
                values[NOTES_COL] = room.note
            cells = [cell(f"{get_column_letter(c + 1)}{r}", styles[c], v) for c, v in enumerate(values)]
            if formula:
                s = f' s="{styles[PER_CODE_COL]}"' if styles[PER_CODE_COL] else ''
                cells[PER_CODE_COL] = f'<c r="{get_column_letter(PER_CODE_COL + 1)}{r}"{s}><f>{formula}</f></c>'
            new_rows.append(f'<row r="{r}" spans="1:16">' + ''.join(cells) + '</row>')
        if not new_rows:
            # an Excel table needs at least one data row
            new_rows.append(f'<row r="{first}" spans="1:16">'
                            + ''.join(cell(f"{get_column_letter(c + 1)}{first}", styles[c], None) for c in range(16)) + '</row>')
        last = first + len(new_rows) - 1

        sheet_xml = sheet_xml[:start] + ''.join(top_rows) + ''.join(new_rows) + sheet_xml[end:]
        sheet_xml = re.sub(r'<dimension ref="([A-Z]+)1:([A-Z]+)\d+"/>', rf'<dimension ref="\g<1>1:\g<2>{last}"/>', sheet_xml)
        sheet_xml = re.sub(r'topLeftCell="[A-Z]+\d+"', f'topLeftCell="A{first}"', sheet_xml)
        sheet_xml = re.sub(r'activeCell="[A-Z]+\d+" sqref="[^"]*"', f'activeCell="A{first}" sqref="A{first}"', sheet_xml)
        sheet_xml = re.sub(r'(<dataValidation [^>]*sqref=")([A-Z]+)\d+:([A-Z]+)\d+"', rf'\g<1>\g<2>{first}:\g<3>{last}"', sheet_xml)

        # table covers the new rows; clear the saved filter (the template was saved filtered to ECS)
        table_xml = re.sub(r'ref="([A-Z]+)(\d+):([A-Z]+)\d+"', rf'ref="\g<1>\g<2>:\g<3>{last}"', table_xml)
        table_xml = re.sub(r'<filterColumn .*?</filterColumn>', '', table_xml, flags=re.S)

        try:
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as out:
                for item in z.infolist():
                    name = item.filename
                    if name == 'xl/calcChain.xml':
                        continue        # old list of formula cells; Excel rebuilds it
                    data = z.read(name)
                    if name == sheet_path:
                        data = sheet_xml.encode('utf-8')
                    elif name == table_path:
                        data = table_xml.encode('utf-8')
                    elif name.startswith('xl/pivotCache/pivotCacheDefinition') and b'refreshOnLoad' not in data:
                        # pivots still hold the template's numbers -> refresh when the file opens
                        data = data.replace(b'<pivotCacheDefinition ', b'<pivotCacheDefinition refreshOnLoad="1" ', 1)
                    elif name == 'xl/workbook.xml' and b'fullCalcOnLoad' not in data:
                        data = data.replace(b'<calcPr ', b'<calcPr fullCalcOnLoad="1" ', 1)
                    elif name == 'xl/_rels/workbook.xml.rels':
                        data = re.sub(rb'<Relationship [^>]*Target="calcChain.xml"/>', b'', data)
                    elif name == '[Content_Types].xml':
                        data = re.sub(rb'<Override PartName="/xl/calcChain.xml"[^>]*/>', b'', data)
                    out.writestr(item, data)
        except PermissionError:
            raise PermissionError(f"can't write {path} - it's probably open in Excel. close it and try again")
    return {'rooms': len(rooms), 'matched_template': int(matched), 'template': os.path.basename(template_path)}
