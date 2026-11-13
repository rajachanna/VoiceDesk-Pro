"""Twilio HTTP signature verification, call state and booking tests."""
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import pytest
from twilio.request_validator import RequestValidator

from voicedesk.api import create_app
from voicedesk.config import Settings
from voicedesk.store import Store


TOKEN = "very-long-test-Twilio-token-123456789"
KEY = "very-long-test-operator-key-123456789"
BASE = "https://example.org"
SID = "CA1234567890abcdef1234567890abcdef"


@pytest.fixture
def fixture(tmp_path):
    config = Settings(
        db_path=tmp_path / "voice.sqlite",
        operator_key=KEY,
        twilio_auth_token=TOKEN,
        public_base_url=BASE,
    )
    return TestClient(create_app(config)), Store(config)


def post(client, path, **extra):
    form = {"CallSid": SID, "From": "+15550123456", **extra}
    sig = RequestValidator(TOKEN).compute_signature(BASE + path, form)
    return client.post(path, data=form, headers={"X-Twilio-Signature": sig})


def test_unsigned_webhook_is_forbidden(fixture):
    client, _ = fixture
    assert client.post("/twilio/voice", data={"CallSid": SID}).status_code == 403


def test_signature_rejects_modified_body(fixture):
    client, _ = fixture
    original = {"CallSid": SID, "From": "+15550000000"}
    sig = RequestValidator(TOKEN).compute_signature(BASE+"/twilio/voice", original)
    modified = {**original, "From": "+15559999999"}
    assert client.post("/twilio/voice", data=modified, headers={"X-Twilio-Signature": sig}).status_code == 403


def test_inbound_menu_twiml(fixture):
    client, db = fixture
    response = post(client, "/twilio/voice")
    assert response.status_code == 200, response.text
    assert "<Gather" in response.text
    assert "Press 1" in response.text
    assert db.get_session(SID)["phase"] == "MENU"


def test_opening_hours_route(fixture):
    client, _ = fixture
    post(client, "/twilio/voice")
    r = post(client, "/twilio/menu", Digits="2")
    assert r.status_code == 200
    assert "Monday" in r.text


def test_complete_voice_booking_and_idempotent_confirmation(fixture):
    client, db = fixture
    assert post(client, "/twilio/voice").status_code == 200
    assert post(client, "/twilio/menu", Digits="1").status_code == 200
    assert db.get_session(SID)["phase"] == "SLOT"
    assert post(client, "/twilio/select", Digits="1").status_code == 200
    assert db.get_session(SID)["phase"] == "NAME"
    assert post(client, "/twilio/name", SpeechResult="Taylor Green").status_code == 200
    assert db.get_session(SID)["phase"] == "CONFIRM"
    booked = post(client, "/twilio/confirm", Digits="1")
    assert booked.status_code == 200
    assert "confirmed" in booked.text
    assert db.get_session(SID)["phase"] == "DONE"
    assert db.metrics()["appointments_total"] == 1
    repeated = post(client, "/twilio/confirm", Digits="1")
    assert repeated.status_code == 200
    assert db.metrics()["appointments_total"] == 1


def test_cancellation_in_voice_flow(fixture):
    client, db = fixture
    post(client, "/twilio/voice")
    post(client, "/twilio/menu", Digits="1")
    post(client, "/twilio/select", Digits="1")
    post(client, "/twilio/name", SpeechResult="Taylor Green")
    r = post(client, "/twilio/confirm", Digits="2")
    assert r.status_code == 200
    assert db.metrics()["appointments_total"] == 0


def test_invalid_state_rejects_unexpected_confirmation(fixture):
    client, _ = fixture
    post(client, "/twilio/voice")
    assert post(client, "/twilio/confirm", Digits="1").status_code == 409


def test_voice_message_lead_capture(fixture):
    client, db = fixture
    post(client, "/twilio/voice")
    assert post(client, "/twilio/menu", Digits="3").status_code == 200
    assert post(client, "/twilio/message", SpeechResult="Need a meeting next week").status_code == 200
    assert db.metrics()["leads_total"] == 1
    post(client, "/twilio/message", SpeechResult="Second attempt")
    assert db.metrics()["leads_total"] == 1


def test_invalid_call_sid(fixture):
    client, _ = fixture
    r = post(client, "/twilio/voice", CallSid="bad")
    assert r.status_code == 422


def test_missing_telephony_settings_fail_closed(tmp_path):
    client = TestClient(create_app(Settings(db_path=tmp_path/"test.sqlite")))
    assert client.post("/twilio/voice").status_code == 503
