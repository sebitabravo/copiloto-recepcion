"""Bucle del agente: el modelo decide qué herramienta usar, el código valida y ejecuta, y la salida se revisa."""

import asyncio
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from copiloto.ai.llm import LlmClient, LlmTimeout, parse_arguments
from copiloto.ai.prompts import MISSING_DATA, WEEKDAYS, build_system_prompt
from copiloto.ai.sessions import AiSession
from copiloto.ai.tools import GUEST_NAME, LABELS, ToolHooks, ToolRunner, guest_said_yes, pending_proposal, tool_specs
from copiloto.config import Settings
from copiloto.hotel import HotelData
from copiloto.pms import PmsAdapter
from copiloto.textutil import chat_format, money, normalize, parse_guests, parse_stay, plural

MAX_STEPS = 5
MAX_REPLY = 1200
MAX_TOOL_PAYLOAD = 3500
# El modelo no puede declarar hecha una reserva que no existe: cubre afirmaciones en presente y en pasado
# («la reserva quedó hecha», «tu reserva está confirmada»), que es como lo dice un modelo real.
CONFIRM_CLAIM = re.compile(
    r"confirmad[oa]s?|reservad[oa]s?|"
    r"reserva (?:creada|confirmada|hecha|registrada|lista)|\bspa(?:cio)? reservad|"
    r"qued(?:o|ó|aron|amos?) (?:hech[ao]s?|list[ao]s?|registrad[ao]s?|confirmad[ao]s?)",
    re.IGNORECASE,
)
# Pregunta sobre el hotel: se fuerza la herramienta en el primer paso para que no responda de memoria.
HOTEL_QUESTION = re.compile(
    r"(d[oó]nde|ubicaci[oó]n|c[oó]mo llego|direcci[oó]n|servicios?|habitaci[oó]n|suite|piscina|tinaja|"
    r"desayuno|precio|tarifa|cu[aá]nto|disponibilidad|reserv|estacionamiento|wifi)",
    re.IGNORECASE,
)
# Afirmación sobre el hotel sin ninguna herramienta detrás: se descarta. Incluye la primera persona plural
# («tenemos piscina»), que es como el prompt pide hablar del hotel.
HOTEL_CLAIM = re.compile(
    r"estamos|tenemos|contamos con|se encuentra|cuenta con|situad|ubicad|direcci[oó]n|\bcalle\b|\bavenida\b|"
    r"centro de|piscina|tinaja|desayuno|jacuzzi|\$\s?\d",
    re.IGNORECASE,
)
# Frase fija para el dato ausente: la misma que pide el prompt, sin jerga de sistema.
SAFE_NO_DATA = MISSING_DATA
# El modelo a veces narra la llamada en vez de hacerla ("CallCheckAvailability con checkin: ...").
TOOL_NARRATION = re.compile(r"\bCall[A-Z]\w*|check_availability|create_booking|get_hotel_info|handoff_to_human")
SAFE_NARRATION = "Déjame confirmarlo con recepción y te respondo por aquí."

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
    r"ati[eé]ndanme|que me (atienda|responda) (alguien|una persona)",
    re.I,
)


def topic_hint(text: str) -> str | None:
    for topic, pattern in TOPIC_HINTS:
        if pattern.search(text):
            return topic
    return None


SAFE_NO_BOOKING = "Todavía no hay una reserva creada. Cuando me confirmes los datos con un sí, la dejo registrada."
# En modo asistido el asistente no registra nada: prometer que sí sería mentirle al huésped.
SAFE_NO_BOOKING_ASSISTED = (
    "Todavía no hay una reserva creada. Recepción revisa estos datos y te confirma la reserva por aquí."
)
STUCK = "Perdona, se me enredó la consulta. ¿Lo intentamos de nuevo o prefieres que te pase con recepción?"
NO_QUESTION = "Cuéntame un poco más y te ayudo a resolverlo."

# Respuestas rápidas: texto y palabras que las descartan si el huésped ya las preguntó en esta sesión.
QUICK_LOCATION = (("¿Cómo llego?", ("llego", "llegar", "ubicacion")),)
QUICK_SERVICES = (("¿Qué servicios tienen?", ("servicio",)),)
QUICK_POOL = (("¿Tienen piscina?", ("piscina",)),)
QUICK_BOOK = (("Quiero reservar", ("reservar",)), ("Quiero hacer otra reserva", ("otra reserva",)))
QUICK_HUMAN = (("Hablar con una persona", ("persona",)),)
QUICK_OTHER_DATES = (("Probar otras fechas", ("otras fechas",)),)
QUICK_PROPOSAL = (("Sí, confirmo la reserva", ("confirmo la reserva",)), ("Quiero cambiar algo", ("cambiar",)))

SPOKEN_NAME = re.compile(r"(?:soy|me llamo)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ' ]{3,60})", re.IGNORECASE)
NAME_STOPWORDS = frozenset(
    {"y", "e", "de", "del", "la", "el", "los", "las", "mi", "para", "con", "quiero", "necesito", "en"}
)


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


def _result_card(name: str, outcome) -> dict | None:
    """Resumen estructurado para la tarjeta de la demo web; solo la disponibilidad lo necesita."""
    if name != "check_availability" or not outcome.ok:
        return None
    data = outcome.data
    return {
        "lectura": data.get("lectura_pms"),
        "noches": data.get("noches"),
        "opciones": [
            {key: option[key] for key in ("nombre", "cupos", "precio_noche_clp", "total_clp")}
            for option in data.get("opciones", [])
        ],
    }


class Agent:
    def __init__(
        self,
        llm: LlmClient,
        hotel: HotelData,
        pms: PmsAdapter,
        settings: Settings,
        clock: Callable[[], float] = time.time,
    ):
        self.llm, self.hotel, self.pms, self.settings, self.clock = llm, hotel, pms, settings, clock

    def _system(self, session: AiSession, settings: Settings) -> str:
        today = settings.local(self.clock()).date()
        mode = "full" if settings.autonomous_booking else "assisted"
        prompt = build_system_prompt(
            today.isoformat(),
            WEEKDAYS[today.weekday()],
            mode,
            self.hotel.hotel["name"],
            voice=bool(session.state.get("voice")),
        )
        last = session.state.get("last_availability")
        notes = []
        if last:
            options = "; ".join(
                f"{code} = {info['name']} (${info['price']}/noche, {info['units']} cupos)"
                for code, info in last["options"].items()
            )
            notes.append(
                f"Última lectura del PMS ({last['read_label']}): entrada {last['checkin']}, salida "
                f"{last['checkout']}, {last['adults']} adultos, {last['children']} niños. "
                f"Opciones: {options}."
            )
        for made in session.state.get("bookings", []):
            notes.append(
                f"Ya creaste la reserva #{made['booking_id']} ({made['room_name']}, {made['checkin']} a "
                f"{made['checkout']}) a nombre de {made['guest_name']}."
            )
        return prompt + ("\n\nESTADO DE LA SESIÓN\n" + "\n".join(notes) if notes else "")

    async def respond(self, session: AiSession, user_text: str, hooks: ToolHooks, voice: bool = False) -> AgentResult:
        deadline = time.monotonic() + self.settings.ai_turn_timeout_s
        # Por voz el reconocimiento puede errar nombres y fechas: nunca se reserva solo, sea cual sea el modo global
        denied = hooks.extra.get("sandbox_only") is True and hooks.extra.get("sandbox_authorized") is not True
        settings = replace(self.settings, ai_mode="assisted") if voice or denied else self.settings
        if not settings.autonomous_booking:
            session.state.pop("pending_booking", None)
        session.state["voice"] = voice
        session.state["turn"] = session.state.get("turn", 0) + 1
        runner = ToolRunner(self.hotel, self.pms, settings, self.clock, session, hooks)
        # Las herramientas no confían en el modelo: el «sí» del huésped se verifica sobre su propio texto.
        session.state["last_user_text"] = user_text
        specs = tool_specs("full" if settings.autonomous_booking else "assisted")
        messages = [
            {"role": "system", "content": self._system(session, settings)},
            *session.history,
            {"role": "user", "content": user_text},
        ]

        def verified(label: str, data) -> None:
            """Los datos del turno viajan dentro del único mensaje de sistema.

            Qwen3.5 rechaza un `system` a mitad de la conversación («System message must be at the beginning»),
            así que el contexto verificado se agrega al prompt inicial, nunca como turno aparte.
            """
            payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
            messages[0]["content"] = f"{messages[0]['content']}\n\n{label}: {payload}"

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
            result.events.append(
                {
                    "type": "tool_call",
                    "name": "get_hotel_info",
                    "label": LABELS["get_hotel_info"],
                    "arguments": arguments,
                    "summary": outcome.summary,
                    "ms": int((time.monotonic() - tool_started) * 1000),
                    "ok": outcome.ok,
                }
            )
            verified("Datos verificados del hotel (herramienta get_hotel_info)", outcome.data)
        if HANDOFF_INTENT.search(user_text):
            tool_started = time.monotonic()
            outcome = await runner.run("handoff_to_human", {"reason": "Solicitud del huésped"})
            result.tools.append("handoff_to_human")
            result.events.append(
                {
                    "type": "tool_call",
                    "name": "handoff_to_human",
                    "label": LABELS["handoff_to_human"],
                    "arguments": {},
                    "summary": outcome.summary,
                    "ms": int((time.monotonic() - tool_started) * 1000),
                    "ok": outcome.ok,
                }
            )
            if outcome.event:
                result.events.append(outcome.event)
            if outcome.ok:
                session.state["data_seen"] = True
                if hooks.conversation_id is not None and hooks.handoff is not None:
                    # Recepción ya fue avisada y el huésped informado: no se pide otra respuesta al modelo,
                    # porque si fallara el menú pisaría una derivación ya hecha.
                    result.handed_off = True
                    return self._finish(session, user_text, result, None)
            verified("Aviso a recepción", outcome.data)
        for step in range(MAX_STEPS):
            started = time.monotonic()
            if deadline <= started:
                raise LlmTimeout("plazo del turno agotado")
            # No se usa tool_choice="required": llama.cpp lo ignora y el modelo tiende a narrar la llamada.
            try:
                async with asyncio.timeout(max(deadline - started, 0)):
                    sampling = {"temperature": self.settings.llm_temperature}
                    if self.settings.llm_top_p is not None:
                        sampling["top_p"] = self.settings.llm_top_p
                    reply = await self.llm.chat(
                        messages, specs, max_tokens=self.settings.llm_max_tokens, **sampling
                    )
            except TimeoutError:
                raise LlmTimeout("plazo del turno agotado") from None
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
                        arguments = {
                            "checkin": stay[0].isoformat(),
                            "checkout": stay[1].isoformat(),
                            "adults": adults,
                            "children": children or 0,
                        }
                        outcome = await runner.run("check_availability", arguments)
                        result.tools.append("check_availability")
                        if outcome.ok:
                            session.state["data_seen"] = True
                        result.events.append(
                            {
                                "type": "tool_call",
                                "name": "check_availability",
                                "label": LABELS["check_availability"],
                                "arguments": arguments,
                                "summary": outcome.summary,
                                "result": _result_card("check_availability", outcome),
                                "ms": int((time.monotonic() - tool_started) * 1000),
                                "ok": outcome.ok,
                            }
                        )
                        verified("Disponibilidad leída del PMS", outcome.data)
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
                result.events.append(
                    {
                        "type": "tool_call",
                        "name": call.name,
                        "label": LABELS.get(call.name, call.name),
                        "arguments": {k: v for k, v in args.items() if k != "guest_confirmed"},
                        "summary": outcome.summary,
                        "result": _result_card(call.name, outcome),
                        "ms": int((time.monotonic() - tool_started) * 1000),
                        "ok": outcome.ok,
                    }
                )
                if outcome.event:
                    result.events.append(outcome.event)
                if outcome.event and outcome.event.get("type") == "booking_created":
                    result.booking = outcome.data
                payload = json.dumps(outcome.data, ensure_ascii=False)[:MAX_TOOL_PAYLOAD]
                messages.append({"role": "tool", "tool_call_id": call.id, "content": payload})
                if (
                    call.name == "handoff_to_human"
                    and outcome.ok
                    and hooks.conversation_id is not None
                    and hooks.handoff is not None
                ):
                    result.handed_off = True
            if result.handed_off:
                return self._finish(session, user_text, result, None)
        if text is not None:
            await self._propose_from_known_data(session, result, runner, settings)
            await self._confirm_presented_proposal(session, result, runner, settings)
        return self._finish(session, user_text, result, text)

    async def _confirm_presented_proposal(
        self, session: AiSession, result: AgentResult, runner: ToolRunner, settings: Settings
    ) -> None:
        """Un «sí» explícito al resumen del servidor crea la reserva, aunque el modelo no llame la herramienta.

        Con un modelo real el turno del sí se perdía en prosa («la reserva quedó hecha») y el huésped tenía que
        confirmar dos veces. El texto del huésped ya está verificado por `guest_said_yes`, así que aquí solo se
        ejecuta la misma operación que la herramienta habría ejecutado con datos idénticos a la propuesta.
        """
        if not settings.autonomous_booking or session.state.get("voice"):
            return
        if result.booking is not None or "create_booking" in result.tools:
            return
        pending = pending_proposal(session, self.clock(), self.settings.prebooking_minutes * 60)
        if not pending or pending.get("presented_turn") is None:
            return
        if pending["presented_turn"] >= session.state.get("turn", 0):
            return
        if not guest_said_yes(session.state.get("last_user_text")):
            return
        arguments = {
            key: pending[key]
            for key in ("guest_name", "room_code", "checkin", "checkout", "adults", "children")
        }
        arguments["guest_confirmed"] = True
        started = time.monotonic()
        outcome = await runner.run("create_booking", arguments)
        result.tools.append("create_booking")
        result.events.append(
            {
                "type": "tool_call",
                "name": "create_booking",
                "label": LABELS["create_booking"],
                "arguments": {k: v for k, v in arguments.items() if k != "guest_confirmed"},
                "summary": outcome.summary,
                "result": None,
                "ms": int((time.monotonic() - started) * 1000),
                "ok": outcome.ok,
            }
        )
        if not outcome.ok:
            return
        if outcome.event:
            result.events.append(outcome.event)
            if outcome.event.get("type") == "booking_created":
                result.booking = outcome.data

    async def _propose_from_known_data(
        self, session: AiSession, result: AgentResult, runner: ToolRunner, settings: Settings
    ) -> None:
        """Con fechas, personas, habitación y nombre ya dichos, el resumen lo arma el servidor.

        Con un modelo real se vio que escribía su propio resumen sin llamar create_booking, y el huésped tenía
        que decir «sí» dos veces. Aquí la propuesta sale apenas están los datos: el resumen del servidor sigue
        siendo el único resumen y la reserva se crea solo con un sí posterior del huésped.
        """
        if not settings.autonomous_booking or session.state.get("voice") or "create_booking" in result.tools:
            return
        if session.state.get("pending_booking"):
            return
        last = session.state.get("last_availability") or {}
        if not last.get("options"):
            return
        code = _chosen_room(session)
        guest_name = _spoken_name(session.state.get("last_user_text") or "")
        if not code or not guest_name:
            return
        arguments = {
            "guest_name": guest_name,
            "room_code": code,
            "checkin": last["checkin"],
            "checkout": last["checkout"],
            "adults": last["adults"],
            "children": last["children"],
            "guest_confirmed": False,
        }
        started = time.monotonic()
        outcome = await runner.run("create_booking", arguments)
        if not outcome.ok:
            return
        result.tools.append("create_booking")
        result.events.append(
            {
                "type": "tool_call",
                "name": "create_booking",
                "label": LABELS["create_booking"],
                "arguments": {k: v for k, v in arguments.items() if k != "guest_confirmed"},
                "summary": outcome.summary,
                "result": None,
                "ms": int((time.monotonic() - started) * 1000),
                "ok": True,
            }
        )
        if outcome.event:
            result.events.append(outcome.event)

    def _finish(self, session: AiSession, user_text: str, result: AgentResult, text: str | None) -> AgentResult:
        if result.handed_off:
            session.add("user", user_text, self.settings.ai_max_history)
            return result
        reply = text if text is not None else STUCK
        if not reply:
            reply = NO_QUESTION
        # Cada guardarraíl se evalúa sobre el texto del modelo y aplica uno solo: la plantilla de reemplazo
        # no se vuelve a revisar (antes «no lo tengo confirmado» se tomaba como una confirmación inventada).
        # Una reserva inventada pesa más que cualquier otro reemplazo: es la mentira que el huésped no perdona.
        confirmed_claim = CONFIRM_CLAIM.search(reply) is not None and result.booking is None
        if confirmed_claim:
            reply = SAFE_NO_BOOKING if self.settings.autonomous_booking else SAFE_NO_BOOKING_ASSISTED
            result.guardrails.append("confirmation_without_booking")
        elif not result.tools and TOOL_NARRATION.search(reply):
            reply = SAFE_NARRATION
            result.guardrails.append("tool_narration")
        elif not result.tools and not session.state.get("data_seen") and HOTEL_CLAIM.search(reply):
            reply = SAFE_NO_DATA
            result.guardrails.append("data_without_tool")
        reply = reply[:MAX_REPLY]
        pending = pending_proposal(session, self.clock(), self.settings.prebooking_minutes * 60)
        proposal_requested = any(event.get("type") == "booking_proposal" for event in result.events)
        # Present new proposals authoritatively without replacing unrelated later hotel answers.
        if pending and proposal_requested and not result.booking and not session.state.get("voice"):
            b = pending
            reply = (
                f"{b['guest_name']}, te dejo la propuesta: {b['room_name']}, "
                f"{b['checkin']} a {b['checkout']} ({plural(b['nights'], 'noche', 'noches')}), "
                f"{plural(b['adults'], 'adulto', 'adultos')} y {plural(b['children'], 'niño', 'niños')}, "
                f"total {money(b['total_clp'])}. Todavía no hay una reserva creada.\n\n"
                "¿Confirmas estos datos? Responde «Sí, confirmo la reserva» y la dejo lista para recepción."
            )
            if b["simulated"]:
                reply += " Es una demostración con datos ficticios: no es una reserva real."
            pending["presented_turn"] = session.state["turn"]
        if result.booking:
            b = result.booking
            heading = "Reserva de demostración" if b.get("simulated") else "Reserva"
            destination = "PMS simulado" if b.get("simulated") else "PMS"
            reply += (
                f"\n\n{heading} #{b['booking_id']}, ya está en el {destination}: {b['room_name']}, "
                f"{b['checkin']} a {b['checkout']} ({plural(b['nights'], 'noche', 'noches')}), "
                f"{plural(b['adults'], 'adulto', 'adultos')} y {plural(b['children'], 'niño', 'niños')}, "
                f"total {money(b['total_clp'])}."
            )
            if b.get("simulated"):
                reply += " Es una demostración: no es una reserva real."
        # Contrato C2: el huésped ve texto plano con montos en pesos chilenos y bloques separados por una
        # línea en blanco (C1), nunca el Markdown que escribió el modelo.
        result.reply = chat_format(reply)[:MAX_REPLY]
        session.add("user", user_text, self.settings.ai_max_history)
        session.add("assistant", result.reply, self.settings.ai_max_history)
        result.quick_replies = quick_replies(session, result)
        return result


def _asked_text(session: AiSession) -> str:
    return normalize(" ".join(str(m.get("content") or "") for m in session.history if m.get("role") == "user"))


def _fresh(candidates, asked: str) -> list[str]:
    """Sugerencias del turno que el huésped no preguntó ya en esta sesión."""
    return [text for text, words in candidates if not any(word in asked for word in words)][:3]


def _chosen_room(session: AiSession) -> str | None:
    """La habitación que el huésped nombró, solo si la mención es inequívoca."""
    options = (session.state.get("last_availability") or {}).get("options") or {}
    asked = _asked_text(session)
    matched = [
        code
        for code, info in options.items()
        if normalize(str(info.get("name") or "")).replace("habitacion ", "", 1) in asked
        or normalize(code) in asked
    ]
    return matched[0] if len(matched) == 1 else None


def _spoken_name(text: str) -> str | None:
    """Nombre que dijo el huésped («soy Camila Rojas»); nunca uno inventado por el modelo."""
    match = SPOKEN_NAME.search(text)
    if not match:
        return None
    words: list[str] = []
    for word in match.group(1).split():
        if word.lower() in NAME_STOPWORDS:
            break
        words.append(word)
        if len(words) == 4:
            break
    candidate = " ".join(words).strip(" .-")
    if len(candidate.split()) < 2 or not GUEST_NAME.match(candidate):
        return None
    return candidate


def quick_replies(session: AiSession, result: AgentResult) -> list[str]:
    """Sugerencias por paso: nunca repiten una pregunta que el huésped ya hizo en esta sesión."""
    asked = _asked_text(session)
    if result.booking:
        return _fresh((*QUICK_POOL, *QUICK_LOCATION, *QUICK_BOOK), asked)
    if session.state.get("pending_booking"):
        return _fresh(QUICK_PROPOSAL, asked)
    last = session.state.get("last_availability")
    if last and "check_availability" in result.tools:
        if not last["options"]:
            return _fresh((*QUICK_OTHER_DATES, *QUICK_HUMAN), asked)
        names = [info["name"].removeprefix("Habitación ") for info in last["options"].values()]
        rooms = [(f"Quiero la {name}", (normalize(name),)) for name in names]
        return _fresh((*rooms, *QUICK_HUMAN), asked)
    if not session.state.get("seen_location"):
        return _fresh((*QUICK_LOCATION, *QUICK_POOL, *QUICK_BOOK), asked)
    return _fresh((*QUICK_BOOK, *QUICK_SERVICES, *QUICK_HUMAN), asked)
