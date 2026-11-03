# NorthCX Channels and Voice

Status: Draft

## Channel adapter contract
An adapter translates a channel message to `POST /v1/agents/:id/chat {sessionId, message, customerId}` and posts `reply` back. Session ID is stable per conversation on that channel. When `status` is `escalated`, the adapter routes the conversation to the human inbox with the trace link.

## Channels by phase
| Channel | Phase | Notes |
|---|---|---|
| Web chat widget | 1 | Served by the API server |
| Email | 3 | Via inbox integration; thread ID maps to session |
| SMS / WhatsApp | 3 | SMS and WhatsApp built; opt-in and template rules apply |
| Voice | 5 | Built as a WebSocket protocol for a telephony bridge; see `NorthCX_Voice.md` |

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

## WhatsApp channel — as built (C4)

`POST /channels/whatsapp/meta` receives Meta Cloud API webhook calls; `GET` on the same address answers Meta's one-time verification (it echoes the challenge only when `hub.verify_token` matches `NORTHCX_WHATSAPP_VERIFY_TOKEN`, and only for a plain alphanumeric challenge). Neither uses an API key: every POST must carry a valid `X-Hub-Signature-256` (HMAC-SHA256 of the exact body with the app secret); failures are rate limited per address and audited like SMS.

- It runs on the same engine as SMS, so everything below applies unchanged: one conversation per phone number (idle after 24 hours by default), duplicate deliveries ignored, STOP/START/HELP words, a per-number hourly reply limit, a person who has taken over keeps the conversation (customer messages are held for them), hand-offs, privacy export/erase, and agent `channel_styles` under the key `whatsapp`. A person who uses both SMS and WhatsApp is the same customer (`phone:+…`) and shares memory; an opt-out applies to both.
- Text, buttons and list replies are read; images, audio, documents and other media are not, and the agent is told an attachment arrived. Delivery receipts and reactions are ignored.
- Replies go out through the outbox like every other channel and are split at 3,500 characters. Meta only allows free-form replies within 24 hours of the customer's last message: a refusal (any 4xx other than rate limiting) is recorded as `undeliverable` and not retried; network errors, 5xx and 429 are retried.
- **Several numbers.** `NORTHCX_WHATSAPP_PHONE_ID` can list up to ten phone number ids; `NORTHCX_WHATSAPP_AGENTS` gives each its own agent. A conversation belongs to the number it came in on and replies leave from it. Calls for a number that is not listed are ignored.
- **Pictures and documents.** If the agent accepts attachments (`attachments` in its spec) a picture or document the customer sends goes through the same checks as a web upload (content-sniffed, size-limited, optionally scanned, kept with the conversation and erased with it). The file is looked up through the Graph API and fetched only from a WhatsApp/Meta host; any other address is refused. If the agent does not accept attachments, or the file fails a check, the agent is told a file arrived and was not used. Audio, video and stickers are not read.
- **Templates.** `POST /v1/channels/whatsapp/templates/send` with `{phoneId, to, template, params}` (role: channel or admin) sends one of the approved templates listed in `NORTHCX_WHATSAPP_TEMPLATES`. It is refused unless the person has already messaged that number or is on `NORTHCX_WHATSAPP_OPTIN_FILE`, refused for anyone who opted out (STOP), and counts toward the hourly limit per person. The call is audited with a one-way reference to the number, not the number.
- Not built: sending media, interactive messages (buttons and lists) from the agent, automatic fall-back to a template when the 24-hour window has closed (the reply is recorded as undeliverable; send a template explicitly).

## Telegram channel — as built (C4)
`POST /channels/telegram/webhook` receives Bot API updates. Telegram signs nothing, so a secret you choose is registered with `setWebhook` as `secret_token` and every call must carry it in `X-Telegram-Bot-Api-Secret-Token` (constant-time comparison; failures are throttled and audited like the other webhooks). Only private chats are answered; groups, channels, edits and messages from bots are ignored (and acknowledged, so Telegram does not retry).

- It runs on the same engine as SMS and WhatsApp. The customer is the Telegram user (`tg:<id>`), with no phone number involved; `/stop` and `/start` (with or without `@botname`) work as opt-out and opt-in; the hourly reply limit, duplicate handling, hand-offs, privacy export/erase and `channel_styles` (key `telegram`) all apply.
- Photos and files are not read; the agent is told a file arrived. Replies are split at 3,500 characters. A blocked bot or deleted chat (4xx) is recorded as undeliverable and not retried; rate limits and 5xx errors are retried. The bot token is part of Telegram's request address, so it is never included in an error message or log line.
- Not built: groups, inline mode, buttons, sending files.

## One-time-code identity check — as built (C9)

Your server already says who a customer is when it mints the chat token. For sensitive actions this adds a second step: the customer proves they control the email address or phone number you have on file for them.

1. Report the customer's `email` and/or `phone` (international format) through the customer context hook, and set `NORTHCX_VERIFY=1` with email and/or SMS configured.
2. Give the agent the tools `send_verification_code` and `check_verification_code` and gate the sensitive tools with a scope: `tool_scopes: {issue_refund: {facts: {identity_verified: ["yes"]}}}`. The agent is told in its instructions when to ask.
3. The customer receives a six-digit code; the agent passes what the customer types to `check_verification_code`. If it is right, the conversation is verified for 30 minutes (configurable), including for the rest of the same turn.

**Guarantees.** The agent cannot choose where the code goes: the tool has no address field and reads only the facts your systems reported. Codes come from the system random source, are stored only as a keyed hash (HMAC with the server secret, bound to the conversation and customer), are single use, expire after 10 minutes, allow 5 tries (then the code is cancelled), and sending is limited to one per minute and three per hour per conversation. Verification belongs to one conversation and one customer and lapses. The value `identity_verified` is set only by the platform: a stored fact or a context reply that claims it is ignored. The code that is sent is never in a trace, log or audit entry, and the tool call that checks a typed code is recorded with the code masked. Failures to send are reported to the agent in calm words without server details, with a suggestion to hand off to a person.

**Limits.** The message in which the customer types the code is part of the conversation record like any other message (it is single use and short lived, so it is of no use afterwards). Voice, WhatsApp and Telegram conversations can be verified only through the email or SMS channel the code is sent by. Authenticator apps and passkeys are not covered.
