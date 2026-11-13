# Security and privacy

VoiceDesk Pro v0.1 is an **experimental voice + appointment prototype**, not a secure hosted call center or HIPAA-compliant/medical system.

- Do not commit `.env`, Twilio tokens, customer information or OpenAI keys.
- Operator endpoints require `X-Operator-Key` (24+ characters). Dashboard retains it in memory only.
- All Twilio webhooks require a validated `X-Twilio-Signature`. The original external HTTPS webhook URL is reconstructed from a *configured*, trusted `VD_PUBLIC_BASE_URL`, not request Host headers.
- No voice webhook responds with booking confirmation until a caller presses **1** to confirm. Booking time inventory is transactionally enforced by a SQLite partial unique index. A unique CallSid prevents one call from double-booking.
- Twilio speech transcription can process voice input and may have its own retention and compliance rules. This application does not record calls. Caller number and short transcribed message are held in local SQLite; they are sensitive personal data.
- Implement explicit caller notice, lawful processing, retention schedule, deletion/opt-out processes, access controls, encryption at rest, consent, monitoring, secure backups and incident response before production use.
- The current app does not have public authentication for self-service booking: operator secret is required. Twilio access is authenticated via Twilio's signature.
- The demo HTTP service binds to loopback in Docker. A real inbound Twilio deployment requires a secure HTTPS reverse proxy and accurate external base URL, rate limits and webhook anti-abuse protection.
- The optional OpenAI FAQ is **off by default**. The implementation never passes booking/contact records to the LLM; the query-only pathway has a lightweight numeric/email/URL heuristic, **not** a guarantee of PII removal.
- Do not use this demo for medical emergencies or time-sensitive critical business workflows.
- Calendar integration means an **operator-downloadable ICS export only**. Google Calendar bidirectional sync, external CRM sync, SMS, live human call transfer and outbound dialing are **not implemented**.
- Authentication alone does not make a deployment production-ready. Obtain independent privacy and security review before accepting real customer traffic.

Report issues through https://nextgentechdev.com without publicly sharing personal data.
