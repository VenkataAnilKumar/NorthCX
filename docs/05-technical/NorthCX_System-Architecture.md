# NorthCX System Architecture

Status: Draft. Backend is Python and the web platform is TypeScript (Decision Log #3). Component status below describes the TypeScript prototype, which is the reference implementation. Component selections are in the Reference (section 8).

## Layers
```
Channels         web chat | email | SMS | WhatsApp | voice
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
| Component | Responsibility | Status |
|---|---|---|
| Runtime (prototype: `src/prototype/src/core/runtime.ts`; product: Python backend) | Step loop, tool execution, guardrail checks, handoff, approvals | Scaffolded |
| Guardrails (`guardrails.ts`) | Rule and LLM-based supervisors; fail closed | Scaffolded |
| Tools (`agent.ts`) | Zod-validated tools with optional approval rule | Scaffolded |
| Memory (`store.ts`) | Session history and customer facts; pluggable | In-memory only |
| Traces (`trace.ts`) | Event log per run | In-memory / JSONL |
| Server (`src/prototype/src/server`) | HTTP API, auth, widget | Built |
| Approvals | Pending approvals and decisions | Built (in memory); resume Phase 2 |
| Simulation | Scenario runner, simulated customers, judge, CI gate | Phase 2 |
| Release service | Versions, environments, rollback, rollout | Phases 2-4 |
| Audit and access control | Roles, scoped keys, audit log, rate limits | Phase 2 |
| Handoff service | Handoff package, routing, return-to-agent | Phases 2-5 |
| Knowledge service adapter | Retrieval with citations | Phase 3 |
| Channel adapters | Email, messaging, voice, SDK | Phases 3-5 |
| Safety extensions | Input checks, PII redaction, monitoring | Phase 3 |
| Observability export | Redaction and OpenTelemetry export | Phase 3 |
| Studio and Insights | Low-code builder, dashboards | Phase 4 |

## Request flow (chat)
1. Channel adapter receives a message and calls `Runtime.run(agent, {sessionId, message, customerId})`.
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

## Deployment (target)
Docker Compose for development; containers for the server and workers; Postgres for state; optional Redis for queues. Details in the Deployment Guide (planned).

## Open decisions
1. Runtime language (see Tech-Stack-Decisions).
2. Persistence: Postgres schema in `05-technical/NorthCX_Database-Schema.md` (planned).
3. Whether one inbox integration is enough for v1 channels and handoff.

## After 1.0: staff platform
The Workspace, the extended Admin app, the Pilot task engine, personal memory and automations are described in `NorthCX_Staff-Platform-Architecture.md` (proposed, not built).
