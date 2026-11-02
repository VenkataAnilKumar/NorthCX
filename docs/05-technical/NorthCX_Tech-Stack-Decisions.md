# NorthCX Tech Stack Decisions

Status: Draft. Licences and versions are from third-party sources; verify against official repos.

## Decisions
| # | Decision | Choice | Alternatives | Rationale |
|---|---|---|---|---|
| D1 | Runtime language | **TypeScript** (proposed) | Python with Agno | Scaffold exists; Claude SDK, Sim and a web Studio share the language. Revisit if Agno's features are needed. |
| D2 | Model access | Anthropic SDK behind an `LLM` interface | LiteLLM | Keeps Claude first-class while allowing other backends later. |
| D3 | HTTP server | Hono | Fastify, Express | Small, typed, runs on Node and edge. |
| D4 | Validation | Zod | Valibot | Tool schemas double as model tool specs. |
| D5 | Persistence | Postgres | SQLite for dev | Sessions, traces, facts. |
| D6 | Tests | Vitest | Jest | Fast, ESM-native. |
| D7 | Observability | Langfuse via OpenTelemetry | Phoenix (source-available) | Permissive core licence. |
| D8 | Memory adapter | Mem0 behind `MemoryStore` | Letta, Graphiti | Apache-2.0; pluggable. |
| D9 | Knowledge / RAG | Onyx as a retrieval service | Own pgvector | Reuse connectors; verify the `ee/` split. |
| D10 | Channels / handoff | Chatwoot | Build own inbox | Covers email, SMS, WhatsApp, live chat. |
| D11 | Voice | Pipecat | LiveKit Agents | BSD-2; avoids LiveKit model-licence caveat. |
| D12 | Studio | Sim, or custom | Build | Decide at Phase 4. |
| D13 | Supervisor | Own LLM supervisor, NeMo Guardrails optional | NeMo only | Simple first; add rule engine if needed. |

## Language note
Pipecat, NeMo Guardrails, Mem0 and Agno are Python. If used, they run as separate services behind HTTP; the TypeScript runtime does not import them.

## Licence summary
Apache-2.0, MIT and BSD dependencies only in the core. Components with caveats (Onyx `ee/`, Langfuse `ee/`, Chatwoot enterprise features, LiveKit model licence, Phoenix ELv2) must be reviewed before use.
