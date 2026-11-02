# NorthCX API Design

Status: Draft

Base path `/v1`. JSON. Optional `Authorization: Bearer <key>`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/agents/:id/chat` | Send a message; body `{sessionId, message, customerId?}` |
| GET | `/traces/:id` | Fetch a trace |
| GET | `/traces?sessionId=` | List traces for a session |
| GET | `/agents/:id/versions` | List versions (Phase 2) |
| POST | `/agents/:id/versions` | Create version (Phase 2) |
| POST | `/agents/:id/releases` | Publish a version to an environment after checks (Phase 2-3) |
| POST | `/agents/:id/rollback` | Restore a prior version (Phase 2) |
| POST | `/simulations/runs` | Run scenarios (Phase 2) |
| GET | `/audit` | Query the audit log (Phase 2) |
| DELETE | `/customers/:id` | Delete a customer's data (Phase 3) |
| GET | `/approvals?state=` | List approvals (built) |
| POST | `/approvals/:id/decision` | Record approve/reject with `{approved, by}` (built); resuming the run is planned for Phase 2 |

## Chat response
`{reply, status: "completed"|"escalated"|"needs_approval", traceId, pendingApprovals[]}`

## Errors
`400` invalid body, `401` bad key, `404` unknown agent or trace, `429` rate limited, `500` internal. Error body `{error: {code, message}}`.

## Later
Server-sent events for streaming, webhooks for status changes, pagination for lists.
