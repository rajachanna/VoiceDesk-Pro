"""Repeatable, provider-free receptionist demo using synthetic information.

Usage: pip install -e ".[dev]" && python scripts/demo.py

No Twilio number, phone calls, remote AI API or customer data involved.
"""
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo
import json

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from voicedesk.api import create_app
from voicedesk.config import Settings


KEY = "voicedesk-demo-only-operator-key-12345"
TOKEN = "voicedesk-demo-only-twilio-auth-token-12345"
BASE = "https://demo.example"
CALL_SID = "CA1234567890abcdef1234567890abcdef"


def show(label, response):
    print(f"\n{label}: HTTP {response.status_code}")
    if response.headers.get("content-type", "").startswith("application/xml"):
        print(response.text[:180].replace("\n", " ") + "...")
    else:
        value = response.json()
        # Never print a real phone number from actual customer data.
        if isinstance(value, dict) and "phone" in value:
            value["phone"] = "[synthetic demo contact]"
        print(json.dumps(value, indent=2, ensure_ascii=False)[:1100])
    assert response.status_code == 200, f"{label}: {response.text[:300]}"
    return response


def main():
    with TemporaryDirectory(prefix="voicedesk-demo-") as folder:
        config = Settings(
            db_path=Path(folder) / "demo.sqlite",
            operator_key=KEY,
            twilio_auth_token=TOKEN,
            public_base_url=BASE,
            timezone="America/New_York",
        )
        app = create_app(config)
        client = TestClient(app)
        header = {"X-Operator-Key": KEY}
        print("VoiceDesk Pro v0.1 — OFFLINE PROVIDER MOCK / NO LIVE CALLS")

        local = datetime.now(ZoneInfo(config.timezone)).date()
        first_slot = None
        for offset in range(1, 12):
            day = local + timedelta(days=offset)
            data = client.get("/api/slots", params={"day": day.isoformat()}, headers=header)
            if data.json()["slots"]:
                first_slot = data.json()["slots"][0]
                break
        assert first_slot

        show("1. Health", client.get("/health"))
        r = show(
            "2. Confirm local appointment",
            client.post("/api/appointments", headers=header, json={
                "start_utc": first_slot["start_utc"],
                "customer_name": "Sample Customer",
                "phone": "+15550100000",
                "service": "consultation",
                "confirmed": True,
            }),
        )
        booked = r.json()
        duplicate = client.post("/api/appointments", headers=header, json={
            "start_utc": first_slot["start_utc"],
            "customer_name": "Sample Customer",
            "phone": "+15550100000",
            "service": "consultation",
            "confirmed": True,
        })
        print("\n3. Duplicate slot correctly blocked: HTTP", duplicate.status_code)
        assert duplicate.status_code == 409

        show(
            "4. Local lead captured",
            client.post("/api/leads", headers=header, json={
                "name": "Sample Caller", "phone": "+15550100000",
                "message": "Please contact me about service options.",
            }),
        )
        show(
            "5. FAQ reply",
            client.post("/api/faq", headers=header, json={"question": "What hours are you open?"}),
        )

        def signed(path, **fields):
            form = {"CallSid": CALL_SID, "From": "+15550000000", **fields}
            signature = RequestValidator(TOKEN).compute_signature(BASE + path, form)
            return client.post(path, data=form, headers={"X-Twilio-Signature": signature})

        show("6. Signed synthetic inbound call", signed("/twilio/voice"))
        show("7. Opening hours on DTMF menu", signed("/twilio/menu", Digits="2"))
        print("\n8. Calendar ICS export available:", client.get("/api/calendar.ics", headers=header).status_code)
        show("9. Operator cancels booking", client.post(f"/api/appointments/{booked['id']}/cancel", headers=header))
        show("10. Final metrics", client.get("/api/metrics", headers=header))
        print("\nPASS — local receptionist demo completed; no real provider used.")


if __name__ == "__main__":
    main()
