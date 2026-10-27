"""Adaptador del PMS. El resto del copiloto solo conoce `PmsAdapter`.

`MockPxsolAdapter` habla con el servicio pms-mock. `PxsolAdapter` es el contrato pendiente para el
PMS real: Pxsol no publica una API; la integración requiere credenciales del hotel y el contrato
del proveedor (fase 2 real de EVA2).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import httpx


class PmsUnavailable(Exception):
    """El PMS no respondió o respondió con error; el bot no debe afirmar disponibilidad."""


@dataclass(frozen=True)
class RoomOffer:
    code: str
    name: str
    max_adults: int
    max_children: int
    m2: float
    available_units: int
    nightly_price_clp: int


@dataclass(frozen=True)
class PmsReading:
    read_at: str
    source: str
    simulated: bool
    offers: list[RoomOffer]


class PmsAdapter(ABC):
    @abstractmethod
    async def availability(self, checkin: date, checkout: date, adults: int, children: int) -> PmsReading:
        """Lectura fechada de disponibilidad. Debe lanzar `PmsUnavailable` ante cualquier falla."""


class MockPxsolAdapter(PmsAdapter):
    def __init__(self, base_url: str, timeout_s: float = 4.0, http: httpx.AsyncClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=timeout_s)

    async def availability(self, checkin: date, checkout: date, adults: int, children: int) -> PmsReading:
        params = {"checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
                  "adults": adults, "children": children}
        try:
            response = await self._http.get(f"{self._base_url}/api/v1/availability", params=params)
            response.raise_for_status()
            body = response.json()
            offers = [RoomOffer(**{key: item[key] for key in RoomOffer.__dataclass_fields__})
                      for item in body["room_types"]]
            return PmsReading(body["read_at"], body["source"], bool(body.get("simulated", False)), offers)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise PmsUnavailable(str(exc)) from exc


class PxsolAdapter(PmsAdapter):
    """Stub del PMS real. Contrato esperado: misma firma que `MockPxsolAdapter.availability`,
    lectura de solo consulta y con sello de hora; la confirmación de reservas es siempre humana."""

    async def availability(self, checkin: date, checkout: date, adults: int, children: int) -> PmsReading:
        raise NotImplementedError("Integración Pxsol pendiente: requiere credenciales y contrato del proveedor")
