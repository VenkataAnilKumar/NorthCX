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
| `email_sessions` (built) | `session_id` pk, `sender`, `subject`, `last_message_id`, `references` jsonb, `customer_id`, `verified`, `created_at` | One row per email conversation |
| `email_messages` (built) | `message_id` pk, `session_id`, `direction` (in/out), `status`, `peer`, `created_at` | Dedupe by Message-ID; index (`peer`, `direction`, `created_at`) for per-sender limits; `outbox.last_attempt_at` drives back-off |
| `monitor_findings` (built) | `id` pk, `rule`, `severity`, `detail`, `trace_id`, `session_id`, `agent_id`, `agent_version`, `created_at` | Indexes on time, (rule, time), session |
| `idempotency_keys` (built) | `scope` pk (hash of caller, agent, conversation, key), `req_hash`, `response` jsonb (null while running), `created_at` | Expired after 24 h |
| `knowledge_sources` (built) | `id` pk, `name`, `stale_after_days`, `created_at` | |
| `knowledge_documents` (built) | `id` pk, `source_id` fk (cascade), `external_id`, `title`, `url`, `content_hash`, `chunks`, `source_updated_at`, `ingested_at` | Unique (`source_id`, `external_id`) |
| `knowledge_chunks` (built) | `id` identity pk, `document_id` fk (cascade), `seq`, `heading`, `body`, `search_text`, `tsv` (generated full-text vector) | GIN index on `tsv`; deleting a document removes its passages |
| `session_index` (built) | `session_id` + `customer_id` pk (`''` = no known customer), `first_seen`, `last_seen` | Written on every turn; drives export, erasure and retention; `idempotency_keys.session_id` links stored replies to a conversation |
| `customer_memories` (built) | `id` pk, `customer_id`, `text` (max 300), `text_hash`, `source_session`, `created_at`, `updated_at`, `tsv` (generated) | Unique (`customer_id`, `text_hash`); GIN index on `tsv`; at most 200 per customer |
| `inbox_events` (built) | `id` pk, `handoff_id`, `connector`, `event` (created/resolved), `created_at`, `attempts`, `last_attempt_at`, `delivered_at`, `external_ref`, `error` | Delivery queue to helpdesks; retried with back-off up to 12 attempts; erased with the hand-off |
| `trace_exports` (built) | `id` pk, `trace_id`, `exporter`, `created_at`, `attempts`, `last_attempt_at`, `delivered_at`, `error` | Queue of traces to send to observability backends; retried with back-off up to 12 attempts; erased with the conversation |
| `conversation_feedback` (built) | `session_id` pk, `rating` 1-5, `comment`, `created_at` | One rating per conversation; erased with it |
| `conversation_tags` (built) | (`session_id`, `tag`) pk, `by`, `created_at` | At most 20 tags per conversation; erased with it |
| `traces.environment` (built) | `varchar(32)`, default `production` | Which environment answered the turn |
| `agents` | `id` pk, `definition` jsonb, `version`, `published_at` | For Studio, Phase 4 |
| `api_keys` (built) | `key_id` pk, `name`, `role`, `key_hash`, `created_by`, `created_at`, `expires_at`, `revoked_at`, `revoked_by`, `last_used_at` | Only the SHA-256 hash of the secret is stored (migration 0006) |

| `agent_versions` (built) | `id` pk, `agent_id`, `number`, `spec` jsonb, `digest`, `author`, `note`, `created_at` | Unique (`agent_id`, `number`); immutable; numbers assigned under a per-agent lock (migration 0005) |
| `environments` | `id` pk, `agent_id`, `name`, `version_id`, `rollout_percent` | Phase 3; today the latest `releases` row for `production` is what is live |
| `releases` (built) | `seq` identity pk, `id`, `agent_id`, `environment`, `action` (publish/rollback), `version_id` fk (null = spec file), `number`, `previous_number`, `by`, `note`, `gate` jsonb, `created_at` | Append-only; newest by `seq` is live; index (`agent_id`, `environment`, `seq`) |
| `handoffs` (built) | `id` pk, `session_id`, `trace_id`, `agent_id`, `customer_id`, `trigger`, `reason`, `topics` jsonb, `package` jsonb, `state`, `created_at`, `resolved_by`, `resolved_at`, `note` | Indexes (`state`, `created_at`) and `session_id`; resolve is an atomic conditional update (migration 0003); `queue` arrives with routing |
| `audit_log` (built) | `id` pk (assigned under a lock, gapless), `at`, `actor`, `role`, `key_id`, `action`, `target`, `outcome`, `detail` jsonb, `prev_hash`, `hash` | Append-only: triggers refuse UPDATE, DELETE and TRUNCATE; the hash chain exposes edits made around them (migration 0006) |
| `knowledge_sources` | `id` pk, `name`, `kind`, `updated_at`, `status` | |
| `scenarios` | `id` pk, `suite`, `definition` jsonb, `required` bool, `origin_trace_id` | |
| `simulation_runs` (built) | `id` pk, `created_at`, `mode`, `source`, `passed`, `seconds`, `counts` jsonb, `agent_digests` jsonb, `meta` jsonb, `results` jsonb | Index on `created_at`; results hold per-scenario digests used by the gate (migration 0004); `agent_version_id` replaces digests once versions exist |
| `experiments` | `id` pk, `agent_id`, `variant_a`, `variant_b`, `split`, `state` | |

Indexes on `sessions(customer_id)`, `traces(session_id)`, `approvals(state)`. Retention jobs delete old `messages` and `trace_events` by policy.
| `managed_scenarios` (built) | `name` pk, `agent_id`, `required`, `definition` jsonb, `created_by`, `updated_by`, `created_at`, `updated_at`, `revision` | Scenarios saved by the editor; run and gated like file scenarios; a name used by a file belongs to the file |
| `knowledge_documents.body` (built) | `text`, nullable | The document as submitted, so it can be edited; null for documents saved before this column existed |
