# NorthCX API Design

Status: Draft

Base path `/v1`. JSON. `Authorization: Bearer <key>` (required once any key exists; see Security). Errors: `401` missing or invalid key (`token_expired` for a lapsed chat token), `403` the role lacks the permission, `429` rate limited (with `Retry-After`). `GET /` and `GET /health` are public.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness (public) |
| POST | `/chat-tokens` | `{sessionId?, customerId?, agent?, ttlSeconds?}`: mint a chat token for one conversation (channel or admin key); returns `token`, `sessionId`, `expiresAt` (built) |
| POST | `/agents/{id}/chat/stream` | Same request and access rules as chat, answered as server-sent events: `started`, `progress` (`{type: tool, name}`) while tools run, `delta` pieces of the approved reply, then `done` (the full chat response) or `error`. No `Idempotency-Key` (400) (built) |
| GET, POST | `/knowledge/sources` | List or create a knowledge source (`id`, `name`, optional `staleAfterDays`); `knowledge:read` / `knowledge:write` (built) |
| DELETE | `/knowledge/sources/{id}` | Delete a source and all its documents (built) |
| PUT | `/knowledge/sources/{id}/documents/{externalId}` | Add or update a document (`title`, `text`, optional `url`, `sourceUpdatedAt`); returns `created`, `updated` or `unchanged` (built) |
| DELETE | `/knowledge/sources/{id}/documents/{externalId}` | Delete a document and its passages at once (built) |
| GET | `/knowledge/documents` | List documents with freshness; `source`, `stale=true`, `limit` (built) |
| GET | `/knowledge/search` | `q`, `source`, `limit`: ranked passages with title, URL, section, `updatedAt`, `stale` (built) |
| GET | `/monitor/findings` | Monitoring flags, newest first; filters `rule`, `severity`, `agentId`, `sessionId`, `since`, `limit` (`monitor:read`, built) |
| GET | `/monitor/summary` | Counts per rule and severity, rule names, total (built) |
| POST | `/channels/email/inbound` | Raw RFC 822 message as the body (≤ 1,000,000 bytes), `channel:inbound` permission; returns `{status, sessionId, reason, traceId, handoffId}`; 400 unusable, 413 too large, 501 not configured (built) |
| GET | `/me` | The caller's name, role and permissions (any key) |
| GET | `/keys` | Keys (never secrets) and each role's permissions (admin) (built) |
| POST | `/keys` | `{name, role, expiresInDays?}`: create a key; the secret is returned once (admin) (built) |
| POST | `/keys/:id/revoke` | Revoke a key at once; the last admin key is protected (admin) (built) |
| GET | `/audit?limit=&before=&actor_name=&action=` | Audit entries, newest first (audit:read) (built) |
| GET | `/audit/verify` | Check the hash chain; returns `ok`, `checked`, `brokenAt`, `reason`, `head` (built) |
| POST | `/agents/:id/chat` | Send a message; body `{sessionId, message, customerId?}` |
| GET | `/traces/:id` | Fetch a trace |
| GET | `/traces?sessionId=` | List traces for a session |
| POST | `/agents/:id/versions` | `{spec | specYaml | fromBaseline, by, note?}`: save the next version (built) |
| GET | `/agents/:id/versions`, `/agents/:id/versions/:n` | List and read versions with their YAML (built) |
| GET | `/agents/:id/versions/:a/diff/:b` | Reviewable diff between two versions (built) |
| POST | `/agents/:id/releases` | `{version, by, note?}`: publish; 409 `gate_not_satisfied` with `reasons` unless the gate passes for that version (built) |
| POST | `/agents/:id/rollback` | `{by, note?, toVersion?}`: restore a previously live version or the spec file; no gate (built) |
| GET | `/agents/:id/releases`, `/agents/:id/live` | Release history; what is serving now (built) |
| GET | `/simulations/scenarios` | Scenarios and available modes (built) |
| POST | `/simulations/runs` | `{mode, only?, skipJudge?, agent?, version?}`: run scenarios (against a saved version if given) and store the result; 409 if a run is in progress (built) |
| GET | `/simulations/runs`, `/simulations/runs/:id` | Stored runs and a full report (built) |
| GET | `/simulations/gate?agent=&version=` | Whether the agent's spec file, or a saved version, passed every required scenario (built) |
| GET | `/audit` | Query the audit log (Phase 2) |
| DELETE | `/customers/:id` | Delete a customer's data (Phase 3) |
| GET | `/approvals?state=` | List approvals (built) |
| POST | `/approvals/:id/decision` | `{approved, by, note?}`: records the decision, runs the action once if approved, continues the conversation; returns the approval plus `resume` (`reply`, `status`, `traceId` or `error`). 404 unknown, 409 already decided |
| POST | `/approvals/expire` | `{olderThanSeconds}`: expire stale pending approvals and escalate (built) |
| GET | `/handoffs?state=&sessionId=` | Handoff queue (summaries) (built) |
| GET | `/handoffs/:id` | One handoff with its full package (built) |
| POST | `/handoffs/:id/resolve` | `{by, note?}`: mark resolved once; 409 if already resolved (built) |
| GET | `/sessions/:id/outbox?after=` | Messages sent outside a request, such as approval results (built) |

## Chat response
`{reply, status: "completed"|"escalated"|"needs_approval", traceId, pendingApprovals[], handoffId}` (`handoffId` is set when the status is `escalated`)

## Errors
`400` invalid body, `401` bad key, `404` unknown agent or trace, `429` rate limited, `500` internal. Error body `{error: {code, message}}`.

## Later
Server-sent events for streaming, webhooks for status changes, pagination for lists.


## Idempotency

`POST /v1/agents/{id}/chat` accepts an `Idempotency-Key` header (1-200 visible ASCII characters). A retry with the same key, caller, agent and conversation returns the first response unchanged with `Idempotent-Replay: true` and does not run the agent again. The same key with a different message or customer returns 422 `idempotency_key_reused`; a request still running returns 409 `request_in_progress`. Keys are kept 24 hours; a request that never finished (for example a crash) can be retried after five minutes. Failed requests (unknown agent, internal error) are not stored, so retrying them runs normally. Email deliveries are deduplicated by Message-ID instead.


## Streaming

`POST /v1/agents/{id}/chat/stream` returns `text/event-stream`. The agent's work and every supervisor check finish before the first `delta` is sent, so a customer never sees text a check could still reject; the pieces are the approved reply, split at word boundaries (joined they equal `reply` exactly). Progress events let a client show "Using lookup order…" during the wait. If the client disconnects, the turn still completes and is saved. Streaming of tokens straight from the model is not used because it would expose unchecked drafts.
