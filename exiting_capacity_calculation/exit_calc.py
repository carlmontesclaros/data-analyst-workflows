import numpy as np

# occupant load per room = area / m^2 per person
def occupant_load(area, area_per_person):
    return np.ceil(np.round(area / area_per_person, 6))
