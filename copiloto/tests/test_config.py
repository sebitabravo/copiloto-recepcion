from dataclasses import replace

import pytest
from copiloto.app import create_app
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
