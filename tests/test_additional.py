import pytest

from additional_functionality.additional import calc_time, get_wait_seconds, parse_duration, parse_timing_text


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


@pytest.mark.parametrize("text,seconds", [
    ("0 хв", 0),
    ("18 хв", 18 * 60),
    ("2 год 24 хв", 2 * 3600 + 24 * 60),
    ("1 дн 17 год", 86400 + 17 * 3600),
    ("7 дн 2 год", 7 * 86400 + 2 * 3600),
    ("5 дн 20 год", 5 * 86400 + 20 * 3600),
    ("3 дн", 3 * 86400),
    ("1 год", 3600),
    ("  7 дн  2 год ", 7 * 86400 + 2 * 3600),
])
def test_parse_timing_text(text, seconds):
    assert parse_timing_text(text) == seconds


@pytest.mark.parametrize("text", ["", "немає черги", "дн год", None, 5, {}])
def test_parse_timing_text_unknown_format(text):
    assert parse_timing_text(text) is None


def _entry(text):
    return {"id": 14, "timing": {"header": {"text": text, "label": "Час очікування"}, "additional": None}}


def test_get_wait_seconds_from_real_api_shape():
    # реальний формат API v5: числового wait_time немає, лише timing.header.text
    assert get_wait_seconds(_entry("7 дн 2 год")) == 7 * 86400 + 2 * 3600
    assert get_wait_seconds(_entry("0 хв")) == 0


def test_get_wait_seconds_prefers_numeric_wait_time():
    assert get_wait_seconds({"wait_time": 600, **_entry("7 дн 2 год")}) == 600
    assert get_wait_seconds({"wait_time": 0, **_entry("7 дн 2 год")}) == 0


@pytest.mark.parametrize("entry", [
    {}, {"wait_time": None}, {"timing": None}, {"timing": {}}, {"timing": {"header": None}},
    {"timing": {"header": {"text": "???"}}}, {"wait_time": True},
])
def test_get_wait_seconds_unknown(entry):
    assert get_wait_seconds(entry) is None
