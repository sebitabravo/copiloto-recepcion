"""Datos del hotel (data/hotel.yaml) con acceso tipado y reconocimiento de FAQ por palabras clave."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from copiloto.textutil import contains_word, normalize


@dataclass(frozen=True)
class Faq:
    id: str
    label: str
    keywords: tuple[str, ...]
    answer: str
    source: str
    status: str


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
                item["status"])
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

    def match_faq(self, text: str) -> Faq | None:
        """Devuelve la FAQ con más palabras clave presentes; en empate, la de la palabra más larga."""
        plain = normalize(text)
        best: tuple[int, int, Faq] | None = None
        for faq in self.faqs:
            hits = [kw for kw in faq.keywords if contains_word(plain, kw)]
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
