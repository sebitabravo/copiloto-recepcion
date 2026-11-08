"""Los perfiles de IA local mergean bien y los topes quedan coherentes.

`docker compose config` resuelve la composición igual que al levantar el stack, así que esta
prueba cubre lo que se rompe en silencio: la imagen (GPU vs CPU), la reserva de GPU, el alias del
modelo contra `LLM_MODEL` y el orden de los topes (una llamada al modelo siempre puede tardar más
que el turno completo).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = ["docker", "compose", "-f", "infra/docker-compose.yml", "--project-directory", "."]
GPU = [*BASE, "-f", "infra/docker-compose.ia.yml"]
CPU = [*GPU, "-f", "infra/docker-compose.ia-cpu.yml"]
ALIAS = "qwen3-4b-instruct-2507"
needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker compose no disponible")


def compose(files, service):
    return subprocess.run([*files, "config", service], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def timeout(out, name):
    return int(out.split(f'{name}: "')[1].split('"')[0])


def command_tokens(out):
    """Los argumentos del servicio `llm`, leídos de la lista `command:` del YAML resuelto."""
    lines = out.splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == "command:")
    tokens = []
    for line in lines[start + 1:]:
        if not line.startswith("      - "):
            break
        tokens.append(line[8:].strip())
    return tokens


@needs_docker
@pytest.mark.parametrize("files, image, gpu", [(GPU, "server-cuda-b12169", True), (CPU, "server-b12169", False)])
def test_llm_profile_merges(files, image, gpu):
    out = compose(files, "llm")
    assert image in out, out
    assert ("deploy:" in out) is gpu, "solo el perfil de GPU reserva el dispositivo"
    tokens = command_tokens(out)
    assert ("-ngl" in tokens) is gpu, tokens
    assert ("-t" in tokens) is not gpu, tokens
    assert f"- {ALIAS}" in out


@needs_docker
@pytest.mark.parametrize("files", [GPU, CPU])
def test_alias_matches_llm_model_and_timeouts_stay_ordered(files):
    copiloto = compose(files, "copiloto")
    assert f"LLM_MODEL: {ALIAS}" in copiloto
    assert "LLM_BASE_URL: http://llm:8080/v1" in copiloto
    assert timeout(copiloto, "LLM_TIMEOUT_S") > timeout(copiloto, "AI_TURN_TIMEOUT_S"), copiloto
    assert f"- {ALIAS}" in compose(files, "llm"), "el alias servido y el configurado deben ser el mismo"


@needs_docker
def test_cpu_profile_raises_the_time_limits():
    gpu_limit = timeout(compose(GPU, "copiloto"), "AI_TURN_TIMEOUT_S")
    cpu_limit = timeout(compose(CPU, "copiloto"), "AI_TURN_TIMEOUT_S")
    assert gpu_limit < cpu_limit
