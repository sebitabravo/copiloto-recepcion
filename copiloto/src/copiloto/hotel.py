"""Datos del hotel (data/hotel.yaml) con acceso tipado y reconocimiento de FAQ por palabras clave."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from copiloto.textutil import contains_word, normalize

REVIEW_KEY = "revisar_antes_de"

# Temas que sirve get_hotel_info y el bloque del que salen. Los bloques lista (rooms, services, faqs)
# vencen si cualquiera de sus ítems venció: se falla cerrado, sin entregar la parte vigente.
TOPIC_BLOCKS = {
    "ubicacion": "location",
    "habitaciones": "rooms",
    "servicios": "services",
    "politicas": "policies",
    "promociones": "promotions",
    "contacto": "hotel",
    "faq": "faqs",
}


def _review_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class Faq:
    id: str
    label: str
    keywords: tuple[str, ...]
    answer: str
    source: str
    status: str
    answer_en: str = ""


class HotelData:
    def __init__(self, raw: dict):
        self.raw = raw
        self.hotel = raw["hotel"]
        self.location = raw["location"]
        self.policies = raw["policies"]
        self.photos = raw["photos"]
        self.privacy = raw["privacy"]
        self.rooms = raw["rooms"]
        self.faqs = [
            Faq(item["id"], item["label"], tuple(item["keywords"]), item["answer"], item["source"],
                item["status"], item.get("answer_en", ""))
            for item in raw["faqs"]
        ]
        self._rooms_by_code = {room["code"]: room for room in self.rooms}

    @classmethod
    def load(cls, path: str | Path) -> "HotelData":
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise RuntimeError(f"No se pudo leer los datos del hotel en {path}: {exc}") from exc
        for key in ("hotel", "location", "policies", "photos", "privacy", "rooms", "faqs"):
            if key not in raw:
                raise RuntimeError(f"Falta la clave '{key}' en {path}")
        return cls(raw)

    def room(self, code: str) -> dict | None:
        return self._rooms_by_code.get(code)

    def expired_on(self, topic: str, today: date) -> date | None:
        """Fecha de revisión vencida del bloque que sirve `topic` (o de cualquier ítem suyo).

        Devuelve None si el bloque no declara la fecha (datos antiguos: no se endurecen retroactivamente)
        o si sigue vigente. La herramienta del asistente usa esto para fallar cerrado (invariante 5).
        """
        block = self.raw.get(TOPIC_BLOCKS.get(topic, ""))
        if isinstance(block, dict):
            expiry = _review_date(block.get(REVIEW_KEY))
            return expiry if expiry and expiry < today else None
        if isinstance(block, list):
            past = [
                d
                for item in block
                if isinstance(item, dict) and (d := _review_date(item.get(REVIEW_KEY))) and d < today
            ]
            return max(past) if past else None
        return None

    def match_faq(self, text: str) -> Faq | None:
        """Devuelve la FAQ con más palabras clave presentes; en empate, la de la palabra más larga."""
        plain = normalize(text)
        best: tuple[int, int, Faq] | None = None
        for faq in self.faqs:
            hits = [kw for kw in faq.keywords if _term_in(plain, kw)]
            if not hits:
                continue
            score = (len(hits), max(len(normalize(kw)) for kw in hits))
            if best is None or score > best[:2]:
                best = (*score, faq)
        return best[2] if best else None

    def faq_menu(self, limit: int = 9) -> list[Faq]:
        return self.faqs[:limit]

    def faq_by_label(self, text: str) -> Faq | None:
        plain = normalize(text)
        return next((faq for faq in self.faqs if normalize(faq.label) == plain), None)


def _term_in(plain: str, keyword: str) -> bool:
    """Acepta el plural simple: «tarjetas» coincide con la palabra clave «tarjeta»."""
    return any(contains_word(plain, form) for form in (keyword, keyword + "s", keyword + "es"))
