"""El aviso de privacidad debe decir la verdad sobre dónde se procesan los mensajes.

Con un modelo local no hay un tercero que reciba el texto, y el aviso no puede afirmarlo.
"""

from copiloto.hotel import HotelData
from copiloto.privacy import render


def test_local_model_is_not_reported_as_a_third_party(settings):
    hotel = HotelData.load(settings.hotel_data_path)
    page = render(hotel, "qwen2.5-7b-instruct", "http://host.docker.internal:11434/v1")
    assert "no se envían a proveedores externos" in page
    assert "viajan a ese proveedor" not in page


def test_external_provider_keeps_the_third_party_notice(settings):
    hotel = HotelData.load(settings.hotel_data_path)
    page = render(hotel, "deepseek-flash", "https://api.deepseek.com")
    assert "viajan a ese proveedor" in page
