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
