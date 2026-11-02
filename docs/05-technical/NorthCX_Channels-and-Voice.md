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

## Open questions
Streaming replies on the API, identity verification per channel, and per-channel style guidance in instructions.
