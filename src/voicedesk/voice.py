"""Twilio Programmable Voice webhook adapter.

Signed requests only. Uses Twilio's speech recognition/TTS and a deterministic
call state machine; no unverified "AI makes bookings" claims.
"""
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from .config import Settings
from .store import BookingError, Store


def make_voice_router(settings: Settings, get_store):
    routes = APIRouter(prefix="/twilio", tags=["Signed Twilio Voice"])

    async def verified_form(request: Request):
        if not settings.telephony_ready:
            raise HTTPException(status_code=503, detail="Twilio not configured")
        form = await request.form()
        # Derive absolute URL ONLY from configured external HTTPS origin.
        # Never trust Host / X-Forwarded-* on an exposed webhook.
        url = settings.public_base_url.rstrip("/") + request.url.path
        if request.url.query:
            url += "?" + request.url.query
        signature = request.headers.get("X-Twilio-Signature", "")
        if not signature or not RequestValidator(settings.twilio_auth_token).validate(
            url, form, signature
        ):
            raise HTTPException(status_code=403, detail="Invalid Twilio request signature")
        sid = str(form.get("CallSid") or "")
        if not re.fullmatch(r"CA[A-Za-z0-9]{8,64}", sid):
            raise HTTPException(status_code=422, detail="Invalid call identifier")
        return form, sid

    def xml(response):
        return Response(content=str(response), media_type="application/xml")

    def voice_menu():
        r = VoiceResponse()
        g = r.gather(input="dtmf", num_digits=1, timeout=7, action="/twilio/menu", method="POST")
        g.say(
            f"Thank you for calling {settings.business_name}. "
            "Press 1 to book a consultation. Press 2 for business hours. "
            "Press 3 to leave a message."
        )
        r.say("We did not receive an option. Goodbye.")
        return xml(r)

    @routes.post("/voice")
    async def inbound_voice(request: Request):
        form, sid = await verified_form(request)
        caller = str(form.get("From") or "unknown")[:35]
        store: Store = get_store()
        if not store.get_session(sid):
            store.save_session(sid, caller, "MENU", {})
        return voice_menu()

    @routes.post("/menu")
    async def option(request: Request):
        form, sid = await verified_form(request)
        store: Store = get_store()
        session = store.get_session(sid)
        if not session:
            raise HTTPException(status_code=409, detail="Call session not initialized")
        digit = str(form.get("Digits") or "")
        r = VoiceResponse()
        if digit == "1":
            options = store.next_slots(3)
            if not options:
                r.say("I am sorry, no consultation slots are currently available.")
                r.hangup()
                return xml(r)
            store.save_session(sid, session["caller"], "SLOT", {"options": options})
            g = r.gather(input="dtmf", num_digits=1, timeout=9, action="/twilio/select", method="POST")
            g.say("Please select one of these available consultation times.")
            for idx, slot in enumerate(options, 1):
                g.say(f"Press {idx} for {slot['local_time']} in our business time zone.")
            r.say("No selection received. Goodbye.")
        elif digit == "2":
            r.say("Our demo business is open Monday to Friday, 9 A M to 5 P M, in our local business time zone.")
            r.hangup()
        elif digit == "3":
            store.save_session(sid, session["caller"], "MESSAGE", {})
            g = r.gather(
                input="speech", speech_timeout="auto", timeout=8,
                action="/twilio/message", method="POST",
            )
            g.say("After the tone, please say your name and a short message. This is transcribed by the phone provider.")
            r.say("No message received. Goodbye.")
        else:
            return voice_menu()
        return xml(r)

    @routes.post("/select")
    async def choose_slot(request: Request):
        form, sid = await verified_form(request)
        store: Store = get_store()
        session = store.get_session(sid)
        if not session or session["phase"] != "SLOT":
            raise HTTPException(status_code=409, detail="No active slot selection")
        choices = session["data"]["options"]
        digit = str(form.get("Digits") or "")
        if not digit.isdigit() or not 1 <= int(digit) <= len(choices):
            r = VoiceResponse()
            r.say("Invalid option. Please call again.")
            r.hangup()
            return xml(r)
        slot = choices[int(digit) - 1]
        store.save_session(sid, session["caller"], "NAME", {"slot": slot})
        r = VoiceResponse()
        g = r.gather(input="speech", speech_timeout="auto", timeout=8,
                     action="/twilio/name", method="POST")
        g.say(f"You selected {slot['local_time']}. Please say your full name clearly.")
        r.say("No name heard. Please call again.")
        return xml(r)

    @routes.post("/name")
    async def take_name(request: Request):
        form, sid = await verified_form(request)
        store: Store = get_store()
        session = store.get_session(sid)
        if not session or session["phase"] != "NAME":
            raise HTTPException(status_code=409, detail="No pending name request")
        spoken = str(form.get("SpeechResult") or "").strip()
        # Speech recognition may contain punctuation or whitespace;
        # accept letters from Unicode scripts but reject control characters.
        name = " ".join(spoken.split())[:80]
        if not (2 <= len(name) <= 80) or any(ord(c) < 32 for c in name):
            r = VoiceResponse()
            r.say("I could not understand your name. Please call again.")
            r.hangup()
            return xml(r)
        slot = session["data"]["slot"]
        store.save_session(sid, session["caller"], "CONFIRM", {"slot": slot, "name": name})
        r = VoiceResponse()
        g = r.gather(input="dtmf", num_digits=1, timeout=8,
                     action="/twilio/confirm", method="POST")
        g.say(f"Thank you, {name}. For {slot['local_time']}, press 1 to confirm, or 2 to cancel.")
        r.say("Appointment not confirmed. Goodbye.")
        return xml(r)

    @routes.post("/confirm")
    async def confirm(request: Request):
        form, sid = await verified_form(request)
        store: Store = get_store()
        session = store.get_session(sid)
        if not session:
            raise HTTPException(status_code=409, detail="Call session not initialized")
        r = VoiceResponse()
        if session["phase"] == "DONE":
            r.say("Your appointment request has already been completed.")
            r.hangup()
            return xml(r)
        if session["phase"] != "CONFIRM":
            raise HTTPException(status_code=409, detail="Nothing to confirm")
        if str(form.get("Digits") or "") != "1":
            store.save_session(sid, session["caller"], "CANCELLED", {})
            r.say("Your appointment has not been booked. Goodbye.")
            r.hangup()
            return xml(r)
        data = session["data"]
        try:
            booked = store.book(
                start_utc=data["slot"]["start_utc"], customer_name=data["name"],
                phone=session["caller"], call_sid=sid
            )
        except BookingError:
            r.say("That appointment time is no longer available. Please call again.")
            r.hangup()
            return xml(r)
        store.save_session(sid, session["caller"], "DONE", {"booking_id": booked["id"]})
        r.say("Your consultation is confirmed. Thank you for calling.")
        r.hangup()
        return xml(r)

    @routes.post("/message")
    async def take_message(request: Request):
        form, sid = await verified_form(request)
        store: Store = get_store()
        session = store.get_session(sid)
        if not session or session["phase"] not in ("MESSAGE", "MESSAGE_DONE"):
            raise HTTPException(status_code=409, detail="No pending message request")
        r = VoiceResponse()
        if session["phase"] == "MESSAGE_DONE":
            r.say("Your message has already been received.")
            r.hangup()
            return xml(r)
        message = " ".join(str(form.get("SpeechResult") or "").strip().split())[:400]
        if not message:
            r.say("We could not hear a message. Goodbye.")
        else:
            store.add_lead(name="Voice caller", phone=session["caller"], message=message, call_sid=sid)
            store.save_session(sid, session["caller"], "MESSAGE_DONE", {})
            r.say("Thank you. Your message has been saved for the team.")
        r.hangup()
        return xml(r)

    return routes
