"""Respuestas guiadas sin IA para la demo web cuando el modelo no está configurado o falla."""

from copiloto.hotel import HotelData
from copiloto.textutil import normalize

LOCATION_TERMS = ("ubicacion", "donde", "direccion", "como llego", "mapa", "llegar", "queda")
BOOKING_TERMS = ("reserv", "disponib", "precio", "tarifa", "cotiz", "habitacion", "cupo")


def guided_reply(hotel: HotelData, text: str) -> tuple[str, list[str]]:
    plain = normalize(text)
    faq = hotel.match_faq(text)
    if faq:
        return faq.answer, ["¿Cómo llego?", "¿Qué servicios tienen?"]
    if any(term in plain for term in LOCATION_TERMS):
        loc = hotel.location
        return (f"{loc['headline']} {loc['detail']} Dirección: {hotel.hotel['address']}.",
                ["¿Tienen piscina?", "Quiero reservar"])
    if any(term in plain for term in BOOKING_TERMS):
        return ("Para reservar necesito la inteligencia artificial del asistente, que en este servidor no está "
                "configurada. Mientras tanto puedes probar la bandeja real de recepción con el botón «Abrir el chat».",
                ["¿Cómo llego?", "¿Tienen piscina?"])
    return ("Puedo contarte sobre la ubicación, los servicios y las políticas del hotel. "
            "¿Qué te gustaría saber?", ["¿Cómo llego?", "¿Tienen piscina?", "¿Cuál es el horario de check-in?"])
