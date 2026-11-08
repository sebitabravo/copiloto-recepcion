"""Utilidades de texto en español: normalización, fechas de estadía y cantidad de huéspedes.

Aquí viven también las reglas de estadía y capacidad compartidas por el flujo guiado y el asistente
con IA, y los formatos de presentación (dinero, plurales, hora de lectura del PMS).
"""

import re
import unicodedata
from datetime import date, timedelta

# Reglas de estadía compartidas: el menú guiado y las herramientas de la IA aplican los mismos topes.
MAX_NIGHTS = 30
MAX_ADULTS = 4
MAX_CHILDREN = 3

# Hosts que cuentan como infraestructura local del hotel: unión de todas las comprobaciones que antes
# vivían repetidas en flow.py y privacy.py.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal", "0.0.0.0"})

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
# Abreviaturas que el huésped escribe en el chat («20–22 nov»). Van aparte de MONTHS para no ofrecerlas
# como nombre canónico; los patrones prueban primero el nombre largo («mayo» antes que «may»).
MONTH_ABBREVIATIONS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "sept": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_ALL_MONTHS = {**MONTHS, **MONTH_ABBREVIATIONS}
# Alternativa de regex con el nombre más largo primero: «mayo» gana a «may», «septiembre» a «sept».
_MONTH_PATTERN = "|".join(sorted(_ALL_MONTHS, key=len, reverse=True))
WORD_NUMBERS = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "cero": 0,
    "ningun": 0,
    "ninguno": 0,
    "ninguna": 0,
}


def strip_accents(text: str) -> str:
    """NFD + descarte de combining: «sí» y «si» quedan idénticos para las comprobaciones."""
    return "".join(char for char in unicodedata.normalize("NFD", text) if not unicodedata.combining(char))


def normalize(text: str) -> str:
    stripped = strip_accents(text.lower())
    return re.sub(r"\s+", " ", stripped).strip()


def is_local_host(host: str) -> bool:
    """Un hostname explícito (por ejemplo el de COPILOTO_PUBLIC_URL) es local si está en la lista."""
    return (host or "").lower() in LOCAL_HOSTS


def is_local_url(url: str) -> bool:
    """Una URL completa (o 'host:puerto' sin esquema) es local si su hostname exacto está en la lista.

    Se compara el hostname parseado, no una subcadena: 'https://api.deepseek.com/v1?echo=0.0.0.0'
    no es local aunque el query contenga un host de la lista.
    """
    return _url_hostname(url) in LOCAL_HOSTS


def _url_hostname(url: str) -> str | None:
    """Hostname exacto de una URL completa o de 'host:puerto' sin esquema.

    Acepta IPv6 ('::1') con y sin corchetes; un puerto final solo se separa cuando la autoridad
    lo admite sin ambigüedad.
    """
    text = (url or "").strip()
    if not text:
        return None
    authority = text.split("://", 1)[-1].split("/", 1)[0]
    if "@" in authority:  # userinfo: queda fuera del hostname
        authority = authority.rsplit("@", 1)[1]
    if authority.startswith("["):
        end = authority.find("]")
        return authority[1:end].lower() if end != -1 else None
    if authority.count(":") == 1 or (authority.count(":") > 2 and authority.rsplit(":", 1)[1].isdigit()):
        authority = authority.rsplit(":", 1)[0]
    return authority.lower() or None


def nights_exceeded(checkin: date, checkout: date) -> bool:
    return (checkout - checkin).days > MAX_NIGHTS


def guests_out_of_range(adults: int | None, children: int | None) -> bool:
    return adults is None or children is None or not 1 <= adults <= MAX_ADULTS or not 0 <= children <= MAX_CHILDREN


def money(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


def read_label(read_at: str) -> str:
    """'2026-10-27T17:39:54-03:00' → '27-10-2026 17:39'."""
    if len(read_at) < 16:
        return read_at
    year, month, day = read_at[:10].split("-")
    return f"{day}-{month}-{year} {read_at[11:16]}"


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


def _date_text(text: str) -> str:
    """Texto normalizado para fechas: guiones largos como guion simple y «nov.» sin el punto."""
    plain = normalize(text).replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(rf"\b({_MONTH_PATTERN})\.", r"\1", plain)


def _month(name: str) -> int:
    return _ALL_MONTHS[name]


def _ranged_match(plain: str):
    """'20 al 22 de noviembre', '20-22 nov', '20 nov al 22 nov' → (día1, mes1|None, día2, mes2)."""
    return re.search(
        rf"(\d{{1,2}})(?:\s*(?:de\s+)?({_MONTH_PATTERN})\b)?\s*(?:al|a|hasta|-)\s*(\d{{1,2}})\s*(?:de\s+)?({_MONTH_PATTERN})\b",
        plain,
    )


def inverted_stay(text: str, today: date) -> tuple[date, date] | None:
    """Rango escrito al revés ('22 al 20 de noviembre', '22/11 al 20/11'): (llegada, salida) tal cual.

    Sirve para explicarle al huésped el error en vez de responder «no entendí las fechas».
    """
    plain = _date_text(text)
    numeric = re.findall(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", plain)
    if len(numeric) >= 2:
        found = [_explicit_date(int(d), int(m), int(y) if y else None, today) for d, m, y in numeric[:2]]
        if all(found) and found[1] <= found[0]:
            return found[0], found[1]
        return None
    ranged = _ranged_match(plain)
    if not ranged:
        return None
    first_day, first_month, last_day, last_month = ranged.groups()
    month = _month(first_month) if first_month else _month(last_month)
    if month != _month(last_month):
        return None
    start = _next_date(int(first_day), month, today)
    if start is None:
        return None
    try:
        end = date(start.year, month, int(last_day))
    except ValueError:
        return None
    return (start, end) if end <= start else None


def parse_stay(text: str, today: date) -> tuple[date, date] | None:
    """Interpreta un rango de fechas: dd/mm al dd/mm, '15 al 18 de enero', '20-22 nov' o 'este finde'."""
    plain = _date_text(text)
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

    ranged = _ranged_match(plain)
    if ranged:
        first_day, first_month, last_day, last_month = ranged.groups()
        end_month = _month(last_month)
        start_month = _month(first_month) if first_month else end_month
        if start_month == end_month and int(last_day) <= int(first_day):
            # Mismo mes y salida antes de la llegada: es un error del huésped, no un salto de año.
            return None
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


def _nights_value(text: str) -> int | None:
    match = re.search(r"(\d+|una|un|dos|tres|cuatro|cinco|seis|siete)\s+noches?", normalize(text))
    if not match:
        return None
    return _first_number(match.group(1))


def parse_nights(text: str) -> int | None:
    """'3 noches', 'tres noches', 'una noche' → número de noches (1 a MAX_NIGHTS)."""
    nights = _nights_value(text)
    return nights if nights and 1 <= nights <= MAX_NIGHTS else None


def nights_over_limit(text: str) -> bool:
    """True si el texto pide explícitamente más de MAX_NIGHTS noches ('31 noches').

    Distinto de None en parse_nights: la estadía se entiende, solo excede el tope, y el huésped
    debe ver el límite en vez del error genérico de fechas.
    """
    nights = _nights_value(text)
    return nights is not None and nights > MAX_NIGHTS


def parse_one_date(text: str, today: date) -> date | None:
    """Una sola fecha en lenguaje natural: 'mañana', 'el viernes', '15/03', '15 de marzo'."""
    plain = _date_text(text)
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
    named = re.search(rf"(\d{{1,2}})\s*(?:de\s+)?({_MONTH_PATTERN})\b", plain)
    if named:
        return _next_date(int(named.group(1)), _month(named.group(2)), today)
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


# Formato de chat (contrato C2): el huésped ve texto plano y montos en pesos chilenos.
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)
_CODE_FENCE = re.compile(r"^[ \t]*```.*$", re.M)
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
_HEADER = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.M)
_STAR_BULLET = re.compile(r"^([ \t]*)[*•][ \t]+", re.M)
_CLP_GROUPED = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+)(?!\d)")
_CLP_PLAIN = re.compile(r"\$\s?(\d{4,})(?![\d.,]\d)")


def chat_format(text: str, max_blocks: int = 3) -> str:
    """Texto plano para el chat: sin Markdown, montos `$65.000` y a lo más `max_blocks` bloques.

    Una línea en blanco separa ideas (contrato C1: el simulador muestra cada bloque como una burbuja). Los
    bloques que sobran se unen al último con un salto simple, sin perder texto. El `*texto*` simple queda:
    es la negrita de WhatsApp que el simulador muestra.
    """
    text = _CODE_FENCE.sub("", text.replace("\r\n", "\n"))
    text = _BOLD.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _HEADER.sub("", text)
    text = _STAR_BULLET.sub(r"\1- ", text)
    text = _CLP_GROUPED.sub(lambda m: "$" + m.group(1).replace(",", "."), text)
    text = _CLP_PLAIN.sub(lambda m: money(int(m.group(1))), text)
    lines = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    blocks = [block.strip("\n") for block in re.split(r"\n{2,}", lines) if block.strip()]
    if len(blocks) > max_blocks:
        blocks = [*blocks[: max_blocks - 1], "\n".join(blocks[max_blocks - 1 :])]
    return "\n\n".join(blocks)
