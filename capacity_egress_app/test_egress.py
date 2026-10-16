import os
import pandas as pd
import pytest
import egress

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
EXIT_COLUMNS = ['property', 'floor', 'wing', 'into_wing', 'exit_id', 'exit_type', 'clear_width_cm']

def factors(**settings):
    f = {t: pd.read_csv(os.path.join(CONFIG_DIR, f'{t}.csv'))
         for t in ['area_factors', 'width_factors', 'category_map', 'settings']}
    extra = {'room_exclude': '14.3,16', 'open_stairs_count': 'no'}
    extra.update(settings)
    f['settings'] = pd.concat([f['settings'], pd.DataFrame(
        [{'setting': k, 'value': v} for k, v in extra.items()])], ignore_index=True)
    return f

CLASSROOM = '1.2 - Non-Tiered Classroom'

def room(space, area, capacity=None, source='per code', sub=CLASSROOM, floor='3'):
    return {'property': 'Fake Hall', 'floor': floor, 'space': space, 'area_m2': area, 'sub_category': sub,
            'capacity': capacity, 'capacity_source': source if capacity is not None else 'per code',
            'room_type_override': None}

def exit_row(exit_id, exit_type, cm, wing=None, into_wing=None, floor='3'):
    return {'property': 'Fake Hall', 'floor': floor, 'wing': wing, 'into_wing': into_wing,
            'exit_id': exit_id, 'exit_type': exit_type, 'clear_width_cm': cm}

def run(rooms, exits, **settings):
    return egress.calculate(pd.DataFrame(rooms), pd.DataFrame(exits, columns=EXIT_COLUMNS), factors(**settings))

def zone(result, wing=''):
    z = result['zones']
    return z[z['zone_wing'] == wing].iloc[0]

TWO_DOORS = [exit_row('S1 - doorway', 'doorway', 88), exit_row('S2 - doorway', 'doorway', 88)]

def test_visited_zero_stays_zero_unvisited_uses_per_code():
    # B303-like room: 60.55 m2 classroom = 33 per code
    result = run([room('301', 60.55, 0, 'site count'), room('302', 60.55)], TWO_DOORS)
    z = zone(result)
    assert z['total_load'] == 33
    assert z['exit_capacity'] == 288            # 144 + 144, 50% rule
    assert z['status'] == egress.STATUS_WITHIN

def test_pm_change_beats_per_code():
    result = run([room('301', 60.55, 36, 'PM change')], TWO_DOORS)
    assert zone(result)['total_load'] == 36
    assert result['rooms'].iloc[0]['load_source'] == 'PM change'

def test_out_of_scope_rooms_add_nothing():
    result = run([room('301', 60.55, 30, 'site count'), room('C1', 100, sub='16.2.4 - Circulation Space')], TWO_DOORS)
    assert zone(result)['total_load'] == 30

def test_open_stair_not_an_exit_until_ruled():
    exits = [exit_row('S4 - doorway', 'doorway', 88), exit_row('S5 - open stair', 'stairs', 121),
             exit_row('E3 - outside exit', 'doorway', 88)]
    rooms = [room('301', 60.55, 30, 'site count')]
    assert zone(run(rooms, exits))['exit_capacity'] == 288
    assert zone(run(rooms, exits, open_stairs_count='yes'))['exit_capacity'] == 439

def test_one_exit_is_review():
    z = zone(run([room('301', 20, 10, 'site count')], [exit_row('S1', 'doorway', 88)]))
    assert z['exit_capacity'] == 0
    assert z['status'] == egress.STATUS_REVIEW
    assert 'fewer than 2 exits' in z['flags']

def test_wings_and_link_door():
    rooms = [room('B301', 60.55, 161, 'site count'), room('A301', 20, 10, 'site count')]
    exits = [exit_row('S4', 'doorway', 88, 'B'), exit_row('E3', 'doorway', 88, 'B', into_wing='A'),
             exit_row('S2', 'doorway', 88, 'A'), exit_row('S3', 'doorway', 88, 'A')]
    result = run(rooms, exits)
    assert zone(result, 'A')['link_inflow'] == 81    # ceil(161 / 2 exits)
    assert zone(result, 'A')['total_load'] == 91

def test_no_exits_not_surveyed():
    z = zone(run([room('301', 60.55)], []))
    assert z['status'] == egress.STATUS_NOT_SURVEYED
    assert z['total_load'] == 33

def test_calculate_floor_matches_campus():
    rooms = [room('301', 60.55, 30, 'site count'), room('201', 40, floor='2')]
    campus = run(rooms, TWO_DOORS)['zones']
    floor = egress.calculate_floor(pd.DataFrame(rooms), pd.DataFrame(TWO_DOORS), factors(), 'Fake Hall', '3')['zones']
    assert campus[campus['floor'] == '3']['total_load'].tolist() == floor['total_load'].tolist()

# colours (README "Colours")
def test_room_colours():
    rooms = run([room('301', 60.55, 30, 'site count'), room('302', 60.55, 40, 'site count'), room('303', 60.55),
                 room('304', 20, 5, 'site count', sub='16.1 - Circulation')], TWO_DOORS)['rooms'].set_index('space')
    assert [egress.room_colour(rooms.loc[s]) for s in ['301', '302', '303', '304']] == \
           [egress.GREEN, egress.AMBER, egress.GREY, egress.NONE]

def test_zone_colours_red_only_when_over_exit_capacity():
    assert egress.zone_colour(zone(run([room('301', 60.55, 30, 'site count')], TWO_DOORS))) == egress.GREEN
    # one exit -> capacity 0, load over it -> red
    assert egress.zone_colour(zone(run([room('301', 20, 10, 'site count')], [exit_row('S1', 'doorway', 88)]))) == egress.RED
    # review but not over (a stair needing a width review) -> amber
    stairs = [exit_row('S1', 'stairs', 95), exit_row('S2', 'doorway', 88)]
    assert egress.zone_colour(zone(run([room('301', 20, 10, 'site count')], stairs))) == egress.AMBER
    assert egress.zone_colour(zone(run([room('301', 60.55)], []))) == egress.GREY

def test_exit_colours():
    exits = run([room('301', 20)], [exit_row('S1', 'doorway', 88), exit_row('S2', 'doorway', 80),
                                    exit_row('S3', 'stairs', 95), exit_row('S5 - open stair', 'stairs', 121)])['exits']
    assert [egress.exit_colour(e) for _, e in exits.sort_values('exit_id').iterrows()] == \
           [egress.GREEN, egress.RED, egress.AMBER, egress.GREY]

# capacity check -> nothing saved, two answers
def check_tables(rooms, exits):
    rooms = pd.DataFrame(rooms)
    rooms['room_id'] = range(1, len(rooms) + 1)
    return rooms, pd.DataFrame(exits, columns=EXIT_COLUMNS), factors()

def test_check_needs_justification_and_floor_over():
    # 60.55 m2 classroom = 33 per code; two 88 cm doors = 288 exit capacity
    rooms, exits, f = check_tables([room('301', 60.55, 30, 'site count'), room('302', 60.55, 200, 'site count')], TWO_DOORS)
    check = egress.check_capacities(rooms, exits, f, {1: 40})
    r = check['rooms'][0]
    assert (r['current'], r['proposed'], r['per_code_load'], r['over_per_code']) == (30, 40, 33, 7)
    assert r['verdict'] == 'needs justification, +7 over per code' and r['colour'] == egress.AMBER
    z = check['zones'][0]
    assert (z['load_before'], z['load_after'], z['exit_capacity']) == (230, 240, 288)
    assert z['verdict'] == 'within exit capacity' and z['has_checked_room']
    # two rooms together go over -> red
    check = egress.check_capacities(rooms, exits, f, {1: 33, 2: 260})
    z = check['zones'][0]
    assert z['load_after'] == 293 and z['verdict'] == 'over exit capacity by 5' and z['colour'] == egress.RED
    # nothing changed in the tables passed in
    assert rooms['capacity'].tolist() == [30, 200]

def test_check_cant_check_unmeasured_floor_and_one_building_only():
    rooms, exits, f = check_tables([room('301', 60.55)], [])
    check = egress.check_capacities(rooms, exits, f, {1: 20})
    assert check['rooms'][0]['current'] is None and check['rooms'][0]['verdict'] == 'within per code'
    assert check['zones'][0]['verdict'] == egress.CANT_CHECK and check['zones'][0]['colour'] == egress.GREY
    other = dict(room('101', 10), property='Other Hall')
    rooms, exits, f = check_tables([room('301', 60.55), other], [])
    with pytest.raises(ValueError):
        egress.check_capacities(rooms, exits, f, {1: 20, 2: 5})

def test_check_room_type_changes_per_code():
    # 60.55 m2: classroom 33, lab 14, office 7 per code
    rooms, exits, f = check_tables([room('301', 60.55), room('302', 60.55, 200, 'site count')], TWO_DOORS)
    # not visited -> the per code load is what the floor carries, so the zone drops 233 -> 214
    check = egress.check_capacities(rooms, exits, f, {}, {1: 'Lab'})
    r = check['rooms'][0]
    assert (r['room_type_before'], r['room_type'], r['per_code_before'], r['per_code_load']) == ('classroom', 'lab', 33, 14)
    assert r['proposed'] is None and r['type_changed'] and r['verdict'] == 'not visited: uses the per code load'
    assert (check['zones'][0]['load_before'], check['zones'][0]['load_after']) == (233, 214)
    # visited -> floor load unchanged, but the count is now judged against the office per code load
    check = egress.check_capacities(rooms, exits, f, {}, {2: 'office'})
    r = check['rooms'][0]
    assert r['verdict'] == 'needs justification, +193 over per code' and r['colour'] == egress.AMBER
    assert check['zones'][0]['load_after'] == 233
    # capacity and type together, one room each way
    check = egress.check_capacities(rooms, exits, f, {1: 20}, {1: 'lab'})
    r = check['rooms'][0]
    assert (r['proposed'], r['per_code_load'], r['verdict']) == (20, 14, 'needs justification, +6 over per code')
    assert check['zones'][0]['load_after'] == 220
    # excluded -> no per code load
    assert egress.check_capacities(rooms, exits, f, {}, {1: 'excluded'})['rooms'][0]['per_code_load'] == 0
    with pytest.raises(ValueError):
        egress.check_capacities(rooms, exits, f, {}, {1: 'gym'})
    assert rooms['room_type_override'].isna().all()          # nothing changed in the tables passed in

# one rule for a room's verdict and colour -> the card, the check table and the summary all agree (README "Colours")
def test_check_unvisited_room_type_only_is_grey():
    rooms, exits, f = check_tables([room('301', 60.55)], TWO_DOORS)
    r = egress.check_capacities(rooms, exits, f, {}, {1: 'lab'})['rooms'][0]
    assert r['colour'] == egress.GREY and r['verdict'] == 'not visited: uses the per code load'

def test_room_colour_follows_the_same_rule():
    excluded = dict(room('305', 40, 12, 'site count'), room_type_override='excluded')   # counted, but no per code load
    rooms = run([excluded, room('306', 60.55, 40, 'site count')], TWO_DOORS)['rooms'].set_index('space')
    for space in ['305', '306']:
        r = rooms.loc[space]
        assert egress.room_colour(r) == egress.judge_room(r, int(r['capacity']))[1]
    assert egress.room_colour(rooms.loc['305']) == egress.GREY

def test_try_room_with_another_type_or_capacity():
    # 60.55 m2: classroom 33 (1.85), lab 14 (4.6); nothing saved, same rule as the check
    rooms = run([room('301', 60.55, 40, 'site count'), room('302', 60.55)], TWO_DOORS)['rooms'].set_index('space')
    f = factors()
    t = egress.try_room(rooms.loc['301'], f, room_type='lab')
    assert (t['room_type'], t['area_per_person_m2'], t['per_code_load'], t['capacity']) == ('lab', 4.6, 14, 40)
    assert (t['verdict'], t['colour']) == ('needs justification, +26 over per code', egress.AMBER)
    t = egress.try_room(rooms.loc['301'], f, room_type='lab', capacity=10)
    assert (t['capacity'], t['verdict'], t['colour']) == (10, 'within per code', egress.GREEN)
    t = egress.try_room(rooms.loc['302'], f, room_type='lab')
    assert (t['per_code_load'], t['capacity'], t['colour']) == (14, None, egress.GREY)
    t = egress.try_room(rooms.loc['301'], f, room_type='excluded')
    assert (t['per_code_load'], t['verdict'], t['colour']) == (0, 'no per code load (excluded room type)', egress.GREY)
    t = egress.try_room(rooms.loc['301'], f)                                  # nothing tried -> the room as it is
    assert (t['room_type'], t['per_code_load'], t['capacity'], t['colour']) == ('classroom', 33, 40, egress.AMBER)

def test_zone_verdict():
    within = {'status': egress.STATUS_WITHIN, 'total_load': 161, 'exit_capacity': 288}
    over = {'status': egress.STATUS_REVIEW, 'total_load': 297, 'exit_capacity': 288}
    unmeasured = {'status': egress.STATUS_NOT_SURVEYED, 'total_load': 93, 'exit_capacity': 0}
    assert egress.zone_verdict(within) == 'within exit capacity'
    assert egress.zone_verdict(over) == 'over exit capacity by 9'
    assert egress.zone_verdict(unmeasured) == egress.CANT_CHECK

def test_unknown_room_type_is_flagged_not_silent():
    # 'lounge' isn't a code factor room type -> 0 per code, so it must show up in the warnings
    lounge = dict(room('327', 20.0), room_type_override='lounge')
    result = run([lounge, room('301', 60.55)], TWO_DOORS)
    w = result['warnings']
    w = w[w['type'] == 'unknown_room_type']
    assert len(w) == 1 and '327' in w.iloc[0]['detail'] and "'lounge'" in w.iloc[0]['detail']
    assert result['rooms'].set_index('space').loc['327', 'per_code_load'] == 0

def test_unknown_room_type_verdict_names_the_type():
    lounge = dict(room('327', 20.0, 2, 'site count'), room_type_override='lounge')
    r = run([lounge], TWO_DOORS)['rooms'].iloc[0]
    assert egress.judge_room(r, 2)[:2] == ("no per code load (unknown room type 'lounge')", egress.GREY)
