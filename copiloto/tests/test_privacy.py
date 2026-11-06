"""El aviso de privacidad debe decir la verdad sobre dónde se procesan los mensajes.

Con un modelo local no hay un tercero que reciba el texto, y el aviso no puede afirmarlo.
"""

from dataclasses import replace
from pathlib import Path

from conftest import FakeChatwoot
from copiloto.app import create_app
from copiloto.privacy import render
from fastapi.testclient import TestClient


def test_privacy_distinguishes_autonomous_assisted_and_simulated_handoff(harness):
    page = render(harness.hotel)
    assert "modo completo" in page
    assert "confirmación explícita" in page
    assert "asistido y de voz" in page
    assert "no notifica a recepción" in page
    assert "no elimina reservas del PMS" in page
    assert "no constituye una certificación legal" in page
    assert "El asistente no confirma reservas: solo" not in page


def test_voice_disclosure_preserved(harness):
    page = render(hotel=harness.hotel, voice=True)
    assert "ElevenLabs" in page
    assert "Google" in page
    assert "No guardamos el audio" in page


def test_local_model_is_not_reported_as_a_third_party(settings):
    from copiloto.hotel import HotelData

    hotel = HotelData.load(settings.hotel_data_path)
    page = render(hotel, "qwen2.5-7b-instruct", "http://host.docker.internal:11434/v1")
    assert "no se envían a proveedores externos" in page
    assert "viajan a ese proveedor" not in page


def test_external_provider_keeps_the_third_party_notice(settings):
    from copiloto.hotel import HotelData

    hotel = HotelData.load(settings.hotel_data_path)
    page = render(hotel, "deepseek-flash", "https://api.deepseek.com")
    assert "viajan a ese proveedor" in page


def test_notice_renders_the_retention_value_it_is_given(harness):
    assert "90 días" in render(harness.hotel, retention_days=90)
    assert "45 días" in render(harness.hotel, retention_days=45)


def _demo_client(harness, hotel_path):
    settings = replace(harness.settings, hotel_data_path=str(hotel_path))
    app = create_app(settings, chatwoot=FakeChatwoot(), pms=harness.pms, run_workers=False, db=harness.db)
    return TestClient(app), app


def test_privacy_notice_and_purge_share_one_retention_source(harness, tmp_path, monkeypatch):
    """Una sola fuente de verdad: el aviso publicado y la purga leen el mismo valor de retención."""
    custom = tmp_path / "hotel.yaml"
    custom.write_text(
        Path(harness.settings.hotel_data_path)
        .read_text(encoding="utf-8")
        .replace("retention_days: 90", "retention_days: 60"),
        encoding="utf-8",
    )
    monkeypatch.delenv("RETENTION_DAYS", raising=False)
    client, app = _demo_client(harness, custom)
    assert app.state.settings.retention_days == 60
    assert "60 días" in client.get("/privacidad").text


def test_retention_env_override_wins_over_the_hotel_yaml(harness, monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "7")
    client, app = _demo_client(harness, harness.settings.hotel_data_path)
    assert app.state.settings.retention_days == 7
    assert "7 días" in client.get("/privacidad").text
