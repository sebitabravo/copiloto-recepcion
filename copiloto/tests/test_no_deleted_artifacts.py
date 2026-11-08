"""Nada del repositorio apunta a artefactos que ya no existen.

Cuando se retiraron los puentes (WhatsApp y Beds24) y el modelo local quedaron referencias sueltas en
el CI, el Makefile, los scripts y la documentación. Estas pruebas fijan que no vuelvan: un enlace o un
comando roto se descubre en CI, no al presentar.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ELIMINADOS = (
    "wa_bridge", "pms_bridge", "docker-compose.ia.yml", "docker-compose.ia-cpu.yml",
    "local-model.sh", "model_eval.py", "wa-e2e.sh", "wa-session.sh", "beds24_check.py",
    "docs/conector-pms.md", "docs/whatsapp-demo.md", "docs/ia-local.md",
)
# odd/ y el registro de iteraciones son historia: describen lo que hubo, no lo que hay. Esta propia
# prueba nombra los artefactos retirados: es su lista, no una referencia rota.
PERMITIDOS = ("odd/", "docs/eva3/", "copiloto/tests/test_no_deleted_artifacts.py")
ARCHIVOS = ("Makefile", "README.md", ".env.example", ".github/workflows/ci.yml",
            "infra/docker-compose.yml", "infra/bootstrap/seed.rb")


def rutas():
    encontrados = [ROOT / nombre for nombre in ARCHIVOS]
    encontrados += sorted((ROOT / "docs").rglob("*.md"))
    encontrados += sorted((ROOT / "scripts").glob("*"))
    encontrados += sorted((ROOT / "copiloto/src/copiloto").rglob("*.py"))
    encontrados += sorted((ROOT / "copiloto/tests").glob("*.py"))
    return encontrados


@pytest.mark.parametrize("nombre", ELIMINADOS)
def test_no_quedan_referencias_a_lo_eliminado(nombre):
    culpables = []
    for path in rutas():
        if not path.is_file() or path.suffix in {".pyc", ".lock"}:
            continue
        relativo = path.relative_to(ROOT).as_posix()
        if relativo.startswith(PERMITIDOS):
            continue
        try:
            texto = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if nombre in texto:
            culpables.append(relativo)
    assert culpables == [], f"{nombre} sigue citado en {culpables}"


def test_el_compose_ya_no_declara_los_servicios_retirados():
    compose = yaml.safe_load((ROOT / "infra/docker-compose.yml").read_text(encoding="utf-8"))
    servicios = set(compose["services"])
    assert {"landing", "copiloto", "pms-mock"} <= servicios
    for retirado in ("wa-bridge", "openwa", "beds24-bridge", "llm"):
        assert retirado not in servicios, retirado
    volumenes = set(compose.get("volumes", {}))
    assert not volumenes & {"openwa_data", "wa_bridge_state", "llm_models"}


def test_el_seed_no_lee_variables_de_los_puentes():
    seed = (ROOT / "infra/bootstrap/seed.rb").read_text(encoding="utf-8")
    assert "wa_inbox" not in seed and "WA_BRIDGE" not in seed
