"""Puente entre la API v2 de Beds24 y el contrato del copiloto (docs/conector-pms.md).

Beds24 entrega precio y cupos **por día**; el contrato del copiloto pide una oferta **por tipo de
habitación** para una estadía. Este módulo hace esa traducción y nada más: no escribe reservas.

Referencias: API v2 en https://api.beds24.com/v2, autenticación por refresh token, calendario en
`GET /inventory/rooms/calendar`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

DEFAULT_API = "https://api.beds24.com/v2"


class Beds24Error(Exception):
    """La API de Beds24 respondió algo que el puente no puede usar."""


@dataclass(frozen=True)
class RoomMap:
    """Habitación de Beds24 con el código estable que conoce el copiloto."""

    code: str
    room_id: int
    name: str
    max_adults: int
    max_children: int
    m2: float


def parse_rooms(raw: str) -> list[RoomMap]:
    """Lee BEDS24_ROOMS. Un campo faltante se rechaza al arrancar, no en la primera consulta."""
    try:
        items = json.loads(raw)
    except ValueError as exc:
        raise Beds24Error("BEDS24_ROOMS no es JSON válido") from exc
    if not isinstance(items, list) or not items:
        raise Beds24Error("BEDS24_ROOMS debe ser una lista con al menos una habitación")

    rooms: list[RoomMap] = []
    for item in items:
        try:
            rooms.append(RoomMap(code=str(item["code"]), room_id=int(item["roomId"]), name=str(item["name"]),
                                 max_adults=int(item["max_adults"]), max_children=int(item["max_children"]),
                                 m2=float(item["m2"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise Beds24Error(f"Habitación incompleta en BEDS24_ROOMS: {item!r}") from exc
    return rooms


class Beds24Client:
    """Cliente mínimo: obtiene un token de acceso y lee el calendario por rango de fechas."""

    def __init__(self, access_token: str = "", refresh_token: str = "", base_url: str = DEFAULT_API,
                 timeout_s: float = 10.0, http: httpx.AsyncClient | None = None, clock=time.time):
        self._access = access_token
        self._refresh = refresh_token
        self._base = base_url.rstrip("/")
        self._expires_at = 0.0 if not access_token else float("inf")
        self._http = http or httpx.AsyncClient(timeout=timeout_s)
        self._clock = clock

    async def token(self) -> str:
        if self._access and self._clock() < self._expires_at:
            return self._access
        if not self._refresh:
            if self._access:
                return self._access
            raise Beds24Error("Falta BEDS24_ACCESS_TOKEN o BEDS24_REFRESH_TOKEN")
        response = await self._request(f"{self._base}/authentication/token",
                                       headers={"refreshToken": self._refresh})
        payload = self._payload(response)
        self._access = str(payload["token"])
        # El token de Beds24 dura una hora; se renueva un minuto antes para no fallar en el borde.
        self._expires_at = self._clock() + int(payload.get("expiresIn", 3600)) - 60
        return self._access

    async def calendar(self, room_ids: list[int], start: date, end: date) -> list[dict]:
        token = await self.token()
        params: list[tuple[str, str]] = [("roomId", str(room)) for room in room_ids]
        params += [("startDate", start.isoformat()), ("endDate", end.isoformat()),
                   ("includePrices", "true"), ("includeNumAvail", "true")]
        response = await self._request(f"{self._base}/inventory/rooms/calendar", params=params,
                                       headers={"token": token})
        return list(self._payload(response).get("data") or [])

    async def _request(self, url: str, **kwargs) -> httpx.Response:
        try:
            return await self._http.get(url, headers={"accept": "application/json", **kwargs.pop("headers", {})},
                                        **kwargs)
        except httpx.HTTPError as exc:
            raise Beds24Error(f"Beds24 no respondió: {type(exc).__name__}") from exc

    @staticmethod
    def _payload(response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise Beds24Error("Beds24 no devolvió JSON") from exc
        if response.status_code >= 400 or payload.get("success") is False:
            raise Beds24Error(f"Beds24 respondió {response.status_code}: {payload.get('error') or payload}")
        return payload


def stay_offers(rooms: list[RoomMap], days: list[dict], checkin: date, checkout: date, *,
                clp_rate: float = 1.0) -> list[dict]:
    """Convierte filas por día en ofertas por habitación.

    - Cupo: el mínimo de las noches; si falta una noche o alguna está cerrada, no hay oferta.
    - Precio: el promedio de las noches, redondeado. El copiloto multiplica por noches, así que el
      total de la estadía queda correcto aunque la tarifa varíe.
    """
    by_room: dict[int, dict[str, dict]] = {}
    for row in days:
        try:
            room_id = int(row["roomId"])
            night = date.fromisoformat(str(row["date"]))
        except (KeyError, TypeError, ValueError):
            continue
        by_room.setdefault(room_id, {})[night.isoformat()] = row

    nights = [(checkin.fromordinal(checkin.toordinal() + offset)).isoformat()
              for offset in range((checkout - checkin).days)]

    offers: list[dict] = []
    for room in rooms:
        rows = by_room.get(room.room_id, {})
        if any(night not in rows for night in nights):
            continue
        units = [int(rows[night].get("numAvail") or 0) for night in nights]
        prices = [float(rows[night].get("price1") or 0) for night in nights]
        if min(units) <= 0 or min(prices) <= 0:
            continue
        offers.append({
            "code": room.code,
            "name": room.name,
            "max_adults": room.max_adults,
            "max_children": room.max_children,
            "m2": room.m2,
            "available_units": min(units),
            "nightly_price_clp": round(sum(prices) / len(prices) * clp_rate),
        })
    return sorted(offers, key=lambda offer: offer["nightly_price_clp"])


def read_at(now: datetime, timezone: str) -> str:
    """Sello de la lectura con zona, como lo exige el contrato."""
    return now.astimezone(ZoneInfo(timezone)).isoformat(timespec="seconds")
