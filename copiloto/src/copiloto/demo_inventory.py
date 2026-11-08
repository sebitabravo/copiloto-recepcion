"""Inventario de PRUEBA del alojamiento ficticio: lo consulta recepción desde la bandeja de la demo.

Implementa el contrato `PmsAdapter` (lectura fechada, `simulated=True`) a partir de `test_inventory` en
el YAML del alojamiento, sin servicio externo. Fuera de la ventana con datos, o con la caída simulada, falla
con `PmsUnavailable`: la bandeja muestra «cupo desconocido» y nunca lo presenta como confirmado.
No escribe nada: no bloquea cupos ni crea reservas (eso queda para la fase 3, con un PMS real).
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from copiloto.hotel import HotelData
from copiloto.pms import PmsAdapter, PmsReading, PmsUnavailable, RoomOffer


class InventoryPmsAdapter(PmsAdapter):
    def __init__(self, hotel: HotelData, clock: Callable[[], float], timezone: str = "America/Santiago"):
        self.inventory = hotel.raw.get("test_inventory") or {}
        self.rooms = hotel.rooms
        self.clock = clock
        self.tz = ZoneInfo(timezone)
        self.label = str(self.inventory.get("label") or "Inventario de prueba")

    @property
    def configured(self) -> bool:
        return bool(self.inventory)

    def _occupied(self, night: date) -> dict:
        for entry in self.inventory.get("occupied") or []:
            if str(entry.get("date")) == night.isoformat():
                return entry
        return {}

    async def availability(
        self, checkin: date, checkout: date, adults: int, children: int, simulate_down: bool = False
    ) -> PmsReading:
        if simulate_down:
            raise PmsUnavailable("El inventario no respondió (caída simulada)")
        if not self.inventory:
            raise PmsUnavailable("Este alojamiento no tiene inventario de prueba")
        window = self.inventory.get("window") or {}
        start, end = window.get("from"), window.get("to")
        if not start or not end or checkin < _as_date(start) or checkout > _as_date(end) + timedelta(days=1):
            raise PmsUnavailable("Sin dato de inventario para esas fechas: cupo desconocido")
        units = self.inventory.get("units") or {}
        prices = self.inventory.get("nightly_price_clp") or {}
        nights = [checkin + timedelta(days=offset) for offset in range((checkout - checkin).days)]
        offers = []
        for room in self.rooms:
            code = room["code"]
            if room["max_adults"] < adults or room["max_children"] < children or code not in units:
                continue
            free = min(int(units[code]) - int(self._occupied(night).get(code, 0)) for night in nights)
            if free > 0:
                offers.append(
                    RoomOffer(code, room["name"], room["max_adults"], room["max_children"], float(room["m2"]),
                              free, int(prices.get(code, 0)))
                )
        read_at = datetime.fromtimestamp(self.clock(), self.tz).isoformat(timespec="seconds")
        return PmsReading(read_at, self.label, True, offers)


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))
