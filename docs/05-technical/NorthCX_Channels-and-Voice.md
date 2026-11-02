# NorthCX Channels and Voice

Status: Draft

## Channel adapter contract
An adapter translates a channel message to `POST /v1/agents/:id/chat {sessionId, message, customerId}` and posts `reply` back. Session ID is stable per conversation on that channel. When `status` is `escalated`, the adapter routes the conversation to the human inbox with the trace link.

## Channels by phase
| Channel | Phase | Notes |
|---|---|---|
| Web chat widget | 1 | Served by the API server |
| Email | 3 | Via inbox integration; thread ID maps to session |
| SMS / WhatsApp | 3 | Via inbox integration; opt-in and template rules apply |
| Voice | 5 | Real-time speech-to-text and text-to-speech around the same API |

## Voice requirements
Low-latency streaming, barge-in handling, short replies, spoken confirmation for actions, DTMF fallback, and handoff to a phone queue. Latency budget to be set when voice starts.

## Voice legal and consent
Call recording and automated-call rules vary by jurisdiction. The voice adapter must announce that the caller is speaking to an automated agent, obtain recording consent where required, and honour opt-out and data-deletion requests. Legal review is required before launch.

## Identity verification (C9)
Account-affecting actions require verification appropriate to the channel (for example a one-time code to a known contact). The result is recorded as a trusted fact for the session only.

## Multilingual (R9, C6)
Detect the customer's language; reply in it; keep policy text in the base language; voice supports mid-call language switching.

## Attachments (C10)
Images and documents are stored with size and type limits, scanned, and passed to the agent as labelled untrusted input.

## Business hours and routing (H8)
Channels follow the same hours and queue rules; outside hours the agent sets expectations and records a callback or ticket.

## Mobile and web SDK (C7)
Embeddable client with streaming, attachments and handoff status.

## Open questions
Streaming replies on the API, identity verification per channel, and per-channel style guidance in instructions.


## Email channel — as built

- **Inbound:** `POST /v1/channels/email/inbound` with the raw message as the body (≤ 1,000,000 bytes). Requires the `channel:inbound` permission (`channel` and `admin` roles). Responses: `{status, sessionId, reason, traceId, handoffId}`; `status` is `replied`, `escalated`, `needs_approval`, `held_for_person`, `rate_limited`, `ignored` or `duplicate`. 400 unusable message, 413 too large, 501 channel not configured, 500 internal (the gateway should redeliver; nothing is lost because messages are recorded only after handling).
- **Parsing:** plain text preferred, HTML reduced to text, quoted history and signatures removed, attachments listed by name but never read, header injection neutralised.
- **Threading:** `In-Reply-To`/`References` map to a session; a message from a different address starts a new conversation.
- **Never answered:** `Auto-Submitted`, bulk/list mail, bounces, no-reply senders, our own address, duplicates (by Message-ID).
- **Identity:** anonymous unless the gateway reports `dmarc=pass` and `NORTHCX_EMAIL_TRUST_AUTH_RESULTS=1`.
- **Outbound:** SMTP (`smtp://`, `smtp+starttls://`, `smtps://`) through the outbox, so approval results and handoff notices are emailed in the same thread; retried with back-off, exactly once per message.
- **Configuration:** `NORTHCX_EMAIL_FROM`, `NORTHCX_SMTP_URL` (or `_FILE`), `NORTHCX_EMAIL_AGENT`, `NORTHCX_EMAIL_FROM_NAME`, `NORTHCX_EMAIL_TRUST_AUTH_RESULTS`, `NORTHCX_EMAIL_MAX_REPLIES_PER_HOUR`.
- **Storage:** migration 0007 (`email_sessions`, `email_messages`, `outbox.last_attempt_at`).
- **Limits:** no attachments or inline images read; no IMAP polling; replies are plain text.
