from copiloto.privacy import render


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
    page = render(harness.hotel, voice=True)
    assert "ElevenLabs" in page
    assert "Google" in page
    assert "No guardamos el audio" in page


def test_existing_provider_disclosures_preserved(harness):
    local = render(harness.hotel, "modelo-local", "http://localhost:11434/v1")
    external = render(harness.hotel, "modelo-externo", "https://provider.example/v1")
    assert "no se envían a proveedores externos" in local
    assert "viajan a ese proveedor" not in local
    assert "viajan a ese proveedor" in external
    assert "ElevenLabs" not in local
