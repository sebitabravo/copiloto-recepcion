"""Vencimiento de los datos del hotel: pasada la fecha de revisión la herramienta falla cerrado (invariante 5).

`data/hotel.yaml` declara `revisar_antes_de` (ISO) por bloque servido por las herramientas; una fecha
pasada devuelve el camino de «sin respuesta» con un motivo, nunca el dato vencido.
"""

import copy
import json
from datetime import date
from types import SimpleNamespace

from conftest import HOTEL_PATH, FakeClock, local_epoch
from copiloto.ai.tools import ToolHooks, ToolRunner
from copiloto.config import Settings
from copiloto.hotel import HotelData

AUDIT_DAY = date(2026, 11, 6)  # fecha del trabajo: las vigencias declaradas deben ser posteriores


def base_raw() -> dict:
    return copy.deepcopy(HotelData.load(HOTEL_PATH).raw)


async def ask_topic(raw: dict, topic: str, question: str | None = None):
    settings = Settings(hotel_data_path=str(HOTEL_PATH))
    hotel = HotelData(raw)
    clock = FakeClock(local_epoch(2026, 11, 6, 12, 0))
    runner = ToolRunner(hotel, None, settings, clock, SimpleNamespace(state={}), ToolHooks())
    args = {"topic": topic}
    if question:
        args["question"] = question
    return await runner.run("get_hotel_info", args)


async def test_future_date_serves_the_block():
    raw = base_raw()
    raw["location"]["revisar_antes_de"] = "2027-06-30"
    result = await ask_topic(raw, "ubicacion")
    assert result.ok and result.data["resumen"].startswith("Estamos en el sector Molco")
    assert "sin_respuesta" not in result.data


async def test_past_date_fails_closed_and_never_returns_the_stale_value():
    raw = base_raw()
    raw["location"]["revisar_antes_de"] = "2020-01-01"
    result = await ask_topic(raw, "ubicacion")
    assert result.data["sin_respuesta"] is True
    assert result.data["motivo"] == "datos_vencidos"
    assert result.data["revisar_antes_de"] == "2020-01-01"
    assert "Molco" not in json.dumps(result.data), "el dato vencido no se entrega ni siquiera de referencia"


async def test_one_expired_room_fails_closed_for_the_whole_room_list():
    raw = base_raw()
    raw["rooms"][0]["revisar_antes_de"] = "2020-01-01"
    result = await ask_topic(raw, "habitaciones")
    assert result.data["sin_respuesta"] is True and result.data["motivo"] == "datos_vencidos"
    assert "doble_con_jacuzzi" not in json.dumps(result.data)


async def test_every_block_the_tools_serve_declares_a_future_review_date():
    data = HotelData.load(HOTEL_PATH)
    for block in ("hotel", "location", "policies", "promotions", "photos"):
        assert date.fromisoformat(str(data.raw[block]["revisar_antes_de"])) > AUDIT_DAY, block
    for items in ("rooms", "services", "faqs"):
        assert data.raw[items], items
        for item in data.raw[items]:
            label = item.get("id") or item.get("name")
            assert date.fromisoformat(str(item["revisar_antes_de"])) > AUDIT_DAY, (items, label)
