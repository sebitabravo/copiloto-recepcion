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
from copiloto.config import Settings
from copiloto.hotel import HotelData
from copiloto.pms import PmsAdapter

MAX_STEPS = 5
MAX_REPLY = 1200
MAX_TOOL_PAYLOAD = 3500
CONFIRM_CLAIM = re.compile(r"confirmad[oa]s?|reservad[oa]s?|queda(?:ron)? (?:hecha|listo|lista)", re.IGNORECASE)
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
        specs = tool_specs("full" if self.settings.autonomous_booking else "assisted")
        messages = [{"role": "system", "content": self._system(session)}, *session.history,
                    {"role": "user", "content": user_text}]
        result = AgentResult(None)
        text: str | None = None
        for _ in range(MAX_STEPS):
            started = time.monotonic()
            reply = await self.llm.chat(messages, specs, max_tokens=self.settings.llm_max_tokens)
            result.llm_ms += int((time.monotonic() - started) * 1000)
            if reply.tokens is not None:
                result.tokens = (result.tokens or 0) + reply.tokens
            if not reply.tool_calls:
                text = (reply.content or "").strip()
                break
            messages.append(reply.message)
            for call in reply.tool_calls:
                args = parse_arguments(call.arguments)
                tool_started = time.monotonic()
                outcome = await runner.run(call.name, args)
                result.tools.append(call.name)
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
