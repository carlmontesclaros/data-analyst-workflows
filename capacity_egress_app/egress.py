import numpy as np
import pandas as pd
from exit_calc import occupant_load, exit_persons, capacity_50_rule, people_sent

STATUS_REVIEW = 'REVIEW'
STATUS_WITHIN = 'WITHIN CAPACITY - review before acting'
STATUS_NOT_SURVEYED = 'NOT SURVEYED - no exit data'
STATUS_ORDER = {STATUS_REVIEW: 0, STATUS_WITHIN: 1, STATUS_NOT_SURVEYED: 2}
ZONE_KEYS = ['property', 'floor', 'floor_key', 'zone_wing']

# settings table -> values the calculation needs
def read_settings(settings_df):
    s = dict(zip(settings_df['setting'], settings_df['value']))
    if s.get('occupant_load_rounding', 'up') != 'up':
        raise ValueError(f"occupant_load_rounding is '{s['occupant_load_rounding']}', only 'up' is supported")
    link_method = s.get('link_share_method', 'even_split')
    if link_method not in ('even_split', 'half_load'):
        raise ValueError(f"link_share_method '{link_method}' must be even_split or half_load")
    exclude = [c.strip() for c in str(s.get('room_exclude', '') or '').split(',') if c.strip()]
    return {'code_edition': str(s.get('code_edition', '') or '').strip(),
            'min_exits': int(s.get('minimum_exits', 2)),
            'link_method': link_method,
            'room_exclude': exclude,
            'open_stairs_count': str(s.get('open_stairs_count', 'no')).strip().lower() in ('yes', 'true', '1')}

# rooms -> room type, per code load, scope, load used
def prepare_rooms(rooms, factors, settings, warning_rows):
    rooms = rooms.copy()
    area_factor = dict(zip(factors['area_factors']['room_type'], factors['area_factors']['area_per_person_m2']))
    category_map = dict(zip(factors['category_map']['space_sub_category'], factors['category_map']['room_type']))

    # room type -> override wins, else category default
    override = rooms['room_type_override'].fillna('').astype(str).str.strip().str.lower()
    override = override.where(override != '')
    default = rooms['sub_category'].map(category_map)
    rooms['room_type'] = override.fillna(default)
    rooms['room_type_source'] = 'none'
    rooms.loc[default.notna(), 'room_type_source'] = 'category'
    rooms.loc[override.notna(), 'room_type_source'] = 'override'

    no_type = rooms[rooms['room_type'].isna() & (rooms['area_m2'] > 0)]
    for _, row in no_type.iterrows():
        warning_rows.append({'type': 'no_room_type', 'property': row['property'], 'floor': row['floor'],
                             'detail': f"{row['space']}: {row['area_m2']} m2, no sub-category or override - counted as 0 people"})

    # per code load = area / m2 per person, rounded up (BCBC 2024 Table 3.1.17.1.)
    rooms['area_per_person_m2'] = rooms['room_type'].map(area_factor)
    rooms['per_code_load'] = occupant_load(rooms['area_m2'], rooms['area_per_person_m2']).fillna(0).astype(int)

    # scope -> every room except the excluded sub-category codes (a code covers its children)
    # scope is a project decision, not code (Table 3.1.17.1. does give lounges 1.85 m2 per person)
    sub_code = rooms['sub_category'].astype(str).str.split(' - ').str[0].str.strip()
    rooms['in_scope'] = True
    for code in settings['room_exclude']:
        rooms.loc[(sub_code == code) | sub_code.str.startswith(code + '.'), 'in_scope'] = False

    # load used -> room capacity when there is one (visited / PM change, 0 stays 0), else per code
    # BCBC 2024 3.1.17.1.(1)(c) -> not less than Table 3.1.17.1. "unless it can be shown that the area
    #   will be occupied by fewer persons" (the site count), 3.1.17.1.(2) -> that load needs a posted sign
    capacity = pd.to_numeric(rooms['capacity'], errors='coerce')
    rooms['load_used'] = capacity.fillna(rooms['per_code_load'])
    rooms['load_source'] = np.where(capacity.notna(), rooms['capacity_source'], 'per code')
    rooms.loc[~rooms['in_scope'], 'load_used'] = 0
    rooms.loc[~rooms['in_scope'], 'load_source'] = 'out of scope'
    rooms['load_used'] = rooms['load_used'].astype(int)
    rooms['counted'] = rooms['in_scope'] & capacity.notna()
    rooms['count_in_scope'] = capacity.where(rooms['in_scope'])

    # wing -> leading letters of the room number
    rooms['room_wing'] = rooms['space'].astype(str).str.strip().str.extract(r'^([A-Za-z]+)')[0].fillna('').str.upper()
    rooms['floor_key'] = rooms['property'] + ' | ' + rooms['floor']
    return rooms

# exits -> persons, width check, open stairs
def prepare_exits(exits, factors, settings, warning_rows):
    exits = exits.copy()
    width_df = factors['width_factors'].set_index('exit_type')
    exits['exit_type'] = exits['exit_type'].fillna('').astype(str).str.strip().str.lower()
    for col in ['wing', 'into_wing']:
        exits[col] = exits[col].fillna('').astype(str).str.strip().str.upper()
    exits['clear_width_cm'] = pd.to_numeric(exits['clear_width_cm'], errors='coerce')

    exits['mm_per_person'] = exits['exit_type'].map(width_df['mm_per_person'])
    exits['persons'] = exit_persons(exits['clear_width_cm'], exits['mm_per_person']).fillna(0).astype(int)

    # minimum width -> BCBC 2024 3.4.3.2.(8) + Table 3.4.3.2.-A: doorways 850, stairs 900 if serving up to
    #   2 storeys above the lowest exit level, else 1100. app doesnt know storeys -> 900 to 1099 = review
    exits['width_mm'] = exits['clear_width_cm'] * 10
    exits['minimum_mm'] = exits['exit_type'].map(width_df['minimum_mm'])
    exits['minimum_mm_low_rise'] = exits['exit_type'].map(width_df['minimum_mm_low_rise'])
    exits['width_check'] = 'ok'
    exits.loc[exits['width_mm'] < exits['minimum_mm'], 'width_check'] = 'review - depends on storeys served'
    exits.loc[exits['width_mm'] < exits['minimum_mm_low_rise'], 'width_check'] = 'fail - below minimum'
    exits.loc[exits['minimum_mm'].isna() | exits['width_mm'].isna(), 'width_check'] = 'unknown'

    # open stairs -> BCBC 2024 3.4.4.1.(1) every exit is fire separated (45 min or more), so not an exit until Mark rules
    exits['counts_as_exit'] = True
    if not settings['open_stairs_count']:
        open_stair = exits['exit_id'].astype(str).str.lower().str.contains('open stair')
        exits.loc[open_stair, 'counts_as_exit'] = False
        exits.loc[open_stair, 'persons'] = 0
        exits.loc[open_stair, 'width_check'] = 'not an exit - open stair'

    for _, row in exits[exits['mm_per_person'].isna()].iterrows():
        warning_rows.append({'type': 'unknown_exit_type', 'property': row['property'], 'floor': row['floor'],
                             'detail': f"{row['exit_id']}: exit_type '{row['exit_type']}' has no width factor - counted as 0 people"})
    for _, row in exits[exits['clear_width_cm'].isna()].iterrows():
        warning_rows.append({'type': 'missing_width', 'property': row['property'], 'floor': row['floor'],
                             'detail': f"{row['exit_id']}: no clear_width_cm - counted as 0 people"})

    exits['floor_key'] = exits['property'] + ' | ' + exits['floor']
    exits['zone_wing'] = exits['wing']
    return exits

# zones -> occupant load vs exit capacity, links, status
def build_zones(rooms, exits, settings, warning_rows):
    # zone = the floor. BCBC 2024 counts exits per floor area (3.4.2.1.(1), 3.4.3.2.(1)), and a floor area is a
    #   storey between exterior walls and firewalls (Div A 1.4.1.2.). wings split only where an exit has a wing
    #   (supervisor decision, for blocks that aren't open to each other)
    split_floors = set(exits.loc[exits['wing'] != '', 'floor_key'])
    rooms['zone_wing'] = rooms['room_wing'].where(rooms['floor_key'].isin(split_floors), '')

    per_zone = rooms.groupby(ZONE_KEYS, as_index=False).agg(
        area_based_load=('per_code_load', 'sum'), load_used=('load_used', 'sum'),
        counted_capacity=('count_in_scope', 'sum'), rooms_in_scope=('in_scope', 'sum'),
        rooms_counted=('counted', 'sum'))
    exit_count = exits.groupby(ZONE_KEYS, as_index=False)['counts_as_exit'].sum().rename(
        columns={'counts_as_exit': 'exit_count'})

    zones = per_zone.merge(exit_count, on=ZONE_KEYS, how='outer')
    for col in ['area_based_load', 'load_used', 'counted_capacity', 'rooms_in_scope', 'rooms_counted', 'exit_count']:
        zones[col] = zones[col].fillna(0).astype(int)

    # pseudo zones -> split floor, 0 load, no exits
    pseudo = zones['floor_key'].isin(split_floors) & (zones['area_based_load'] == 0) & (zones['exit_count'] == 0)
    zones = zones[~pseudo].copy()

    # exit capacity -> 50% rule (BCBC 2024 3.4.3.2.(7))
    cap = exits.groupby(ZONE_KEYS, as_index=False)['persons'].agg(total_persons='sum', largest_exit='max')
    cap['exit_capacity'] = capacity_50_rule(cap['total_persons'], cap['largest_exit'])
    zones = zones.merge(cap[ZONE_KEYS + ['exit_capacity']], on=ZONE_KEYS, how='left')
    zones['exit_capacity'] = zones['exit_capacity'].fillna(0).astype(int)

    # link doors -> people sent into another wing (closest clause BCBC 2024 3.4.3.1.(2))
    links = exits.loc[exits['into_wing'] != '', ZONE_KEYS + ['exit_id', 'into_wing', 'persons']]
    links = links.merge(zones[ZONE_KEYS + ['load_used', 'exit_count']], on=ZONE_KEYS, how='left')
    if len(links):
        links['people_sent'] = people_sent(links['load_used'], links['exit_count'], links['persons'],
                                           settings['link_method']).astype(int)
    else:
        links['people_sent'] = pd.Series(dtype=int)
    inflow = links.groupby(['floor_key', 'into_wing'], as_index=False)['people_sent'].sum().rename(
        columns={'into_wing': 'zone_wing', 'people_sent': 'link_inflow'})
    zones = zones.merge(inflow, on=['floor_key', 'zone_wing'], how='left')
    zones['link_inflow'] = zones['link_inflow'].fillna(0).astype(int)
    zones['total_load'] = zones['load_used'] + zones['link_inflow']

    zone_ids = set(zones['floor_key'] + ' | ' + zones['zone_wing'])
    for _, row in links.iterrows():
        if f"{row['floor_key']} | {row['into_wing']}" not in zone_ids:
            warning_rows.append({'type': 'link_to_missing_wing', 'property': row['property'], 'floor': row['floor'],
                                 'detail': f"{row['exit_id']}: into_wing '{row['into_wing']}' has no zone - {row['people_sent']} people not added"})

    # width problems per zone
    exits['width_fail'] = exits['width_check'].str.startswith('fail')
    exits['width_review'] = exits['width_check'].str.startswith('review')
    exits['width_unknown'] = exits['width_check'] == 'unknown'
    width_flags = exits.groupby(ZONE_KEYS, as_index=False)[['width_fail', 'width_review', 'width_unknown']].any()
    zones = zones.merge(width_flags, on=ZONE_KEYS, how='left')
    for col in ['width_fail', 'width_review', 'width_unknown']:
        zones[col] = zones[col].eq(True)
    sending = set(links['floor_key'] + ' | ' + links['zone_wing'])
    zones['link_sends'] = (zones['floor_key'] + ' | ' + zones['zone_wing']).isin(sending)

    # stairs are not cumulative across floors (BCBC 2024 3.4.3.2.(4)) -> each floor only counts its own rooms, nothing to add
    # status + flags, minimum exits per zone from the minimum_exits setting
    # BCBC 2024 3.4.2.1.(1) -> at least 2 exits. (2) allows 1 exit for small floors up to 60 people, not checked -> review
    min_exits = settings['min_exits']
    statuses, flag_texts = [], []
    for _, z in zones.iterrows():
        flags = []
        if z['exit_count'] < min_exits:
            flags.append(f"fewer than {min_exits} exits")
        if z['total_load'] > z['exit_capacity']:
            flags.append("occupant load over exiting capacity")
        if z['width_fail']:
            flags.append("exit below minimum width")
        if z['width_review']:
            flags.append("stair width depends on storeys served")
        if z['width_unknown']:
            flags.append("exit type or width unknown")
        if z['link_sends'] and z['link_inflow'] > 0:
            flags.append("wing sends and receives link traffic")
        if z['total_load'] == 0:
            flags.append("load is 0 - no rooms in scope, or all counted as 0")

        if z['exit_count'] == 0:
            status, flags = STATUS_NOT_SURVEYED, []
        elif flags:
            status = STATUS_REVIEW
        else:
            status = STATUS_WITHIN
        statuses.append(status)
        flag_texts.append('; '.join(flags))
    zones['status'] = statuses
    zones['flags'] = flag_texts
    zones['status_order'] = zones['status'].map(STATUS_ORDER)
    zones = zones.sort_values(['status_order', 'property', 'floor', 'zone_wing']).drop(columns='status_order')
    return zones.reset_index(drop=True)

# whole calculation -> rooms / exits tables + code factors in, 4 tables out
def calculate(rooms, exits, factors):
    settings = read_settings(factors['settings'])
    warning_rows = []
    rooms = prepare_rooms(rooms, factors, settings, warning_rows)
    exits = prepare_exits(exits, factors, settings, warning_rows)
    zones = build_zones(rooms, exits, settings, warning_rows)
    # which edition these results were screened under -> old results stay comparable after a code change
    zones['code_edition'] = settings['code_edition']
    warnings_df = pd.DataFrame(warning_rows, columns=['type', 'property', 'floor', 'detail'])
    return {'zones': zones, 'rooms': rooms, 'exits': exits, 'warnings': warnings_df, 'settings': settings}

# one floor only -> zones never cross floors, so this gives the same answer much faster
def calculate_floor(rooms, exits, factors, prop, floor):
    r = rooms[(rooms['property'] == prop) & (rooms['floor'] == floor)]
    e = exits[(exits['property'] == prop) & (exits['floor'] == floor)]
    return calculate(r, e, factors)

# colours -> same meaning on every table (README "Colours"): red only ever means over a hard limit
GREEN, AMBER, RED, GREY, NONE = 'green', 'amber', 'red', 'grey', ''

def room_colour(room):
    if not room['in_scope']:
        return NONE
    capacity = pd.to_numeric(room['capacity'], errors='coerce')
    if pd.isna(capacity):
        return GREY                                   # not visited -> per code
    if pd.notna(room['area_per_person_m2']) and capacity > room['per_code_load']:
        return AMBER                                  # needs justification (BCBC 2024 3.1.17.1.(1)(c))
    return GREEN

def zone_colour(zone):
    if zone['status'] == STATUS_NOT_SURVEYED:
        return GREY
    if zone['total_load'] > zone['exit_capacity']:
        return RED
    return AMBER if zone['status'] == STATUS_REVIEW else GREEN

def exit_colour(exit_row):
    check = str(exit_row['width_check'])
    if not exit_row['counts_as_exit'] or check == 'unknown':
        return GREY
    if check.startswith('fail'):
        return RED
    return AMBER if check.startswith('review') else GREEN

# capacity check -> what if these rooms had these capacities? nothing is saved
CANT_CHECK = "Can't check egress: exits on this floor haven't been measured."

def room_verdict(room, proposed):
    if pd.isna(room['area_per_person_m2']):
        return 'no per code load (no room type)', 0
    over = int(proposed) - int(room['per_code_load'])
    if over > 0:
        return f"needs justification, +{over} over per code", over
    return 'within per code', 0

def check_capacities(rooms, exits, factors, changes):
    # rooms / exits / factors straight from the database; changes = {room_id: proposed capacity}
    changes = {int(k): int(v) for k, v in changes.items()}
    picked = rooms[rooms['room_id'].isin(changes)]
    if len(picked) != len(changes):
        raise ValueError("a room in the check isn't in the database any more")
    if picked['property'].nunique() > 1:
        raise ValueError("a check holds rooms from one building only")
    trial = rooms.copy()
    for room_id, proposed in changes.items():
        if proposed < 0:
            raise ValueError("a capacity can't be negative")
        mask = trial['room_id'] == room_id
        trial.loc[mask, 'capacity'] = proposed
        trial.loc[mask, 'capacity_source'] = 'PM change'

    room_rows, zone_rows = [], []
    for (prop, floor), floor_rooms in picked.groupby(['property', 'floor'], sort=True):
        before = calculate_floor(rooms, exits, factors, prop, floor)
        after = calculate_floor(trial, exits, factors, prop, floor)
        split = (after['zones']['zone_wing'] != '').any()
        now = before['rooms'].set_index('room_id')
        for room_id in floor_rooms['room_id']:
            r = now.loc[room_id]
            verdict, over = room_verdict(r, changes[room_id])
            capacity = pd.to_numeric(r['capacity'], errors='coerce')
            room_rows.append({'room_id': int(room_id), 'property': prop, 'floor': floor, 'space': r['space'],
                              'zone_wing': r['room_wing'] if split else '',
                              'room_type': r['room_type'], 'area_m2': r['area_m2'],
                              'current': None if pd.isna(capacity) else int(capacity),
                              'current_source': r['capacity_source'] if pd.notna(capacity) else 'per code',
                              'proposed': changes[room_id], 'per_code_load': int(r['per_code_load']),
                              'in_scope': bool(r['in_scope']), 'verdict': verdict, 'over_per_code': over,
                              'colour': AMBER if over > 0 else (GREEN if r['in_scope'] else NONE)})
        old = before['zones'].set_index('zone_wing')
        changed_wings = {row['zone_wing'] for row in room_rows if row['floor'] == floor and row['property'] == prop}
        for _, z in after['zones'].sort_values('zone_wing').iterrows():
            load_before = int(old.loc[z['zone_wing'], 'total_load']) if z['zone_wing'] in old.index else 0
            over = int(z['total_load']) - int(z['exit_capacity'])
            if z['status'] == STATUS_NOT_SURVEYED:
                verdict = CANT_CHECK
            elif over > 0:
                verdict = f"over exit capacity by {over}"
            else:
                verdict = 'within exit capacity'
            other = [f for f in z['flags'].split('; ') if f and f != 'occupant load over exiting capacity']
            zone_rows.append({'property': prop, 'floor': floor, 'zone_wing': z['zone_wing'],
                              'has_checked_room': z['zone_wing'] in changed_wings,
                              'load_before': load_before, 'load_after': int(z['total_load']),
                              'exit_capacity': int(z['exit_capacity']), 'verdict': verdict,
                              'other_flags': '; '.join(other), 'colour': zone_colour(z)})
    return {'rooms': room_rows, 'zones': zone_rows,
            'code_edition': read_settings(factors['settings'])['code_edition']}
