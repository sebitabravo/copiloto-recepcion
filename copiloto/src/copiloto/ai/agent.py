"""Bucle del agente: el modelo decide qué herramienta usar, el código valida y ejecuta, y la salida se revisa."""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from copiloto.ai.llm import LlmClient, parse_arguments
from copiloto.ai.prompts import WEEKDAYS, build_system_prompt
from copiloto.ai.sessions import AiSession
from copiloto.ai.tools import LABELS, ToolHooks, ToolRunner, tool_specs
from copiloto.textutil import parse_guests, parse_stay
from copiloto.config import Settings
from copiloto.hotel import HotelData
from copiloto.pms import PmsAdapter

MAX_STEPS = 5
MAX_REPLY = 1200
MAX_TOOL_PAYLOAD = 3500
CONFIRM_CLAIM = re.compile(r"confirmad[oa]s?|reservad[oa]s?|queda(?:ron)? (?:hecha|listo|lista)", re.IGNORECASE)
# Pregunta sobre el hotel: se fuerza la herramienta en el primer paso para que no responda de memoria.
HOTEL_QUESTION = re.compile(
    r"(d[oó]nde|ubicaci[oó]n|c[oó]mo llego|direcci[oó]n|servicios?|habitaci[oó]n|suite|piscina|tinaja|"
    r"desayuno|precio|tarifa|cu[aá]nto|disponibilidad|reserv|estacionamiento|wifi)", re.IGNORECASE)
# Afirmación sobre el hotel sin ninguna herramienta detrás: se descarta.
HOTEL_CLAIM = re.compile(
    r"estamos|se encuentra|situad|ubicad|direcci[oó]n|\bcalle\b|\bavenida\b|centro de|piscina|tinaja|"
    r"desayuno|jacuzzi|\$\s?\d", re.IGNORECASE)
SAFE_NO_DATA = ("No quiero darte un dato sin verificarlo. Déjame confirmarlo en el sistema del hotel: "
                "¿me repites la pregunta?")
# El modelo a veces narra la llamada en vez de hacerla ("CallCheckAvailability con checkin: ...").
TOOL_NARRATION = re.compile(r"\bCall[A-Z]\w*|check_availability|create_booking|get_hotel_info|handoff_to_human")
SAFE_NARRATION = "Déjame revisarlo en el sistema del hotel antes de responderte."

# Tema deducible del mensaje, para consultar el hotel sin depender de que el modelo llame la herramienta.
TOPIC_HINTS = (
    ("ubicacion", re.compile(r"d[oó]nde|ubicaci|direcci|c[oó]mo llego|llego al|llegar|distancia|queda", re.I)),
    ("habitaciones", re.compile(r"habitaci|pieza|suite|jacuzzi|cama|capacidad", re.I)),
    ("politicas", re.compile(r"pol[ií]tica|mascota|check-?in|check-?out|cancel|fumar", re.I)),
    ("servicios", re.compile(r"servicio|piscina|tinaja|desayuno|wifi|wi-fi|estacionamiento|spa|turismo", re.I)),
)
# Si el huésped quiere reservar, el turno lo maneja el modelo con sus herramientas: no se precarga nada.
BOOKING_INTENT = re.compile(r"reserv|disponib|coti[zs]|fecha|noche|adulto|niñ", re.I)
# Pedir una persona es una acción del producto, no una decisión del modelo.
HANDOFF_INTENT = re.compile(
    r"hablar con (una |alguien )?(persona|humano|recepci|agente)|con un humano|persona real|"
    r"ati[eé]ndanme|que me (atienda|responda) (alguien|una persona)", re.I)


def topic_hint(text: str) -> str | None:
    for topic, pattern in TOPIC_HINTS:
        if pattern.search(text):
            return topic
    return None
SAFE_NO_BOOKING = ("Todavía no hay una reserva creada. Cuando me confirmes los datos con un sí, la dejo "
                   "registrada.")
STUCK = "Se me enredó la consulta. ¿Lo intentamos de nuevo o prefieres que te pase con recepción?"


@dataclass
class AgentResult:
    reply: str | None
    events: list[dict] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    llm_ms: int = 0
    tokens: int | None = None
    handed_off: bool = False
    booking: dict | None = None
    guardrails: list[str] = field(default_factory=list)
    quick_replies: list[str] = field(default_factory=list)


def _count(value: int, singular: str, plural: str) -> str:
    return f"{value} {singular if value == 1 else plural}"


def _money(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")


class Agent:
    def __init__(self, llm: LlmClient, hotel: HotelData, pms: PmsAdapter, settings: Settings,
                 clock: Callable[[], float] = time.time):
        self.llm, self.hotel, self.pms, self.settings, self.clock = llm, hotel, pms, settings, clock

    def _system(self, session: AiSession) -> str:
        today = self.settings.local(self.clock()).date()
        mode = "full" if self.settings.autonomous_booking else "assisted"
        prompt = build_system_prompt(today.isoformat(), WEEKDAYS[today.weekday()], mode)
        last = session.state.get("last_availability")
        notes = []
        if last:
            options = "; ".join(f"{code} = {info['name']} (${info['price']}/noche, {info['units']} cupos)"
                                for code, info in last["options"].items())
            notes.append(f"Última lectura del PMS ({last['read_label']}): entrada {last['checkin']}, salida "
                         f"{last['checkout']}, {last['adults']} adultos, {last['children']} niños. "
                         f"Opciones: {options}.")
        for made in session.state.get("bookings", []):
            notes.append(f"Ya creaste la reserva #{made['booking_id']} ({made['room_name']}, {made['checkin']} a "
                         f"{made['checkout']}) a nombre de {made['guest_name']}.")
        return prompt + ("\n\nESTADO DE LA SESIÓN\n" + "\n".join(notes) if notes else "")

    async def respond(self, session: AiSession, user_text: str, hooks: ToolHooks) -> AgentResult:
        runner = ToolRunner(self.hotel, self.pms, self.settings, self.clock, session, hooks)
        # Las herramientas no confían en el modelo: el «sí» del huésped se verifica sobre su propio texto.
        session.state["last_user_text"] = user_text
        specs = tool_specs("full" if self.settings.autonomous_booking else "assisted")
        messages = [{"role": "system", "content": self._system(session)}, *session.history,
                    {"role": "user", "content": user_text}]
        result = AgentResult(None)
        text: str | None = None
        # Una pregunta sobre el hotel obliga a consultar una herramienta antes de responder.
        forced = bool(HOTEL_QUESTION.search(user_text) or BOOKING_INTENT.search(user_text))
        # Se consulta antes de preguntar: así la respuesta sale con datos reales y la traza muestra la
        # herramienta, aunque el servidor local no respete tool_choice="required".
        hint = topic_hint(user_text) if forced and not BOOKING_INTENT.search(user_text) else None
        # Sin tema claro se busca en las FAQ aprobadas: mismo principio de recuperación que un corpus.
        faq_lookup = forced and not BOOKING_INTENT.search(user_text) and hint is None
        if hint or faq_lookup:
            tool_started = time.monotonic()
            arguments = {"topic": hint} if hint else {"topic": "faq", "question": user_text}
            outcome = await runner.run("get_hotel_info", arguments)
            result.tools.append("get_hotel_info")
            if outcome.ok:
                session.state["data_seen"] = True
            result.events.append({
                "type": "tool_call", "name": "get_hotel_info", "label": LABELS["get_hotel_info"],
                "arguments": arguments, "summary": outcome.summary,
                "ms": int((time.monotonic() - tool_started) * 1000), "ok": outcome.ok})
            messages.append({"role": "system", "content": "Datos verificados del hotel (herramienta "
                             "get_hotel_info): " + json.dumps(outcome.data, ensure_ascii=False)})
        if HANDOFF_INTENT.search(user_text):
            tool_started = time.monotonic()
            outcome = await runner.run("handoff_to_human", {"reason": "Solicitud del huésped"})
            result.tools.append("handoff_to_human")
            result.events.append({
                "type": "tool_call", "name": "handoff_to_human", "label": LABELS["handoff_to_human"],
                "arguments": {}, "summary": outcome.summary,
                "ms": int((time.monotonic() - tool_started) * 1000), "ok": outcome.ok})
            if outcome.event:
                result.events.append(outcome.event)
            if outcome.ok:
                session.state["data_seen"] = True
            messages.append({"role": "system", "content": "Aviso a recepción: "
                             + json.dumps(outcome.data, ensure_ascii=False)})
        for step in range(MAX_STEPS):
            started = time.monotonic()
            # No se usa tool_choice="required": llama.cpp lo ignora y el modelo tiende a narrar la llamada.
            reply = await self.llm.chat(messages, specs, max_tokens=self.settings.llm_max_tokens)
            result.llm_ms += int((time.monotonic() - started) * 1000)
            if reply.tokens is not None:
                result.tokens = (result.tokens or 0) + reply.tokens
            if not reply.tool_calls:
                text = (reply.content or "").strip()
                # Respaldo determinista: con fechas y personas dichas por el huésped, la lectura del PMS
                # no depende de que el modelo decida llamar la herramienta.
                if step == 0 and not result.tools and BOOKING_INTENT.search(user_text):
                    stay = parse_stay(user_text, self.settings.local(self.clock()).date())
                    adults, children = parse_guests(user_text)
                    if stay and adults:
                        tool_started = time.monotonic()
                        arguments = {"checkin": stay[0].isoformat(), "checkout": stay[1].isoformat(),
                                     "adults": adults, "children": children or 0}
                        outcome = await runner.run("check_availability", arguments)
                        result.tools.append("check_availability")
                        if outcome.ok:
                            session.state["data_seen"] = True
                        result.events.append({
                            "type": "tool_call", "name": "check_availability",
                            "label": LABELS["check_availability"], "arguments": arguments,
                            "summary": outcome.summary,
                            "ms": int((time.monotonic() - tool_started) * 1000), "ok": outcome.ok})
                        messages.append({"role": "system", "content": "Disponibilidad leída del PMS: "
                                         + json.dumps(outcome.data, ensure_ascii=False)})
                        continue
                break
            messages.append(reply.message)
            for call in reply.tool_calls:
                args = parse_arguments(call.arguments)
                tool_started = time.monotonic()
                outcome = await runner.run(call.name, args)
                result.tools.append(call.name)
                if outcome.ok:
                    session.state["data_seen"] = True
                result.events.append({
                    "type": "tool_call", "name": call.name, "label": LABELS.get(call.name, call.name),
                    "arguments": {k: v for k, v in args.items() if k != "guest_confirmed"},
                    "summary": outcome.summary, "ms": int((time.monotonic() - tool_started) * 1000),
                    "ok": outcome.ok})
                if outcome.event:
                    result.events.append(outcome.event)
                if call.name == "create_booking" and outcome.ok and not outcome.data.get("ya_existia"):
                    result.booking = outcome.data
                payload = json.dumps(outcome.data, ensure_ascii=False)[:MAX_TOOL_PAYLOAD]
                messages.append({"role": "tool", "tool_call_id": call.id, "content": payload})
                if call.name == "handoff_to_human" and outcome.ok and hooks.conversation_id is not None:
                    result.handed_off = True
            if result.handed_off:
                return self._finish(session, user_text, result, None)
        return self._finish(session, user_text, result, text)

    def _finish(self, session: AiSession, user_text: str, result: AgentResult, text: str | None) -> AgentResult:
        if result.handed_off:
            session.add("user", user_text, self.settings.ai_max_history)
            return result
        reply = text if text is not None else STUCK
        if not reply:
            reply = "¿Me cuentas un poco más para ayudarte mejor?"
        if not result.tools and TOOL_NARRATION.search(reply):
            reply = SAFE_NARRATION
            result.guardrails.append("tool_narration")
        if not result.tools and not session.state.get("data_seen") and HOTEL_CLAIM.search(reply):
            reply = SAFE_NO_DATA
            result.guardrails.append("data_without_tool")
        if CONFIRM_CLAIM.search(reply) and result.booking is None:
            reply = SAFE_NO_BOOKING
            result.guardrails.append("confirmation_without_booking")
        reply = reply[:MAX_REPLY]
        if result.booking:
            b = result.booking
            reply += (f"\n\nReserva de demostración #{b['booking_id']} creada en el PMS simulado: {b['room_name']}, "
                      f"{b['checkin']} a {b['checkout']} ({_count(b['nights'], 'noche', 'noches')}), "
                      f"{_count(b['adults'], 'adulto', 'adultos')} y {_count(b['children'], 'niño', 'niños')}, "
                      f"total {_money(b['total_clp'])}. Es una demostración: no es una reserva real.")
        result.reply = reply
        session.add("user", user_text, self.settings.ai_max_history)
        session.add("assistant", reply, self.settings.ai_max_history)
        result.quick_replies = quick_replies(session, result)
        return result


def quick_replies(session: AiSession, result: AgentResult) -> list[str]:
    if result.booking:
        return ["¿Tienen piscina?", "Quiero hacer otra reserva"]
    last = session.state.get("last_availability")
    if last and "check_availability" in result.tools and last["options"]:
        names = [info["name"].removeprefix("Habitación ") for info in last["options"].values()]
        return [f"Quiero la {name}" for name in names[:3]]
    if not session.state.get("seen_location"):
        return ["¿Cómo llego?", "¿Tienen piscina?", "Quiero reservar para 2 adultos"]
    return ["Quiero reservar", "¿Qué servicios tienen?", "Hablar con una persona"]
