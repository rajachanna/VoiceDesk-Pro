# VoiceDesk Pro — Development roadmap

## Implemented v0.1 (prototype)

- Local FastAPI appointment and lead APIs with operator key
- Transactional local half-hour appointment inventory, weekday 9–17 and IANA time zone
- Cancellation and calendar ICS export
- Signed Twilio inbound Programmable Voice webhook adapter
- DTMF menu, three available consultation choices, speech-recognized customer name, DTMF booking confirmation
- Voice message lead capture; per-call session and repeat confirmation protection
- Rules-based FAQ and optional (unverified) OpenAI FAQ adapter
- Responsive dashboard for local account records
- Python tests with mocked Twilio-signed traffic and local SQLite

## Next: external integrations and production readiness

- Twilio number configuration, real inbound call validation, transcripts and failure testing
- Real Google Calendar OAuth integration with free/busy checks and calendar event reconciliation
- One-way/bi-directional n8n, HubSpot, or another CRM integration with consent mapping
- Live human call transfer, voicemail notifications and outage failover
- Actual multilingual speech recognition/TTS, localization and pronunciation testing
- LLM conversation agent with escalation policies, tool-calling and sandboxed booking workflow
- Consent, data retention/deletion UI, rate limiting, multi-tenant isolation, monitoring and security review
- More extensive concurrency/load tests and TLS/certificate deployment guide

**Important:** v0.1 does not make real phone calls without customer-owned Twilio setup; it does not book into Google Calendar or CRM or prove production readiness.
