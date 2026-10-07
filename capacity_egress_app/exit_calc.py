import numpy as np

# the BCBC formulas, one function per rule. clauses checked against BCBC 2024 (revision 2) on 2026-10-07
# the numbers these use (m2 per person, mm per person, minimum widths) live in the database, not here
# new code edition changes a formula -> README "When the building code changes", change it here + its test

# occupant load per room = area / m^2 per person, rounded up (round to 6 first so float noise doesnt bump it)
# BCBC 2024 3.4.3.1.(1) -> load from 3.1.17.1.(1)(c), m2 per person from Table 3.1.17.1.
# rounding up is our choice (code doesnt say), it's the conservative one
def occupant_load(area, area_per_person):
    return np.ceil(np.round(area / area_per_person, 6))

# people per exit = width in mm / mm per person, rounded down (our choice, conservative)
# BCBC 2024 3.4.3.2.(1) -> (a) 6.1 doorways, corridors, ramps up to 1 in 8
#   (b) 8.0 stairs with rise <= 180 mm and run >= 280 mm, (c) 9.2 other stairs, ramps steeper than 1 in 8
def exit_persons(width_cm, mm_per_person):
    return np.floor(np.round(width_cm * 10 / mm_per_person, 6))

# exiting capacity of a zone -> 50% rule, no exit counts for more than half
# BCBC 2024 3.4.3.2.(7) -> if more than one exit is required, each exit counts for at most half the required width
def capacity_50_rule(total, largest):
    others = total - largest
    return np.minimum(total, 2 * others)

# people sent through a link door into another wing
# closest clause BCBC 2024 3.4.3.1.(2) -> exit width is cumulative where exits converge
# the share method is a supervisor decision, not code text (link_share_method setting)
# even_split = sending wing load / its exits, half_load = load / 2, never more than the door holds
def people_sent(load, exit_count, door_persons, method='even_split'):
    if method == 'even_split':
        share = np.ceil(np.round(load / exit_count, 6))
    elif method == 'half_load':
        share = np.ceil(np.round(load / 2, 6))
    else:
        raise ValueError(f"link_share_method '{method}' must be even_split or half_load")
    return np.minimum(share, door_persons)
