from exit_calc import occupant_load

def test_b303_classroom():
    assert occupant_load(60.55, 1.85) == 33

def test_float_noise_lab():
    assert occupant_load(13.8, 4.6) == 3
