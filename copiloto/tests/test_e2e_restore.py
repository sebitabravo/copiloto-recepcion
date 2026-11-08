"""El e2e no puede degradar la IA al restaurar: el overlay sigue, el estado se comprueba y el
perfil de CPU conserva sus topes.

`scripts/e2e.py` recrea `copiloto` al terminar cada caso. Si esa recreación pierde el overlay de
IA, la consola vuelve en modo guiado para el resto del día y el e2e lo reporta como PASS.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("e2e_script", ROOT / "scripts" / "e2e.py")
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)


class Calls(list):
    """Guarda el comando y el entorno de cada `docker compose` que el e2e lanza."""

    def record(self, command, **kwargs):
        self.append((command, kwargs.get("env", {})))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")


@pytest.fixture
def runner(monkeypatch):
    calls = Calls()
    monkeypatch.setattr(e2e.subprocess, "run", calls.record)
    monkeypatch.setattr(e2e.Runner, "wait_health", lambda self, url: None)
    runtime = {"CHATWOOT_ACCOUNT_ID": "1", "CHATWOOT_ADMIN_TOKEN": "token", "CHATWOOT_WEBSITE_TOKEN": "web"}
    return e2e.Runner(runtime, e2e.Results()), calls


def test_restore_drops_the_test_shift_and_the_off_mode(runner, monkeypatch):
    r, calls = runner
    r.recreate("copiloto", {"SHIFT_START": "00:00", "SHIFT_END": "00:00", "AI_MODE": "off"})
    r.recreate("copiloto", {"SIMULATE_DOWN": "0"})
    _command, env = calls[-1]
    assert "SHIFT_START" not in env and "SHIFT_END" not in env, env
    assert env.get("AI_MODE") != "off", env


def test_spurious_docker_failure_is_reported_as_failure(runner, monkeypatch):
    """Si la recreación apaga una IA que estaba activa, la restauración falla."""
    r, _calls = runner
    states = iter([True, False])
    monkeypatch.setattr(r, "ai_enabled", lambda: next(states))
    passed = r.restore("copiloto")
    assert passed is False
    assert r.results.rows[-1][2] == "FAIL"


def test_restore_passes_when_the_ai_state_matches(runner, monkeypatch):
    r, _calls = runner
    monkeypatch.setattr(r, "ai_enabled", lambda: True)
    passed = r.restore("copiloto")
    assert passed is True
    assert r.results.rows[-1][2] == "PASS"
