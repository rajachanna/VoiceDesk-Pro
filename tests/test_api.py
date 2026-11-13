"""Local booking and operator API regression checks; no external accounts."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest

from voicedesk.api import create_app
from voicedesk.config import Settings


KEY = "voice-desk-test-operator-key-123456789"
HEADERS = {"X-Operator-Key": KEY}


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        db_path=tmp_path / "test.sqlite", operator_key=KEY,
        business_name="Sample Studio", timezone="America/New_York",
    )
    return TestClient(create_app(settings))


def first_day(client):
    local = datetime.now(ZoneInfo("America/New_York")).date()
    for offset in range(1, 14):
        day = local + timedelta(days=offset)
        resp = client.get("/api/slots", params={"day": day.isoformat()}, headers=HEADERS)
        if resp.json()["slots"]:
            return day, resp.json()["slots"][0]
    raise AssertionError("No future business day slots")


def sample(slot):
    return {
        "start_utc": slot["start_utc"],
        "customer_name": "Alex Morgan",
        "phone": "+15550100101",
        "service": "consultation", "confirmed": True,
    }


def test_health_without_credentials(client):
    assert client.get("/health").json()["telephony"] == "NOT_CONFIGURED"


def test_dashboard(client):
    assert client.get("/").status_code == 200
    assert "VoiceDesk" in client.get("/").text


def test_operator_authorization(client):
    for path in ("/api/appointments", "/api/leads", "/api/metrics", "/api/calendar.ics"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Operator-Key": "invalid"}).status_code == 401


def test_booking_and_double_book_rejected(client):
    _, slot = first_day(client)
    r = client.post("/api/appointments", json=sample(slot), headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"
    r2 = client.post("/api/appointments", json=sample(slot), headers=HEADERS)
    assert r2.status_code == 409
    assert client.get("/api/metrics", headers=HEADERS).json()["appointments_total"] == 1


def test_cancellation_frees_slot(client):
    day, slot = first_day(client)
    booking = client.post("/api/appointments", json=sample(slot), headers=HEADERS).json()
    taken = client.get("/api/slots", params={"day": day.isoformat()}, headers=HEADERS).json()["slots"]
    assert slot not in taken
    assert client.post(f"/api/appointments/{booking['id']}/cancel", headers=HEADERS).json()["cancelled"]
    assert client.get("/api/slots", params={"day": day.isoformat()}, headers=HEADERS).json()["slots"]
    assert client.get("/api/metrics", headers=HEADERS).json()["appointments_total"] == 0


def test_confirmation_required(client):
    _, slot = first_day(client)
    req = sample(slot)
    req["confirmed"] = False
    assert client.post("/api/appointments", json=req, headers=HEADERS).status_code == 422


def test_invalid_slot_rejected(client):
    _, slot = first_day(client)
    req = sample(slot)
    req["start_utc"] = datetime.now(timezone.utc).isoformat()
    assert client.post("/api/appointments", json=req, headers=HEADERS).status_code == 422


def test_weekend_has_no_slots(client):
    day = datetime.now(ZoneInfo("America/New_York")).date()
    while day.weekday() != 5:
        day += timedelta(days=1)
    assert client.get("/api/slots", params={"day": day.isoformat()}, headers=HEADERS).json()["slots"] == []


def test_lead_capture_and_metrics(client):
    new_lead = {"name": "Robin", "phone": "+15551112222", "message": "Call about opening hours"}
    r = client.post("/api/leads", json=new_lead, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert client.get("/api/metrics", headers=HEADERS).json()["leads_total"] == 1
    leads = client.get("/api/leads", headers=HEADERS).json()["leads"]
    assert leads[0]["name"] == "Robin"


def test_empty_message_rejected(client):
    r = client.post("/api/leads", json={
        "name": "Robin", "phone": "+15551112222", "message": ""
    }, headers=HEADERS)
    assert r.status_code == 422


def test_calendar_export(client):
    _, slot = first_day(client)
    client.post("/api/appointments", json=sample(slot), headers=HEADERS)
    r = client.get("/api/calendar.ics", headers=HEADERS)
    assert r.status_code == 200
    assert "BEGIN:VCALENDAR" in r.text
    assert "BEGIN:VEVENT" in r.text
    assert "Alex Morgan" not in r.text
    assert "+15550100101" not in r.text


def test_rules_faq_is_honest(client):
    q = client.post("/api/faq", json={"question": "How much does this cost?"}, headers=HEADERS).json()
    assert q["engine"] == "rules"
    assert "not configured" in q["reply"]


def test_external_ai_disabled_by_default(client):
    result = client.post("/api/faq", json={"question": "When are you open?"}, headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["engine"] == "rules"


def test_unconfigured_operator_secret_blocks_requests(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "x.sqlite", operator_key="REPLACE_WITH_DEMO"))
    assert TestClient(app).get("/api/metrics", headers={"X-Operator-Key":"REPLACE_WITH_DEMO"}).status_code == 401
