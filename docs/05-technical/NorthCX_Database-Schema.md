# NorthCX Database Schema

Status: Draft. The tables marked **built** exist in migration `0001` and match `northcx/db/models.py`; the rest are proposals for later sprints.

| Table | Columns | Notes |
|---|---|---|
| `sessions` (built) | `id` pk, `created_at`, `updated_at` | `agent_id`, `customer_id` and `channel` columns arrive with deletion (K8) and channels |
| `messages` (built) | `id` identity pk, `session_id` fk (cascade), `seq`, `role`, `content` jsonb | Unique (`session_id`, `seq`); history is replaced atomically on save |
| `customer_facts` (built) | `customer_id`, `key`, `value`, `updated_at` | pk (`customer_id`, `key`); `source_trace_id` later |
| `traces` (built) | `id` pk, `session_id`, `agent_id`, `agent_version`, `status`, `started_at`, `tools` jsonb, `event_count` | Summary columns written at save so lists never load events |
| `trace_events` (built) | `id` identity pk, `trace_id` fk (cascade), `seq`, `type`, `t`, `data` jsonb | Unique (`trace_id`, `seq`) |
| `approvals` (built) | `id` pk, `trace_id`, `session_id`, `agent_id`, `customer_id`, `tool`, `input` jsonb, `reason`, `state`, `created_at`, `decided_by`, `decided_at`, `note`, `result` jsonb | State machine in the Handoff and Approvals spec; every transition is an atomic conditional update (migration 0002 added the context, note and result columns) |
| `outbox` (built) | `id` identity pk, `session_id`, `kind`, `payload` jsonb, `created_at`, `delivered_at`, `attempts` | Index (`session_id`, `id`); undelivered rows are retried |
| `agents` | `id` pk, `definition` jsonb, `version`, `published_at` | For Studio, Phase 4 |
| `api_keys` | `id` pk, `hash`, `role`, `created_at`, `revoked_at` | Store hashes only |

| `agent_versions` (built) | `id` pk, `agent_id`, `number`, `spec` jsonb, `digest`, `author`, `note`, `created_at` | Unique (`agent_id`, `number`); immutable; numbers assigned under a per-agent lock (migration 0005) |
| `environments` | `id` pk, `agent_id`, `name`, `version_id`, `rollout_percent` | Phase 3; today the latest `releases` row for `production` is what is live |
| `releases` (built) | `seq` identity pk, `id`, `agent_id`, `environment`, `action` (publish/rollback), `version_id` fk (null = spec file), `number`, `previous_number`, `by`, `note`, `gate` jsonb, `created_at` | Append-only; newest by `seq` is live; index (`agent_id`, `environment`, `seq`) |
| `handoffs` (built) | `id` pk, `session_id`, `trace_id`, `agent_id`, `customer_id`, `trigger`, `reason`, `topics` jsonb, `package` jsonb, `state`, `created_at`, `resolved_by`, `resolved_at`, `note` | Indexes (`state`, `created_at`) and `session_id`; resolve is an atomic conditional update (migration 0003); `queue` arrives with routing |
| `audit_log` | `id` pk, `actor`, `action`, `target`, `detail` jsonb, `at` | Append-only |
| `knowledge_sources` | `id` pk, `name`, `kind`, `updated_at`, `status` | |
| `scenarios` | `id` pk, `suite`, `definition` jsonb, `required` bool, `origin_trace_id` | |
| `simulation_runs` (built) | `id` pk, `created_at`, `mode`, `source`, `passed`, `seconds`, `counts` jsonb, `agent_digests` jsonb, `meta` jsonb, `results` jsonb | Index on `created_at`; results hold per-scenario digests used by the gate (migration 0004); `agent_version_id` replaces digests once versions exist |
| `experiments` | `id` pk, `agent_id`, `variant_a`, `variant_b`, `split`, `state` | |

Indexes on `sessions(customer_id)`, `traces(session_id)`, `approvals(state)`. Retention jobs delete old `messages` and `trace_events` by policy.
