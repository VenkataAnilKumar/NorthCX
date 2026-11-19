# AG-UI endpoint (WP 3.2)

`POST /v1/agents/{agent_id}/agui` streams one run as AG-UI events (server-sent events, one `data:` line per event). It sits beside `POST /v1/agents/{agent_id}/chat/stream`, which is unchanged, and shares its checks (access, per-conversation rate limit, token scope, attachments rules, the approved-reply rule). Permission: `chat:send`. Status: built 2026-11-19; the interrupt and resume field names are **unverified** against the specification (see `NorthCX_AG-UI-Check.md`, decision 203).

## Request
```json
{"threadId": "conversation-1", "runId": "r1", "messages": [{"id": "m1", "role": "user", "content": "Where is order 1042?"}]}
```
`threadId` is the conversation (`sessionId` elsewhere). The newest user message with text is the customer's message. `state`, `tools`, `context` and `forwardedProps` are accepted and not used. Send a message **or** `resume`, not both. No `Idempotency-Key` (as on the other stream).

## Events
| When | Event |
|---|---|
| First | `RUN_STARTED` `{threadId, runId}` |
| A tool starts | `TOOL_CALL_START` `{toolCallId, toolCallName}` then `TOOL_CALL_END` `{toolCallId}`. The runtime reports a tool when it starts, with no arguments or result, so there are no `TOOL_CALL_ARGS` or `TOOL_CALL_RESULT` events yet |
| The reply | `TEXT_MESSAGE_START` `{messageId, role: "assistant"}`, `TEXT_MESSAGE_CONTENT` `{messageId, delta}` in the same pieces as the other stream, `TEXT_MESSAGE_END`. Sent only after every supervisor has approved the reply, as on the other stream |
| Last | `RUN_FINISHED` `{threadId, runId, outcome, result}`; `result` is `{status, traceId, handoffId, agentVersion}`. Or `RUN_ERROR` `{message, code}` |

`outcome` is `success`, or `interrupt` when a held action is waiting; then `interrupts` lists each: `{id, reason: "approval_required", toolCallName, input, message}`. `id` is the approval id.

## Resume
```json
{"threadId": "conversation-1", "runId": "r2", "resume": [{"interruptId": "<approval id>", "approved": true, "note": "ok"}]}
```
- Only a person with `approvals:decide` who is not a customer token (403 otherwise; decision 203).
- One request must answer every action waiting in that conversation, each once. An unknown id, a repeated id, a missing one (the message names it), or nothing waiting (409) is refused before anything runs.
- Each answer calls the same code as `POST /v1/approvals/{id}/decision`: decided once, the tool runs once, audit entry `approval.decide`, the customer is told through their channel. A second request for an already-decided action is refused.
- The stream then carries the follow-up reply and ends with `RUN_FINISHED`.

## What it does not do
- Token streaming (the reply arrives after the run finishes, as on the other stream), shared state events, and a thread that refuses new messages while something is waiting (a customer may keep talking while a refund waits for a person, as today).

## Checks
`src/backend/tests/test_agui.py`: same text and tool calls as the existing stream; interrupt with the approval id; resume approves and rejects through the decision code with an audit entry; a second resume is refused; partial, unknown and duplicate answers; customer token and viewer refused; access rules; a failed model ends as a handoff result. Not yet tested: a real AG-UI client.
