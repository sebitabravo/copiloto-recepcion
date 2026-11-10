"""El JSON que usa la función de IA en Vercel coincide con data/hotel.yaml.

Una función serverless no puede leer el YAML (no viaja PyYAML ni el archivo), así que los hechos
aprobados se publican como `api/_hotel.json`. Esta prueba es la que impide que el asistente publicado
responda con datos viejos.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gen-api-hotel.py"
DATA = ROOT / "api" / "_hotel.json"


def test_the_published_hotel_json_matches_the_source():
    result = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_the_published_json_carries_what_the_assistant_needs():
    import json

    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert data["name"] == "Hotel Boutique Bordeluz"
    assert len(data["faqs"]) >= 10, "las respuestas aprobadas viajan al prompt"
    assert any("piscina" in faq["answer"].lower() for faq in data["faqs"])
    assert data["location"], "la ubicación es obligatoria: se muestra antes de preguntar"
    assert data["policies"], "las políticas (check-in, niños, depósito) también"
    assert len(data["rooms"]) >= 10
    assert not any("localhost" in json.dumps(faq) for faq in data["faqs"]), "sin enlaces locales"
