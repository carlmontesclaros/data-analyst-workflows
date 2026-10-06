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

    # per code load = area / m2 per person, rounded up
    rooms['area_per_person_m2'] = rooms['room_type'].map(area_factor)
    rooms['per_code_load'] = occupant_load(rooms['area_m2'], rooms['area_per_person_m2']).fillna(0).astype(int)

    # scope -> every room except the excluded sub-category codes (a code covers its children)
    sub_code = rooms['sub_category'].astype(str).str.split(' - ').str[0].str.strip()
    rooms['in_scope'] = True
    for code in settings['room_exclude']:
        rooms.loc[(sub_code == code) | sub_code.str.startswith(code + '.'), 'in_scope'] = False

    # load used -> room capacity when there is one (visited / PM change, 0 stays 0), else per code
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

    # minimum width (Table 3.4.3.2.-A)
    exits['width_mm'] = exits['clear_width_cm'] * 10
    exits['minimum_mm'] = exits['exit_type'].map(width_df['minimum_mm'])
    exits['minimum_mm_low_rise'] = exits['exit_type'].map(width_df['minimum_mm_low_rise'])
    exits['width_check'] = 'ok'
    exits.loc[exits['width_mm'] < exits['minimum_mm'], 'width_check'] = 'review - depends on storeys served'
    exits.loc[exits['width_mm'] < exits['minimum_mm_low_rise'], 'width_check'] = 'fail - below minimum'
    exits.loc[exits['minimum_mm'].isna() | exits['width_mm'].isna(), 'width_check'] = 'unknown'

    # open stairs -> not fire separated, not an exit (3.4.4.1.(1)) until Mark rules
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

    # exit capacity -> 50% rule (3.4.3.2.(7))
    cap = exits.groupby(ZONE_KEYS, as_index=False)['persons'].agg(total_persons='sum', largest_exit='max')
    cap['exit_capacity'] = capacity_50_rule(cap['total_persons'], cap['largest_exit'])
    zones = zones.merge(cap[ZONE_KEYS + ['exit_capacity']], on=ZONE_KEYS, how='left')
    zones['exit_capacity'] = zones['exit_capacity'].fillna(0).astype(int)

    # link doors -> people sent into another wing (3.4.3.1.(2))
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

    # stairs are not cumulative across floors (3.4.3.2.(4)) -> each floor only counts its own rooms, nothing to add
    # status + flags, minimum exits per zone from the minimum_exits setting
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
