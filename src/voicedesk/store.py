"""SQLite storage for local booking inventory, leads and voice sessions.

All customer records remain local; no automatic CRM export or Google sync.
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, time, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import json
import sqlite3

from .config import Settings


class BookingError(ValueError):
    pass


class FullyBooked(BookingError):
    pass


def now_utc():
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, config: Settings):
        self.config = config
        self.config.validate()
        Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS appointments(
                    id TEXT PRIMARY KEY, start_utc TEXT NOT NULL,
                    customer_name TEXT NOT NULL, phone TEXT NOT NULL,
                    service TEXT NOT NULL, status TEXT NOT NULL,
                    call_sid TEXT UNIQUE, created_utc TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_booking
                    ON appointments(start_utc) WHERE status='confirmed';
                CREATE TABLE IF NOT EXISTS leads(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
                    message TEXT NOT NULL, call_sid TEXT UNIQUE,
                    created_utc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(
                    call_sid TEXT PRIMARY KEY, caller TEXT NOT NULL,
                    phase TEXT NOT NULL, data_json TEXT NOT NULL,
                    updated_utc TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.config.db_path), isolation_level=None, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=20000")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
        finally:
            db.close()

    def candidate_slots(self, day: date):
        zone = ZoneInfo(self.config.timezone)
        now = now_utc()
        if day.weekday() >= 5 or not (now.date() - timedelta(days=1) <= day <= (now + timedelta(days=46)).date()):
            return []
        result = []
        for hour in range(9, 17):
            for minute in (0, 30):
                local = datetime.combine(day, time(hour, minute), tzinfo=zone)
                utc = local.astimezone(timezone.utc)
                if utc <= now + timedelta(minutes=15):
                    continue
                result.append({
                    "start_utc": utc.isoformat(),
                    "local_time": local.strftime("%a, %b %-d at %-I:%M %p") if False
                        else local.strftime("%a %b %d, %I:%M %p"),
                    "timezone": self.config.timezone,
                })
        return result

    def available(self, day: date):
        options = self.candidate_slots(day)
        if not options:
            return []
        with self.connect() as db:
            booked = {r["start_utc"] for r in db.execute(
                "SELECT start_utc FROM appointments WHERE status='confirmed'"
            )}
        return [x for x in options if x["start_utc"] not in booked]

    def next_slots(self, count=3):
        day = now_utc().astimezone(ZoneInfo(self.config.timezone)).date()
        slots = []
        for i in range(46):
            slots.extend(self.available(day + timedelta(days=i)))
            if len(slots) >= count:
                break
        return slots[:count]

    def book(self, *, start_utc, customer_name, phone, service="consultation", call_sid=None):
        # Validate before database mutation. Then enforce uniqueness *inside* a
        # write-locked transaction for concurrent voice/web requests.
        try:
            dt = datetime.fromisoformat(start_utc)
        except (ValueError, TypeError) as exc:
            raise BookingError("Appointment requires an ISO-8601 timestamp") from exc
        if dt.tzinfo is None:
            raise BookingError("Appointment timestamp must specify a timezone")
        canonical = dt.astimezone(timezone.utc).isoformat()
        zone = ZoneInfo(self.config.timezone)
        day = dt.astimezone(zone).date()
        if canonical not in {x["start_utc"] for x in self.candidate_slots(day)}:
            raise BookingError("Select an available weekday, half-hour appointment slot")
        if not (2 <= len(customer_name.strip()) <= 80):
            raise BookingError("Customer name must have 2 to 80 characters")
        if len(phone.strip()) > 35 or not phone.strip():
            raise BookingError("Provide a valid contact phone string")
        if not (1 <= len(service.strip()) <= 60):
            raise BookingError("Service must have 1 to 60 characters")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if call_sid:
                prior = db.execute(
                    "SELECT * FROM appointments WHERE call_sid=?", (call_sid,)
                ).fetchone()
                if prior:
                    db.execute("ROLLBACK")
                    return dict(prior)
            appointment_id = uuid4().hex
            try:
                db.execute(
                    """INSERT INTO appointments
                    (id,start_utc,customer_name,phone,service,status,call_sid,created_utc)
                    VALUES(?,?,?,?,?,'confirmed',?,?)""",
                    (appointment_id,canonical,customer_name.strip(),phone.strip(),
                     service.strip(),call_sid,now_utc().isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                db.execute("ROLLBACK")
                raise FullyBooked("That slot has just been booked; choose another") from exc
            record = db.execute(
                "SELECT * FROM appointments WHERE id=?", (appointment_id,)
            ).fetchone()
            db.execute("COMMIT")
        return dict(record)

    def cancel(self, appointment_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "UPDATE appointments SET status='cancelled' WHERE id=? AND status='confirmed'",
                (appointment_id,),
            )
            db.execute("COMMIT")
            return bool(cursor.rowcount)

    def appointments(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM appointments ORDER BY created_utc DESC LIMIT 200"
            )]

    def add_lead(self, *, name, phone, message, call_sid=None):
        name = name.strip()[:80] or "Unknown caller"
        message = message.strip()[:400]
        if not message:
            raise BookingError("Lead message cannot be empty")
        if not phone.strip() or len(phone) > 35:
            raise BookingError("Phone number missing or too long")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if call_sid:
                prior = db.execute(
                    "SELECT * FROM leads WHERE call_sid=?", (call_sid,)
                ).fetchone()
                if prior:
                    db.execute("ROLLBACK")
                    return dict(prior)
            lead_id = uuid4().hex
            db.execute(
                "INSERT INTO leads VALUES(?,?,?,?,?,?)",
                (lead_id,name,phone.strip(),message,call_sid,now_utc().isoformat()),
            )
            item = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
            db.execute("COMMIT")
        return dict(item)

    def leads(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM leads ORDER BY created_utc DESC LIMIT 200"
            )]

    def get_session(self, call_sid):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE call_sid=?", (call_sid,)
            ).fetchone()
        if not row:
            return None
        session = dict(row)
        session["data"] = json.loads(session.pop("data_json"))
        return session

    def save_session(self, call_sid, caller, phase, data):
        with self.connect() as db:
            db.execute(
                """INSERT INTO sessions VALUES(?,?,?,?,?)
                ON CONFLICT(call_sid) DO UPDATE SET
                caller=excluded.caller,phase=excluded.phase,
                data_json=excluded.data_json,updated_utc=excluded.updated_utc""",
                (call_sid,caller,phase,json.dumps(data),now_utc().isoformat()),
            )

    def metrics(self):
        with self.connect() as db:
            return {
                "appointments_total": db.execute(
                    "SELECT count(*) FROM appointments WHERE status='confirmed'"
                ).fetchone()[0],
                "leads_total": db.execute("SELECT count(*) FROM leads").fetchone()[0],
                "voice_sessions": db.execute("SELECT count(*) FROM sessions").fetchone()[0],
            }
