# NorthCX Feature Catalog

Status: Draft. The complete list of NorthCX features. Priority: P0 must, P1 should, P2 could. Phase numbers follow `08-implementation/NorthCX_Implementation-Phases.md`. State: Built, Planned.

## 1. Agent definition and authoring
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| A1 | Agent defined by natural-language goals and policies | P0 | 1 | Built |
| A2 | Agents as code (version-controlled definitions, YAML spec) | P0 | 1-2 | Built |
| A3 | Reusable skills composed into workflows (for example triage, respond, confirm) | P1 | 3 | Planned |
| A4 | Adjustable workflow flexibility (strict steps to free-form) per skill | P1 | 3 | Planned |
| A5 | Journeys: scenario blueprints with goals, guardrails and required steps | P1 | 4 | Planned |
| A6 | Journeys described in plain language and converted to definitions | P2 | 4 | Planned |
| A7 | Templates for common support intents | P1 | 3 | Planned |
| A8 | Agent-assisted building: generate an agent from procedures, transcripts or call recordings | P2 | 6 | Planned |
| A9 | Per-agent model choice and settings | P0 | 1 | Built |
| A10 | Brand voice and tone settings | P1 | 3 | Planned |

## 2. Runtime
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| R1 | Multi-step reasoning loop with tools | P0 | 1 | Built |
| R2 | Step limit and rewrite limit | P0 | 1 | Built |
| R3 | Valid saved history on every exit path | P0 | 1 | Built |
| R4 | Graceful escalation on model failure | P0 | 1 | Built |
| R5 | Model fallback and retry with backoff | P1 | 3 | Built |
| R6 | Streaming responses | P1 | 3 | Built as progressive delivery of the checked reply plus tool progress; raw token streaming deliberately not used |
| R7 | Per-conversation token and cost budget | P1 | 3 | Built for tokens (per turn and per day); cost in currency planned |
| R8 | Multi-agent orchestration (specialist agents, routing) | P2 | 5 | Planned |
| R9 | Multilingual conversations with automatic language detection | P1 | 4 | Planned |
| R10 | Resume a run after a human decision | P0 | 2 | Built |

## 3. Tools and actions
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| T1 | Typed tools with schema validation | P0 | 1 | Built |
| T2 | Tool errors returned to the model | P0 | 1 | Built |
| T3 | Approval rules per tool and per input | P0 | 1 | Built |
| T4 | Idempotency keys and retries for writes | P1 | 3 | Built |
| T5 | Connector library (orders, billing, accounts, helpdesk) | P1 | 3 | Planned |
| T6 | Tool permissions per agent and per customer scope | P1 | 3 | Planned |
| T7 | Secrets management for tool credentials | P0 | 2 | Built (environment or mounted files, scrubbed from everything stored) |
| T8 | Tool sandbox or dry-run mode for testing | P1 | 2 | Built (write tools are simulated in simulations) |

## 4. Supervision and safety
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| S1 | Reply guardrails | P0 | 1 | Built |
| S2 | Tool-call guardrails | P0 | 1 | Built |
| S3 | Model-based policy supervisor | P0 | 1 | Built |
| S4 | Payment-card number rule | P0 | 1 | Built |
| S5 | Fail closed on supervisor or model error | P0 | 1 | Built |
| S6 | Customer data treated as untrusted in prompts | P0 | 1 | Built |
| S7 | Topics the agent must never handle alone (forced handoff list) | P0 | 2 | Built |
| S8 | Input-side checks (prompt-injection, abuse detection) | P1 | 3 | Partly built: customer input and tool results are screened; abuse detection planned |
| S9 | PII detection and redaction | P1 | 3 | Planned |
| S10 | Monitoring of every conversation, not a sample | P1 | 3 | Built: deterministic rules on every turn, findings API; a Monitoring page and alert delivery planned |
| S11 | Policy library with tests | P1 | 3 | Built: five configurable policies, each with allow and block cases run in CI; more policies to add |

## 5. Handoff and human collaboration
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| H1 | Handoff to a human with reason | P0 | 1 | Built |
| H2 | Pending approvals stored with IDs | P0 | 1 | Built |
| H3 | Approvals API (list, decide) | P0 | 1 | Built |
| H4 | Handoff package: transcript, customer profile, actions taken, summary | P0 | 2 | Built (deterministic summary) |
| H5 | Human inbox integration | P1 | 3 | Planned |
| H6 | Agent assist for humans: suggested replies, next steps, call scripts | P2 | 5 | Planned |
| H7 | Return conversation to the agent after human help | P2 | 5 | Planned |
| H8 | Business hours and queue routing | P1 | 3 | Planned |

## 6. Channels
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| C1 | HTTP chat API | P0 | 1 | Built |
| C2 | Web chat widget | P0 | 1 | Built (demo page; uses chat tokens) |
| C3 | Email | P1 | 3 | Planned |
| C4 | SMS and messaging apps | P1 | 3 | Planned |
| C5 | Voice (phone) | P2 | 5 | Planned |
| C6 | Voice: multilingual, language switching, barge-in | P2 | 5 | Planned |
| C7 | Embeddable SDK for mobile and web apps | P2 | 5 | Planned |
| C8 | One agent definition across channels with channel-specific style | P1 | 3 | Planned |
| C9 | Identity verification per channel | P1 | 3 | Partly built: the company's server vouches for the customer by minting the chat token with that customer's id; one-time-code verification planned |
| C10 | Attachments (images, documents) | P2 | 5 | Planned |

## 7. Knowledge and memory
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| K1 | Session memory | P0 | 1 | Built (in memory) |
| K2 | Customer facts | P0 | 1 | Built; long-term memories (free-text notes with recall) added |
| K3 | Persistent store | P0 | 2 | Built |
| K4 | Knowledge retrieval with source citations | P1 | 3 | Built: keyword search, numbered citations; meaning-based ranking planned |
| K5 | Knowledge source connectors and freshness | P1 | 3 | Partly built: document API and freshness flags; connectors and file parsing planned |
| K6 | History summarisation for long sessions | P1 | 3 | Built |
| K7 | Customer context pulled from business systems at conversation start | P1 | 3 | Built (Python hook and signed HTTPS endpoint) |
| K8 | Retention, export and deletion per customer | P1 | 3 | Built |

## 8. Testing and release
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| Q1 | Unit tests with a scripted model | P0 | 1 | Built |
| Q2 | Scenario simulations with assertions | P0 | 2 | Built |
| Q3 | Judge-model scoring with calibration | P1 | 2 | Judge and agreement check built; not yet calibrated with a real model |
| Q4 | CI gate on required scenarios | P0 | 2 | Built: CI step, stored runs and gate rule; enforced at promotion in sprint 10 |
| Q5 | Regression scenarios from production traces | P1 | 3 | Planned |
| Q6 | Simulated customers with personas, including adversarial ones | P1 | 3 | Planned |
| Q7 | Re-run simulations when knowledge or policies change | P1 | 3 | Planned |
| Q8 | Agent versioning and change history | P0 | 2 | Built |
| Q9 | Environments (dev, staging, production) and promotion | P1 | 3 | Planned (one production environment exists today) |
| Q10 | Rollback to a prior version | P0 | 2 | Built |
| Q11 | Staged rollout and A/B experiments | P2 | 4 | Planned |
| Q12 | Load and cost testing | P2 | 6 | Planned |

## 9. Observability and insights
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| O1 | Per-run traces | P0 | 1 | Built |
| O2 | Trace API | P0 | 1 | Built |
| O3 | Trace export to an external backend | P1 | 3 | Planned |
| O4 | Redaction before export | P1 | 3 | Planned |
| O5 | Metrics: resolution, escalation, guardrail blocks, tool errors, latency, cost | P1 | 4 | Planned |
| O6 | Containment rate, satisfaction score, intent gaps | P1 | 4 | Planned |
| O7 | Workflow failure analysis | P1 | 4 | Planned |
| O8 | Natural-language analytics questions | P2 | 6 | Planned |
| O9 | Alerts on error rate, latency and policy spikes | P1 | 4 | Planned |
| O10 | Conversation search and tagging | P1 | 4 | Planned |

## 10. Studio
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| U1 | Agent editor (instructions, tools, guardrails, approvals) | P1 | 4 | Planned |
| U2 | Test console with live trace | P1 | 4 | Planned |
| U3 | Simulation runner and results | P1 | 4 | Early version built (runs, results, release gate); scenario editing planned |
| U4 | Conversation review and failure tagging | P1 | 4 | Planned |
| U5 | Approval queue | P1 | 4 | Planned |
| U6 | Knowledge management | P1 | 4 | Planned |
| U7 | Publish workflow with required checks | P1 | 4 | Early version built (versions page: save, run scenarios, publish, roll back) |
| U8 | Role-based views | P1 | 4 | Early version built (navigation, buttons and forms follow the signed-in role) |

## 11. Security, administration and platform
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| P1 | Bearer API key auth | P0 | 1 | Built |
| P2 | Roles and scoped keys | P0 | 2 | Built: seven roles, hashed keys with expiry and revocation (not yet limited to particular agents) |
| P3 | Audit log | P0 | 2 | Built (append-only, hash-chained) |
| P4 | Rate limiting | P1 | 2 | Built (per process) |
| P5 | Single sign-on for Studio | P2 | 4 | Planned |
| P6 | Data residency options | P2 | 6 | Planned |
| P7 | Self-hosting with containers | P0 | 2 | Built (backend and web images, compose stack) |
| P8 | Webhooks for status events | P1 | 3 | Planned |
| P9 | Configuration through environment and files | P0 | 1 | Built |
| P10 | Multi-tenancy | P2 | Later | Planned |
| P11 | Usage metering and outcome-based billing | P2 | Later | Planned |

## Counts
106 features. Built: 28. Everything else is planned. Features marked P0 and Planned define the remaining work for Phases 1 and 2.

## Traceability
Product requirements FR1-FR34 in the PRD list the catalog IDs they cover in their "Catalog" column. Every P0 and P1 feature maps to at least one requirement.
