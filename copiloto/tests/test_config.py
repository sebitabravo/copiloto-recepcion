from dataclasses import replace

import pytest
from copiloto.app import create_app
from copiloto.config import Settings
from copiloto.store import anonymous_id


def test_production_refuses_to_start_with_weak_or_missing_secrets(settings, harness):
    prod = replace(settings, env="production")
    with pytest.raises(ValueError, match="PSEUDONYM_SALT"):
        create_app(prod, chatwoot=harness.chatwoot, pms=harness.pms, run_workers=False, db=harness.db)


def test_production_starts_with_strong_secrets(settings, harness):
    strong = replace(settings, env="production", webhook_secret="w" * 32, pms_events_secret="p" * 32,
                     panel_token="t" * 32, pseudonym_salt="s" * 32, chatwoot_bot_token="b" * 32)
    assert create_app(strong, chatwoot=harness.chatwoot, pms=harness.pms, run_workers=False, db=harness.db)


def test_development_does_not_require_secrets(settings, harness):
    assert settings.env == "development"
    assert create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, run_workers=False, db=harness.db)


def test_pseudonyms_depend_on_the_secret_salt():
    assert anonymous_id(7, "a" * 16) == anonymous_id(7, "a" * 16)
    assert anonymous_id(7, "a" * 16) != anonymous_id(7, "b" * 16)
    assert anonymous_id(7, "a" * 16) < 0


def test_equal_shift_start_and_end_means_a_24_hour_shift(settings):
    from conftest import local_epoch
    always = replace(settings, shift_start="00:00", shift_end="00:00")
    for hour, minute in ((0, 0), (12, 30), (23, 59)):
        assert always.in_shift(local_epoch(2026, 10, 28, hour, minute))


def test_overnight_and_regular_shifts(settings):
    from conftest import local_epoch
    assert settings.in_shift(local_epoch(2026, 10, 28, 8, 0))
    assert not settings.in_shift(local_epoch(2026, 10, 28, 22, 0))
    overnight = replace(settings, shift_start="20:00", shift_end="06:00")
    assert overnight.in_shift(local_epoch(2026, 10, 28, 23, 30))
    assert overnight.in_shift(local_epoch(2026, 10, 28, 5, 59))
    assert not overnight.in_shift(local_epoch(2026, 10, 28, 12, 0))


@pytest.mark.parametrize("url", ["http://pms-mock:8200", "http://localhost:8200/", "http://127.0.0.1:8200"])
def test_demo_sandbox_only_accepts_known_local_mock_destinations(settings, url):
    assert replace(settings, pms_url=url).demo_sandbox_authorized is True


@pytest.mark.parametrize("changes", [
    {"pms_adapter": "none"}, {"pms_url": "https://pms-mock:8200"},
    {"pms_url": "http://hotel.example:8200"}, {"pms_url": "http://pms-mock:8200.evil.test"},
    {"pms_url": "http://user@pms-mock:8200"}, {"pms_url": "http://localhost:8200/api"},
    {"pms_url": "http://localhost:8200?target=real"}, {"pms_booking_path": "/api/v1/bookings/"},
    {"pms_booking_path": "https://hotel.example/bookings"}, {"pms_booking_path": "/api/v1/../bookings"},
])
def test_demo_sandbox_fails_closed_for_other_destinations_and_paths(settings, changes):
    assert replace(settings, **changes).demo_sandbox_authorized is False


def test_production_rejects_non_loopback_http_public_url(settings):
    strong = replace(settings, env="production", webhook_secret="w" * 32, pms_events_secret="p" * 32,
                     panel_token="t" * 32, pseudonym_salt="s" * 32, chatwoot_bot_token="b" * 32,
                     public_url="http://hotel.example")
    with pytest.raises(ValueError, match="HTTPS"):
        strong.validate_runtime()


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("YES", True), (" on ", True),
    ("0", False), ("false", False), ("no", False), ("False", False), ("off", False), ("", False),
])
def test_demo_enabled_uses_an_explicit_truthy_set(monkeypatch, value, expected):
    """«False», «off» y «» no activan la demo: solo un conjunto explícito de valores verdaderos."""
    monkeypatch.setenv("DEMO_ENABLED", value)
    assert Settings.from_env().demo_enabled is expected


def test_prebooking_minutes_is_read_from_the_environment(monkeypatch):
    """docs/ia.md promete PREBOOKING_MINUTES con 15 por defecto: Settings debe leerla."""
    monkeypatch.delenv("PREBOOKING_MINUTES", raising=False)
    assert Settings.from_env().prebooking_minutes == 15
    monkeypatch.setenv("PREBOOKING_MINUTES", "45")
    assert Settings.from_env().prebooking_minutes == 45


@pytest.mark.parametrize("name,field,default", [
    ("PREBOOKING_MINUTES", "prebooking_minutes", 15),
    ("RETENTION_DAYS", "retention_days", 90),
])
def test_blank_knob_values_count_as_unconfigured(monkeypatch, name, field, default):
    """El compose pasa `${VAR:-}`: la variable existe pero llega vacía cuando el .env no la define.
    Un valor en blanco debe tratarse como ausente (por defecto documentado), no romper int("")."""
    monkeypatch.setenv(name, "")
    assert getattr(Settings.from_env(), field) == default
    monkeypatch.setenv(name, "   ")
    assert getattr(Settings.from_env(), field) == default


@pytest.mark.parametrize("name,field,value,expected", [
    ("PREBOOKING_MINUTES", "prebooking_minutes", " 30 ", 30),
    ("RETENTION_DAYS", "retention_days", " 7 ", 7),
])
def test_knob_values_surrounding_whitespace_are_still_parsed(monkeypatch, name, field, value, expected):
    monkeypatch.setenv(name, value)
    assert getattr(Settings.from_env(), field) == expected


def test_sampling_settings_come_from_the_environment(monkeypatch):
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    monkeypatch.delenv("LLM_TOP_P", raising=False)
    default = Settings.from_env()
    assert default.llm_temperature == 0.3 and default.llm_top_p is None
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("LLM_TOP_P", "0.8")
    tuned = Settings.from_env()
    assert tuned.llm_temperature == 0.7 and tuned.llm_top_p == 0.8
    # El compose pasa `${VAR:-}`: en blanco cuenta como sin configurar.
    monkeypatch.setenv("LLM_TEMPERATURE", " ")
    monkeypatch.setenv("LLM_TOP_P", "")
    blank = Settings.from_env()
    assert blank.llm_temperature == 0.3 and blank.llm_top_p is None


# --- Perfil Docker liviano (make up): arranca sin Chatwoot sembrado y con el webhook cerrado ---

LIGHT_SECRETS = {"PMS_EVENTS_SECRET": "p" * 32, "PANEL_TOKEN": "t" * 32, "PSEUDONYM_SALT": "s" * 32,
                 "WEBHOOK_SECRET": "w" * 32, "COPILOTO_ENV": "production"}


def test_light_profile_boots_without_the_chatwoot_bot_token(monkeypatch):
    """Copia limpia: bootstrap crea .env, pero CHATWOOT_BOT_TOKEN solo llega al sembrar Chatwoot."""
    for key, value in LIGHT_SECRETS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CHATWOOT_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CHATWOOT_ENABLED", raising=False)
    settings = Settings.from_env()
    assert settings.chatwoot_enabled is False
    settings.validate_runtime()


def test_the_bot_token_is_required_when_the_chatwoot_integration_is_enabled(monkeypatch):
    for key, value in LIGHT_SECRETS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CHATWOOT_ENABLED", "1")
    monkeypatch.delenv("CHATWOOT_BOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="CHATWOOT_BOT_TOKEN"):
        Settings.from_env().validate_runtime()
    monkeypatch.delenv("CHATWOOT_ENABLED")
    monkeypatch.setenv("CHATWOOT_BOT_TOKEN", "b" * 32)
    assert Settings.from_env().chatwoot_enabled is True, "con el token sembrado la integración queda activa"


def test_the_webhook_stays_closed_without_the_integration(settings):
    from conftest import FakeChatwoot, FakePms
    from copiloto.app import create_app
    from copiloto.events import connect, init_db
    from fastapi.testclient import TestClient

    db = connect(":memory:")
    init_db(db)
    closed = TestClient(create_app(replace(settings, chatwoot_enabled=False), chatwoot=FakeChatwoot(), pms=FakePms(),
                                   run_workers=False, db=db))
    assert closed.post("/webhooks/chatwoot", json={"event": "message_created"}).status_code == 503
    opened = TestClient(create_app(settings, chatwoot=FakeChatwoot(), pms=FakePms(), run_workers=False, db=db))
    assert opened.post("/webhooks/chatwoot", json={"event": "message_created"}).status_code == 401, "sin firma"
