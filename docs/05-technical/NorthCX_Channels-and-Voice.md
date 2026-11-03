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


## SMS channel — as built (C4)

- **Webhook:** `POST /channels/sms/twilio` is public (outside `/v1`) and authenticated only by the provider's signature (`X-Twilio-Signature`: HMAC-SHA1 over the configured public URL plus the sorted form fields, compared in constant time). Forged requests get 403, are audited (sampled) and, once an address exceeds the failed-attempt limit, 429; valid requests are never throttled by this. The reply is an empty `<Response/>`; texts go out through the outbox, which retries with back-off.
- **Identity:** the sender's number, once the signature is valid, is the customer (`phone:+E164`) and facts, memories and company context follow it. A signed chat token minted by the company's own server remains the way to identify web customers.
- **Conversations:** one rolling conversation per customer number and business number; after 24 idle hours (configurable) a new one starts. Duplicate deliveries are ignored by message id. Conversations with an open hand-off are recorded for the person and the agent stays quiet.
- **Opt-out:** STOP, STOPALL, UNSUBSCRIBE, CANCEL, END and QUIT stop all texts to that number (also any reply still waiting in the outbox); START and UNSTOP resume; HELP sends a fixed help text. Opt-outs are stored by one-way hash and survive customer erasure so a STOP is never forgotten.
- **Replies:** split at sentence ends into up to three texts of at most 1,500 characters, the rest cut with an ellipsis. Per-number limit of 20 replies per hour. Attachments are noted, never read.
- **Style (C8):** an agent spec may carry `channel_styles` (for example `sms: "Two short sentences, no markdown"`); the matching style is added to the prompt for that channel (`sms`, `email`, and `web` for chat-token callers; API callers may send `channel`). Specs without it keep their digests.
- **Provider interface:** `valid_signature(url, params, signature)` and `send(to, from, body)`; a different provider needs only those two. Limits: no WhatsApp or other messaging apps yet, no delivery receipts, no media, and the signature algorithm is implemented from the provider's published description and checked against its documented example, not against a live account.

## Languages (R9)

An agent spec can list the languages it supports, for example `languages: [en, es, fr]`; the first is the default. On every customer message the runtime detects the language (offline, from the script and common words; no model call) and tells the model to reply in it. When the message is too short or unclear (such as "ok"), the conversation keeps the language of the last clear customer message. A customer writing in a language outside the list gets a reply in the default language, a short note that this is what the service supports, and an offer to bring in a person.

Known codes: en, es, fr, de, pt, it, nl, ru, ja, zh, ko, ar, hi. The detected language is recorded on the trace, shown on hand-off packages, broken down in Insights (with containment per language) and searchable (`language` filter).

Limits: fixed platform messages (the model-failure fallback, after-hours notices) and forced-topic replies are written by the operator, so write them in the languages you support (a forced-topic pattern is a regular expression and can list words from several languages). Detection is weakest for very short text and for closely related languages written without accents.
