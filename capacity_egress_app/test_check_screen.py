import pandas as pd
from check_screen import find_rooms, initials, match_buildings

ROOMS = pd.DataFrame([
    {'room_id': 1, 'property': 'David Turpin Building', 'floor': '1', 'space': 'A120'},
    {'room_id': 2, 'property': 'David Turpin Building', 'floor': '1', 'space': 'A102'},
    {'room_id': 3, 'property': 'David Turpin Building', 'floor': '3', 'space': 'B303'},
    {'room_id': 4, 'property': 'Clearihue Building', 'floor': '1', 'space': 'A120'},
    {'room_id': 5, 'property': 'Engineering Office Wing', 'floor': '1', 'space': '120'},
])

def ids(found):
    return found['room_id'].tolist()

def test_initials():
    assert initials('David Turpin Building') == 'dtb'
    assert initials('Engineering / Computer Science Building') == 'ecsb'

def test_search_building_and_room():
    assert ids(find_rooms(ROOMS, 'DTB A120')) == [1]
    assert ids(find_rooms(ROOMS, 'turpin a120')) == [1]
    assert ids(find_rooms(ROOMS, 'A120')) == [4, 1]                     # exact room number, any building
    assert ids(find_rooms(ROOMS, '120')) == [5]                         # exact beats contains
    assert ids(find_rooms(ROOMS, 'A1')) == [4, 2, 1]                    # no exact -> contains
    assert ids(find_rooms(ROOMS, 'turpin')) == [2, 1, 3]

def test_search_with_dropdowns_and_empty():
    assert ids(find_rooms(ROOMS, '', 'David Turpin Building', '3')) == [3]
    assert ids(find_rooms(ROOMS, '')) == []
    assert ids(find_rooms(ROOMS, 'nowhere')) == []

def test_match_buildings():
    names = ['Clearihue Building', 'David Turpin Building', 'Engineering / Computer Science Building', 'Turpin Annex']
    assert match_buildings(names, 'tur') == ['Turpin Annex', 'David Turpin Building']   # starts-with first
    assert match_buildings(names, 'DTB') == ['David Turpin Building']                   # initials
    assert match_buildings(names, 'comp sci') == ['Engineering / Computer Science Building']
    assert match_buildings(names, '') == names
    assert match_buildings(names, 'zzz') == []
