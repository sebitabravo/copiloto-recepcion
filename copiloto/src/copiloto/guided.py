"""Respuestas guiadas sin IA para la demo web cuando el modelo no está configurado o falla."""

from copiloto.hotel import HotelData
from copiloto.textutil import normalize
from copiloto.voice import guess_language

LOCATION_TERMS = ("ubicacion", "donde", "direccion", "como llego", "mapa", "llegar", "queda")
BOOKING_TERMS = ("reserv", "disponib", "precio", "tarifa", "cotiz", "habitacion", "cupo")


GREETINGS = ("hola", "holi", "buenas", "buenos dias", "buenas tardes", "buenas noches", "hello", "hi")


def _contact(hotel: HotelData) -> str:
    return f"{hotel.hotel['whatsapp']} o {hotel.hotel['email']}"


def guided_reply(hotel: HotelData, text: str) -> tuple[str, list[str]]:
    plain = normalize(text)
    faq = hotel.match_faq(text)
    if faq:
        english = guess_language(text) == "en" and faq.answer_en
        return (faq.answer_en if english else faq.answer), ["¿Cómo llego?", "¿Qué servicios tienen?"]
    if any(term in plain for term in LOCATION_TERMS):
        loc = hotel.location
        return (f"{loc['headline']} {loc['detail']} Dirección: {hotel.hotel['address']}.",
                ["¿Tienen piscina?", "Quiero reservar"])
    if guess_language(text) == "en" and not any(term in plain for term in BOOKING_TERMS):
        return (f"I don't have that information published. For details, contact reception: {_contact(hotel)}.",
                ["¿Cómo llego?", "¿Tienen piscina?"])
    if any(term in plain for term in BOOKING_TERMS):
        # Sin IA no se cotiza: se indica a quién escribir, sin mencionar la configuración del servidor
        return (f"Para revisar disponibilidad y precios, escribe a recepción: {_contact(hotel)}.",
                ["¿Cómo llego?", "¿Tienen piscina?"])
    if plain in GREETINGS or any(plain.startswith(greeting + " ") for greeting in GREETINGS):
        return ("Puedo contarte sobre la ubicación, los servicios y las políticas del hotel. "
                "¿Qué te gustaría saber?", ["¿Cómo llego?", "¿Tienen piscina?", "¿Cuál es el horario de check-in?"])
    return (f"No tengo ese dato publicado. Para confirmarlo, escribe a recepción: {_contact(hotel)}.",
            ["¿Cómo llego?", "¿Tienen piscina?", "¿Cuál es el horario de check-in?"])
