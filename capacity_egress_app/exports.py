import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
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

# capacity export -> space report layout for the FMIS capacity import
# room capacity only where someone set one, per code only for visited rooms, no Pictures column
CAPACITY_EXPORT_COLS = ['Property', 'Floor', 'Space', 'Building Number', 'Net Space (sq m)', 'Space Category',
                        'Space Sub-Category', 'Capacity (Occupants)', 'Capacity (per code)',
                        'Room type (per code m^2 used in capacity)', 'Capacity source', 'Note']

def write_capacity_export(result, path, properties=None, floors=None):
    rooms = pick(result['rooms'], properties, floors)
    rooms = rooms[rooms['in_latest_report'] == 1]
    out = pd.DataFrame({
        'Property': rooms['property'], 'Floor': rooms['floor'], 'Space': rooms['space'],
        'Building Number': rooms['building_number'], 'Net Space (sq m)': rooms['area_m2'],
        'Space Category': rooms['space_category'], 'Space Sub-Category': rooms['sub_category'],
        'Capacity (Occupants)': pd.to_numeric(rooms['capacity'], errors='coerce').astype('Int64'),
        'Capacity (per code)': rooms['per_code_load'].where(rooms['visited'] == 1).astype('Int64'),
        'Room type (per code m^2 used in capacity)': rooms['room_type_override'],
        'Capacity source': rooms['capacity_source'], 'Note': rooms['note'],
    })[CAPACITY_EXPORT_COLS].sort_values(['Property', 'Floor', 'Space'])
    try:
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            out.to_excel(writer, sheet_name='capacity', index=False)
            format_sheets(writer)
    except PermissionError:
        raise PermissionError(f"can't write {path} - it's probably open in Excel. close it and try again")
    return len(out)
