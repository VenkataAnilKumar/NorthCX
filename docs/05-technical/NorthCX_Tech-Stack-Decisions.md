# NorthCX Tech Stack Decisions

Status: Draft. Named third-party components and alternatives are recorded in `00-reference/NorthCX_Reference.md` (section 8).

## Core decisions
| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Runtime language | TypeScript (proposed) | Scaffold exists; one language across runtime, server and Studio |
| D2 | Model access | Anthropic SDK behind an `LLM` interface | Claude first-class; other backends possible |
| D3 | HTTP server | Hono | Small, typed, runs on Node and edge |
| D4 | Validation | Zod | Tool schemas double as model tool specs |
| D5 | Persistence | Postgres (SQLite for dev) | Sessions, traces, customer facts |
| D6 | Tests | Vitest | Fast, ESM-native |

## Integration points (implemented behind interfaces)
| Capability | Interface | Selection |
|---|---|---|
| Memory | `MemoryStore` | See Reference §8 |
| Knowledge retrieval | A tool calling an external service | See Reference §8 |
| Observability | OpenTelemetry export of traces | See Reference §8 |
| Channels and human inbox | Webhook adapter calling the chat API | See Reference §8 |
| Voice | Adapter calling the chat API | See Reference §8 |
| Supervisor | `Guardrail` interface | Own LLM supervisor first |
| Studio | Edits the agent definition format | Decide at Phase 4 |

## Constraints
- Only permissively licensed dependencies in the core (Apache-2.0, MIT, BSD).
- Components not written in TypeScript run as separate services behind HTTP.
- Licence caveats are tracked in the Reference.
