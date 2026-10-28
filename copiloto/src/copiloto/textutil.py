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


WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}


def _next_weekday(name: str, today: date, after: date | None = None) -> date:
    base = after or today
    delta = (WEEKDAYS[name] - base.weekday()) % 7
    return base + timedelta(days=delta or (7 if after else 0))


def parse_nights(text: str) -> int | None:
    """'3 noches', 'tres noches', 'una noche' → número de noches (1 a 30)."""
    match = re.search(r"(\d+|una|un|dos|tres|cuatro|cinco|seis|siete)\s+noches?", normalize(text))
    if not match:
        return None
    nights = _first_number(match.group(1))
    return nights if nights and 1 <= nights <= 30 else None


def parse_one_date(text: str, today: date) -> date | None:
    """Una sola fecha en lenguaje natural: 'mañana', 'el viernes', '15/03', '15 de marzo'."""
    plain = normalize(text)
    if re.search(r"\bpasado manana\b", plain):
        return today + timedelta(days=2)
    if re.search(r"\bmanana\b", plain):
        return today + timedelta(days=1)
    if re.search(r"\bhoy\b", plain):
        return today
    numeric = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", plain)
    if numeric:
        day, month, year = numeric.groups()
        return _explicit_date(int(day), int(month), int(year) if year else None, today)
    month_names = "|".join(MONTHS)
    named = re.search(rf"(\d{{1,2}}) de ({month_names})", plain)
    if named:
        return _next_date(int(named.group(1)), MONTHS[named.group(2)], today)
    weekday = re.search(r"\b(" + "|".join(WEEKDAYS) + r")\b", plain)
    if weekday:
        return _next_weekday(weekday.group(1), today)
    return None


def parse_weekday_range(text: str, today: date) -> tuple[date, date] | None:
    """'del viernes al domingo' → próximas fechas de esos días."""
    names = "|".join(WEEKDAYS)
    match = re.search(rf"\b({names})\b\s*(?:al|a|hasta|-)\s*(?:el\s+)?({names})\b", normalize(text))
    if not match:
        return None
    start = _next_weekday(match.group(1), today)
    end = _next_weekday(match.group(2), today, after=start)
    return start, end
