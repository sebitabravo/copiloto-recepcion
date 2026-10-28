"""El agente no puede afirmar datos del hotel sin haber consultado una herramienta.

Regresión observada con un modelo local: respondió «calle Santa Fe 1234, Santiago» —
una dirección inventada— sin llamar a get_hotel_info.
"""

import json

from conftest import say
from copiloto.ai.agent import SAFE_NO_DATA


def tools_used(harness):
    used = []
    for row in harness.events("ai_reply"):
        used.extend(json.loads(row["payload"]).get("tools", []))
    return used


async def test_a_question_about_the_hotel_consults_the_tool_first(make_ai):
    h, _ = make_ai([say("El hotel queda camino a Pucón.")])
    await h.say("hola")
    await h.say("¿dónde están ubicados?")
    assert "get_hotel_info" in tools_used(h), "la ubicación se consulta, no se recuerda de memoria"


async def test_invented_reply_without_tools_is_replaced(make_ai):
    h, _ = make_ai([say("Estamos en calle Santa Fe 1234, pleno centro de Santiago.")])
    await h.say("hola")
    await h.say("cuéntame algo interesante del lugar")
    assert h.chatwoot.guest_texts()[-1] == SAFE_NO_DATA
