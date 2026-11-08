"""Corridas aisladas de la demo e inventario de prueba separado.

- El servidor emite la corrida; el huésped y la recepción de una corrida comparten el caso, y otra corrida no lo
  ve (lista, detalle, tomar, responder, cerrar, inventario, resumen del turno ni métricas).
- El operador tiene un id estable (llave del navegador + corrida, firmado por el servidor): el nombre es solo una
  etiqueta. Dos «Sofía» en corridas distintas no se ven; en la misma corrida no responden casos de la otra.
- La demo lee SU inventario de prueba: un adaptador operativo instrumentado recibe cero llamadas. Sin inventario
  de prueba configurado (o caído) la demo dice «Disponibilidad por verificar» y la solicitud entra igual.
"""

from dataclasses import replace

import pytest
from conftest import DEMO_SESSION, FakeChatwoot, FakePms, new_run, staff_login
from copiloto.app import create_app
from copiloto.config import Settings
from copiloto.pms import DemoPmsUnconfigured, HttpPmsAdapter, build_demo_pms_adapter
from fastapi.testclient import TestClient
from test_demo_requests import REPLY, canonical

from copiloto import app as app_module
from copiloto import store


def guest_says(demo, text, run, session):
    demo.clock.advance(3)
    response = demo.guest.post("/api/demo/chat", json={"session_id": session, "message": text, "run": run})
    assert response.status_code == 200, response.text
    return response.json()


def requests_of(client):
    return client.get("/api/panel/requests").json()["requests"]


# ---------- corridas ----------

def test_two_sofias_in_different_runs_never_see_each_other(demo):
    demo.say("Hablar con recepción")
    [mine] = requests_of(demo.sofia)
    other_run = new_run(demo.guest)
    other_sofia = demo.staff("Sofía", key="operadora-sofia-9999", run=other_run)
    guest_says(demo, "Hablar con recepción", other_run, "eva3-huesped-otra-corrida-01")
    [theirs] = requests_of(other_sofia)
    assert theirs["id"] != mine["id"]
    assert [item["id"] for item in requests_of(demo.sofia)] == [mine["id"]], "cada corrida ve solo sus casos"
    for path in ("", "/take", "/inventory", "/close"):
        method = other_sofia.get if path == "" else other_sofia.post
        assert method(f"/api/panel/requests/{mine['id']}{path}").status_code == 404, path or "detalle"
    reply = other_sofia.post(f"/api/panel/requests/{mine['id']}/reply", json={"body": REPLY})
    assert reply.status_code == 404
    selected = other_sofia.get("/api/panel/requests", params={"selected": mine["id"]}).json()["selected"]
    assert selected is None, "pedir el detalle por id tampoco cruza de corrida"
    assert other_sofia.get(f"/api/panel/{mine['conversation_id']}").status_code == 404
    demo.clock.advance(1)  # la ventana del resumen es [desde, ahora): el traspaso ocurrió en el segundo anterior
    assert other_sofia.get("/api/panel/shift").json()["handoffs"] == 1, "su resumen cuenta solo su corrida"
    assert demo.sofia.get("/api/panel/shift").json()["handoffs"] == 1
    assert other_sofia.get("/metricas/data.json").json()["commercial_started_in_shift"] == 1


def test_guest_and_reception_of_the_same_run_share_the_case(demo):
    body = demo.say("Hablar con recepción")
    [item] = requests_of(demo.sofia)
    assert item["code"] == body["request"]["code"]
    assert demo.sofia.post(f"/api/panel/requests/{item['id']}/take").status_code == 200
    assert demo.sofia.post(f"/api/panel/requests/{item['id']}/reply", json={"body": REPLY}).status_code == 200
    seen = demo.guest.get("/api/demo/conversation",
                          params={"session_id": DEMO_SESSION, "run": demo.run}).json()
    assert seen["messages"][-1]["body"] == REPLY and seen["request"]["status"] == "respondida"


def test_two_sofias_in_the_same_run_are_two_operators(demo):
    demo.say("Hablar con recepción")
    [item] = requests_of(demo.sofia)
    assert demo.sofia.post(f"/api/panel/requests/{item['id']}/take").status_code == 200
    namesake = demo.staff("Sofía", key="operadora-sofia-0002")
    detail = namesake.get(f"/api/panel/requests/{item['id']}").json()
    assert detail["assignee"] == "Sofía" and detail["mine"] is False
    assert detail["actions"]["reply"] is False and detail["actions"]["close"] is False
    assert namesake.post(f"/api/panel/requests/{item['id']}/reply", json={"body": REPLY}).status_code == 409
    assert namesake.post(f"/api/panel/requests/{item['id']}/close").status_code == 409
    # La misma persona (misma llave) que vuelve a entrar conserva sus casos: el id no depende de la sesión.
    staff_login(demo.sofia, "Sofía", demo.run, key="operadora-sofia-0001")
    assert demo.sofia.get(f"/api/panel/requests/{item['id']}").json()["mine"] is True
    assert demo.sofia.post(f"/api/panel/requests/{item['id']}/reply", json={"body": REPLY}).status_code == 200


def test_a_guest_session_never_changes_run(demo):
    demo.say("¿Dónde queda el hotel?")
    other_run = new_run(demo.guest)
    moved = demo.guest.post("/api/demo/chat",
                            json={"session_id": DEMO_SESSION, "message": "Hola", "run": other_run})
    assert moved.status_code == 409
    peek = demo.guest.get("/api/demo/conversation", params={"session_id": DEMO_SESSION, "run": other_run}).json()
    assert peek["messages"] == [] and peek["conversation_id"] is None, "no se confirma ni que exista"


def test_invented_or_expired_runs_are_refused(demo, settings):
    invented = "corrida-inventada-0001"
    chat = demo.guest.post("/api/demo/chat", json={"session_id": "eva3-huesped-inventada", "message": "Hola",
                                                   "run": invented})
    assert chat.status_code == 404
    assert demo.guest.post("/api/demo/session", json={"name": "Sofía", "run": invented}).status_code == 404
    assert demo.guest.get(f"/api/demo/run/{demo.run}").status_code == 200
    demo.clock.advance(settings.demo_session_ttl_s + 60)
    assert demo.guest.get(f"/api/demo/run/{demo.run}").status_code == 404, "la corrida vence sin actividad"


def test_a_cookie_from_another_run_does_not_open_this_run(demo):
    demo.say("Hablar con recepción")
    other_run = new_run(demo.guest)
    response = demo.sofia.get("/api/panel/requests", headers={"X-Demo-Run": other_run})
    assert response.status_code == 401, "otra pestaña con otra corrida vuelve a entrar en vez de ver ajenos"
    assert demo.sofia.get("/api/panel/requests", headers={"X-Demo-Run": demo.run}).status_code == 200


def test_a_session_without_run_sees_no_case(demo):
    demo.say("Hablar con recepción")
    anonymous = TestClient(demo.app)
    assert anonymous.post("/api/demo/session", json={"name": "Sofía"}).status_code == 204
    assert requests_of(anonymous) == []
    assert anonymous.get("/api/panel/queue").json()["conversations"] == []


def test_run_creation_is_capped(settings, harness, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_RUNS_PER_HOUR", 2)
    client = TestClient(create_app(replace(settings, demo_ai=False), chatwoot=FakeChatwoot(), pms=harness.pms,
                                   demo_pms=harness.pms, clock=harness.clock, run_workers=False, db=harness.db))
    first, second = client.post("/api/demo/run").json()["run"], client.post("/api/demo/run").json()["run"]
    assert first != second and len(first) >= 16
    blocked = client.post("/api/demo/run")
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


# ---------- inventario de prueba ----------

class OperationalPms(FakePms):
    """PMS de la operación instrumentado: la demo no debe llamarlo nunca."""


@pytest.fixture
def split(settings, harness, demo):
    operational, test_inventory = OperationalPms(), FakePms()
    app = create_app(replace(settings, demo_ai=False), chatwoot=FakeChatwoot(), pms=operational,
                     demo_pms=test_inventory, clock=demo.clock, run_workers=False, db=harness.db)
    demo.app, demo.guest, demo.sofia = app, TestClient(app), TestClient(app)
    demo.run = new_run(demo.guest)
    staff_login(demo.sofia, "Sofía", demo.run, key="operadora-sofia-0001")
    return operational, test_inventory


def test_the_demo_never_calls_the_operational_pms(demo, split):
    operational, test_inventory = split
    sent = canonical(demo)
    assert "Disponible según lectura del PMS" in "\n".join(m["body"] for m in sent["messages"]) or test_inventory.calls
    [item] = requests_of(demo.sofia)
    demo.sofia.post(f"/api/panel/requests/{item['id']}/take")
    assert demo.sofia.post(f"/api/panel/requests/{item['id']}/inventory", json={}).json()["ok"] is True
    assert operational.calls == 0, "ni el resumen ni la bandeja de la demo leen el PMS de la operación"
    assert test_inventory.calls >= 2


def test_without_a_test_inventory_the_demo_says_availability_pending_and_still_hands_off(demo, settings, harness):
    real_hotel = replace(settings, demo_ai=False, pms_url="https://pms.hotel-real.example", demo_pms_url="")
    operational = OperationalPms()
    app = create_app(real_hotel, chatwoot=FakeChatwoot(), pms=operational, clock=demo.clock, run_workers=False,
                     db=harness.db)
    demo.app, demo.guest, demo.sofia = app, TestClient(app), TestClient(app)
    demo.run = new_run(demo.guest)
    staff_login(demo.sofia, "Sofía", demo.run, key="operadora-sofia-0001")
    demo.say("Consultar fechas")
    demo.say("20–22 nov · 2 adultos")
    summary = demo.say("Sin niños")
    assert "Disponibilidad por verificar" in summary["reply"] and "Disponible según" not in summary["reply"]
    sent = demo.say("Enviar a recepción")
    assert sent["request"] is not None and sent["handled_by"] == "recepcion", "la solicitud entra igual"
    [item] = requests_of(demo.sofia)
    demo.sofia.post(f"/api/panel/requests/{item['id']}/take")
    reading = demo.sofia.post(f"/api/panel/requests/{item['id']}/inventory", json={}).json()
    assert reading["ok"] is False and reading["label"] == "Disponibilidad por verificar"
    assert operational.calls == 0


def test_the_demo_adapter_is_its_own_instance_and_never_carries_the_token_elsewhere():
    sandbox = replace(Settings(), pms_url="http://localhost:8200", pms_staff_token="token-de-personal-1234")
    adapter = build_demo_pms_adapter(sandbox)
    assert isinstance(adapter, HttpPmsAdapter)
    foreign = build_demo_pms_adapter(replace(sandbox, demo_pms_url="https://otro-inventario.example"))
    assert isinstance(foreign, HttpPmsAdapter) and not foreign._staff_token, "el token solo va al PMS simulado"
    real = build_demo_pms_adapter(replace(sandbox, pms_url="https://pms.hotel-real.example"))
    assert isinstance(real, DemoPmsUnconfigured), "un PMS real nunca es el inventario de la demo"
    assert store.DEMO_SOURCE == "demo"
