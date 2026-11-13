"""Conservative FAQ responder; optional OpenAI answers only to public business facts.

The LLM cannot read or edit bookings, leads or customer records.
"""
import re

PUBLIC_FACTS = (
    "Northstar Demo Studio is a fictional appointment-based business. "
    "Consultations last 30 minutes. Available appointment windows are Monday "
    "through Friday, 9:00 AM to 5:00 PM in the configured business time zone. "
    "Prices, medical services, refunds and policies are not provided."
)


def answer(question: str, *, api_key: str = "", model: str = "gpt-4.1-mini") -> dict:
    question = question.strip()[:350]
    if not question:
        return {"reply": "Please ask a question about our hours or appointments.", "engine": "rules"}
    # Do not send obvious PII to a remote model. This is a lightweight gate,
    # NOT a production-grade PII classifier. Actual privacy review required.
    if api_key and not re.search(r"\d{3,}|@|(?:https?://)", question):
        try:
            from openai import OpenAI  # optional dependency
            result = OpenAI(api_key=api_key, timeout=8.0, max_retries=0).responses.create(
                model=model,
                instructions=(
                    "You are a concise demo receptionist. Answer ONLY from these facts: "
                    + PUBLIC_FACTS
                    + " Never invent prices, policies or availability. "
                    "For bookings, instruct the user to select an available time via the booking system."
                ),
                input=question,
                max_output_tokens=130,
            )
            text = str(result.output_text or "").strip()[:600]
            if text:
                return {"reply": text, "engine": "optional_openai_faq"}
        except Exception:
            pass  # Fail to safe local FAQ, not a false booking or HTTP 500.

    lower = question.lower()
    if any(word in lower for word in ("hour", "open", "close", "time")):
        reply = "We offer consultations Monday through Friday, 9 AM to 5 PM in our business time zone."
    elif any(word in lower for word in ("book", "appointment", "meeting", "schedule")):
        reply = "Consultations last 30 minutes. Check the available slots and confirm a booking with the receptionist."
    elif any(word in lower for word in ("price", "cost", "fee", "insurance")):
        reply = "Pricing and payment policies are not configured in this demo. Please contact the business directly."
    elif any(word in lower for word in ("human", "person", "agent", "representative")):
        reply = "Human transfer is not enabled in this demo. Please leave a message for the team."
    else:
        reply = "I can help with consultation hours and appointments. Other details need staff confirmation."
    return {"reply": reply, "engine": "rules"}
