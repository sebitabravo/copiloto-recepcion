"""El «sí» del huésped no lo declara el modelo: se verifica sobre el texto que escribió.

Regresión: antes, `guest_confirmed=true` era un argumento que la IA podía inventar, así que una
pregunta del huésped ("¿cuánto sale?") bastaba para crear la reserva.
"""

from conftest import call, say
from copiloto.ai.tools import guest_said_yes

STAY = {"checkin": "2026-11-15", "checkout": "2026-11-18", "adults": 2, "children": 1}


def test_only_an_explicit_answer_counts_as_confirmation():
    assert guest_said_yes("sí, la doble con jacuzzi, soy Camila Rojas")
    assert guest_said_yes("dale, confírmala")
    assert guest_said_yes("perfecto")
    assert not guest_said_yes("¿cuánto sale la doble?")
    assert not guest_said_yes("no, mejor otra")
    assert not guest_said_yes("")
    assert not guest_said_yes(None)


async def test_booking_is_refused_when_the_guest_only_asked_a_question(make_ai):
    avail = call("check_availability", **STAY)
    book = call("create_booking", call_id="c2", guest_name="Camila Rojas", room_code="doble_con_jacuzzi",
                guest_confirmed=True, **STAY)
    h, _ = make_ai([avail, say("Te muestro las opciones."), book, say("Te repito el resumen.")])
    await h.say("hola")
    await h.say("2 adultos y 1 niño del 15 al 18 de noviembre")
    await h.say("¿cuánto sale la doble con jacuzzi?")
    assert h.pms.bookings == [], "una pregunta no es una confirmación del huésped"


async def test_booking_is_refused_when_the_model_invents_the_guest_name(make_ai):
    """El huésped nunca dio su nombre: la reserva no puede crearse aunque el modelo diga que sí."""
    avail = call("check_availability", **STAY)
    book = call("create_booking", call_id="c2", guest_name="Camila Rojas", room_code="doble_con_jacuzzi",
                guest_confirmed=True, **STAY)
    h, _ = make_ai([avail, say("Te muestro las opciones."), book, say("Listo.")])
    await h.say("hola")
    await h.say("2 adultos y 1 niño del 15 al 18 de noviembre")
    await h.say("perfecto, resérvala")
    assert h.pms.bookings == [], "el nombre lo debe aportar el huésped"
