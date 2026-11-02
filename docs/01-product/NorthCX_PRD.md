# NorthCX PRD

Status: Draft

## Goals
1. Resolve common customer requests autonomously with measurable accuracy.
2. Make agent behavior safe, auditable and testable.
3. Be deployable by a small team on its own infrastructure.

## Success metrics
| Metric | Target (initial, to be validated) |
|---|---|
| Resolution rate on pilot intents | >= 60% |
| Policy violations reaching customers | 0 on the simulation suite |
| Correct handoff when unresolved | >= 95% |
| Time to first agent from a template | < 1 day |

## Requirements
| ID | Requirement | Priority | Phase |
|---|---|---|---|
| R1 | Define an agent with instructions, tools and guardrails | P0 | 1 |
| R2 | Tool calls validated against schemas; failures returned to the model | P0 | 1 |
| R3 | Supervisor checks on replies and tool calls; fail closed | P0 | 1 |
| R4 | Human approval for sensitive actions | P0 | 1 |
| R5 | Handoff to a human with transcript | P0 | 1 |
| R6 | Per-conversation trace store with API access | P0 | 1 |
| R7 | HTTP chat API and web widget | P0 | 1 |
| R8 | Conversation simulation tests with assertions and a judge model | P0 | 2 |
| R9 | Session and long-term memory behind a pluggable store | P1 | 2 |
| R10 | Knowledge retrieval tool (RAG) | P1 | 3 |
| R11 | Email, SMS, WhatsApp via a helpdesk/inbox integration | P1 | 3 |
| R12 | Trace export to an observability backend | P1 | 3 |
| R13 | Low-code Studio for non-engineers | P2 | 4 |
| R14 | Voice channel | P2 | 5 |
| R15 | Analytics / insights dashboards | P2 | 4 |

## Out of scope for v1
Outcome-based billing, multi-tenant SaaS, agent-builds-agent (Ghostwriter equivalent).

## Risks
| Risk | Mitigation |
|---|---|
| Hallucinated or unauthorised actions | Schema validation, approval gates, supervisor, simulations |
| Source claims about Sierra are unverified | Re-verify when docs are reachable |
| Dependency licence surprises (`ee/` dirs, source-available) | Licence matrix; prefer Apache/MIT/BSD |
| Model cost and latency | Cheaper supervisor model; caching; step limits |

## Open questions
See `05-technical/NorthCX_Build-vs-Adopt.md`.
