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
    checks = dict(zip(exits['exit_id'], exits['width_check'], strict=False))
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

def test_widths_read_as_nullable_ints_work():
    # read_exits gives Int64 columns with <NA> for blanks -> the door vs stair compare must not choke on them
    exits = pd.DataFrame([exit_row('S4 - doorway', 'doorway', 88, stair_cm=110, stair_type='stairs'),
                          exit_row('E3 - outside exit', 'doorway', 88)], columns=EXIT_COLUMNS)
    for col in ['clear_width_cm', 'stair_width_cm']:
        exits[col] = exits[col].astype('Int64')
    e = egress.calculate(pd.DataFrame([room('301', 20)]), exits, factors())['exits'].set_index('exit_id')
    assert (e.loc['S4 - doorway', 'persons'], e.loc['E3 - outside exit', 'persons']) == (137, 144)

# wing groups -> a zone on a split floor can hold several wings (Clearihue 1: B on its own, A + C + D together)
HALL = '16.2.4 - Circulation Space'

def clearihue_1(b_exits=True):
    # A+C+D: 10 + 5 + 8 counted = 23, three 88 cm doors (432). B: 60.55 m2 classroom = 33 per code
    rooms = [room('A101', 20, 10, 'site count'), room('C101', 20, 5, 'site count'), room('D101', 20, 8, 'site count'),
             room('B103', 60.55), room('S1', 39.68, sub=HALL), room('L11', 4.38, sub=HALL), room('_General', 0, sub=None)]
    exits = [exit_row('E1 - outside exit (A101A)', 'doorway', 88, 'A+C+D'),
             exit_row('E1 - outside exit (C101A)', 'doorway', 88, 'A+C+D'),
             exit_row('E1 - outside exit (D101A)', 'doorway', 88, 'A+C+D')]
    if b_exits:
        exits += [exit_row('S10 - doorway', 'doorway', 88, 'B'), exit_row('E1 - outside exit (B101A)', 'doorway', 88, 'B'),
                  exit_row('E1 - link into A', 'doorway', 88, 'B', into_wing='A')]
    return rooms, exits

def test_floor_split_into_b_and_a_c_d_group():
    result = run(*clearihue_1())
    assert sorted(result['zones']['zone_wing']) == ['A+C+D', 'B']   # stairs, lifts, _General carry 0 -> no zone
    acd, b = zone(result, 'A+C+D'), zone(result, 'B')
    assert (acd['load_used'], acd['exit_count'], acd['exit_capacity']) == (23, 3, 432)
    assert (b['load_used'], b['exit_count'], b['exit_capacity']) == (33, 3, 432)
    # link door into A -> lands in A's group: ceil(33 / 3 exits) = 11
    assert (acd['link_inflow'], acd['total_load'], b['total_load']) == (11, 34, 33)
    zones_of = result['rooms'].set_index('space')['zone_wing']
    assert [zones_of[s] for s in ['A101', 'C101', 'D101', 'B103']] == ['A+C+D', 'A+C+D', 'A+C+D', 'B']
    assert result['warnings'].query("type in ['wing_not_in_a_group', 'link_to_missing_wing']").empty

def test_wing_group_written_any_way_is_one_zone():
    rooms, exits = clearihue_1()
    exits[0]['wing'], exits[1]['wing'], exits[2]['wing'] = 'd + a+c', 'A+C+D', 'c+d+a'
    exits[-1]['into_wing'] = 'a+c+d'                  # a link door may name the whole group too
    result = run(rooms, exits)
    assert sorted(result['zones']['zone_wing']) == ['A+C+D', 'B']
    assert (zone(result, 'A+C+D')['exit_count'], zone(result, 'A+C+D')['link_inflow']) == (3, 11)

def test_wing_in_no_group_is_its_own_zone_and_flagged():
    # Clearihue 1 today: the A+C+D group is set, no B exit measured yet -> B is not lost, it shows not surveyed
    rooms, exits = clearihue_1(b_exits=False)
    rooms.append(room('101', 20, 4, 'site count'))   # no wing letter
    result = run(rooms, exits)
    b = zone(result, 'B')
    assert (b['status'], b['total_load']) == (egress.STATUS_NOT_SURVEYED, 33)
    assert zone(result, '')['total_load'] == 4
    w = result['warnings'].query("type == 'wing_not_in_a_group'")
    assert len(w) == 2
    assert "wing B: 1 room, load 33" in w.iloc[0]['detail'] and 'A+C+D' in w.iloc[0]['detail']
    assert "no wing letter: 1 room, load 4" in w.iloc[1]['detail']
    assert set(w['floor']) == {'3'}

def test_link_door_into_its_own_group_adds_no_people():
    # A->C link door kept after the floor is regrouped A+C+D -> C is the same zone, 10 + 5 + 8 = 23 stays 23
    rooms, exits = clearihue_1(b_exits=False)
    exits.append(exit_row('E2 - link into C', 'doorway', 88, 'A+C+D', into_wing='C'))
    result = run(rooms, exits)
    z = zone(result, 'A+C+D')
    assert (z['link_inflow'], z['total_load'], z['link_sends']) == (0, 23, False)
    # an inside door, not a way out -> the three 88 cm outside doors only: 3 x 144, 50% rule keeps 432
    assert (z['exit_count'], z['exit_capacity']) == (3, 432)
    w = result['warnings'].query("type == 'link_within_zone'")
    assert len(w) == 1 and 'E2 - link into C' in w.iloc[0]['detail'] and 'A+C+D' in w.iloc[0]['detail']

def test_wing_in_two_groups_on_one_floor_is_flagged():
    rooms = [room('A101', 20, 10, 'site count'), room('C101', 20, 5, 'site count'), room('D101', 20, 8, 'site count')]
    exits = [exit_row('S1', 'doorway', 88, 'A+C'), exit_row('S2', 'doorway', 88, 'A+C'),
             exit_row('S3', 'doorway', 88, 'C+D'), exit_row('S4', 'doorway', 88, 'C+D')]
    result = run(rooms, exits)
    w = result['warnings'].query("type == 'wing_in_two_groups'")
    assert len(w) == 1 and "wing C is in A+C and C+D" in w.iloc[0]['detail']
    # first group alphabetically takes it, so C's people are counted once
    assert (zone(result, 'A+C')['load_used'], zone(result, 'C+D')['load_used']) == (15, 8)

def test_unreadable_wing_is_flagged():
    result = run([room('A101', 20, 10, 'site count')], [exit_row('S1', 'doorway', 88, 'A, C'),
                                                        exit_row('S2', 'doorway', 88, 'A, C')])
    w = result['warnings'].query("type == 'bad_wing'")
    assert len(w) == 2 and "'A, C'" in w.iloc[0]['detail']

def test_floor_with_no_wing_on_its_exits_stays_one_zone():
    # several prefixes, no wing on any exit -> one zone holding every room, as before groups
    rooms = [room('A301', 20, 10, 'site count'), room('B301', 60.55), room('C301', 20, 5, 'site count'),
             room('S1', 39.68, sub=HALL)]
    result = run(rooms, TWO_DOORS)
    assert result['zones']['zone_wing'].tolist() == ['']
    assert (zone(result)['total_load'], zone(result)['exit_capacity']) == (48, 288)
    assert set(result['rooms']['zone_wing']) == {''}
    assert result['warnings'].query("type == 'wing_not_in_a_group'").empty

def test_single_letter_wings_unchanged():
    # Turpin-like: B measured, A not -> zone A not surveyed, as before groups (now also listed in the warnings)
    rooms = [room('B301', 60.55, 161, 'site count'), room('A301', 20, 10, 'site count')]
    exits = [exit_row('S4', 'doorway', 88, 'B'), exit_row('S5', 'doorway', 88, 'B')]
    result = run(rooms, exits)
    assert (zone(result, 'B')['total_load'], zone(result, 'B')['exit_capacity']) == (161, 288)
    assert (zone(result, 'A')['status'], zone(result, 'A')['total_load']) == (egress.STATUS_NOT_SURVEYED, 10)

def test_counted_room_with_no_per_code_load_is_not_dropped():
    # wing A: one counted room of an excluded type -> per code load 0, but 12 people counted. no A exit -> the zone
    #   used to be dropped as a pseudo zone and the 12 vanished. it stays, not surveyed, and is listed
    excluded = dict(room('A301', 20, 12, 'site count'), room_type_override='excluded')
    rooms = [room('B301', 60.55, 161, 'site count'), excluded]
    exits = [exit_row('S4', 'doorway', 88, 'B'), exit_row('S5', 'doorway', 88, 'B')]
    result = run(rooms, exits)
    a = zone(result, 'A')
    assert (a['area_based_load'], a['load_used'], a['exit_count']) == (0, 12, 0)
    assert (a['status'], a['total_load']) == (egress.STATUS_NOT_SURVEYED, 12)
    assert result['zones']['load_used'].sum() == 161 + 12
    assert result['warnings'].query("type == 'wing_not_in_a_group'")['detail'].str.contains('load 12').any()

def test_wing_with_no_load_and_no_exits_is_still_dropped():
    # an uncounted excluded room: 0 per code, 0 counted -> nothing to lose, no zone, as before
    excluded = dict(room('A301', 20), room_type_override='excluded')
    rooms = [room('B301', 60.55, 161, 'site count'), excluded]
    exits = [exit_row('S4', 'doorway', 88, 'B'), exit_row('S5', 'doorway', 88, 'B')]
    assert zone(run(rooms, exits), 'B')['total_load'] == 161
    assert run(rooms, exits)['zones']['zone_wing'].tolist() == ['B']

def test_check_names_the_group_a_room_is_in():
    rooms, exits, f = check_tables(*clearihue_1())
    check = egress.check_capacities(rooms, exits, f, {1: 40})        # A101 10 -> 40
    assert check['rooms'][0]['zone_wing'] == 'A+C+D'
    acd = next(z for z in check['zones'] if z['zone_wing'] == 'A+C+D')
    assert (acd['has_checked_room'], acd['load_before'], acd['load_after']) == (True, 34, 64)
    assert not next(z for z in check['zones'] if z['zone_wing'] == 'B')['has_checked_room']

@pytest.mark.parametrize('typed, group', [('', ''), (None, ''), ('b', 'B'), ('BM', 'BM'), (' d + a+c ', 'A+C+D'),
                                          ('A+A+C', 'A+C')])
def test_wing_group_notation(typed, group):
    assert egress.wing_group(typed) == group

@pytest.mark.parametrize('typed', ['A, C', 'A+', 'A+1', 'A C', 'A/C'])
def test_wing_group_refuses_other_notations(typed):
    with pytest.raises(ValueError):
        egress.wing_group(typed)

def test_wing_label():
    assert [egress.wing_label(w) for w in ['', 'B', 'A+C+D']] == ['', 'wing B', 'wings A+C+D']

# --- one floor redone, the rest kept -> exactly what a whole-campus calculation gives -------------------------------
# what the editor screen does after a save on one floor (zones never cross floors, so nothing else can have moved)

def raw_room(room_id, floor, space, area, capacity=None, source='per code', override=None, sub=CLASSROOM, prop='Fake Hall'):
    return {'room_id': room_id, 'property': prop, 'floor': floor, 'space': space, 'area_m2': area, 'sub_category': sub,
            'capacity': capacity, 'capacity_source': source, 'room_type_override': override}

def raw_exit(exit_pk, floor, exit_id, exit_type, cm, wing=None, into_wing=None, prop='Fake Hall', stair_cm=None, stair_type=None):
    return {'exit_pk': exit_pk, 'property': prop, 'floor': floor, 'wing': wing, 'into_wing': into_wing,
            'exit_id': exit_id, 'exit_type': exit_type, 'clear_width_cm': cm, 'stair_width_cm': stair_cm,
            'stair_type': stair_type}

# four floors with the awkward things a real campus has: wings and a link door, a room type nobody knows,
# a floor with no exits, a floor where no room has a count yet
CAMPUS_ROOMS = [
    raw_room(1, '1', 'A101', 50.0, 20, 'site count'), raw_room(2, '1', 'B102', 30.0), raw_room(3, '1', 'C103', 45.0, 0, 'site count'),
    raw_room(4, '2', '201', 40.0), raw_room(5, '2', '202', 40.0, override='lounge'), raw_room(6, '2', '203', 25.0),
    raw_room(7, '3', '301', 60.0, 35, 'PM change'), raw_room(8, '3', '302', 60.0, 10, 'PM change'),
    raw_room(9, '4', '401', 35.0, sub=None), raw_room(10, '1', 'A104', 20.0, 5, 'site count', prop='Other Hall'),
]
CAMPUS_EXITS = [
    raw_exit(1, '1', 'S1 - doorway', 'doorway', 88, wing='A'), raw_exit(2, '1', 'S2 - doorway', 'doorway', 88, wing='B'),
    raw_exit(3, '1', 'L1 - link', 'doorway', 88, wing='A', into_wing='B'),
    raw_exit(4, '2', 'S1 - doorway', 'doorway', 88), raw_exit(5, '2', 'S2 - doorway', 'trapdoor', 88),
    raw_exit(6, '3', 'S1 - doorway', 'doorway', 88), raw_exit(7, '3', 'S2 - doorway', 'doorway', None),
    raw_exit(8, '1', 'S1 - doorway', 'doorway', 100, prop='Other Hall'),
]

def frames(rooms, exits):
    return pd.DataFrame(rooms), pd.DataFrame(exits, columns=list(CAMPUS_EXITS[0]))

# same rows in the same order with the same values. a blank is a blank (None or NaN), and the way a column is stored
# (text or the string type) may differ from a fresh load, but a column of numbers must stay numbers
def assert_same_frame(got, want, obj):
    blanks = lambda df: df.astype(object).where(df.notna(), None)    # noqa: E731
    pd.testing.assert_frame_equal(blanks(got), blanks(want), check_dtype=False, obj=obj)
    for column in want.columns:
        assert pd.api.types.is_numeric_dtype(got[column]) == pd.api.types.is_numeric_dtype(want[column]), f"{obj}.{column}"

def assert_same_result(got, want):
    for table in ('rooms', 'exits', 'zones'):
        assert_same_frame(got[table], want[table], table)
    assert got['settings'] == want['settings']
    # the warnings are the same rows; only the order they were found in can differ
    key = ['type', 'property', 'floor', 'detail']
    assert_same_frame(got['warnings'].sort_values(key).reset_index(drop=True),
                      want['warnings'].sort_values(key).reset_index(drop=True), 'warnings')

def refreshed(rooms, exits, new_rooms, new_exits, prop, floor):
    # the screen's way: the building's old result + only that floor's rows read again and redone
    f = factors()
    campus = egress.Campus(*frames(rooms, exits), f)
    campus.building(prop)
    floor_rooms = pd.DataFrame([r for r in new_rooms if (r['property'], r['floor']) == (prop, floor)])
    floor_exits = pd.DataFrame([e for e in new_exits if (e['property'], e['floor']) == (prop, floor)], columns=list(CAMPUS_EXITS[0]))
    got = campus.refresh_floor(prop, floor, floor_rooms, floor_exits)
    want_rooms, want_exits = frames(new_rooms, new_exits)
    assert_same_frame(got.rooms, want_rooms, 'loaded rooms')
    assert_same_frame(got.exits, want_exits, 'loaded exits')
    return renumbered(got.building(prop)), renumbered(building_rows(egress.calculate(want_rooms, want_exits, f), prop))

def edited(rows, key, value, **changes):
    return [r | changes if r[key] == value else r for r in rows]

@pytest.mark.parametrize('why, new_rooms, new_exits, floor', [
    ('a capacity changed', edited(CAMPUS_ROOMS, 'room_id', 7, capacity=77, capacity_source='site count'), CAMPUS_EXITS, '3'),
    ('a room type chosen', edited(CAMPUS_ROOMS, 'room_id', 6, room_type_override='office'), CAMPUS_EXITS, '2'),
    ('a count on the floor nobody had counted', edited(CAMPUS_ROOMS, 'room_id', 9, capacity=12, capacity_source='site count'), CAMPUS_EXITS, '4'),
    ('an exit added to a floor with wings and a link door',
     CAMPUS_ROOMS, CAMPUS_EXITS + [raw_exit(9, '1', 'S3 - doorway', 'doorway', 120, wing='C')], '1'),
    ('an exit added to a floor that had none', CAMPUS_ROOMS, CAMPUS_EXITS + [raw_exit(9, '4', 'S1 - doorway', 'doorway', 90)], '4'),
    ('every exit on a floor deleted', CAMPUS_ROOMS, [e for e in CAMPUS_EXITS if e['floor'] != '3'], '3'),
    ('an exit width changed', CAMPUS_ROOMS, edited(CAMPUS_EXITS, 'exit_pk', 7, clear_width_cm=95), '3'),
])
def test_one_floor_redone_gives_the_whole_campus_answer(why, new_rooms, new_exits, floor):
    got, want = refreshed(CAMPUS_ROOMS, CAMPUS_EXITS, new_rooms, new_exits, 'Fake Hall', floor)
    assert_same_result(got, want)

# a floor whose rooms have no capacity at all comes back from the database as a column of None, not numbers ->
# it must not turn the whole capacity column into text
def test_a_floor_of_blank_capacities_keeps_the_number_columns_numbers():
    got, want = refreshed(CAMPUS_ROOMS, CAMPUS_EXITS, CAMPUS_ROOMS, CAMPUS_EXITS, 'Fake Hall', '2')
    assert_same_result(got, want)
    assert pd.api.types.is_numeric_dtype(got['rooms']['capacity'])

# a column with a value in every row loads as whole numbers. a save that leaves one blank (a door with no stair behind it,
# a room nobody counted) must give numbers with blanks, like a whole reload, not fail or lose the other values
STAIRED_EXITS = [e | {'stair_width_cm': 110, 'stair_type': 'stairs'} for e in CAMPUS_EXITS]
COUNTED_ROOMS = [r | {'capacity': 10, 'capacity_source': 'site count'} if r['capacity'] is None else r for r in CAMPUS_ROOMS]

@pytest.mark.parametrize('why, rooms, exits, new_rooms, new_exits, floor', [
    ('one door on the floor has its stair cleared', CAMPUS_ROOMS, STAIRED_EXITS, CAMPUS_ROOMS,
     edited(STAIRED_EXITS, 'exit_pk', 4, stair_width_cm=None, stair_type=None), '2'),
    ('every door on the floor has its stair cleared', CAMPUS_ROOMS, STAIRED_EXITS, CAMPUS_ROOMS,
     [e | {'stair_width_cm': None, 'stair_type': None} if e['floor'] == '2' else e for e in STAIRED_EXITS], '2'),
    ('a plain doorway added to a floor that had no exits', CAMPUS_ROOMS, STAIRED_EXITS, CAMPUS_ROOMS,
     STAIRED_EXITS + [raw_exit(9, '4', 'S1 - doorway', 'doorway', 90)], '4'),
    ('a stair width that is not a whole number', CAMPUS_ROOMS, STAIRED_EXITS, CAMPUS_ROOMS,
     edited(STAIRED_EXITS, 'exit_pk', 4, stair_width_cm=110.5), '2'),
    ('a room count cleared', COUNTED_ROOMS, CAMPUS_EXITS,
     edited(COUNTED_ROOMS, 'room_id', 4, capacity=None, capacity_source='per code'), CAMPUS_EXITS, '2'),
])
def test_a_blank_in_a_column_of_whole_numbers(why, rooms, exits, new_rooms, new_exits, floor):
    got, want = refreshed(rooms, exits, new_rooms, new_exits, 'Fake Hall', floor)
    assert_same_result(got, want)

def test_refresh_floor_keeps_the_database_order_and_other_floors_untouched():
    rooms, exits = frames(CAMPUS_ROOMS, CAMPUS_EXITS)
    campus = egress.Campus(rooms, exits, factors())
    before = campus.building('Fake Hall')
    floor = pd.DataFrame([raw_room(7, '3', '301', 60.0, 99, 'site count')])       # room 8 is gone from the floor
    refreshed_campus = campus.refresh_floor('Fake Hall', '3', floor, exits.iloc[0:0])
    got = refreshed_campus.building('Fake Hall')
    assert refreshed_campus.rooms['room_id'].tolist() == [1, 2, 3, 4, 5, 6, 7, 9, 10]
    assert got['rooms']['room_id'].tolist() == [1, 2, 3, 4, 5, 6, 7, 9]
    assert got['rooms'].loc[got['rooms']['room_id'] == 7, 'capacity'].item() == 99
    assert got['rooms'].loc[got['rooms']['room_id'] == 1, 'capacity'].item() == 20
    assert list(got['rooms'].index) == list(range(len(got['rooms'])))
    assert before['rooms'].shape[0] == 9 and campus.rooms.shape[0] == 10        # the old result is not changed

# a floor where no room has a sub-category (a store, a plant floor) calculates like any other
def test_a_floor_with_no_sub_categories_calculates():
    rooms = [room('S1', 12.0, sub=None), room('S2', 8.0, sub=None)]
    result = run(rooms, TWO_DOORS)
    assert result['rooms']['in_scope'].tolist() == [True, True]
    assert result['rooms']['per_code_load'].tolist() == [0, 0]
    assert result['warnings']['type'].tolist().count('no_room_type') == 2

# --- the campus calculated a building at a time, as the editor screen shows it -> the same answer as all at once -----
# zones never cross floors, so a building calculated alone must be exactly its rows of the whole-campus result

# a second building with its own awkward things: a room type nobody knows, wings with a link door, a wing no exit names
TWO_BUILDINGS_ROOMS = CAMPUS_ROOMS + [
    raw_room(11, '1', 'B105', 30.0, 12, 'site count', prop='Other Hall'), raw_room(12, '2', '201', 40.0, override='lounge', prop='Other Hall'),
    raw_room(13, '2', 'C202', 25.0, prop='Other Hall'), raw_room(14, '2', 'D203', 15.0, 4, 'site count', prop='Other Hall'),
]
TWO_BUILDINGS_EXITS = CAMPUS_EXITS + [
    raw_exit(9, '1', 'S2 - doorway', 'doorway', 88, prop='Other Hall'),
    raw_exit(10, '2', 'S1 - doorway', 'doorway', 88, wing='C', prop='Other Hall'),
    raw_exit(11, '2', 'L1 - link', 'doorway', 88, wing='C', into_wing='D', prop='Other Hall'),
]

def building_rows(result, prop):
    return {t: result[t][result[t]['property'] == prop] for t in ('rooms', 'exits', 'zones', 'warnings')} | \
           {'settings': result['settings']}

# row numbers say nothing about a room; a building's tables are numbered from 0 like any other table
def renumbered(result):
    return {t: v.reset_index(drop=True) if isinstance(v, pd.DataFrame) else v for t, v in result.items()}

def test_a_building_alone_is_its_rows_of_the_whole_campus():
    rooms, exits = frames(TWO_BUILDINGS_ROOMS, TWO_BUILDINGS_EXITS)
    want = egress.calculate(rooms, exits, factors())
    assert set(want['warnings']['property']) == {'Fake Hall', 'Other Hall'}       # both buildings have warnings to keep
    campus = egress.Campus(rooms, exits, factors())
    for prop in ('Other Hall', 'Fake Hall'):
        assert_same_result(renumbered(campus.building(prop)), renumbered(building_rows(want, prop)))
    assert_same_result(campus.whole(), want)
    # the warnings come in the order a whole calculation finds them, so the exports read the same as before
    assert_same_frame(campus.whole(in_fresh_order=True)['warnings'], want['warnings'], 'warnings')

# nothing is calculated until it's asked for, and a building already calculated isn't calculated again
def test_the_campus_is_calculated_only_as_far_as_asked(monkeypatch):
    rooms, exits = frames(TWO_BUILDINGS_ROOMS, TWO_BUILDINGS_EXITS)
    sizes, real = [], egress.calculate
    monkeypatch.setattr(egress, 'calculate', lambda r, e, f: sizes.append(len(r)) or real(r, e, f))
    campus = egress.Campus(rooms, exits, factors())
    assert sizes == []
    first = campus.building('Other Hall')
    assert campus.building('Other Hall') is first
    assert sizes == [5]
    whole = campus.whole()
    assert campus.whole() is whole and campus.whole(in_fresh_order=True) is whole
    assert campus.building('Other Hall') is first
    assert sizes == [5, 14]

# a save on one floor -> that floor read again: every building's result and the whole campus as a fresh calculation gives
@pytest.mark.parametrize('why, new_rooms, new_exits, prop, floor', [
    ('a capacity changed', edited(TWO_BUILDINGS_ROOMS, 'room_id', 13, capacity=9, capacity_source='site count'),
     TWO_BUILDINGS_EXITS, 'Other Hall', '2'),
    ('an exit added to a floor with wings and a link door', TWO_BUILDINGS_ROOMS,
     TWO_BUILDINGS_EXITS + [raw_exit(12, '2', 'S2 - doorway', 'doorway', 100, wing='D', prop='Other Hall')], 'Other Hall', '2'),
    ('every exit on a floor deleted', TWO_BUILDINGS_ROOMS, [e for e in TWO_BUILDINGS_EXITS if e['floor'] != '3'], 'Fake Hall', '3'),
])
def test_a_floor_refreshed_in_the_campus_gives_a_fresh_calculation(why, new_rooms, new_exits, prop, floor, monkeypatch):
    f = factors()
    campus = egress.Campus(*frames(TWO_BUILDINGS_ROOMS, TWO_BUILDINGS_EXITS), f)
    other = 'Fake Hall' if prop == 'Other Hall' else 'Other Hall'
    kept = campus.building(other)
    campus.building(prop)
    campus.whole()
    floor_rooms = pd.DataFrame([r for r in new_rooms if (r['property'], r['floor']) == (prop, floor)], columns=list(CAMPUS_ROOMS[0]))
    floor_exits = pd.DataFrame([e for e in new_exits if (e['property'], e['floor']) == (prop, floor)], columns=list(CAMPUS_EXITS[0]))
    want_rooms, want_exits = frames(new_rooms, new_exits)
    want = egress.calculate(want_rooms, want_exits, f)
    sizes, real = [], egress.calculate
    monkeypatch.setattr(egress, 'calculate', lambda r, e, f: sizes.append(len(r)) or real(r, e, f))
    got = campus.refresh_floor(prop, floor, floor_rooms, floor_exits)

    assert_same_frame(got.rooms, want_rooms, 'loaded rooms')
    assert_same_frame(got.exits, want_exits, 'loaded exits')
    for p in (prop, other):
        assert_same_result(renumbered(got.building(p)), renumbered(building_rows(want, p)))
    assert got.building(other) is kept                                          # the other building isn't redone
    assert_same_result(got.whole(), want)
    assert sizes == [len(floor_rooms)]                                          # only the saved floor is calculated again
    # the exports: the warnings in the order a fresh start finds them
    assert_same_result(got.whole(in_fresh_order=True), want)
    assert_same_frame(got.whole(in_fresh_order=True)['warnings'], want['warnings'], 'warnings')
    assert sizes == [len(floor_rooms), len(want_rooms)]
    assert_same_result(campus.whole(), egress.calculate(*frames(TWO_BUILDINGS_ROOMS, TWO_BUILDINGS_EXITS), f))  # old one unchanged

# --- room zones -> a zone typed on a room wins over its room-number letters ------------------------------------------
# Cornett floor 1 in miniature: three parts with no indoor path between them, and the letters don't follow them.
# West = B107 + A137, North-east = B130, South = A121 -> A and B are each in two parts

PARTS = {'B107': 'WEST', 'A137': 'WEST', 'B130': 'NORTH', 'A121': 'SOUTH'}
COUNTS = {'B107': 200, 'A137': 40, 'B130': 300, 'A121': 60}

def cornett_rooms(zones=PARTS, extra=()):
    rooms = [room(space, 60.55, COUNTS[space], 'site count') | {'zone_override': zones.get(space)} for space in COUNTS]
    return rooms + list(extra)

# two doors to each part: West 182 cm (298 people each), North-east 89 cm (145), South 159 cm (260)
def cornett_exits(west='WEST', north='NORTH', south='SOUTH'):
    return [exit_row(f"{name} {n}", 'doorway', cm, wing)
            for name, cm, wing in [('west', 182, west), ('north', 89, north), ('south', 159, south)] for n in (1, 2)]

def loads(result):
    return {z['zone_wing']: (z['total_load'], z['exit_capacity']) for _, z in result['zones'].iterrows()}

def warned(result, kind):
    w = result['warnings']
    return w.loc[w['type'] == kind, 'detail'].tolist()

def test_room_zones_check_each_part_of_a_floor_against_its_own_exits():
    result = run(cornett_rooms(), cornett_exits())
    assert loads(result) == {'WEST': (240, 596), 'NORTH': (300, 290), 'SOUTH': (60, 520)}
    assert zone(result, 'NORTH')['status'] == egress.STATUS_REVIEW
    assert 'occupant load over exiting capacity' in zone(result, 'NORTH')['flags']
    assert zone(result, 'WEST')['status'] == zone(result, 'SOUTH')['status'] == egress.STATUS_WITHIN
    assert result['warnings']['type'].tolist() == []
    rooms = result['rooms'].set_index('space')
    assert rooms['zone_wing'].to_dict() == PARTS
    assert rooms.loc['B107', 'room_wing'] == 'B'                # the room-number letter is still reported as it is

# no zone typed anywhere -> the letters decide, as before: B130's 300 are pooled with B107 against the north doors,
# and the south doors are credited to A137
def test_without_room_zones_the_room_number_letters_decide():
    result = run(cornett_rooms(zones={}), cornett_exits(west='A', north='B', south='A'))
    assert loads(result) == {'A': (100, 1116), 'B': (500, 290)}
    assert result['warnings']['type'].tolist() == []

@pytest.mark.parametrize('blank', [None, '', '   ', float('nan')])
def test_a_blank_room_zone_changes_nothing(blank):
    exits = cornett_exits(west='A', north='B', south='A') + [exit_row('c 1', 'doorway', 88, 'C')]
    extra = [room('S1', 12.0), room('D140', 20.0, 5, 'site count'), room('101', 20.0)]
    plain = [{k: v for k, v in r.items() if k != 'zone_override'} for r in cornett_rooms(zones={}, extra=extra)]
    without = run(plain, exits)
    with_blank = run([r | {'zone_override': blank} for r in plain], exits)
    assert_same_frame(with_blank['zones'], without['zones'], 'zones')
    assert_same_frame(with_blank['warnings'], without['warnings'], 'warnings')
    assert with_blank['rooms']['zone_wing'].tolist() == without['rooms']['zone_wing'].tolist()

def test_a_room_zone_matches_in_any_case():
    result = run(cornett_rooms(zones={k: f" {v.lower()} " for k, v in PARTS.items()}), cornett_exits(west='west'))
    assert loads(result) == {'WEST': (240, 596), 'NORTH': (300, 290), 'SOUTH': (60, 520)}

# a new FMIS room has no zone -> it falls back to its letter, so it is always listed, never silently placed
def test_a_room_with_no_zone_on_a_floor_with_zones_is_listed():
    extra = [room('A199', 60.55, 25, 'site count'), room('A198', 60.55), room('A100C', 40.0, sub='16.2.4 - Circulation Space'),
             room('A197', 20.0, 0, 'site count'), room('A201', 60.55, floor='2')]
    result = run(cornett_rooms(extra=extra), cornett_exits() + [exit_row('up 1', 'doorway', 88, 'A', floor='2')])
    assert warned(result, 'room_without_zone') == [
        "wing A: 2 rooms with no zone (A198, A199), load 58 - this floor has room zones, so they go by their room number"]
    rooms = result['rooms'].set_index('space')
    assert rooms.index[rooms['no_zone_set']].tolist() == ['A199', 'A198']
    # no exit names A -> its own zone with no exits, as today
    first = result['zones'][result['zones']['floor'] == '3'].set_index('zone_wing')
    assert (first.loc['A', 'status'], first.loc['A', 'total_load']) == (egress.STATUS_NOT_SURVEYED, 58)
    assert len(warned(result, 'wing_not_in_a_group')) == 1

# the dangerous case: the room's letter IS an exit's wing, so the room joins that zone and nothing else looks wrong
def test_a_room_with_no_zone_is_listed_even_when_an_exit_names_its_letter():
    result = run(cornett_rooms(zones=PARTS | {'B107': None}), cornett_exits(south='B'))
    assert zone(result, 'B')['total_load'] == 200
    assert warned(result, 'room_without_zone') == [
        "wing B: 1 room with no zone (B107), load 200 - this floor has room zones, so it goes by its room number"]
    assert warned(result, 'wing_not_in_a_group') == [
        "wing SOUTH: 1 room, load 60 - not in any exit's wing (B, NORTH, WEST), so it's its own zone with no exits"]

def test_a_room_zone_no_exit_names_is_its_own_zone_with_no_exits():
    result = run(cornett_rooms(zones=PARTS | {'A121': 'SOTH'}), cornett_exits())
    z = zone(result, 'SOTH')
    assert (z['total_load'], z['exit_count'], z['status']) == (60, 0, egress.STATUS_NOT_SURVEYED)
    assert zone(result, 'SOUTH')['total_load'] == 0                          # its doors are there, nobody joins them
    assert warned(result, 'wing_not_in_a_group') == [
        "wing SOTH: 1 room, load 60 - not in any exit's wing (NORTH, SOUTH, WEST), so it's its own zone with no exits"]

# zones typed before the exits are tagged -> like wing letters, they split nothing until an exit has a wing
def test_room_zones_on_a_floor_whose_exits_have_no_wing_leave_it_one_zone():
    result = run(cornett_rooms(zones=PARTS | {'B107': None}), cornett_exits(None, None, None))
    assert loads(result) == {'': (600, 2 * (298 + 145 + 260))}
    assert warned(result, 'room_without_zone') == []
    assert not result['rooms']['no_zone_set'].any()

def test_a_link_door_into_a_room_zone():
    exits = cornett_exits() + [exit_row('link', 'doorway', 88, 'NORTH', into_wing='SOUTH')]
    result = run(cornett_rooms(), exits)
    assert zone(result, 'SOUTH')['link_inflow'] == 100           # ceil(300 / 3 exits)
    assert warned(result, 'link_to_missing_wing') == []

# a zone is matched like a wing letter -> a wing group holding it takes the room, whether the name is a letter or a word
@pytest.mark.parametrize('group, typed', [('A+C', 'a'), ('SOUTH+WEST', 'west')])
def test_a_room_zone_joins_the_group_holding_it(group, typed):
    rooms = [room('B101', 60.55, 30, 'site count') | {'zone_override': typed}]
    result = run(rooms, [exit_row('E1', 'doorway', 88, group), exit_row('E2', 'doorway', 88, group)])
    assert loads(result) == {egress.wing_group(group): (30, 288)}
    assert result['warnings']['type'].tolist() == []

@pytest.mark.parametrize('text, saved', [(' west ', 'WEST'), ('A', 'A'), ('', ''), (None, ''), (float('nan'), '')])
def test_a_zone_is_written_one_way(text, saved):
    assert egress.room_zone(text) == saved

@pytest.mark.parametrize('text', ['WEST+SOUTH', 'north-east', 'West 1', 'W2', 'ouest é'])
def test_a_zone_is_one_name_in_letters_only(text):
    with pytest.raises(ValueError, match='letters only'):
        egress.room_zone(text)

# a zone set or cleared on one floor -> that floor redone gives what a whole calculation gives, both ways round
@pytest.mark.parametrize('before, after', [(None, 'WEST'), ('WEST', None)])
def test_one_floor_redone_after_a_zone_change_gives_the_whole_campus_answer(before, after):
    rooms = [r | {'zone_override': before if r['room_id'] == 1 else None} for r in CAMPUS_ROOMS]
    new_rooms = [r | {'zone_override': after if r['room_id'] == 1 else None} for r in CAMPUS_ROOMS]
    got, want = refreshed(rooms, CAMPUS_EXITS, new_rooms, CAMPUS_EXITS, 'Fake Hall', '1')
    assert_same_result(got, want)
