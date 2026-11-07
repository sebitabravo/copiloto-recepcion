"""Tono humano del asistente (S6): prompt 2026-11.2, formato de chat (C1, C2), plantillas y respuestas rápidas.

La guía de agentes pide texto plano, turnos cortos, una pregunta como máximo, frase fija para el dato ausente
e identidad honesta; el servidor garantiza el formato aunque el modelo escriba Markdown o montos en inglés.
"""

import json
from dataclasses import replace

import httpx
import pytest
from conftest import call, say
from copiloto.ai.agent import MAX_REPLY, SAFE_NARRATION, SAFE_NO_BOOKING, SAFE_NO_DATA, STUCK
from copiloto.ai.llm import LlmClient
from copiloto.ai.prompts import MISSING_DATA, PROMPT_VERSION, VOICE_NOTE, build_system_prompt
from copiloto.ai.sessions import AiSession
from copiloto.ai.tools import ToolHooks
from copiloto.flow import AI_FALLBACK_NOTICE
from copiloto.textutil import chat_format
from test_booking_proposal import prepare

STAY = {"checkin": "2026-11-15", "checkout": "2026-11-18", "adults": 2, "children": 1}
JARGON = ("sistema", "asistente inteligente", "menú guiado", "pms", "herramienta", "modelo de lenguaje")


# ---------- formato de chat (C2) ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("**Doble con Jacuzzi**: $85.000 la noche", "Doble con Jacuzzi: $85.000 la noche"),
        ("__Suite__ lista", "Suite lista"),
        ("### Opciones\nDoble", "Opciones\nDoble"),
        ("Usa `check-in` a las 15:00", "Usa check-in a las 15:00"),
        (
            "1. **Doble Sin Vista**: $70.000\n2. **Doble con Jacuzzi**: $85.000",
            "1. Doble Sin Vista: $70.000\n2. Doble con Jacuzzi: $85.000",
        ),
        ("* Piscina\n* Tinajas", "- Piscina\n- Tinajas"),
        ("Es *gratis* para niños", "Es *gratis* para niños"),
        ("```\nhola\n```", "hola"),
    ],
)
def test_markdown_is_stripped_to_plain_chat_text(raw, expected):
    assert chat_format(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$65,000 la noche", "$65.000 la noche"),
        ("$65000 la noche", "$65.000 la noche"),
        ("total $ 1,250,000.", "total $1.250.000."),
        ("total $255000, con desayuno", "total $255.000, con desayuno"),
        ("$65.000 ya está bien", "$65.000 ya está bien"),
        ("$500 de propina", "$500 de propina"),
        ("el 15/11/2026 a las 15:00", "el 15/11/2026 a las 15:00"),
    ],
)
def test_amounts_use_the_chilean_format(raw, expected):
    assert chat_format(raw) == expected


def test_blank_lines_collapse_and_cap_three_blocks_without_losing_text():
    raw = "Hola, Camila.  \n\n\n\nTenemos dos opciones.\n\n\nDoble: $70.000\n\nJacuzzi: $85.000\n\n¿Cuál prefieres?\n"
    out = chat_format(raw)
    assert "\n\n\n" not in out and out == out.strip()
    assert len(out.split("\n\n")) == 3
    for piece in ("Hola, Camila.", "Tenemos dos opciones.", "Doble: $70.000", "Jacuzzi: $85.000", "¿Cuál prefieres?"):
        assert piece in out
    assert all(line == line.rstrip() for line in out.splitlines())


async def test_chatwoot_reply_is_plain_text_with_chilean_amounts_in_one_message(make_ai):
    h, _ = make_ai([
        call("check_availability", **STAY),
        say("**Doble Sin Vista**: $70,000 la noche\n\n\n\n**Doble con Jacuzzi**: $85000 la noche"),
    ])
    await h.say("hola")
    before = len(h.chatwoot.guest_texts())
    await h.say("2 adultos y 1 niño del 15 al 18 de noviembre")
    assert h.chatwoot.guest_texts()[before:] == [
        "Doble Sin Vista: $70.000 la noche\n\nDoble con Jacuzzi: $85.000 la noche"
    ]


async def test_reply_cap_still_applies_after_formatting(make_ai):
    h, _ = make_ai([say("Hola.\n\n" + "palabra " * 400)])
    result = await h.core.agent.respond(AiSession("demo:cap"), "cuéntame", ToolHooks())
    assert len(result.reply) <= MAX_REPLY and result.reply.startswith("Hola.")


# ---------- prompt 2026-11.2 ----------


def test_prompt_speaks_as_the_hotel_in_short_plain_turns():
    assert PROMPT_VERSION == "2026-11.2"
    prompt = build_system_prompt("2026-10-28", "miércoles", "assisted", "Hotel Bordeluz")
    for rule in (
        "primera persona plural",
        "«tenemos piscina»",
        "1 a 3 frases cortas",
        "como máximo una pregunta por turno",
        "No termines siempre con una pregunta",
        "entusiasmo automático",
        "devuelve el saludo",
        "su nombre",
        "Texto plano, sin Markdown",
        "Doble con Jacuzzi: $80.000 la noche, $240.000 en total",
        "una línea en blanco",
        MISSING_DATA,
        "asistente virtual",
        "sin prometer",
        "NO puedes crear reservas",
    ):
        assert rule in prompt, rule
    assert "listas con guiones" not in prompt
    # El rol es breve: la guía pide no incluir personalidad extensa.
    assert len(prompt.split("\n\n")[0]) < 400


def test_voice_note_keeps_the_same_identity_and_drops_chat_blocks():
    assert "asistente virtual" in VOICE_NOTE and "bloques" in VOICE_NOTE
    assert "sin markdown" in VOICE_NOTE.lower()


# ---------- plantillas del servidor ----------


def test_fixed_templates_sound_like_reception_not_like_a_system():
    for text in (SAFE_NO_DATA, SAFE_NARRATION, STUCK, SAFE_NO_BOOKING, AI_FALLBACK_NOTICE):
        lowered = text.lower()
        assert not [word for word in JARGON if word in lowered], text
        assert text.count("?") <= 1, text


async def test_assisted_mode_correction_does_not_promise_to_register_the_booking(make_ai, ai_settings):
    h, _ = make_ai([say("¡Tu reserva está confirmada!")], replace(ai_settings, ai_mode="assisted"))
    result = await h.core.agent.respond(AiSession("demo:assisted"), "reserva ya", ToolHooks())
    assert "Todavía no hay una reserva creada" in result.reply and "Recepción" in result.reply
    assert "registrada" not in result.reply and result.guardrails == ["confirmation_without_booking"]


async def test_llm_outage_notice_is_a_human_apology_followed_by_the_menu(make_ai):
    from copiloto.ai.llm import LlmUnavailable

    h, _ = make_ai([LlmUnavailable("http 503")])
    await h.say("hola")
    await h.say("quiero reservar")
    texts = h.chatwoot.guest_texts()
    assert AI_FALLBACK_NOTICE in texts and "asistente inteligente" not in " ".join(texts)
    assert h.chatwoot.messages[-1]["options"], "queda el menú de botones"


async def test_ai_welcome_is_warm_and_honest_about_ai_demo_and_provider(make_ai, ai_settings):
    h, _ = make_ai([])
    await h.say("hola")
    first = h.chatwoot.guest_texts()[0]
    assert first.startswith("¡Hola!") and "inteligencia artificial" in first and "privacidad" in first
    assert "demostración" in first and "no escribas datos personales reales" in first
    assert "tercero" not in first, "con el modelo local ningún tercero recibe el texto"
    assert "(demo)" not in first and "Soy el asistente" not in first
    external, _ = make_ai([], replace(ai_settings, llm_base_url="https://api.deepseek.com"))
    await external.say("hola")
    assert "de un tercero" in external.chatwoot.guest_texts()[0]


async def test_guided_welcome_is_warm_and_keeps_the_human_confirmation(harness):
    await harness.say("hola")
    first = harness.chatwoot.guest_texts()[0]
    assert first.startswith("¡Hola!") and "recepción" in first and "privacidad" in first
    assert "(demo)" not in first and "Copiloto de Recepción" not in first
    assert harness.chatwoot.guest_texts()[1].startswith("Ubicación:")


async def test_server_proposal_reads_like_a_receptionist_and_keeps_every_field(make_ai):
    _, _, _, result = await prepare(make_ai)
    reply = result.reply
    for value in ("Camila", "Doble con Jacuzzi", "2026-11-15", "2026-11-18", "$255.000", "3 noches",
                  "2 adultos", "1 niño", "Todavía no hay una reserva creada", "¿Confirmas", "Sí, confirmo la reserva"):
        assert value in reply, value
    assert "(doble_con_jacuzzi)" not in reply and "PMS" not in reply
    assert len(reply.split("\n\n")) <= 3 and reply.count("?") <= 1


# ---------- respuestas rápidas ----------


async def test_quick_replies_never_repeat_a_question_the_guest_already_asked(make_ai):
    h, _ = make_ai([say("Sí, tenemos piscina temperada todo el año."), say("Estamos a orillas del lago.")])
    session = AiSession("demo:qr")
    result = await h.core.agent.respond(session, "hola, ¿tienen piscina?", ToolHooks())
    assert result.quick_replies and not any("piscina" in q.lower() for q in result.quick_replies)
    result = await h.core.agent.respond(session, "¿cómo llego?", ToolHooks())
    asked = " ".join(result.quick_replies).lower()
    assert result.quick_replies and "piscina" not in asked and "llego" not in asked


async def test_quick_replies_follow_the_step_of_the_conversation(make_ai):
    h, _ = make_ai([call("check_availability", **STAY), say("Para esas fechas no nos queda cupo.")])
    h.pms.offers = []
    result = await h.core.agent.respond(AiSession("demo:full"), "2 adultos y 1 niño del 15 al 18 de noviembre",
                                        ToolHooks())
    assert "Probar otras fechas" in result.quick_replies
    _, _, _, proposal = await prepare(make_ai)
    assert proposal.quick_replies and not any(q.startswith("Quiero la") for q in proposal.quick_replies)
    assert "Quiero cambiar algo" in proposal.quick_replies


# ---------- muestreo configurable ----------


async def test_llm_client_sends_top_p_only_when_configured_and_no_server_specific_params():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hola"}}]})

    client = LlmClient("http://localhost:11434/v1", "local", "m",
                       http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await client.chat([{"role": "user", "content": "hola"}])
    await client.chat([{"role": "user", "content": "hola"}], temperature=0.7, top_p=0.8)
    assert bodies[0]["temperature"] == 0.3 and "top_p" not in bodies[0]
    assert bodies[1]["temperature"] == 0.7 and bodies[1]["top_p"] == 0.8
    for body in bodies:
        assert not {"top_k", "min_p", "repeat_penalty", "chat_template_kwargs"} & set(body)


async def test_agent_uses_the_configured_sampling(make_ai, ai_settings):
    class Recorder:
        def __init__(self):
            self.kwargs = []

        async def chat(self, messages, tools=None, **kwargs):
            self.kwargs.append(kwargs)
            return say("Hola, ¿en qué te ayudo?")

    for settings, expected in (
        (ai_settings, {"temperature": 0.3}),
        (replace(ai_settings, llm_temperature=0.7, llm_top_p=0.8), {"temperature": 0.7, "top_p": 0.8}),
    ):
        h, _ = make_ai([], settings)
        h.core.agent.llm = recorder = Recorder()
        await h.core.agent.respond(AiSession("demo:sampling"), "hola", ToolHooks())
        assert {k: v for k, v in recorder.kwargs[0].items() if k in ("temperature", "top_p")} == expected


# ---------- contrato con el servidor del modelo ----------


async def test_the_model_always_receives_a_single_system_message_first(make_ai):
    """Regresión: Qwen3.5 rechaza un `system` a mitad de la conversación («System message must be at the
    beginning»). Los datos verificados del turno viajan dentro del único mensaje de sistema."""
    h, llm = make_ai([
        say("Tenemos piscina temperada todo el año."),
        say("Te paso con recepción."),
        say("Déjame revisar."),
        say("Para esas fechas tenemos dos opciones."),
    ])
    await h.core.agent.respond(AiSession("demo:a"), "¿tienen piscina?", ToolHooks())
    await h.core.agent.respond(AiSession("demo:b"), "quiero hablar con una persona", ToolHooks())
    await h.core.agent.respond(AiSession("demo:c"), "2 adultos y 1 niño del 15 al 18 de noviembre", ToolHooks())
    assert len(llm.calls) == 4
    for sent in llm.calls:
        systems = [index for index, m in enumerate(sent["messages"]) if m["role"] == "system"]
        assert systems == [0], sent["messages"]
    assert "piscina" in llm.calls[0]["messages"][0]["content"].lower()
    assert "Aviso a recepción" in llm.calls[1]["messages"][0]["content"]
    assert "Disponibilidad leída del PMS" in llm.calls[3]["messages"][0]["content"]


async def test_complete_booking_data_gets_the_server_proposal_even_if_the_model_writes_its_own(make_ai):
    """Con un modelo real se vio un resumen propio sin create_booking: el huésped tenía que decir sí dos veces."""
    h, llm = make_ai([
        call("check_availability", **STAY),
        say("Para esas fechas tenemos la Doble con Jacuzzi y la Doble Sin Vista."),
        say("Muy bien. ¿A nombre de quién la dejamos?"),
        say("La Doble con Jacuzzi cuesta $255.000 en total. ¿Confirma esta opción, Camila?"),
    ])
    session = AiSession("demo:nudge")
    await h.core.agent.respond(session, "2 adultos y 1 niño del 15 al 18 de noviembre", ToolHooks())
    chosen = await h.core.agent.respond(session, "quiero la doble con jacuzzi", ToolHooks())
    assert not any(e["type"] == "booking_proposal" for e in chosen.events), "sin nombre no hay propuesta"
    result = await h.core.agent.respond(session, "soy Camila Rojas", ToolHooks())
    proposal = next(e for e in result.events if e["type"] == "booking_proposal")
    assert proposal["room_code"] == "doble_con_jacuzzi" and proposal["guest_name"] == "Camila Rojas"
    assert "¿Confirmas" in result.reply and "¿Confirma esta opción" not in result.reply and h.pms.bookings == []
    book = {**STAY, "guest_name": "Camila Rojas", "room_code": "doble_con_jacuzzi", "guest_confirmed": True}
    llm.script.extend([call("create_booking", **book), say("Listo, Camila.")])
    result = await h.core.agent.respond(session, "Sí, confirmo la reserva", ToolHooks())
    assert result.booking and len(h.pms.bookings) == 1, "un solo «sí» basta tras el resumen del servidor"


async def test_assisted_mode_never_prepares_a_proposal_on_its_own(make_ai, ai_settings):
    h, _ = make_ai([
        call("check_availability", **STAY),
        say("Tenemos la Doble con Jacuzzi."),
        say("Gracias, Camila. Recepción confirma la reserva."),
    ], replace(ai_settings, ai_mode="assisted"))
    session = AiSession("demo:assisted-nudge")
    await h.core.agent.respond(session, "2 adultos y 1 niño del 15 al 18 de noviembre", ToolHooks())
    result = await h.core.agent.respond(session, "la doble con jacuzzi, soy Camila Rojas", ToolHooks())
    assert not any(e["type"] == "booking_proposal" for e in result.events)
    assert "create_booking" not in result.tools and h.pms.bookings == []


async def test_one_explicit_yes_to_the_server_summary_books_even_if_the_model_forgets_the_tool(make_ai):
    """Transcripción real de qwen3-4b: tras el resumen del servidor el modelo no llamó create_booking
    y afirmó «la reserva quedó hecha» sin reserva. Un sí explícito debe bastar, y la afirmación sin
    reserva no puede llegar al huésped."""
    h, llm = make_ai([
        call("check_availability", **STAY),
        say("Perfecto, reservaremos del 15 al 18 de noviembre. ¿Cuál es el nombre completo del huésped?"),
        say("La Doble con Jacuzzi cuesta $255.000 en total. ¿Cuál es el nombre completo del huésped?"),
        say("La Doble con Jacuzzi cuesta $255.000 en total. ¿Confirma esta opción, Camila?"),
        say("Perfecto, la reserva de Camila Rojas quedó hecha. ¡Bienvenida!"),
    ])
    session = AiSession("demo:oneyes")
    await h.core.agent.respond(session, "quiero reservar del 15 al 18 de noviembre para 2 adultos y 1 niño",
                               ToolHooks())
    await h.core.agent.respond(session, "la doble con jacuzzi", ToolHooks())
    await h.core.agent.respond(session, "soy Camila Rojas", ToolHooks())
    assert h.pms.bookings == [], "la propuesta no es una reserva"
    result = await h.core.agent.respond(session, "Sí, confirmo la reserva", ToolHooks())
    assert len(h.pms.bookings) == 1 and result.booking is not None
    assert any(e.get("type") == "booking_created" for e in result.events)
    assert "Reserva de demostración #7" in result.reply and "no es una reserva real" in result.reply


async def test_no_past_tense_booking_claim_reaches_the_guest_without_a_booking(make_ai):
    claims = [
        "Perfecto, la reserva quedó hecha: Doble con Jacuzzi.",
        "Listo, tu reserva creada para el 15 de noviembre.",
        "La reserva quedó registrada a tu nombre.",
        "¡Tu reserva está confirmada!",
    ]
    for text in claims:
        h, _ = make_ai([say(text)])
        result = await h.core.agent.respond(AiSession("demo:claim"), "te confirmo", ToolHooks())
        assert "Todavía no hay una reserva creada" in result.reply, text
        assert h.pms.bookings == [], text
