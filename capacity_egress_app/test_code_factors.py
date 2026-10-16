import code_factors as cf
from test_egress import factors

# one place that knows how the code factor tables are laid out -> every caller asks it
def test_room_types_and_m2_per_person():
    f = factors()
    assert cf.room_types(f) == ['classroom', 'excluded', 'lab', 'non-fixed', 'office']
    m2 = cf.area_per_person(f)
    assert (m2['classroom'], m2['lab'], m2['office']) == (1.85, 4.6, 9.3)

def test_default_room_type_by_sub_category():
    defaults = cf.default_room_types(factors())
    assert defaults['1.2 - Non-Tiered Classroom'] == 'classroom'
    assert defaults.get('no such sub-category') is None

def test_unknown_room_types():
    assert cf.unknown_room_types(factors(), ['lab', 'lounge', None, '', 'Office ', 'gym', 'lounge']) == ['gym', 'lounge']
