from datetime import date

import pytest
from copiloto.textutil import parse_count, parse_guests, parse_stay

TODAY = date(2026, 10, 28)


@pytest.mark.parametrize("text,expected", [
    ("15/11 al 18/11", (date(2026, 11, 15), date(2026, 11, 18))),
    ("del 15 al 18 de noviembre", (date(2026, 11, 15), date(2026, 11, 18))),
    ("20 de diciembre al 2 de enero", (date(2026, 12, 20), date(2027, 1, 2))),
    ("5/1/2027 - 8/1/2027", (date(2027, 1, 5), date(2027, 1, 8))),
    ("este finde", (date(2026, 10, 30), date(2026, 11, 1))),
])
def test_parse_stay_accepts_common_spanish_formats(text, expected):
    assert parse_stay(text, TODAY) == expected


@pytest.mark.parametrize("text", ["hola", "18/11 al 15/11", "31/02 al 02/03"])
def test_parse_stay_rejects_invalid_ranges(text):
    assert parse_stay(text, TODAY) is None


def test_parse_guests_reads_adults_and_children():
    assert parse_guests("2 adultos y 1 niño") == (2, 1)
    assert parse_guests("somos dos adultos") == (2, None)
    assert parse_guests("hola") == (None, None)


def test_parse_count_understands_words_and_digits():
    assert parse_count("dos") == 2 and parse_count("3") == 3 and parse_count("ninguno") == 0
    assert parse_count("quizás") is None
