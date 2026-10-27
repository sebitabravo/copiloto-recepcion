"""Utilidades de texto en español: normalización, fechas de estadía y cantidad de huéspedes."""

import re
import unicodedata
from datetime import date, timedelta

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
WORD_NUMBERS = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
                "cero": 0, "ningun": 0, "ninguno": 0, "ninguna": 0}


def normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in stripped if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip()


def contains_word(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(normalize(term))}(?![a-z0-9])", text) is not None


def _next_date(day: int, month: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def _explicit_date(day: int, month: int, year: int | None, today: date) -> date | None:
    if year is None:
        return _next_date(day, month, today)
    year = year + 2000 if year < 100 else year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_stay(text: str, today: date) -> tuple[date, date] | None:
    """Interpreta un rango de fechas: dd/mm al dd/mm, '15 al 18 de enero' o 'este finde'."""
    plain = normalize(text)
    if re.search(r"\b(este )?(finde|fin de semana)\b", plain):
        days_to_friday = (4 - today.weekday()) % 7
        friday = today + timedelta(days=days_to_friday)
        return friday, friday + timedelta(days=2)

    numeric = re.findall(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", plain)
    if len(numeric) >= 2:
        found = [_explicit_date(int(d), int(m), int(y) if y else None, today) for d, m, y in numeric[:2]]
        if all(found) and found[1] > found[0]:
            return found[0], found[1]
        return None

    month_names = "|".join(MONTHS)
    ranged = re.search(
        rf"(\d{{1,2}})(?: de ({month_names}))?\s*(?:al|a|hasta|-)\s*(\d{{1,2}}) de ({month_names})", plain
    )
    if ranged:
        first_day, first_month, last_day, last_month = ranged.groups()
        end_month = MONTHS[last_month]
        start_month = MONTHS[first_month] if first_month else end_month
        start = _next_date(int(first_day), start_month, today)
        if start is None:
            return None
        end = _explicit_date(int(last_day), end_month, start.year, today)
        if end and end > start:
            return start, end
        if end:
            end = _explicit_date(int(last_day), end_month, start.year + 1, today)
            return (start, end) if end and end > start else None
    return None


def _first_number(chunk: str) -> int | None:
    digit = re.search(r"\d+", chunk)
    if digit:
        return int(digit.group())
    for word in re.findall(r"[a-z]+", chunk):
        if word in WORD_NUMBERS:
            return WORD_NUMBERS[word]
    return None


def parse_count(text: str) -> int | None:
    """Número suelto ('2', 'dos', 'ninguno'); None si no se entiende."""
    return _first_number(normalize(text))


def parse_guests(text: str) -> tuple[int | None, int | None]:
    """Extrae (adultos, niños) de frases como '2 adultos y 1 niño'. Cada valor puede ser None."""
    plain = normalize(text)
    adults = children = None
    match = re.search(r"(\d+|un|uno|una|dos|tres|cuatro|cinco|seis)\s+adult", plain)
    if match:
        adults = _first_number(match.group(1))
    match = re.search(r"(\d+|un|uno|una|dos|tres|cuatro|cinco|seis)\s+(?:nin|menor|bebe|hij)", plain)
    if match:
        children = _first_number(match.group(1))
    return adults, children
