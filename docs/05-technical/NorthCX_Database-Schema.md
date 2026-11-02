# NorthCX Database Schema

Status: Draft proposal (Postgres).

| Table | Columns | Notes |
|---|---|---|
| `sessions` | `id` pk, `agent_id`, `customer_id`, `channel`, `created_at`, `updated_at` | |
| `messages` | `id` pk, `session_id` fk, `seq`, `role`, `content` jsonb, `created_at` | Ordered by `seq` |
| `customer_facts` | `customer_id`, `key`, `value`, `source_trace_id`, `updated_at` | pk (`customer_id`, `key`) |
| `traces` | `id` pk, `session_id` fk, `agent_id`, `status`, `started_at`, `finished_at` | |
| `trace_events` | `id` pk, `trace_id` fk, `seq`, `type`, `data` jsonb, `t` | Index (`trace_id`, `seq`) |
| `approvals` | `id` pk, `trace_id` fk, `tool`, `input` jsonb, `reason`, `state`, `decided_by`, `decided_at` | state: pending/approved/rejected |
| `agents` | `id` pk, `definition` jsonb, `version`, `published_at` | For Studio, Phase 4 |
| `api_keys` | `id` pk, `hash`, `role`, `created_at`, `revoked_at` | Store hashes only |

Indexes on `sessions(customer_id)`, `traces(session_id)`, `approvals(state)`. Retention jobs delete old `messages` and `trace_events` by policy.
