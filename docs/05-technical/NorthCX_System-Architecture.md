# NorthCX System Architecture

Status: Draft. Proposed, pending the runtime-language decision recorded in Tech-Stack-Decisions.

## Layers
```
Channels         web chat | email | SMS | WhatsApp | voice
                     |            |
                 Channel adapters (HTTP API, Chatwoot webhooks, Pipecat)
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
| Runtime (`src/core/runtime.ts`) | Step loop, tool execution, guardrail checks, handoff, approvals | Scaffolded |
| Guardrails (`guardrails.ts`) | Rule and LLM-based supervisors; fail closed | Scaffolded |
| Tools (`agent.ts`) | Zod-validated tools with optional approval rule | Scaffolded |
| Memory (`store.ts`) | Session history and customer facts; pluggable | In-memory only |
| Traces (`trace.ts`) | Event log per run | In-memory / JSONL |
| Server | HTTP API, SSE, widget | Planned |
| Simulation | Scenario runner, assertions, judge | Planned |
| Channel adapters | Chatwoot and voice bridges | Planned |
| Studio | Low-code builder | Planned |

## Request flow (chat)
1. Channel adapter receives a message and calls `Runtime.run(agent, {sessionId, message, customerId})`.
2. Runtime loads history and customer facts, builds the system prompt, calls the model with tool specs.
3. Tool calls are validated, checked by guardrails, held for approval if flagged, then executed.
4. The draft reply passes through reply guardrails; rejected drafts are rewritten up to twice, then escalated.
5. History and trace are saved; the reply and status (`completed`, `escalated`, `needs_approval`) return to the channel.

## Cross-cutting
- **Security:** schema validation on all tool input; approval gates; supervisors fail closed.
- **Observability:** one trace per run, exportable to an OpenTelemetry backend.
- **Model access:** behind an `LLM` interface (Claude by default; scripted model for tests).

## Deployment (target)
Docker Compose for development; containers for the server and workers; Postgres for state; optional Redis for queues. Details in the Deployment Guide (planned).

## Open decisions
1. Runtime language (see Tech-Stack-Decisions).
2. Persistence: Postgres schema in `05-technical/NorthCX_Database-Schema.md` (planned).
3. Whether Chatwoot is the only channel/handoff integration in v1.
