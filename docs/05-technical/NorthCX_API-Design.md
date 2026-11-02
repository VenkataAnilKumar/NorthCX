# NorthCX API Design

Status: Draft

Base path `/v1`. JSON. `Authorization: Bearer <key>` (required once any key exists; see Security). Errors: `401` missing or invalid key, `403` the role lacks the permission, `429` rate limited (with `Retry-After`). `GET /` and `GET /health` are public.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness (public) |
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
