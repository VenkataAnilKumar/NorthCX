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

| `agent_versions` | `id` pk, `agent_id`, `number`, `definition` jsonb, `author`, `note`, `created_at` | Immutable |
| `environments` | `id` pk, `agent_id`, `name`, `version_id`, `rollout_percent` | |
| `releases` | `id` pk, `agent_id`, `version_id`, `environment`, `by`, `checks` jsonb, `created_at` | |
| `handoffs` | `id` pk, `trace_id`, `reason`, `trigger`, `package` jsonb, `queue`, `state` | |
| `audit_log` | `id` pk, `actor`, `action`, `target`, `detail` jsonb, `at` | Append-only |
| `knowledge_sources` | `id` pk, `name`, `kind`, `updated_at`, `status` | |
| `scenarios` | `id` pk, `suite`, `definition` jsonb, `required` bool, `origin_trace_id` | |
| `simulation_runs` | `id` pk, `agent_version_id`, `results` jsonb, `passed` bool, `at` | |
| `experiments` | `id` pk, `agent_id`, `variant_a`, `variant_b`, `split`, `state` | |

Indexes on `sessions(customer_id)`, `traces(session_id)`, `approvals(state)`. Retention jobs delete old `messages` and `trace_events` by policy.
