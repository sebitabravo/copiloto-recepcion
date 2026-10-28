"""Adaptador del PMS. El resto del copiloto solo conoce `PmsAdapter`.

`MockPxsolAdapter` habla con el servicio pms-mock. `PxsolAdapter` es el contrato pendiente para el
PMS real: Pxsol no publica una API; la integración requiere credenciales del hotel y el contrato
del proveedor (fase 2 real de EVA2).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import httpx
from pydantic import BaseModel, Field, ValidationError


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


class _OfferPayload(BaseModel):
    """Contrato de una habitación en la respuesta del PMS. Un valor fuera de rango es un error de contrato."""

    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    max_adults: int = Field(ge=1)
    max_children: int = Field(ge=0)
    m2: float = Field(gt=0)
    available_units: int = Field(ge=0)
    nightly_price_clp: int = Field(ge=0)


class _ReadingPayload(BaseModel):
    read_at: str = Field(min_length=16)
    source: str = Field(min_length=1)
    simulated: bool = False
    room_types: list[_OfferPayload]


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
            payload = _ReadingPayload.model_validate(response.json())
            offers = [RoomOffer(**offer.model_dump()) for offer in payload.room_types]
            return PmsReading(payload.read_at, payload.source, payload.simulated, offers)
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            raise PmsUnavailable(str(exc)) from exc


class PxsolAdapter(PmsAdapter):
    """Stub del PMS real. Contrato esperado: misma firma que `MockPxsolAdapter.availability`,
    lectura de solo consulta y con sello de hora; la confirmación de reservas es siempre humana."""

    async def availability(self, checkin: date, checkout: date, adults: int, children: int) -> PmsReading:
        raise NotImplementedError("Integración Pxsol pendiente: requiere credenciales y contrato del proveedor")
