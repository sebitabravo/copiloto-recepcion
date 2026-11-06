from copiloto.guided import guided_reply


def test_booking_fallback_does_not_claim_missing_configuration(harness):
    reply, suggestions = guided_reply(harness.hotel, "Quiero reservar")
    assert "no crea reservas ni consulta disponibilidad" in reply
    assert "Chatwoot" in reply
    assert "no está configurada" not in reply
    assert suggestions == ["¿Cómo llego?", "¿Tienen piscina?"]


def test_location_and_faq_remain_available(harness):
    reply, _ = guided_reply(harness.hotel, "¿Cómo llego?")
    assert harness.hotel.hotel["address"] in reply
    reply, suggestions = guided_reply(harness.hotel, "¿Tienen piscina?")
    assert reply
    assert suggestions
