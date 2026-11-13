# VoiceDesk Pro — Engineering case study

**Developer:** Raja Channa · NextGen Tech Solutions

## Business challenge

Appointment-based businesses often miss prospective customers because staff are answering phones, serving other customers or not available after hours. A dependable software receptionist must capture intent, explain basic information, offer slots, confirm a booking, and keep records.

## What the portfolio prototype actually demonstrates

**1. Signed phone-webhook boundary:** Twilio sends an inbound call webhook; application verifies the Twilio request signature against a configured public HTTPS origin before processing caller information.

**2. Repeatable call flow:** A deterministic voice menu handles business hours, choosing from three local slots and leaving a short message. Speech input is recognized by Twilio. The system asks for a spoken name, then explicitly requires pressing 1 for booking confirmation.

**3. Atomic appointment inventory:** The local SQLite booking store enforces one active booking per UTC time slot using a unique index. Duplicate call confirmations are protected using the CallSid.

**4. Operator visibility:** The responsive dashboard shows stored appointments, messages and counts. An operator key protects private fields.

**5. Independent evaluation:** Automated tests exercise booking conflicts, cancellations, unauthorized requests, signature verification, call-state transitions and repeat Twilio callbacks.

The project also includes a lightweight rules-based FAQ. Optional external OpenAI FAQ is supported only when configured but is not used for autonomous booking and has not been provider-verified as part of this project.

## Technical choices

| Engineering decision | Why it matters | Current limitation |
| --- | --- | --- |
| SQLite atomic writes and unique active slot | Prevents obvious local double bookings | No Google Calendar or outside-booking visibility |
| Explicit confirmation step | Caller makes final booking decision | Speech/DTMF recognition can still fail |
| Twilio signature validator | Rejects unsigned webhook calls | Requires correct production URL, TLS and provider configuration |
| IANA timezone | Produces local operating-hour slots | 9–17 weekday schedule is presently fixed |
| Local session state | Keeps multi-step IVR context | SQLite is not a multi-region high-availability store |
| Small operator dashboard | Demonstrates practical client workflow | Not a production CRM or team dashboard |
| Rules fallback for questions | Unknown policies are not invented | Not a full multilingual conversational agent |

## Portfolio demo checklist

1. Clone the repository and run the server locally.
2. Add a strong operator key; open the dashboard.
3. Inspect available future business-day slots.
4. Confirm one local appointment; verify that duplicate booking returns HTTP 409.
5. Cancel and confirm that the time becomes available again.
6. Save a demo lead, open the FAQ, export the calendar as ICS.
7. Review the signed Twilio-webhook test flow in `tests/test_twilio.py`.
8. Review GitHub Actions results and the security limitations before adopting any code.

## Scope for an actual customer

**Milestone 1:** discovery (telephony vendor, region, consent, business hours, booking rules, calendar/CRM, call budget)

**Milestone 2:** provision test Twilio number and live-inbound verification, robust fallback for misheard speech

**Milestone 3:** calendar/CRM OAuth integration, duplicate prevention across systems, staff handoff

**Milestone 4:** monitored pilot, call-quality evaluation, privacy/security review, measurable acceptance report

**Contact:** https://nextgentechdev.com

> No production call volume, real conversion-rate improvement, 24/7 uptime, multilingual certification or real calendar sync is claimed by the portfolio prototype.
