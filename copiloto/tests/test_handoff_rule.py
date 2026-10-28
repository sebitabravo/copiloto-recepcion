"""Pedir una persona es una acción del producto, no una decisión del modelo (R4).

Regresión: con un modelo local, «quiero hablar con una persona» recibía una respuesta amable pero
sin derivación registrada.
"""

from conftest import say


async def test_asking_for_a_person_records_the_handoff(make_ai):
    h, _ = make_ai([say("Te paso con una persona de recepción.")])
    await h.say("hola")
    await h.say("quiero hablar con una persona de recepción")
    assert h.events("handoff"), "la derivación no puede depender de que el modelo la decida"
