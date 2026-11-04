"""Modo sin IA: lo que el huésped recibe cuando el asistente con modelo no está disponible."""

from pathlib import Path

from copiloto.guided import guided_reply
from copiloto.hotel import HotelData

HOTEL = HotelData.load(str(Path(__file__).resolve().parents[2] / "data" / "hotel.yaml"))


def test_plural_questions_still_reach_their_verified_faq():
    reply, _ = guided_reply(HOTEL, "¿Aceptan tarjetas?")
    assert "abono del 50%" in reply


def test_unknown_topic_says_so_and_points_to_reception_without_inventing_facts():
    reply, _ = guided_reply(HOTEL, "¿Tienen gimnasio?")
    assert "No tengo ese dato" in reply
    assert HOTEL.hotel["whatsapp"] in reply and HOTEL.hotel["email"] in reply
    assert "Puedo contarte" not in reply


def test_price_question_without_ai_never_mentions_configuration():
    reply, _ = guided_reply(HOTEL, "¿Cuánto cuesta la habitación?")
    assert "configurada" not in reply and "inteligencia artificial" not in reply.lower()
    assert HOTEL.hotel["whatsapp"] in reply


def test_english_unknown_question_gets_an_english_pointer_to_reception():
    reply, _ = guided_reply(HOTEL, "Do you have a gym?")
    assert "reception" in reply.lower() and HOTEL.hotel["email"] in reply


def test_greeting_still_gets_the_menu_introduction():
    reply, quick = guided_reply(HOTEL, "hola")
    assert "Puedo contarte" in reply and quick


def test_english_questions_get_english_answers_for_the_core_topics():
    pool, _ = guided_reply(HOTEL, "Do you have a pool?")
    assert pool.startswith("We have a heated pool")
    breakfast, _ = guided_reply(HOTEL, "Is breakfast included?")
    assert "breakfast" in breakfast.lower()
    checkin, _ = guided_reply(HOTEL, "What time is check-in?")
    assert "15:00" in checkin and "12:00" in checkin


def test_spanish_questions_keep_the_spanish_answers():
    reply, _ = guided_reply(HOTEL, "¿Tienen piscina?")
    assert reply.startswith("Tenemos piscina temperada")
