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


from copiloto.textutil import parse_nights, parse_one_date, parse_weekday_range  # noqa: E402


def test_natural_single_dates_and_nights():
    assert parse_one_date("mañana", TODAY) == date(2026, 10, 29)
    assert parse_one_date("pasado mañana", TODAY) == date(2026, 10, 30)
    assert parse_one_date("llego el 15 de marzo", TODAY) == date(2027, 3, 15)
    assert parse_one_date("el viernes", TODAY) == date(2026, 10, 30)
    assert parse_one_date("quizás", TODAY) is None
    assert parse_nights("3 noches") == 3 and parse_nights("tres noches") == 3 and parse_nights("una noche") == 1
    assert parse_nights("hola") is None and parse_nights("90 noches") is None


def test_weekday_ranges():
    assert parse_weekday_range("del viernes al domingo", TODAY) == (date(2026, 10, 30), date(2026, 11, 1))
    assert parse_weekday_range("sábado a lunes", TODAY) == (date(2026, 10, 31), date(2026, 11, 2))
    assert parse_weekday_range("el viernes", TODAY) is None


from copiloto.textutil import (  # noqa: E402
    MAX_ADULTS,
    MAX_CHILDREN,
    MAX_NIGHTS,
    guests_out_of_range,
    is_local_host,
    is_local_url,
    money,
    nights_exceeded,
    plural,
    read_label,
)


def test_shared_presentation_helpers():
    assert money(255000) == "$255.000"
    assert plural(1, "noche", "noches") == "1 noche" and plural(3, "noche", "noches") == "3 noches"
    assert read_label("2026-10-27T17:39:54-03:00") == "27-10-2026 17:39"
    assert read_label("corto") == "corto"


def test_local_host_detection_is_the_union_of_both_previous_checks():
    for host in ("localhost", "127.0.0.1", "::1", "host.docker.internal", "0.0.0.0"):
        assert is_local_host(host) and is_local_url(f"http://{host}:11434/v1")
    assert not is_local_host("hotelbordeluz.cl")
    assert not is_local_url("https://api.deepseek.com")


def test_stay_rules_are_shared_constants():
    assert MAX_NIGHTS == 30 and MAX_ADULTS == 4 and MAX_CHILDREN == 3
    assert nights_exceeded(date(2026, 11, 1), date(2026, 12, 15))
    assert not nights_exceeded(date(2026, 11, 1), date(2026, 11, 15))
    assert guests_out_of_range(0, 1) and guests_out_of_range(2, 4) and guests_out_of_range(None, 0)
    assert not guests_out_of_range(2, 3)
