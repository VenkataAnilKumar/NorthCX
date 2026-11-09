# NorthCX System Architecture

Status: Built (1.0 release candidate); the staff platform is designed, not built. Backend is Python and the web apps are TypeScript (Decision Log #3). Component selections are in the Reference (section 8).

## Layers
```
Channels         web chat | email | SMS | WhatsApp | Telegram | voice
                     |            |
                 Channel adapters (HTTP API, inbox webhooks, voice adapter)
                     |
Agent runtime    loop: model -> tool calls -> supervisor -> reply
                     |        |            |
                  Tools    Guardrails   Handoff / approvals
                     |
Data services    Memory store | Knowledge (RAG) | Trace store
                     |
Platform         Studio | Simulation & evals | Observability | Auth/RBAC
```

## Components
Python backend modules are under `src/backend/northcx/`; web apps under `src/apps/`. The TypeScript prototype in `src/prototype` is a reference implementation kept in CI, not part of the product. Status as of 2026-11-09.
| Component | Responsibility | Where | Status |
|---|---|---|---|
| Runtime | Step loop, tool execution, guardrail checks, hand-off, approvals, streaming | `runtime.py`, `agent.py`, `spec.py` | Built |
| Guardrails and safety | Rule and model supervisors (fail closed), input checks, tool-output checks, abuse | `guardrails.py`, `safety/` | Built |
| Tools and connectors | Typed tools, approval rules, scopes, idempotent writes, connectors defined as data | `agent.py`, `connectors.py`, `idempotency.py` | Built |
| Memory and facts | Session history, customer facts, long-term memories, summaries | `store.py`, `memory.py`, `summarize.py`, `db/` | Built (Postgres) |
| Knowledge | Sources, ingestion, crawls and schedules, embeddings, retrieval with citations | `knowledge.py`, `ingest.py`, `crawler.py`, `embeddings.py` | Built |
| Traces and observability | Event log per run, export with redaction, monitoring and alerts | `trace.py`, `trace_export.py`, `monitor.py`, `alerts.py` | Built |
| Approvals and hand-offs | Pending approvals and resume, hand-off package, inbox delivery, transfers | `approvals.py`, `approval_flow.py`, `handoffs.py`, `inbox.py`, `transfers.py` | Built |
| Simulation | Scenario runner, simulated customers, judge, CI gate, regression from traces | `simulation/`, `regression.py`, `scenario_draft.py` | Built |
| Release service | Versions, environments, rollback, staged rollout | `versions.py`, `rollout.py` | Built |
| Access and audit | Roles, keys, SSO, audit chain, rate limits, residency | `access.py`, `keys.py`, `sso.py`, `audit.py`, `residency.py` | Built |
| Channels | Web widget and SDK, email, SMS, WhatsApp, Telegram, voice bridge | `channels/`, `widget.py`, `voice.py`, `src/sdk` | Built |
| Model providers | `LLM` interface, provider registry, Claude (SDK or HTTPS), reliability wrapper, budgets | `providers/`, `llm.py`, `reliability.py`, `cost.py` | Partly built (E1) |
| Insights and analytics | Figures with denominators, resolution rate, plain-language questions | `insights.py`, `analytics_qa.py` | Built |
| Events | Signed status-event webhooks with retries, pollable feed, test sender | `events.py`, `outbox.py` | Built |
| Several processes | Roles (`all`, `api`, `worker`), job leases, shared limits and alert state | `leases.py`, `bootstrap/`, `db/stores/` | Built |
| Studio | Operator console | `src/apps/studio` | Built (flat navigation); regrouped Admin designed |
| Workspace | Staff app | `src/apps/workspace` | Early work in progress; designed (see `NorthCX_Staff-Platform-Architecture.md`) |
| Tenancy, staff backend, automations, Agent Hub | Staff platform | | Planned (E2, E5, E6, E8, E22) |

## Request flow (chat)
1. A channel adapter receives a message and calls `Runtime.run(agent, session_id, message, customer_id)` after input checks (`northcx/runtime.py`).
2. Runtime loads history and customer facts, builds the system prompt, calls the model with tool specs.
3. Tool calls are validated, checked by guardrails, held for approval if flagged, then executed.
4. The draft reply passes through reply guardrails; rejected drafts are rewritten up to twice, then escalated.
5. History and trace are saved; the reply and status (`completed`, `escalated`, `needs_approval`) return to the channel.

## Release path
Agent definition, then version, then required simulations, then promotion to an environment, then optional staged rollout with metric comparison, with rollback at every step. See `03-specs/NorthCX_Release-Management.md`.

## Cross-cutting
- **Security:** schema validation on all tool input; approval gates; supervisors fail closed.
- **Observability:** one trace per run, exportable to an OpenTelemetry backend.
- **Model access:** behind an `LLM` interface (Claude by default; scripted model for tests).

## Deployment
Container images and a Docker Compose stack (built and tested); Postgres 16 with pgvector for state; several processes with roles `api` and `worker` share state through the database (no Redis needed). Details in `../08-implementation/NorthCX_Deployment-Guide.md`.

## Decisions already made
Runtime language: Python (Tech-Stack-Decisions). Persistence: Postgres, schema in `NorthCX_Database-Schema.md`. Hand-off inbox: a signed webhook plus a Chatwoot adapter for 1.0. Tenancy model for after 1.0: shared schema with row-level security (D3, decision 170).

## After 1.0: staff platform
The Workspace, the extended Admin app, the Pilot task engine, personal memory and automations are described in `NorthCX_Staff-Platform-Architecture.md` (proposed, not built).
