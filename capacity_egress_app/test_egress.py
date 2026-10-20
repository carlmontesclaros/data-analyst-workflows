import os
import pandas as pd
import pytest
import egress

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
EXIT_COLUMNS = ['property', 'floor', 'wing', 'into_wing', 'exit_id', 'exit_type', 'clear_width_cm',
                'stair_width_cm', 'stair_type']

def factors(**settings):
    f = {t: pd.read_csv(os.path.join(CONFIG_DIR, f'{t}.csv'))
         for t in ['area_factors', 'width_factors', 'category_map', 'settings']}
    extra = {'room_exclude': '16', 'open_stairs_count': 'yes'}
    extra.update(settings)
    f['settings'] = pd.concat([f['settings'], pd.DataFrame(
        [{'setting': k, 'value': v} for k, v in extra.items()])], ignore_index=True)
    return f

CLASSROOM = '1.2 - Non-Tiered Classroom'

def room(space, area, capacity=None, source='per code', sub=CLASSROOM, floor='3'):
    return {'property': 'Fake Hall', 'floor': floor, 'space': space, 'area_m2': area, 'sub_category': sub,
            'capacity': capacity, 'capacity_source': source if capacity is not None else 'per code',
            'room_type_override': None}

def exit_row(exit_id, exit_type, cm, wing=None, into_wing=None, floor='3', stair_cm=None, stair_type=None):
    return {'property': 'Fake Hall', 'floor': floor, 'wing': wing, 'into_wing': into_wing,
            'exit_id': exit_id, 'exit_type': exit_type, 'clear_width_cm': cm,
            'stair_width_cm': stair_cm, 'stair_type': stair_type}

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

def test_open_stair_counts_unless_switched_off():
    exits = [exit_row('S4 - doorway', 'doorway', 88), exit_row('S5 - open stair', 'stairs', 121),
             exit_row('E3 - outside exit', 'doorway', 88)]
    rooms = [room('301', 60.55, 30, 'site count')]
    # Carl 2026-10-20: the open stair leads down to an exit door, so it counts (S4 144 + S5 151 + E3 144)
    assert zone(run(rooms, exits))['exit_capacity'] == 439
    assert zone(run(rooms, exits, open_stairs_count='no'))['exit_capacity'] == 288

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
                                    exit_row('S3', 'stairs', 95), exit_row('S5 - open stair', 'stairs', 121)],
                open_stairs_count='no')['exits']
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
    # 'gym' isn't a code factor room type -> 0 per code, so it must show up in the warnings
    gym = dict(room('327', 20.0), room_type_override='gym')
    result = run([gym, room('301', 60.55)], TWO_DOORS)
    w = result['warnings']
    w = w[w['type'] == 'unknown_room_type']
    assert len(w) == 1 and '327' in w.iloc[0]['detail'] and "'gym'" in w.iloc[0]['detail']
    assert result['rooms'].set_index('space').loc['327', 'per_code_load'] == 0

def test_unknown_room_type_verdict_names_the_type():
    gym = dict(room('327', 20.0, 2, 'site count'), room_type_override='gym')
    r = run([gym], TWO_DOORS)['rooms'].iloc[0]
    assert egress.judge_room(r, 2)[:2] == ("no per code load (unknown room type 'gym')", egress.GREY)

def test_lounges_and_kitchens_use_per_code_circulation_stays_out():
    # BCBC 2024 Table 3.1.17.1. -> lounges 1.85, kitchens 9.30; non-assignable 16.x has no row
    lounge = room('110', 20.0, sub='14.3 - Lounge & Service Space')
    kitchen = room('111', 18.6, sub='7.2 - Food Facility Service')
    hall = room('112', 40.0, sub='16.2.4 - Circulation Space')
    r = run([lounge, kitchen, hall], TWO_DOORS)['rooms'].set_index('space')
    assert (r.loc['110', 'room_type'], r.loc['110', 'per_code_load'], bool(r.loc['110', 'in_scope'])) == ('lounge', 11, True)
    assert (r.loc['111', 'room_type'], r.loc['111', 'per_code_load'], bool(r.loc['111', 'in_scope'])) == ('kitchen', 2, True)
    assert (bool(r.loc['112', 'in_scope']), r.loc['112', 'load_used']) == (False, 0)

def test_stair_behind_the_door_limits_the_exit():
    # BCBC 2024 3.4.3.2.(1) -> door 6.1, stair 8.0 mm/person; the exit carries what its smaller part carries
    exits = run([room('301', 20)], [exit_row('S4 - doorway', 'doorway', 88, stair_cm=110, stair_type='stairs'),
                                    exit_row('S6 - doorway', 'doorway', 88, stair_cm=121, stair_type='stairs'),
                                    exit_row('E3 - outside exit', 'doorway', 88)])['exits'].set_index('exit_id')
    assert (exits.loc['S4 - doorway', 'persons'], exits.loc['S4 - doorway', 'limited_by']) == (137, 'stair')
    assert (exits.loc['S6 - doorway', 'persons'], exits.loc['S6 - doorway', 'limited_by']) == (144, 'door')
    assert (exits.loc['E3 - outside exit', 'persons'], exits.loc['E3 - outside exit', 'limited_by']) == (144, 'door')

def test_stair_minimum_width_is_checked_too():
    # Table 3.4.3.2.-A -> stairs under 900 mm fail even when the door is fine
    exits = run([room('301', 20)], [exit_row('S4 - doorway', 'doorway', 88, stair_cm=85, stair_type='stairs'),
                                    exit_row('S6 - doorway', 'doorway', 88, stair_cm=95, stair_type='stairs')])['exits']
    checks = dict(zip(exits['exit_id'], exits['width_check']))
    assert checks == {'S4 - doorway': 'fail - below minimum', 'S6 - doorway': 'review - depends on storeys served'}

def test_stair_door_without_a_stair_width_is_listed():
    # an S exit measured at the door only -> warning so the stair gets measured next visit
    result = run([room('301', 20)], [exit_row('S4 - doorway', 'doorway', 88), exit_row('E3 - outside exit', 'doorway', 88)])
    w = result['warnings']
    w = w[w['type'] == 'stair_not_measured']
    assert len(w) == 1 and 'S4 - doorway' in w.iloc[0]['detail']

def test_doors_into_the_same_stair_count_once():
    # Clearihue 2 S2: doors 179 (293) and 103 (168) into one 157 cm stair (196) -> one exit of 196, not 364
    exits = [exit_row('S2 - doorway (A201b)', 'doorway', 179, stair_cm=157, stair_type='stairs'),
             exit_row('S2 - doorway (A206)', 'doorway', 103),
             exit_row('E2 - outside exit', 'doorway', 88)]
    result = run([room('301', 60.55, 30, 'site count')], exits)
    e = result['exits'].set_index('exit_id')
    assert (e.loc['S2 - doorway (A201b)', 'persons'], bool(e.loc['S2 - doorway (A201b)', 'counts_as_exit'])) == (196, True)
    assert (e.loc['S2 - doorway (A206)', 'persons'], bool(e.loc['S2 - doorway (A206)', 'counts_as_exit'])) == (0, False)
    assert e.loc['S2 - doorway (A206)', 'shares_stair'] == 'S2 - doorway (A201b)'
    z = zone(result)
    assert (z['exit_count'], z['exit_capacity']) == (2, 288)       # 196 + 144, 50% rule -> 2 x 144
    assert len(result['warnings'].query("type == 'stair_not_measured'")) == 0   # the stair is measured on S2's other door

def test_shared_stair_doors_smaller_than_the_stair():
    # two 88 doors (144 + 144 = 288) into a 250 cm stair (312) -> the doors are slower, 288
    exits = [exit_row('S1 - doorway (A)', 'doorway', 88, stair_cm=250, stair_type='stairs'),
             exit_row('S1 - doorway (B)', 'doorway', 88)]
    e = run([room('301', 20)], exits)['exits'].set_index('exit_id')
    assert (e.loc['S1 - doorway (A)', 'persons'], e.loc['S1 - doorway (A)', 'limited_by']) == (288, 'door')
