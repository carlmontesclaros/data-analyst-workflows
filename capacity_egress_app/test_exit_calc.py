from exit_calc import occupant_load, exit_persons, capacity_50_rule, people_sent
import pytest

def test_b303_classroom():
    assert occupant_load(60.55, 1.85) == 33

def test_float_noise_lab():
    assert occupant_load(13.8, 4.6) == 3

def test_stairs_121():
    assert exit_persons(121, 8.0) == 151

def test_doorway_88():
    assert exit_persons(88, 6.1) == 144

def test_steep_stairs_121():
    assert exit_persons(121, 9.2) == 131

def test_50_rule_three_exits():
    exits = [151, 144, 144]
    assert capacity_50_rule(sum(exits), max(exits)) == 439

def test_50_rule_two_exits():
    exits = [151, 144]
    assert capacity_50_rule(sum(exits), max(exits)) == 288

def test_50_rule_one_big_exit():
    exits = [400, 100]
    assert capacity_50_rule(sum(exits), max(exits)) == 200

def test_50_rule_equal_exits():
    exits = [100, 100]
    assert capacity_50_rule(sum(exits), max(exits)) == 200

def test_50_rule_single_exit():
    exits = [144]
    assert capacity_50_rule(sum(exits), max(exits)) == 0

def test_link_even_split():
    assert people_sent(100, 4, 144) == 25

def test_link_rounds_up():
    assert people_sent(101, 4, 144) == 26

def test_link_door_limit():
    assert people_sent(100, 4, 20) == 20

def test_link_half_load():
    assert people_sent(100, 4, 144, 'half_load') == 50

def test_link_bad_method():
    with pytest.raises(ValueError):
        people_sent(100, 4, 144, 'typo')