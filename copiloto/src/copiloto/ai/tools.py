"""Herramientas del asistente. El modelo propone argumentos; este módulo los valida y ejecuta.

Nada de lo que diga el modelo se toma como cierto: las fechas, la capacidad, el tipo de habitación y la
disponibilidad previa se vuelven a comprobar aquí antes de leer o escribir en el PMS.
"""

import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

from copiloto.ai.sessions import AiSession
from copiloto.config import Settings
from copiloto.hotel import HotelData
from copiloto.pms import PmsAdapter, PmsConflict, PmsUnavailable

MAX_NIGHTS = 30
MAX_BOOKINGS_PER_SESSION = 2
GUEST_NAME = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ'.\- ]{2,79}$")
TOPICS = ["ubicacion", "habitaciones", "servicios", "politicas", "promociones", "contacto", "faq"]

LABELS = {
    "get_hotel_info": "Consultando información del hotel",
    "check_availability": "Consultando disponibilidad en el PMS",
    "create_booking": "Creando la reserva en el PMS simulado",
    "handoff_to_human": "Avisando a una persona de recepción",
}


@dataclass
class ToolResult:
    ok: bool
    data: dict
    summary: str
    event: dict | None = None


@dataclass
class ToolHooks:
    """Efectos que dependen del canal (Chatwoot o demo web). Todos son opcionales."""

    conversation_id: int | None = None
    in_shift: bool = True
    on_availability: Callable[[dict], Awaitable[None]] | None = None
    on_booking: Callable[[dict], Awaitable[None]] | None = None
    handoff: Callable[[str], Awaitable[dict]] | None = None
    record: Callable[[str, dict], None] | None = None
    extra: dict = field(default_factory=dict)


def tool_specs(mode: str) -> list[dict]:
    def spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False}}}

    specs = [
        spec("get_hotel_info", "Entrega datos verificados del hotel. Úsala para cualquier dato del hotel.",
             {"topic": {"type": "string", "enum": TOPICS, "description": "Tema a consultar"},
              "question": {"type": "string", "description": "Solo para topic=faq: la pregunta del huésped"}},
             ["topic"]),
        spec("check_availability", "Lee la disponibilidad y los precios simulados del PMS para unas fechas y "
             "una cantidad de huéspedes. Devuelve opciones con hora de lectura.",
             {"checkin": {"type": "string", "description": "Entrada, formato AAAA-MM-DD"},
              "checkout": {"type": "string", "description": "Salida, formato AAAA-MM-DD"},
              "adults": {"type": "integer", "minimum": 1, "maximum": 4},
              "children": {"type": "integer", "minimum": 0, "maximum": 3}},
             ["checkin", "checkout", "adults", "children"]),
        spec("handoff_to_human", "Deriva la conversación a una persona de recepción con el contexto reunido.",
             {"reason": {"type": "string", "description": "Motivo breve del traspaso"}}, ["reason"]),
    ]
    if mode == "full":
        specs.insert(2, spec(
            "create_booking", "Crea la reserva en el PMS simulado. Solo después de check_availability con los "
            "mismos datos, de repetir el resumen y de recibir un «sí» explícito del huésped.",
            {"guest_name": {"type": "string", "description": "Nombre y apellido del huésped"},
             "room_code": {"type": "string", "description": "Código de una opción devuelta por check_availability"},
             "checkin": {"type": "string"}, "checkout": {"type": "string"},
             "adults": {"type": "integer"}, "children": {"type": "integer"},
             "guest_confirmed": {"type": "boolean", "description": "true solo si el huésped dijo sí al resumen"}},
            ["guest_name", "room_code", "checkin", "checkout", "adults", "children", "guest_confirmed"]))
    return specs


def _date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _read_label(read_at: str) -> str:
    if len(read_at) < 16:
        return read_at
    year, month, day = read_at[:10].split("-")
    return f"{day}-{month}-{year} {read_at[11:16]}"


class ToolRunner:
    def __init__(self, hotel: HotelData, pms: PmsAdapter, settings: Settings, clock: Callable[[], float],
                 session: AiSession, hooks: ToolHooks):
        self.hotel, self.pms, self.settings, self.clock = hotel, pms, settings, clock
        self.session, self.hooks = session, hooks

    def today(self) -> date:
        return self.settings.local(self.clock()).date()

    async def run(self, name: str, args: dict) -> ToolResult:
        handler = {"get_hotel_info": self._hotel_info, "check_availability": self._availability,
                   "create_booking": self._booking, "handoff_to_human": self._handoff}.get(name)
        if handler is None or (name == "create_booking" and not self.settings.autonomous_booking):
            return ToolResult(False, {"error": "herramienta_no_disponible"}, "Herramienta no disponible")
        return await handler(args)

    # ---------- información del hotel ----------

    async def _hotel_info(self, args: dict) -> ToolResult:
        topic = args.get("topic")
        hotel = self.hotel
        if topic == "ubicacion":
            self.session.state["seen_location"] = True
            loc = hotel.location
            data = {"resumen": loc["headline"], "detalle": loc["detail"], "direccion": hotel.hotel["address"],
                    "mapa": hotel.hotel["maps_url"], "distancias": loc["distances"],
                    "por_validar": [c["detail"] for c in hotel.hotel.get("conflicts", [])]}
        elif topic == "habitaciones":
            data = {"tipos": [{"codigo": r["code"], "nombre": r["name"], "m2": r["m2"], "max_adultos": r["max_adults"],
                               "max_ninos": r["max_children"], "incluye": r["amenities"][:4]} for r in hotel.rooms],
                    "fotos": hotel.photos["rooms_url"], "galeria": hotel.photos["gallery_url"],
                    "nota": "Todas incluyen desayuno continental y piscina temperada; las tinajas cuestan aparte."}
        elif topic == "servicios":
            data = {"servicios": hotel.raw["services"]}
        elif topic == "politicas":
            data = {k: v for k, v in hotel.policies.items() if k not in ("source", "status")}
        elif topic == "promociones":
            data = {"promociones": hotel.raw["promotions"]["items"],
                    "nota": "Vigencia y cupos los confirma recepción."}
        elif topic == "contacto":
            data = {"whatsapp": hotel.hotel["whatsapp"], "email": hotel.hotel["email"]}
        elif topic == "faq":
            faq = hotel.match_faq(str(args.get("question") or ""))
            if faq:
                data = {"respuesta": faq.answer, "verificado": faq.status == "verificado", "tema": faq.label}
            else:
                data = {"sin_respuesta": True, "temas_disponibles": [f.label for f in hotel.faqs],
                        "instruccion": "Dile que no tienes ese dato y ofrece derivar a recepción."}
        else:
            return ToolResult(False, {"error": "tema_invalido", "temas": TOPICS}, "Tema no reconocido")
        return ToolResult(True, data, f"Información: {topic}")

    # ---------- disponibilidad ----------

    async def _availability(self, args: dict) -> ToolResult:
        checkin, checkout = _date(args.get("checkin")), _date(args.get("checkout"))
        adults, children = _int(args.get("adults")), _int(args.get("children"))
        error = self._validate_stay(checkin, checkout, adults, children)
        if error:
            return ToolResult(False, {"error": error}, error)
        started = time.monotonic()
        try:
            reading = await self.pms.availability(checkin, checkout, adults, children)
        except PmsUnavailable:
            self._record("pms_read", {"ok": False, "latency_ms": 0})
            return ToolResult(False, {"error": "pms_no_disponible",
                                      "instruccion": "No afirmes disponibilidad. Dile que recepción verificará cupos "
                                                     "y usa handoff_to_human."}, "El PMS no responde")
        self._record("pms_read", {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)})
        nights = (checkout - checkin).days
        options = sorted(reading.offers, key=lambda o: o.nightly_price_clp)[:6]
        info = {"checkin": checkin.isoformat(), "checkout": checkout.isoformat(), "adults": adults,
                "children": children, "read_at": reading.read_at, "read_label": _read_label(reading.read_at),
                "simulated": reading.simulated,
                "options": {o.code: {"name": o.name, "price": o.nightly_price_clp, "units": o.available_units}
                            for o in options}, "ts": self.clock()}
        self.session.state["last_availability"] = info
        if self.hooks.on_availability:
            await self.hooks.on_availability(info)
        data = {"lectura_pms": info["read_label"], "simulado": reading.simulated, "noches": nights,
                "opciones": [{"codigo": o.code, "nombre": o.name, "m2": o.m2, "cupos": o.available_units,
                              "precio_noche_clp": o.nightly_price_clp, "total_clp": o.nightly_price_clp * nights}
                             for o in options],
                "nota": "Lectura fechada: puede cambiar. Los precios y cupos son simulados."}
        if not options:
            data["instruccion"] = "No hay cupo para esas fechas y personas. Ofrece otras fechas o handoff_to_human."
        return ToolResult(True, data, f"{len(options)} tipo(s) de habitación disponibles" if options
                          else "Sin cupo para esas fechas")

    def _validate_stay(self, checkin: date | None, checkout: date | None, adults: int | None,
                       children: int | None) -> str | None:
        if checkin is None or checkout is None:
            return "Las fechas deben venir como AAAA-MM-DD."
        if checkin < self.today():
            return "La fecha de entrada ya pasó: pide fechas desde hoy en adelante."
        if checkout <= checkin:
            return "La salida debe ser posterior a la entrada."
        if (checkout - checkin).days > MAX_NIGHTS:
            return f"Por ahora la demo acepta estadías de hasta {MAX_NIGHTS} noches."
        if adults is None or children is None or not 1 <= adults <= 4 or not 0 <= children <= 3:
            return "Adultos entre 1 y 4 y niños entre 0 y 3."
        return None

    # ---------- reserva ----------

    async def _booking(self, args: dict) -> ToolResult:
        if args.get("guest_confirmed") is not True:
            return ToolResult(False, {"error": "falta_confirmacion_del_huesped",
                                      "instruccion": "Repite el resumen y pide un sí explícito."},
                              "Falta el sí del huésped")
        name = str(args.get("guest_name") or "").strip()
        if not GUEST_NAME.match(name) or len(name.split()) < 2:
            return ToolResult(False, {"error": "nombre_invalido",
                                      "instruccion": "Pide nombre y apellido, solo letras."}, "Nombre inválido")
        checkin, checkout = _date(args.get("checkin")), _date(args.get("checkout"))
        adults, children = _int(args.get("adults")), _int(args.get("children"))
        error = self._validate_stay(checkin, checkout, adults, children)
        if error:
            return ToolResult(False, {"error": error}, error)
        last = self.session.state.get("last_availability")
        room_code = str(args.get("room_code") or "")
        fresh = last and self.clock() - last["ts"] <= self.settings.prebooking_minutes * 60
        same = last and (last["checkin"], last["checkout"], last["adults"], last["children"]) == (
            checkin.isoformat(), checkout.isoformat(), adults, children)
        if not (fresh and same):
            return ToolResult(False, {"error": "sin_lectura_vigente",
                                      "instruccion": "Primero llama check_availability con esos mismos datos "
                                                     "y elige una opción de la lista."}, "Falta una lectura vigente")
        if room_code not in last["options"]:
            return ToolResult(False, {"error": "habitacion_no_ofrecida", "opciones_vigentes": list(last["options"]),
                                      "instruccion": "Esa habitación no está entre las opciones disponibles para "
                                                     "esas fechas. Ofrece una de las opciones vigentes."},
                              "Esa habitación no está disponible para esas fechas")
        for made in self.session.state.get("bookings", []):
            if (made["guest_name"], made["room_code"], made["checkin"], made["checkout"]) == (
                    name, room_code, checkin.isoformat(), checkout.isoformat()):
                return ToolResult(True, {**made, "ya_existia": True}, f"Reserva #{made['booking_id']} ya creada")
        if len(self.session.state.get("bookings", [])) >= MAX_BOOKINGS_PER_SESSION:
            return ToolResult(False, {"error": "limite_de_la_demo"}, "Límite de reservas de la demo")
        try:
            created = await self.pms.book(name, room_code, checkin, checkout, adults, children,
                                          self.hooks.conversation_id)
        except PmsConflict:
            return ToolResult(False, {"error": "sin_cupo", "instruccion": "Ya no hay cupo: vuelve a consultar "
                                                                         "disponibilidad y ofrece alternativas."},
                              "El PMS rechazó la reserva (sin cupo)")
        except (PmsUnavailable, NotImplementedError):
            return ToolResult(False, {"error": "pms_no_disponible", "instruccion": "No afirmes que hay reserva; "
                                                                                   "usa handoff_to_human."},
                              "El PMS no respondió")
        room = self.hotel.room(room_code) or {}
        price = last["options"][room_code]["price"]
        nights = (checkout - checkin).days
        booking = {"booking_id": created["booking_id"], "guest_name": name, "room_code": room_code,
                   "room_name": room.get("name", room_code).removeprefix("Habitación "),
                   "checkin": checkin.isoformat(), "checkout": checkout.isoformat(), "nights": nights,
                   "adults": adults, "children": children, "total_clp": price * nights}
        self.session.state.setdefault("bookings", []).append(booking)
        if self.hooks.on_booking:
            await self.hooks.on_booking(booking)
        event = {"type": "booking_created", **{k: booking[k] for k in (
            "booking_id", "room_name", "checkin", "checkout", "nights", "adults", "children", "total_clp")},
                 "simulated": True}
        return ToolResult(True, booking, f"Reserva #{booking['booking_id']} creada", event)

    # ---------- traspaso ----------

    async def _handoff(self, args: dict) -> ToolResult:
        reason = str(args.get("reason") or "Solicitud del huésped")[:200]
        if self.hooks.handoff:
            data = await self.hooks.handoff(reason)
        else:
            data = {"avisado": True, "simulado": True}
        data.setdefault("en_horario", self.hooks.in_shift)
        data.setdefault("horario_recepcion", f"{self.settings.shift_start} a {self.settings.shift_end}")
        return ToolResult(True, data, "Se avisó a recepción", {"type": "handoff", "reason": reason,
                                                               "simulated": self.hooks.conversation_id is None})

    def _record(self, kind: str, payload: dict) -> None:
        if self.hooks.record:
            self.hooks.record(kind, payload)
