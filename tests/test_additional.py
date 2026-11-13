import pytest

from additional_functionality.additional import calc_time, parse_duration


def test_calc_time_zero():
    assert calc_time(0) == "0 хвилин"


def test_calc_time_mixed():
    assert calc_time(86400 + 2 * 3600 + 5 * 60) == "1 днів 2 годин 5 хвилин"


def test_calc_time_skips_zero_units():
    assert calc_time(3600) == "1 годин"


def test_parse_duration_ok():
    assert parse_duration("1 2 3") == 86400 + 2 * 3600 + 3 * 60
    assert parse_duration("0,0,1") == 60


@pytest.mark.parametrize("text", ["1 2", "1 2 3 4", "0 24 0", "0 0 60", "-1 0 0"])
def test_parse_duration_invalid(text):
    with pytest.raises(ValueError):
        parse_duration(text)
