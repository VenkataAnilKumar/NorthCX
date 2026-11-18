# NorthCX Tech Stack Decisions

Status: **Reference**. Updated: 2026-11-09. Master for: technology choices. Named third-party components and alternatives are recorded in `00-reference/NorthCX_Reference.md` (section 8).

## Backend language: decided
Decision (2026-11-02): **Python backend with a TypeScript web platform.** NorthCX copies and adapts reference code, and most reusable backend code is Python while the Studio source is TypeScript (Reference sections 11 and 12). The earlier TypeScript prototype (now in `src/prototype`) is kept as a **reference implementation** of the runtime semantics (history validity, fail-closed supervision, approvals) and is not the product.

## Core decisions
| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Backend language | Python 3.12+ | Largest body of reusable code (agent runtime, memory, guardrails, knowledge, voice) |
| D2 | Web platform language | TypeScript, Next.js, React, Tailwind | Source of the Studio and insights screens |
| D3 | Model access | An `LLM` interface and a provider registry; Claude through the Anthropic SDK or a direct HTTPS client | Claude first-class; other providers planned (E1) |
| D4 | Backend HTTP framework | FastAPI | Typed, async, OpenAPI for the web platform and adapters |
| D5 | Validation and tool schemas | Pydantic | Tool schemas double as model tool specs |
| D6 | Persistence | Postgres; the backend owns domain data and migrations | One owner of data; the web platform calls the backend API |
| D7 | Backend tests | pytest, scripted model, no network; Postgres tests with `NORTHCX_REQUIRE_DB=1` | Same rules as the prototype tests |
| D8 | Web tests | vitest component tests and browser smoke tests | Studio and SDK flows |
| D9 | Authentication | API keys for programs; OpenID Connect single sign-on for people, issuing short-lived keys | One auth system for backend and web |
| D10 | Containers | Separate backend and web images, one compose file | Self-hosting |

## Integration points (implemented behind interfaces)
| Capability | Interface | Selection |
|---|---|---|
| Memory | `MemoryStore`, `MemoryService` | Built in-house (Postgres) |
| Knowledge retrieval | The `search_knowledge` tool over the built-in knowledge store | Built in-house; optional external embeddings service |
| Observability | Trace export | OpenTelemetry (OTLP) and Langfuse exporters, built in-house |
| Channels and human inbox | Channel adapters calling the runtime; hand-off webhook and Chatwoot adapter | Built in-house |
| Voice | WebSocket bridge protocol | Built in-house; speech and telephony from the operator's bridge |
| Supervisor | `Guardrail` interface | Own LLM supervisor first |
| Studio | Edits the agent definition format | Built in-house |

## Constraints
- Only permissively licensed dependencies in the core (Apache-2.0, MIT, BSD).
- Components not written in Python or TypeScript (for example the inbox) are integrated through their APIs.
- Licence caveats are tracked in the Reference.
