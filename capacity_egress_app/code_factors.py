import pandas as pd

# code factors -> the tables from capacity_db.load_code_factors (area_factors, width_factors, category_map, settings)
# the one place that knows how they're laid out, so callers ask here instead of rebuilding lookups

# room types -> the rows of area_factors (classroom, lab, ...); excluded is a type with no m2 per person
def room_types(factors):
    return sorted(factors['area_factors']['room_type'])

def area_per_person(factors):
    table = factors['area_factors']
    return dict(zip(table['room_type'], table['area_per_person_m2']))

# sub-category -> room type it gets when the room has no override (category_map.csv)
def default_room_types(factors):
    table = factors['category_map']
    return dict(zip(table['space_sub_category'], table['room_type']))

# room type text as stored -> lowercase, blank = none
def clean_room_type(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value).strip().lower() or None

# room types written somewhere (space report, a screen) that aren't code factor room types
def unknown_room_types(factors, values):
    known = set(room_types(factors))
    return sorted({t for t in map(clean_room_type, values) if t is not None and t not in known})
