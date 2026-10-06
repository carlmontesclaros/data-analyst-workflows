import numpy as np

# the BCBC formulas, one function per rule. clause numbers are BCBC 2024 (checked against the 2018 text, confirm in 2024)
# the numbers these use (m2 per person, mm per person, minimum widths) live in the database, not here
# new code edition changes a formula -> README "When the building code changes", change it here + its test

# occupant load per room = area / m^2 per person, rounded up (round to 6 first so float noise doesnt bump it)
# 3.4.3.1.(1) -> occupant load from Subsection 3.1.17 (Table 3.1.17.1.)
def occupant_load(area, area_per_person):
    return np.ceil(np.round(area / area_per_person, 6))

# people per exit = width in mm / mm per person, rounded down
# 3.4.3.2.(1) -> (a) doorways 6.1, (b) stairs 8.0, (c) steep stairs 9.2
def exit_persons(width_cm, mm_per_person):
    return np.floor(np.round(width_cm * 10 / mm_per_person, 6))

# exiting capacity of a zone -> 50% rule, no exit counts for more than half
# 3.4.3.2.(7)
def capacity_50_rule(total, largest):
    others = total - largest
    return np.minimum(total, 2 * others)

# people sent through a link door into another wing
# 3.4.3.1.(2), share method is a supervisor decision (link_share_method setting)
# even_split = sending wing load / its exits, half_load = load / 2, never more than the door holds
def people_sent(load, exit_count, door_persons, method='even_split'):
    if method == 'even_split':
        share = np.ceil(np.round(load / exit_count, 6))
    elif method == 'half_load':
        share = np.ceil(np.round(load / 2, 6))
    else:
        raise ValueError(f"link_share_method '{method}' must be even_split or half_load")
    return np.minimum(share, door_persons)
