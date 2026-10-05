import numpy as np

# occupant load per room = area / m^2 per person, rounded up (round to 6 first so float noise doesnt bump it)
def occupant_load(area, area_per_person):
    return np.ceil(np.round(area / area_per_person, 6))

# people per exit = width in mm / mm per person, rounded down
def exit_persons(width_cm, mm_per_person):
    return np.floor(np.round(width_cm * 10 / mm_per_person, 6))

# exiting capacity of a zone -> 50% rule per BCBC 3.4.3.2.(7), no exit counts for more than half
def capacity_50_rule(total, largest):
    others = total - largest
    return np.minimum(total, 2 * others)

# people sent through a link door into another wing BCBC 3.4.3.1.(2)
# even_split = sending wing load / its exits, half_load = load / 2, never more than the door holds
def people_sent(load, exit_count, door_persons, method='even_split'):
    if method == 'even_split':
        share = np.ceil(np.round(load / exit_count, 6))
    elif method == 'half_load':
        share = np.ceil(np.round(load / 2, 6))
    else:
        raise ValueError(f"link_share_method '{method}' must be even_split or half_load")
    return np.minimum(share, door_persons)
