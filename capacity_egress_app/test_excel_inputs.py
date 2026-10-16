import pytest
from openpyxl import Workbook
import excel_inputs as xi

# fake exports with the quirks of the real ones: rows above the header, float floors, duplicates, blanks
def workbook(path, rows):
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    wb.save(path)
    return str(path)

def test_space_report_header_found_and_rooms_cleaned(tmp_path):
    header = xi.SPACE_REPORT_COLS
    room = ['David Turpin Building', 3.0, 'B303', 237, 60.55, '1 - Classroom', '1.2 - Non-Tiered Classroom', 24, 'Classroom', None]
    path = workbook(tmp_path / 'report.xlsx', [['ROOM CAPACITY'], [], ['slicer area'], header, room, room,
                                               [None, '1', 'X1'] + [None] * 7])
    df = xi.read_space_report(path)
    assert len(df) == 1                                        # exact duplicate dropped, no-Property row dropped
    assert df.iloc[0][['Property', 'Floor', 'Space']].tolist() == ['David Turpin Building', '3', 'B303']

def test_not_a_space_report(tmp_path):
    with pytest.raises(ValueError, match='not a space report'):
        xi.read_space_report(workbook(tmp_path / 'other.xlsx', [['a', 'b'], [1, 2]]))

def test_exits_file_keeps_measured_rows_only(tmp_path):
    header = xi.EXIT_COLS
    measured = ['David Turpin Building', 3, 'B', None, 'S4 - doorway', 'doorway', 88.0, '2026-10-08', 'Carl', None, None, None]
    placeholder = ['David Turpin Building', 2] + [None] * 10
    df = xi.read_exits(workbook(tmp_path / 'exits.xlsx', [header, measured, placeholder]))
    assert len(df) == 1
    row = df.iloc[0]
    assert (row['Floor'], row['clear_width_cm'], row['measured_date']) == ('3', 88, '2026-10-08')
