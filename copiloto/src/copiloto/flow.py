"""Máquina de estados determinista del copiloto (sin LLM).

Flujo: saludo + aviso de privacidad → ubicación → menú → FAQ | fechas y huéspedes → lectura del PMS
→ traspaso a recepción. El bot nunca confirma una reserva: solo muestra lecturas fechadas del PMS y
deja una pre-información para que una persona valide.
"""

import asyncio
import logging
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from copiloto import store
from copiloto.chatwoot import ChatwootClient
from copiloto.config import Settings
from copiloto.events import mark_processed, record_event
from copiloto.hotel import Faq, HotelData
from copiloto.pms import PmsAdapter, PmsReading, PmsUnavailable, RoomOffer
from copiloto.textutil import normalize, parse_count, parse_guests, parse_stay

logger = logging.getLogger(__name__)

WEB_WIDGET = "Channel::WebWidget"
MENU_OPTIONS = [
    ("Ubicación", "ubicacion"),
    ("Habitaciones y fotos", "habitaciones"),
    ("Disponibilidad", "disponibilidad"),
    ("Servicios y preguntas", "faq"),
    ("Hablar con recepción", "recepcion"),
]
GREETING_WORDS = {"hola", "holi", "buenas", "buenos dias", "buenas tardes", "buenas noches", "hello", "hi",
                  "ola", "alo", "saludos", "buen dia"}
HUMAN_TERMS = ("recepcion", "humano", "persona", "agente", "ejecutivo", "operador", "hablar con alguien")
COMMERCIAL_TERMS = ("reservar", "reserva", "disponibilidad", "disponible", "cotizar", "cotizacion", "precio",
                    "precios", "tarifa", "tarifas", "cupo", "cupos", "cuanto cuesta", "quiero una habitacion",
                    "necesito una habitacion", "pieza", "alojar", "alojamiento")
PHOTO_TERMS = ("foto", "fotos", "galeria", "imagenes", "habitaciones", "tipos de habitacion")
LOCATION_TERMS = ("ubicacion", "donde", "direccion", "como llegar", "mapa", "llegar", "queda")
MAX_ADULTS = 4
MAX_CHILDREN = 3


@dataclass
class Context:
    conversation_id: int
    text: str
    plain: str
    channel: str
    now: float
    state: store.ConversationState


def money(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


class Copiloto:
    def __init__(self, settings: Settings, hotel: HotelData, db: sqlite3.Connection, chatwoot: ChatwootClient,
                 pms: PmsAdapter, clock: Callable[[], float] = time.time):
        self.settings = settings
        self.hotel = hotel
        self.db = db
        self.chatwoot = chatwoot
        self.pms = pms
        self.clock = clock
        self._locks: dict[int, asyncio.Lock] = {}

    # ---------- entrada de webhooks ----------

    async def handle_webhook(self, event: dict) -> None:
        try:
            if event.get("event") == "message_created":
                await self._on_message(event)
        except Exception:
            logger.exception("Falla procesando webhook %s", event.get("event"))

    @staticmethod
    def _message_type(event: dict) -> str:
        raw = event.get("message_type")
        return {0: "incoming", 1: "outgoing", 2: "activity", 3: "template"}.get(raw, raw)

    @staticmethod
    def _sender_type(event: dict) -> str:
        sender = event.get("sender") or {}
        return str(sender.get("type") or event.get("sender_type") or "").lower()

    async def _on_message(self, event: dict) -> None:
        message_type = self._message_type(event)
        conversation = event.get("conversation") or {}
        conversation_id = conversation.get("id") or event.get("conversation_id")
        if conversation_id is None or event.get("private"):
            return
        now = self.clock()
        if message_type == "incoming":
            if conversation.get("status") != "pending" or not (event.get("content") or "").strip():
                return
            if not mark_processed(self.db, f"msg:{event['id']}", now):
                return
            sender = event.get("sender") or {}
            async with self._lock(conversation_id):
                await self._guest_message(conversation_id, event["content"].strip(),
                                          conversation.get("channel") or WEB_WIDGET, sender.get("name"), now)
        elif message_type == "outgoing" and self._sender_type(event) in {"user", "agent"}:
            if mark_processed(self.db, f"msg:{event['id']}", now):
                self.on_human_reply(conversation_id, (event.get("sender") or {}).get("id"), now)

    def _lock(self, conversation_id: int) -> asyncio.Lock:
        return self._locks.setdefault(conversation_id, asyncio.Lock())

    # ---------- mensajes del huésped ----------

    async def _guest_message(self, conversation_id: int, text: str, channel: str, contact_name: str | None,
                             now: float) -> None:
        state = store.get_state(self.db, conversation_id)
        if contact_name and not state.contact_name:
            state.contact_name = contact_name
        ctx = Context(conversation_id, text, normalize(text), channel, now, state)
        if state.step == "handed_off":
            returning_greeting = ctx.plain.strip("!¡., ") in GREETING_WORDS
            record_event(self.db, conversation_id, "inbound", now, {"text": text, "greeting": returning_greeting})
            if now <= state.data.get("handoff_at", 0):
                # El mensaje llegó antes del traspaso y esperó el lock: ya lo ve recepción
                return
            # La conversación volvió a pending (p. ej. se resolvió y el huésped escribió de nuevo)
            state.reset_session()
            store.clear_sla(self.db, conversation_id)
            store.save_state(self.db, state, now)
            return await self._restart_session(ctx)
        greeting = state.step == "start" and ctx.plain.strip("!¡., ") in GREETING_WORDS
        record_event(self.db, conversation_id, "inbound", now, {"text": text, "greeting": greeting})
        try:
            await self._route(ctx, greeting)
        except Exception:
            logger.exception("Falla en el flujo de la conversación %s; se deriva a recepción", conversation_id)
            await self._safe_handoff_after_failure(ctx)
        finally:
            store.save_state(self.db, ctx.state, now)

    async def _restart_session(self, ctx: Context) -> None:
        """Huésped que vuelve tras un traspaso: empieza una consulta nueva con el mismo flujo."""
        greeting = ctx.plain.strip("!¡., ") in GREETING_WORDS
        try:
            await self._route(ctx, greeting)
        except Exception:
            logger.exception("Falla en el flujo de la conversación %s; se deriva a recepción", ctx.conversation_id)
            await self._safe_handoff_after_failure(ctx)
        finally:
            store.save_state(self.db, ctx.state, ctx.now)

    async def _safe_handoff_after_failure(self, ctx: Context) -> None:
        """Último recurso: que una persona vea la conversación, con su nota, aunque el flujo haya fallado."""
        try:
            now = self.clock()
            in_shift = self.settings.in_shift(now)
            if ctx.state.step != "handed_off":
                self._persist_handoff(ctx, "error", now, in_shift)
            await self._say(ctx, "Tuve un problema técnico. Paso tu consulta a recepción para que te ayuden.")
            await self.chatwoot.send_message(ctx.conversation_id, self._note(ctx, "error", in_shift, now),
                                             private=True)
            await self._open_for_humans(ctx, in_shift)
        except Exception:
            logger.exception("No se pudo derivar la conversación %s", ctx.conversation_id)

    async def _open_for_humans(self, ctx: Context, in_shift: bool) -> None:
        labels = ["comercial"] + ([] if in_shift else ["nocturna"])
        await self.chatwoot.add_labels(ctx.conversation_id, labels)
        await self.chatwoot.assign_team(ctx.conversation_id)
        await self.chatwoot.set_status(ctx.conversation_id, "open")

    async def _route(self, ctx: Context, greeting: bool) -> None:
        state = ctx.state
        if state.step == "start":
            await self._welcome(ctx)
            state.step = "menu"
            if greeting:
                await self._send_menu(ctx)
            elif self._wants_human(ctx.plain):
                await self._handoff(ctx, "human_requested")
            else:
                await self._menu_level(ctx, after_welcome=True)
            return
        faq = self.hotel.match_faq(ctx.text)
        if self._wants_human(ctx.plain) and not (faq and faq.id == "recepcion_horario"):
            await self._handoff(ctx, "human_requested")
            return
        if ctx.plain in ("menu", "inicio", "volver", "volver al menu"):
            state.step = "menu"
            await self._send_menu(ctx)
            return
        handler = {
            "menu": self._menu_level, "faq_menu": self._faq_step, "ask_dates": self._dates_step,
            "ask_adults": self._adults_step, "ask_children": self._children_step,
            "pick_room": self._pick_room_step,
        }.get(state.step, self._menu_level)
        await handler(ctx)

    @staticmethod
    def _wants_human(plain: str) -> bool:
        if "decida" in plain:
            return False
        return any(re.search(rf"(?<![a-z]){term}(?![a-z])", plain) for term in HUMAN_TERMS)

    # ---------- piezas de conversación ----------

    async def _say(self, ctx: Context, content: str) -> None:
        await self.chatwoot.send_message(ctx.conversation_id, content)

    async def _ask(self, ctx: Context, content: str, options: list[tuple[str, str]]) -> None:
        """Botones en el widget; en otros canales, lista numerada ('Responde 1, 2 o 3')."""
        if ctx.channel == WEB_WIDGET:
            await self.chatwoot.send_select(ctx.conversation_id, content, options)
            return
        lines = [f"{index}. {title}" for index, (title, _) in enumerate(options, start=1)]
        hint = "Responde con el número de la opción."
        await self.chatwoot.send_message(ctx.conversation_id, "\n".join([content, *lines, hint]))

    async def _welcome(self, ctx: Context) -> None:
        name = self.hotel.hotel["name"]
        await self._say(ctx, (
            f"¡Hola! Soy el Copiloto de Recepción del {name} (demo). Resuelvo al tiro las consultas frecuentes "
            "y paso tu solicitud a recepción, que es quien valida y cierra cada reserva. "
            f"Al escribirme aceptas el tratamiento de tus datos según el aviso de privacidad: "
            f"{self.settings.public_url}/privacidad"
        ))
        await self._show_location(ctx)

    async def _show_location(self, ctx: Context) -> None:
        loc = self.hotel.location
        await self._say(ctx, (
            f"Ubicación: {loc['headline']} {loc['detail']}\n"
            f"Dirección: {self.hotel.hotel['address']}\nMapa: {self.hotel.hotel['maps_url']}"
        ))
        record_event(self.db, ctx.conversation_id, "location_shown", ctx.now)

    async def _show_distances(self, ctx: Context) -> None:
        lines = [f"• {item['place']}: {item['distance']}" for item in self.hotel.location["distances"]]
        await self._say(ctx, "Distancias desde el hotel:\n" + "\n".join(lines))

    async def _send_menu(self, ctx: Context) -> None:
        ctx.state.step = "menu"
        await self._ask(ctx, "¿En qué te ayudo?", MENU_OPTIONS)

    async def _show_rooms(self, ctx: Context) -> None:
        lines = []
        for room in self.hotel.rooms:
            guests = plural(room["max_adults"], "adulto", "adultos")
            if room["max_children"]:
                guests += " + " + plural(room["max_children"], "niño", "niños")
            lines.append(f"• {room['name'].removeprefix('Habitación ')}: {room['m2']} m², hasta {guests}")
        await self._say(ctx, "Nuestras habitaciones (todas con desayuno continental, piscina temperada y playa "
                             "a pasos):\n" + "\n".join(lines))
        await self._say(ctx, f"Fotos y detalle: {self.hotel.photos['rooms_url']} · Galería: "
                             f"{self.hotel.photos['gallery_url']}")

    async def _answer_faq(self, ctx: Context, faq: Faq) -> None:
        await self._say(ctx, faq.answer)
        record_event(self.db, ctx.conversation_id, "faq_answered", self.clock(),
                     {"faq_id": faq.id, "inbound_ts": ctx.now, "status": faq.status})

    # ---------- nivel menú ----------

    def _menu_choice(self, ctx: Context) -> str | None:
        plain = ctx.plain
        for index, (title, value) in enumerate(MENU_OPTIONS, start=1):
            if plain in (normalize(title), value) or plain == str(index):
                return value
        return None

    async def _menu_level(self, ctx: Context, after_welcome: bool = False) -> None:
        state = ctx.state
        choice = None if after_welcome else self._menu_choice(ctx)
        plain = ctx.plain
        faq = self.hotel.match_faq(ctx.text)

        if choice == "ubicacion" or (choice is None and any(t in plain for t in LOCATION_TERMS) and not faq):
            if after_welcome:
                await self._show_distances(ctx)
            else:
                await self._show_location(ctx)
                await self._show_distances(ctx)
            await self._send_menu(ctx)
        elif choice == "habitaciones" or (choice is None and not self._commercial_intent(plain)
                                          and any(t in plain for t in PHOTO_TERMS)):
            await self._show_rooms(ctx)
            await self._send_menu(ctx)
        elif choice == "recepcion":
            await self._handoff(ctx, "human_requested")
        elif choice == "faq":
            state.step = "faq_menu"
            await self._ask(ctx, "Elige un tema o escríbeme tu pregunta:", self._faq_options())
        elif choice == "disponibilidad" or (choice is None and not faq and self._commercial_intent(plain)):
            await self._start_booking(ctx)
        elif faq:
            await self._answer_faq(ctx, faq)
            await self._send_menu(ctx)
        else:
            await self._fallback(ctx)

    @staticmethod
    def _commercial_intent(plain: str) -> bool:
        return any(term in plain for term in COMMERCIAL_TERMS)

    async def _fallback(self, ctx: Context) -> None:
        count = ctx.state.data.get("fallbacks", 0) + 1
        ctx.state.data["fallbacks"] = count
        extra = " También puedes escribir «recepción» para hablar con una persona." if count >= 2 else ""
        await self._say(ctx, "No estoy seguro de haberte entendido. Elige una opción del menú." + extra)
        await self._send_menu(ctx)

    # ---------- FAQ ----------

    def _faq_options(self) -> list[tuple[str, str]]:
        return [(faq.label, faq.id) for faq in self.hotel.faq_menu()] + [("Volver al menú", "menu")]

    async def _faq_step(self, ctx: Context) -> None:
        options = self._faq_options()
        faq = None
        if ctx.plain.isdigit() and 1 <= int(ctx.plain) <= len(options) - 1:
            faq = self.hotel.faq_menu()[int(ctx.plain) - 1]
        faq = faq or self.hotel.faq_by_label(ctx.text) or self.hotel.match_faq(ctx.text)
        if faq:
            await self._answer_faq(ctx, faq)
            await self._ask(ctx, "¿Quieres saber algo más?", options)
        elif self._commercial_intent(ctx.plain):
            await self._start_booking(ctx)
        else:
            await self._fallback(ctx)

    # ---------- disponibilidad ----------

    async def _start_booking(self, ctx: Context) -> None:
        # La ubicación ya se mostró en el saludo (R2): recién ahora se piden datos.
        ctx.state.step = "ask_dates"
        ctx.state.data.pop("fallbacks", None)
        await self._say(ctx, "Para revisar disponibilidad necesito tus fechas. Escríbelas así: «15/01 al 18/01», "
                             "«del 15 al 18 de enero» o «este finde».")

    def _today(self, ctx: Context) -> date:
        return self.settings.local(ctx.now).date()

    async def _dates_step(self, ctx: Context) -> None:
        stay = parse_stay(ctx.text, self._today(ctx))
        if stay is None:
            faq = self.hotel.match_faq(ctx.text)
            if faq:
                await self._answer_faq(ctx, faq)
                await self._say(ctx, "Cuando quieras, dime tus fechas (ej. «15/01 al 18/01»).")
            else:
                await self._say(ctx, "No pude leer las fechas. Prueba con «15/01 al 18/01» o «este finde».")
            return
        if stay[0] < self._today(ctx):
            await self._say(ctx, "Esas fechas ya pasaron. Indícame fechas desde hoy en adelante "
                                 "(ej. «15/01 al 18/01»).")
            return
        data = ctx.state.data
        data["checkin"], data["checkout"] = stay[0].isoformat(), stay[1].isoformat()
        adults, children = parse_guests(ctx.text)
        if adults:
            data["adults"] = adults
        if children is not None:
            data["children"] = children
        await self._after_dates(ctx)

    async def _after_dates(self, ctx: Context) -> None:
        data = ctx.state.data
        if not data.get("adults"):
            ctx.state.step = "ask_adults"
            await self._say(ctx, "¿Cuántos adultos viajan? (1 a 4)")
        elif data.get("children") is None:
            ctx.state.step = "ask_children"
            await self._say(ctx, "¿Y niños? Escribe 0 si no viajan niños.")
        else:
            await self._check_availability(ctx)

    async def _adults_step(self, ctx: Context) -> None:
        adults, children = parse_guests(ctx.text)
        adults = adults or parse_count(ctx.text)
        if not adults or not 1 <= adults <= MAX_ADULTS:
            await self._say(ctx, f"Necesito un número de adultos entre 1 y {MAX_ADULTS}.")
            return
        ctx.state.data["adults"] = adults
        if children is not None:
            ctx.state.data["children"] = children
        await self._after_dates(ctx)

    async def _children_step(self, ctx: Context) -> None:
        _, children = parse_guests(ctx.text)
        if children is None:
            children = 0 if ctx.plain in ("no", "sin ninos", "sin niños") else parse_count(ctx.text)
        if children is None or not 0 <= children <= MAX_CHILDREN:
            await self._say(ctx, f"Escribe cuántos niños viajan (0 a {MAX_CHILDREN}).")
            return
        ctx.state.data["children"] = children
        await self._check_availability(ctx)

    async def _check_availability(self, ctx: Context) -> None:
        data = ctx.state.data
        started = time.monotonic()
        try:
            reading = await self.pms.availability(date.fromisoformat(data["checkin"]),
                                                  date.fromisoformat(data["checkout"]),
                                                  data["adults"], data["children"])
        except PmsUnavailable:
            record_event(self.db, ctx.conversation_id, "pms_read", self.clock(), {"ok": False, "latency_ms": 0})
            await self._handoff(ctx, "pms_down", intro=(
                "No pude consultar el sistema de reservas en este momento, así que no puedo asegurarte cupos. "
                "Recepción verificará cupos y te responderá. "))
            return
        latency_ms = int((time.monotonic() - started) * 1000)
        record_event(self.db, ctx.conversation_id, "pms_read", self.clock(), {"ok": True, "latency_ms": latency_ms})
        data["read_at"] = reading.read_at
        data["read_label"] = self._read_label(reading.read_at)
        data["simulated"] = reading.simulated
        offers = sorted(reading.offers, key=lambda offer: offer.nightly_price_clp)[:5]
        data["offers"] = [offer.code for offer in offers]
        if not offers:
            await self._say(ctx, f"Según lectura del PMS del {self._read_label(reading.read_at)} no veo cupo "
                                 "para esas fechas y esa cantidad de huéspedes. Recepción revisará alternativas.")
            await self._handoff(ctx, "commercial")
            return
        prebooking_id = store.create_prebooking(self.db, ctx.conversation_id, data, ctx.now,
                                                self.settings.prebooking_minutes)
        record_event(self.db, ctx.conversation_id, "prebooking_created", ctx.now, {"prebooking_id": prebooking_id})
        await self._say(ctx, self._availability_text(reading, offers))
        ctx.state.step = "pick_room"
        options = [(self._short_name(offer), offer.code) for offer in offers] + [("Que decida recepción", "any")]
        await self._ask(ctx, "¿Cuál te interesa?", options)

    @staticmethod
    def _short_name(offer: RoomOffer) -> str:
        return offer.name.removeprefix("Habitación ")

    @staticmethod
    def _read_label(read_at: str) -> str:
        """'2026-10-27T17:39:54-03:00' → '27-10-2026 17:39'."""
        if len(read_at) < 16:
            return read_at
        year, month, day = read_at[:10].split("-")
        return f"{day}-{month}-{year} {read_at[11:16]}"

    @staticmethod
    def _clock_text(read_at: str) -> str:
        return read_at[11:16] if len(read_at) >= 16 else read_at

    def _availability_text(self, reading: PmsReading, offers: list[RoomOffer]) -> str:
        lines = []
        for offer in offers:
            lines.append(f"• {self._short_name(offer)} ({offer.m2:g} m²): {money(offer.nightly_price_clp)} por noche"
                         f" · quedan {offer.available_units}")
        read_date = self._read_label(reading.read_at)[:10]
        simulated = " Precios y cupos simulados (prototipo)." if reading.simulated else ""
        return (f"Disponible según lectura del PMS a las {self._clock_text(reading.read_at)} del {read_date}:\n"
                + "\n".join(lines)
                + f"\n\nPendiente de confirmación por recepción: la lectura puede cambiar y nada queda cerrado "
                  f"hasta que una persona lo valide.{simulated} Dejé una pre-información abierta por "
                  f"{self.settings.prebooking_minutes} minutos que no bloquea el sistema.")

    async def _pick_room_step(self, ctx: Context) -> None:
        offers: list[str] = ctx.state.data.get("offers", [])
        choice: str | None = None
        if ctx.plain.isdigit():
            index = int(ctx.plain)
            if 1 <= index <= len(offers):
                choice = offers[index - 1]
            elif index == len(offers) + 1:
                choice = "any"
        for code in offers:
            room = self.hotel.room(code)
            if room and ctx.plain in (normalize(room["name"].removeprefix("Habitación ")), normalize(room["name"]),
                                      code):
                choice = code
        if ctx.plain in ("any", "que decida recepcion", "da igual", "cualquiera", "no se"):
            choice = "any"
        if choice is None:
            faq = self.hotel.match_faq(ctx.text)
            if faq:
                await self._answer_faq(ctx, faq)
                await self._say(ctx, "Cuando quieras, elige una habitación de la lista o escribe «recepción».")
            else:
                await self._say(ctx, "Elige una habitación de la lista, o dime «que decida recepción».")
            return
        room_code = None if choice == "any" else choice
        ctx.state.data["room_code"] = room_code
        store.set_prebooking_room(self.db, ctx.conversation_id, room_code)
        await self._handoff(ctx, "commercial")

    # ---------- traspaso a recepción ----------

    def _local_text(self, epoch: float, fmt: str = "%H:%M") -> str:
        return self.settings.local(epoch).strftime(fmt)

    def _note(self, ctx: Context, reason: str, in_shift: bool, now: float) -> str:
        data = ctx.state.data
        rooms = self.hotel.room(data["room_code"]) if data.get("room_code") else None
        if data.get("checkin"):
            nights = (date.fromisoformat(data["checkout"]) - date.fromisoformat(data["checkin"])).days
            stay = f"{data['checkin']} → {data['checkout']} ({plural(nights, 'noche', 'noches')})"
        else:
            stay = "sin fechas capturadas"
        if data.get("adults"):
            kids = data.get("children")
            guests = plural(data["adults"], "adulto", "adultos") + (
                f", {plural(kids, 'niño', 'niños')}" if kids is not None else ", niños sin informar")
        else:
            guests = "sin huéspedes capturados"
        reasons = {"commercial": "consulta comercial", "human_requested": "pidió hablar con una persona",
                   "pms_down": "PMS sin respuesta: verificar cupos a mano",
                   "error": "falla técnica del copiloto: retomar la conversación a mano"}
        lines = [
            "Pre-información del copiloto",
            f"Huésped: {ctx.state.contact_name or 'sin nombre'} (conversación #{ctx.conversation_id})",
            f"Fechas: {stay}",
            f"Huéspedes: {guests}",
            f"Habitación de interés: {rooms['name'] if rooms else 'a definir por recepción'}",
            f"Origen: {ctx.channel.removeprefix('Channel::')}",
        ]
        if data.get("read_at"):
            sim = " (simulada)" if data.get("simulated") else ""
            when = data.get("read_label", data["read_at"])
            lines.append(f"Lectura PMS: {when}{sim}. Revalidar antes de confirmar.")
        prebooking = store.active_prebooking(self.db, ctx.conversation_id)
        if prebooking and prebooking["status"] == "active":
            lines.append(f"Pre-reserva auxiliar hasta las {self._local_text(prebooking['expires_at'])} "
                         "(no bloquea el PMS).")
        lines.append(f"Motivo: {reasons.get(reason, reason)}")
        if in_shift:
            deadline = self._local_text(now + self.settings.sla_red_s)
            lines.append(f"Meta: responder antes de las {deadline} ({self.settings.sla_red_s // 60}:00).")
        else:
            lines.append(f"Captura fuera de turno: atender desde las {self.settings.shift_start}.")
        return "\n".join(lines)

    async def _handoff(self, ctx: Context, reason: str, intro: str = "") -> None:
        state = ctx.state
        data = state.data
        now = self.clock()
        in_shift = self.settings.in_shift(now)
        complete = bool(data.get("checkin") and data.get("adults") and data.get("children") is not None)
        note = self._note(ctx, reason, in_shift, now)
        if in_shift:
            closing = ("Ya pasé tu consulta a recepción con estos datos. Una persona te responde en breve; "
                       "ella valida disponibilidad y cierra la reserva contigo.")
        else:
            closing = (f"Estamos fuera del horario de recepción ({self.settings.shift_start} a "
                       f"{self.settings.shift_end}). Dejé tu consulta registrada y recepción te responde desde las "
                       f"{self.settings.shift_start}.")

        self._persist_handoff(ctx, reason, now, in_shift, complete)
        await self._say(ctx, intro + closing)
        await self.chatwoot.send_message(ctx.conversation_id, note, private=True)
        await self._open_for_humans(ctx, in_shift)

    def _persist_handoff(self, ctx: Context, reason: str, now: float, in_shift: bool,
                         complete: bool = False) -> None:
        """La frontera del traspaso (estado, eventos y reloj) se persiste antes de abrir la conversación a
        recepción: así una respuesta humana inmediata nunca llega antes que el inicio del cronómetro."""
        state = ctx.state
        state.step = "handed_off"
        state.data["handoff_at"] = now
        store.save_state(self.db, state, now)
        record_event(self.db, ctx.conversation_id, "handoff", now, {"reason": reason})
        record_event(self.db, ctx.conversation_id, "commercial_started", now, {"in_shift": in_shift})
        if in_shift:
            store.start_sla(self.db, ctx.conversation_id, now)
        else:
            record_event(self.db, ctx.conversation_id, "night_capture", now, {"complete": complete})

    # ---------- eventos externos ----------

    def on_human_reply(self, conversation_id: int, user_id: int | None, now: float) -> None:
        """Primer mensaje saliente de una persona: detiene el cronómetro del SLA."""
        if store.stop_sla(self.db, conversation_id, now):
            record_event(self.db, conversation_id, "human_first_reply", now, {"user_id": user_id})

    async def on_booking_confirmed(self, conversation_id: int | None, booking_id: int) -> None:
        """Reserva confirmada por una persona en el PMS (webhook de pms-mock)."""
        now = self.clock()
        key = f"booking:{booking_id}"
        if self.db.execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (key,)).fetchone():
            return
        record_event(self.db, conversation_id or 0, "booking_confirmed", now, {"booking_id": booking_id})
        if conversation_id is not None:
            store.convert_prebooking(self.db, conversation_id)
        mark_processed(self.db, key, now)
        if conversation_id is None:
            return
        try:
            await self.chatwoot.send_message(
                conversation_id, f"Reserva #{booking_id} cerrada por recepción en el PMS.", private=True)
        except Exception:
            logger.exception("No se pudo anotar la reserva en la conversación %s", conversation_id)
