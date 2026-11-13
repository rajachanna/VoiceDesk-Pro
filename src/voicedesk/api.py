"""Operator API, local dashboard and signed provider voice integration."""
from datetime import date, datetime, timezone
from hmac import compare_digest
from pathlib import Path
import re

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ConfigDict

from . import __version__
from .config import Settings
from .faq import answer
from .store import BookingError, FullyBooked, Store
from .voice import make_voice_router


class AppointmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_utc: str = Field(min_length=20, max_length=40)
    customer_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=3, max_length=35)
    service: str = Field(default="consultation", min_length=1, max_length=60)
    confirmed: bool


class LeadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=3, max_length=35)
    message: str = Field(min_length=1, max_length=400)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=350)


def create_app(config: Settings | None = None):
    settings = config or Settings.from_env()
    settings.validate()
    app = FastAPI(
        title="VoiceDesk Pro — Voice Receptionist & Local CRM",
        version=__version__,
        description="Secure Twilio inbound voice adapter and locally booked appointments. "
        "Demo mode is not a production telephony deployment.",
    )
    store: Store | None = None

    def get_store():
        nonlocal store
        if store is None:
            store = Store(settings)
        return store

    def operator_only(x_operator_key: str | None = Header(default=None)):
        if (
            not settings.operator_ready or x_operator_key is None
            or not compare_digest(settings.operator_key, x_operator_key)
        ):
            raise HTTPException(status_code=401, detail="Invalid operator key")

    @app.get("/", include_in_schema=False)
    def homepage():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    def health():
        return {
            "ready": True,
            "version": __version__,
            "telephony": "CONFIGURED_NOT_VERIFIED" if settings.telephony_ready else "NOT_CONFIGURED",
            "mode": "LOCAL_DEMO" if settings.demo_mode else "INTEGRATION",
        }

    @app.get("/api/slots", dependencies=[Depends(operator_only)])
    def slots(day: date):
        return {
            "business_timezone": settings.timezone,
            "day": day.isoformat(),
            "slots": get_store().available(day),
            "note": "Local SQLite inventory only; no external Google Calendar sync.",
        }

    @app.post("/api/appointments", dependencies=[Depends(operator_only)])
    def book(req: AppointmentRequest):
        if not req.confirmed:
            raise HTTPException(422, "Explicit customer booking confirmation is required")
        try:
            return get_store().book(
                start_utc=req.start_utc,
                customer_name=req.customer_name,
                phone=req.phone,
                service=req.service,
            )
        except FullyBooked as exc:
            raise HTTPException(409, str(exc)) from exc
        except BookingError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/appointments", dependencies=[Depends(operator_only)])
    def appointments():
        return {"appointments": get_store().appointments()}

    @app.post("/api/appointments/{booking_id}/cancel", dependencies=[Depends(operator_only)])
    def cancel(booking_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", booking_id):
            raise HTTPException(404, "Appointment not found")
        if not get_store().cancel(booking_id):
            raise HTTPException(404, "Appointment not found or already cancelled")
        return {"cancelled": True, "booking_id": booking_id}

    @app.post("/api/leads", dependencies=[Depends(operator_only)])
    def lead(req: LeadRequest):
        try:
            return get_store().add_lead(
                name=req.name, phone=req.phone, message=req.message
            )
        except BookingError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/leads", dependencies=[Depends(operator_only)])
    def leads():
        return {"leads": get_store().leads()}

    @app.get("/api/metrics", dependencies=[Depends(operator_only)])
    def metrics():
        result = get_store().metrics()
        return {
            **result,
            "mode": "LOCAL_DEMO" if settings.demo_mode else "INTEGRATION",
            "note": "Counts reflect only this local database, not a deployed phone service.",
        }

    @app.post("/api/faq", dependencies=[Depends(operator_only)])
    def faq(req: Question):
        return answer(
            req.question,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    @app.get("/api/calendar.ics", dependencies=[Depends(operator_only)])
    def calendar_export():
        def safe(text):
            return re.sub(r"[^A-Za-z0-9 ._-]", "", text)[:60]
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//VoiceDesk Pro//Local Appointments//EN"]
        for item in get_store().appointments():
            if item["status"] != "confirmed":
                continue
            start = datetime.fromisoformat(item["start_utc"]).astimezone(timezone.utc)
            end = start.timestamp() + 1800
            from datetime import datetime as dt
            end_dt = dt.fromtimestamp(end, timezone.utc)
            lines.extend([
                "BEGIN:VEVENT",
                "UID:" + item["id"] + "@voicedesk.local",
                "DTSTAMP:" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "DTSTART:" + start.strftime("%Y%m%dT%H%M%SZ"),
                "DTEND:" + end_dt.strftime("%Y%m%dT%H%M%SZ"),
                "SUMMARY:" + safe(item["service"]),
                "END:VEVENT",
            ])
        lines.append("END:VCALENDAR")
        return Response(
            "\r\n".join(lines) + "\r\n",
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="voicedesk-demo.ics"'},
        )

    app.include_router(make_voice_router(settings, get_store))
    return app


app = create_app()
