"""Notas de voz: se transcriben aquí, el audio no queda guardado y el huésped siempre recibe respuesta."""

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from wa_bridge.bridge import UNSUPPORTED_REPLY, VOICE_NOTICE, VOICE_UNCLEAR_REPLY, Bridge
from wa_bridge.config import Settings
from wa_bridge.transcribe import AudioTooLong, WhisperTranscriber

from wa_bridge import store

GUEST = "56911111111@c.us"


class FakeChatwoot:
    def __init__(self):
        self.messages: list[tuple[str, int, str]] = []
        self.statuses: dict[int, str | None] = {}

    async def create_contact(self, chat_id, name):
        return "source-1"

    async def create_conversation(self, source_id):
        self.statuses[100] = "pending"
        return 100

    async def post_guest_message(self, source_id, conversation_id, content):
        self.messages.append((source_id, conversation_id, content))

    async def conversation_status(self, conversation_id):
        return self.statuses.get(conversation_id)


class FakeOpenWA:
    def __init__(self):
        self.sent: list[str] = []

    async def send_text(self, target, text):
        self.sent.append(text)

    async def allowed_session_ids(self):
        return {"default"}


class FakeTranscriber:
    def __init__(self, text="quiero una habitación", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    async def __call__(self, audio: bytes) -> str:
        self.calls.append(audio)
        if self.fail:
            raise RuntimeError("modelo no disponible")
        return self.text


def settings(**overrides) -> Settings:
    values = dict(openwa_url="http://openwa:2785", openwa_api_key="k", openwa_webhook_secret="s",
                  chatwoot_url="http://chatwoot:3000", chatwoot_account_id=1, chatwoot_admin_token="t",
                  inbox_identifier="ident", inbox_secret="i", db_path=":memory:", retry_delays_s=())
    values.update(overrides)
    return Settings(**values)


def voice_event(message_id="v1", audio=b"ogg-bytes", voice_type="voice"):
    return {"event": "message.received", "data": {
        "id": message_id, "chatId": GUEST, "from": GUEST, "body": "", "type": voice_type,
        "fromMe": False, "isGroup": False, "contact": {"pushName": "Ana"},
        "media": {"mimetype": "audio/ogg; codecs=opus", "data": base64.b64encode(audio).decode()}}}


def bridge(transcriber=None, **overrides):
    chatwoot, openwa = FakeChatwoot(), FakeOpenWA()
    cfg = settings(**overrides)
    instance = Bridge(cfg, store.connect(":memory:"), chatwoot, openwa, lambda: 1000.0,
                      sleep=lambda seconds: _none(), transcriber=transcriber)
    return instance, chatwoot, openwa


async def _none():
    return None


async def test_voice_note_text_reaches_chatwoot_after_the_notice():
    transcriber = FakeTranscriber()
    instance, chatwoot, openwa = bridge(transcriber)
    await instance.handle_openwa(voice_event())
    assert transcriber.calls == [b"ogg-bytes"]
    assert chatwoot.messages == [("source-1", 100, "quiero una habitación")]
    assert openwa.sent == [VOICE_NOTICE]


async def test_the_voice_notice_is_sent_once_per_guest():
    instance, _, openwa = bridge(FakeTranscriber())
    await instance.handle_openwa(voice_event("v1"))
    await instance.handle_openwa(voice_event("v2"))
    assert openwa.sent.count(VOICE_NOTICE) == 1


async def test_without_a_transcriber_voice_notes_keep_the_text_only_reply():
    instance, chatwoot, openwa = bridge(transcriber=None)
    await instance.handle_openwa(voice_event())
    assert openwa.sent == [UNSUPPORTED_REPLY] and chatwoot.messages == []


async def test_a_failed_transcription_asks_for_the_message_again_without_crashing():
    instance, chatwoot, openwa = bridge(FakeTranscriber(fail=True))
    await instance.handle_openwa(voice_event())
    assert VOICE_UNCLEAR_REPLY in openwa.sent and chatwoot.messages == []


async def test_an_empty_transcript_is_treated_as_not_understood():
    instance, chatwoot, openwa = bridge(FakeTranscriber(text="   "))
    await instance.handle_openwa(voice_event())
    assert VOICE_UNCLEAR_REPLY in openwa.sent and chatwoot.messages == []


async def test_an_oversized_voice_note_is_refused_before_transcribing():
    transcriber = FakeTranscriber()
    instance, chatwoot, openwa = bridge(transcriber, max_voice_bytes=4)
    await instance.handle_openwa(voice_event(audio=b"demasiado grande"))
    assert transcriber.calls == [] and VOICE_UNCLEAR_REPLY in openwa.sent


async def test_a_voice_note_without_media_data_is_not_understood():
    transcriber = FakeTranscriber()
    instance, _, openwa = bridge(transcriber)
    event = voice_event()
    del event["data"]["media"]
    await instance.handle_openwa(event)
    assert transcriber.calls == [] and VOICE_UNCLEAR_REPLY in openwa.sent


async def test_the_notice_is_recorded_so_a_restart_does_not_repeat_it():
    instance, _, openwa = bridge(FakeTranscriber())
    await instance.handle_openwa(voice_event("v1"))
    assert store.notice_sent(instance.db, GUEST)


def fake_model(duration: float, record: dict):
    class Model:
        def transcribe(self, path, **kwargs):
            record["path"] = Path(path)
            record["existed_during_call"] = Path(path).exists()
            segments = [SimpleNamespace(text=" quiero una "), SimpleNamespace(text="habitación ")]
            return iter(segments), SimpleNamespace(duration=duration)
    return Model()


async def test_whisper_transcriber_deletes_the_audio_after_transcribing(tmp_path):
    record: dict = {}
    transcriber = WhisperTranscriber(model_factory=lambda: fake_model(4.0, record), tmp_dir=tmp_path, max_seconds=60)
    text = await transcriber(b"audio")
    assert text == "quiero una habitación"
    assert record["existed_during_call"] is True
    assert not record["path"].exists() and list(tmp_path.iterdir()) == []


async def test_whisper_transcriber_refuses_audio_longer_than_the_limit(tmp_path):
    record: dict = {}
    transcriber = WhisperTranscriber(model_factory=lambda: fake_model(120.0, record), tmp_dir=tmp_path, max_seconds=60)
    with pytest.raises(AudioTooLong):
        await transcriber(b"audio")
    assert not record["path"].exists()


async def test_the_model_is_loaded_once_for_many_notes(tmp_path):
    loads = []

    def factory():
        loads.append(1)
        return fake_model(2.0, {})

    transcriber = WhisperTranscriber(model_factory=factory, tmp_dir=tmp_path, max_seconds=60)
    for _ in range(3):
        await transcriber(b"audio")
    assert len(loads) == 1


def test_the_voice_notice_record_expires_with_the_mapping_retention():
    db = store.connect(":memory:")
    store.mark_notice(db, "viejo@c.us", 100.0)
    store.mark_notice(db, "reciente@c.us", 900.0)
    store.purge_mappings(db, older_than=500.0)
    assert not store.notice_sent(db, "viejo@c.us") and store.notice_sent(db, "reciente@c.us")
