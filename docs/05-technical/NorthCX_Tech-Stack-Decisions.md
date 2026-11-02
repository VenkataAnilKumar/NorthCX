# NorthCX Tech Stack Decisions

Status: Draft. Named third-party components and alternatives are recorded in `00-reference/NorthCX_Reference.md` (section 8).

## Backend language: decided
Decision (2026-11-02): **Python backend with a TypeScript web platform.** NorthCX copies and adapts reference code, and most reusable backend code is Python while the Studio source is TypeScript (Reference sections 11 and 12). The earlier TypeScript prototype in `src/`, `examples/` and `tests/` is kept as a **reference implementation** of the runtime semantics (history validity, fail-closed supervision, approvals) and is not the product.

## Core decisions
| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Backend language | Python 3.12+ | Largest body of reusable code (agent runtime, memory, guardrails, knowledge, voice) |
| D2 | Web platform language | TypeScript, Next.js, React, Tailwind | Source of the Studio and insights screens |
| D3 | Model access | Anthropic SDK behind an `LLM` interface | Claude first-class; other backends possible |
| D4 | Backend HTTP framework | FastAPI | Typed, async, OpenAPI for the web platform and adapters |
| D5 | Validation and tool schemas | Pydantic | Tool schemas double as model tool specs |
| D6 | Persistence | Postgres; the backend owns domain data and migrations | One owner of data; the web platform calls the backend API |
| D7 | Backend tests | pytest, scripted model, no network | Same rules as the prototype tests |
| D8 | Web tests | Component and end-to-end tests | Studio flows |
| D9 | Authentication | One identity provider shared by backend and web | Avoid two auth systems; reconcile the reference projects' differing choices |
| D10 | Containers | Separate backend and web images, one compose file | Self-hosting |

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
- Components not written in Python or TypeScript (for example the inbox) are integrated through their APIs.
- Licence caveats are tracked in the Reference.
