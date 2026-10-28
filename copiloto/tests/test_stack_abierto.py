"""Regla del proyecto: sin servicios de pago por defecto y sin CDNs en la landing.

Ver docs/stack-abierto.md. Si alguien vuelve a poner una API pagada como modelo por defecto o mete
un CDN en la página, estas pruebas fallan.
"""

from pathlib import Path

from copiloto.config import Settings

LANDING = Path(__file__).resolve().parents[2] / "landing"


def test_the_default_model_is_local():
    settings = Settings.from_env()
    base = settings.llm_base_url.lower()
    assert "deepseek" not in base and "openai" not in base
    assert "11434" in base or "localhost" in base or "127.0.0.1" in base


def test_the_landing_does_not_load_anything_from_a_cdn():
    for name in ("index.html", "demo.css", "demo.js"):
        text = (LANDING / name).read_text(encoding="utf-8")
        for forbidden in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn.", "unpkg.com", "jsdelivr"):
            assert forbidden not in text, f"{name} carga {forbidden}"
