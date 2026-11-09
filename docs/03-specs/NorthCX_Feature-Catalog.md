# NorthCX Feature Catalog

Status: Draft. The complete list of NorthCX features. Priority: P0 must, P1 should, P2 could. Phase numbers follow `08-implementation/NorthCX_Implementation-Phases.md`. State: Built, Planned.

## 1. Agent definition and authoring
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| A1 | Agent defined by natural-language goals and policies | P0 | 1 | Built |
| A2 | Agents as code (version-controlled definitions, YAML spec) | P0 | 1-2 | Built |
| A3 | Reusable skills composed into workflows (for example triage, respond, confirm) | P1 | 3 | Built (skill files, composed into the agent; step lists) |
| A4 | Adjustable workflow flexibility (strict steps to free-form) per skill | P1 | 3 | Built (strict is enforced, guided and free are advice) |
| A5 | Journeys: scenario blueprints with goals, guardrails and required steps | P1 | 4 | Built (journeys inside the agent spec: goal, steps tied to tools, rules, done-when, hand-off conditions; strict ordering enforced; progress measured from tools used; test scenarios generated) |
| A6 | Journeys described in plain language and converted to definitions | P2 | 4 | Built (model drafts a checked definition for review; never saved by itself; needs a live model) |
| A7 | Templates for common support intents | P1 | 3 | Built (four templates with scenarios; API; gallery page planned) |
| A8 | Agent-assisted building: generate an agent from procedures, transcripts or call recordings | P2 | 6 | Built (reviewable draft from procedures, transcripts and, with a transcription service, recordings; masked, checked; refinement by instruction; automatic test scenarios) |
| A9 | Per-agent model choice and settings | P0 | 1 | Built |
| A10 | Brand voice and tone settings | P1 | 3 | Built (forbidden phrases are enforced) |

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
| R8 | Multi-agent orchestration (specialist agents, routing) | P2 | 5 | Built (an agent lists specialists and when to use them; the conversation moves to the specialist in the same turn and stays with it; limits, checks and simulations apply; parallel or supervisor-style orchestration not built) |
| R9 | Multilingual conversations with automatic language detection | P1 | 4 | Built (offline detection of 13 languages, same-language replies from a per-agent language list, language in hand-offs, insights and search; fallback messages and forced-topic replies stay in the language their author wrote) |
| R10 | Resume a run after a human decision | P0 | 2 | Built |

## 3. Tools and actions
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| T1 | Typed tools with schema validation | P0 | 1 | Built |
| T2 | Tool errors returned to the model | P0 | 1 | Built |
| T3 | Approval rules per tool and per input | P0 | 1 | Built |
| T4 | Idempotency keys and retries for writes | P1 | 3 | Built |
| T5 | Connector library (orders, billing, accounts, helpdesk) | P1 | 3 | Built (connectors as YAML data with host allowlist; five generic starting points, not product-specific integrations; paged lists with four styles; OAuth 2 client-credentials and refresh-token sign-in) |
| T6 | Tool permissions per agent and per customer scope | P1 | 3 | Built (customer, facts and channel scopes) |
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
| S8 | Input-side checks (prompt-injection, abuse detection) | P1 | 3 | Built: customer input and tool results are screened for injection; optional abuse detection (threats, abusive language, repetition, bursts) with calm handling and hand-off |
| S9 | PII detection and redaction | P1 | 3 | Built for customer input (masking or refusing emails, phone numbers, card and national-id numbers) and tool results (masked before the model sees them), and in conversation search, exports and drafting; a reply-side redaction policy is covered by the `no_personal_data_in_reply` and `no_card_numbers` rules |
| S10 | Monitoring of every conversation, not a sample | P1 | 3 | Built: deterministic rules on every turn, findings API; a Monitoring page and alert delivery planned |
| S11 | Policy library with tests | P1 | 3 | Built: five configurable policies, each with allow and block cases run in CI; more policies to add |

## 5. Handoff and human collaboration
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| H1 | Handoff to a human with reason | P0 | 1 | Built |
| H2 | Pending approvals stored with IDs | P0 | 1 | Built |
| H3 | Approvals API (list, decide) | P0 | 1 | Built |
| H4 | Handoff package: transcript, customer profile, actions taken, summary | P0 | 2 | Built (deterministic summary) |
| H5 | Human inbox integration | P1 | 3 | Built (signed webhook and Chatwoot adapter, queued retried delivery); inbound sync from the helpdesk via the resolve API |
| H6 | Agent assist for humans: suggested replies, next steps, call scripts | P2 | 5 | Built for chat (suggested reply, next steps, key facts, cautions on demand or automatically, shown in Studio and added to Chatwoot or webhook inboxes); call scripts come with voice |
| H7 | Return conversation to the agent after human help | P2 | 5 | Built (the agent stays quiet while a person has the conversation, people reply from Studio, and resolving hands the conversation back with the person's note) |
| H8 | Business hours and queue routing | P1 | 3 | Built (routing file, queues, holidays, after-hours message, queue filter) |

## 6. Channels
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| C1 | HTTP chat API | P0 | 1 | Built |
| C2 | Web chat widget | P0 | 1 | Built (demo page; uses chat tokens) |
| C3 | Email | P1 | 3 | Built (inbound mail, threaded replies, SMTP sending, loop and auto-reply protection; see the Channels document) |
| C4 | SMS and messaging apps | P1 | 3 | SMS built (Twilio-compatible); WhatsApp built (Meta Cloud API, several numbers, pictures and documents in, approved templates out); Telegram built; other messaging apps, sending media and buttons planned |
| C5 | Voice (phone) | P2 | 5 | Built as the conversation side with a provider-neutral WebSocket bridge protocol (disclosure, recording consent, speakable replies, keypad, hand-off to a phone queue or callback, silence, call records); no telephony or speech provider included and not tested on a real line |
| C6 | Voice: multilingual, language switching, barge-in | P2 | 5 | Built (barge-in that keeps only what the caller heard, per-utterance language detection with mid-call switching, platform phrases in four languages) |
| C7 | Embeddable SDK for mobile and web apps | P2 | 5 | Built for the web (dependency-free client with streaming, retries, token renewal, uploads, teammate replies and ratings, plus a drop-in `<northcx-chat>` widget); native iOS and Android SDKs not built (the REST calls are documented) |
| C8 | One agent definition across channels with channel-specific style | P1 | 3 | Built (per-channel style text in the agent spec) |
| C9 | Identity verification per channel | P1 | 3 | Built: the company's server vouches for the customer by minting the chat token with that customer's id; one-time-code verification by email or SMS gates sensitive tools through a tool scope |
| C10 | Attachments (images, documents) | P2 | 5 | Built (pictures, PDFs and plain text; PDFs as the file or, with `pdf_text`, as text with personal data masked, enabled per agent, checked by content, size-limited, optionally scanned, kept with the conversation and erased with it; the web test console can attach files; customer-facing upload UI comes with the client SDK) |

## 7. Knowledge and memory
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| K1 | Session memory | P0 | 1 | Built (in memory) |
| K2 | Customer facts | P0 | 1 | Built; long-term memories (free-text notes with recall) added |
| K3 | Persistent store | P0 | 2 | Built |
| K4 | Knowledge retrieval with source citations | P1 | 3 | Built: keyword search, numbered citations; optional meaning-based (hybrid) ranking through a configured embeddings service, with keyword fallback, an automatic approximate index for large knowledge bases and an optional model per source |
| K5 | Knowledge source connectors and freshness | P1 | 3 | Built: document API, freshness flags, file import (PDF, Word, PowerPoint, Excel, HTML, Markdown, text) and a polite website crawler with scheduled re-crawls; connectors to document systems and Office formats not built |
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
| Q5 | Regression scenarios from production traces | P1 | 3 | Built (draft endpoint with masking and warnings; review before use) |
| Q6 | Simulated customers with personas, including adversarial ones | P1 | 3 | Built (8 personas; fixed-line attack suites in CI; model-played customers in live runs, not yet run against a real model) |
| Q7 | Re-run simulations when knowledge or policies change | P1 | 3 | Built for knowledge changes (policies are covered by the release gate); live mode needed to notice changed answers |
| Q8 | Agent versioning and change history | P0 | 2 | Built |
| Q9 | Environments (dev, staging, production) and promotion | P1 | 3 | Built (API, test console selector, promote buttons on the versions page) |
| Q10 | Rollback to a prior version | P0 | 2 | Built |
| Q11 | Staged rollout and A/B experiments | P2 | 4 | Built (staged rollout of a proven candidate to a share of new conversations with sticky arms, side-by-side comparison, promote or stop; automatic stop rules and multi-arm tests still planned) |
| Q12 | Load and cost testing | P2 | 6 | Built (load test tool with release-gating targets, token-cost estimator with a CI baseline, measured numbers in `NorthCX_Performance.md`; real-model and long-run soak results not measured) |

## 9. Observability and insights
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| O1 | Per-run traces | P0 | 1 | Built |
| O2 | Trace API | P0 | 1 | Built |
| O3 | Trace export to an external backend | P1 | 3 | Built (Langfuse and OTLP, queued and retried) |
| O4 | Redaction before export | P1 | 3 | Built (none, masked, full; sampling) |
| O5 | Metrics: resolution, escalation, guardrail blocks, tool errors, latency, cost | P1 | 4 | Built (resolution is reported as containment until an agreed definition exists) |
| O6 | Containment rate, satisfaction score, intent gaps | P1 | 4 | Built (ratings are posted by the company's front end) |
| O7 | Workflow failure analysis | P1 | 4 | Built (ranked causes with example traces) |
| O8 | Natural-language analytics questions | P2 | 6 | Built (model plans a validated query over a fixed list of figures, with filters, conversation-finding and charts; answers are computed, not generated) |
| O9 | Alerts on error rate, latency and policy spikes | P1 | 4 | Built (six default rules, findings and signed webhook) |
| O10 | Conversation search and tagging | P1 | 4 | Built |

## 10. Studio
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| U1 | Agent editor (instructions, tools, guardrails, approvals) | P1 | 4 | Built (form editor with live checks, save as version, try in dev) |
| U2 | Test console with live trace | P1 | 4 | Built (streamed replies, trace, environment selector; opens from Studio) |
| U3 | Simulation runner and results | P1 | 4 | Built (runner, results, release gate, and a scenario editor with saved scenarios) |
| U4 | Conversation review and failure tagging | P1 | 4 | Built |
| U5 | Approval queue | P1 | 4 | Built (Studio Approvals page: pending approvals with the tool call and reason, approve or reject with a note) |
| U6 | Knowledge management | P1 | 4 | Built (sources, documents with editing, freshness, try-a-question) |
| U7 | Publish workflow with required checks | P1 | 4 | Built (checklist of required checks and warnings per version and environment; staged rollout built under Q11) |
| U8 | Role-based views | P1 | 4 | Early version built (navigation, buttons and forms follow the signed-in role) |

## 11. Security, administration and platform
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| P1 | Bearer API key auth | P0 | 1 | Built |
| P2 | Roles and scoped keys | P0 | 2 | Built: seven roles, hashed keys with expiry and revocation (not yet limited to particular agents) |
| P3 | Audit log | P0 | 2 | Built (append-only, hash-chained) |
| P4 | Rate limiting | P1 | 2 | Built (per process by default; shared across processes with `NORTHCX_LIMITS_BACKEND=postgres`) |
| P5 | Single sign-on for Studio | P2 | 4 | Built (OpenID Connect with PKCE, group-to-role mapping, short-lived session keys; multi-factor, directory sync and per-agent scoping remain with the identity provider or later work) |
| P6 | Data residency options | P2 | 6 | Built (residency policy file checked at start-up, strict mode, data-flow report for audits; one region per deployment) |
| P7 | Self-hosting with containers | P0 | 2 | Built (backend and web images, compose stack) |
| P8 | Webhooks for status events | P1 | 3 | Built (fifteen event types, signed webhook with retries, pollable feed; no message text in events) |
| P9 | Configuration through environment and files | P0 | 1 | Built |
| P10 | Multi-tenancy | P2 | Later | Planned |
| P11 | Usage metering and outcome-based billing | P2 | Later | Planned |

## Counts
106 features in sections 1 to 11 (the 1.0 set). Section 12 lists 76 further planned features for after 1.0. Built: 28. Everything else is planned. Features marked P0 and Planned define the remaining work for Phases 1 and 2.

## Traceability
Product requirements FR1-FR34 (the 1.0 set) in the PRD list the catalog IDs they cover in their "Catalog" column. Every P0 and P1 feature maps to at least one requirement.

## 12. Staff platform (designed 2026-11-09, planned after 1.0)
None of these is built. Requirements: `NorthCX_Workspace-Spec.md`, `NorthCX_Pilot-Spec.md`, `NorthCX_Personal-Intelligence-Spec.md`, `NorthCX_Automations-Spec.md`, `../07-design/NorthCX_Agent-Hub-Design.md`, `../04-ai-architecture/NorthCX_Hybrid-Model-Selection.md`. Product requirements FR35 to FR41 cover them.

### Workspace app
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| W1 | Home: what needs me, what is ready, recent work | P1 | After 1.0 | Planned (designed) |
| W2 | Inbox: hand-offs grouped, suggested reply, resolve with note | P1 | After 1.0 | Planned (designed) |
| W3 | Approvals tab in the Workspace | P1 | After 1.0 | Planned (designed) |
| W4 | Customers: cross-channel timeline, audited (second release) | P2 | After 1.0 | Planned (designed) |
| W5 | Pilot window (see PI) | P1 | After 1.0 | Planned (designed) |
| W6 | Assistants catalog | P1 | After 1.0 | Planned (designed) |
| W7 | Search across everything the person may see | P1 | After 1.0 | Planned (designed) |
| W8 | Library: sources, playbooks, canned answers | P1 | After 1.0 | Planned (designed) |
| W9 | Outputs | P1 | After 1.0 | Planned (designed) |
| W10 | Spaces | P1 | After 1.0 | Planned (designed) |
| W11 | Automations tab (see AU) | P2 | After 1.0 | Planned (designed) |
| W12 | Quality: review queue, scorecards, coaching | P2 | After 1.0 | Planned (designed) |
| W13 | Performance: personal and team figures | P2 | After 1.0 | Planned (designed) |
| W14 | Notifications, availability, app switcher, command bar | P1 | After 1.0 | Planned (designed) |

### Pilot
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| PI1 | Plan before work with estimate | P1 | After 1.0 | Planned (designed) |
| PI2 | Clarifying questions | P1 | After 1.0 | Planned (designed) |
| PI3 | Live Steps view | P1 | After 1.0 | Planned (designed) |
| PI4 | Pause, redirect, stop | P1 | After 1.0 | Planned (designed) |
| PI5 | Writes always ask first | P0 | After 1.0 | Planned (designed) |
| PI6 | Signed-in person's permissions | P0 | After 1.0 | Planned (designed) |
| PI7 | Citations | P1 | After 1.0 | Planned (designed) |
| PI8 | Files, sources, spaces, masked conversation context | P1 | After 1.0 | Planned (designed) |
| PI9 | Result tab with versions and sharing | P1 | After 1.0 | Planned (designed) |
| PI10 | Background runs | P1 | After 1.0 | Planned (designed) |
| PI11 | Side chat | P2 | After 1.0 | Planned (designed) |
| PI12 | Chat history and temporary chat | P1 | After 1.0 | Planned (designed) |
| PI13 | Drafts open in Inbox, never auto-sent | P0 | After 1.0 | Planned (designed) |
| PI14 | Cost and step limits per task | P1 | After 1.0 | Planned (designed) |

### Personal intelligence
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| PN1 | Layered instructions with fixed precedence | P0 | After 1.0 | Planned (designed) |
| PN2 | Persona and style | P2 | After 1.0 | Planned (designed) |
| PN3 | Memory with scopes and sources | P1 | After 1.0 | Planned (designed) |
| PN4 | Per-chat switches | P1 | After 1.0 | Planned (designed) |
| PN5 | What it used | P1 | After 1.0 | Planned (designed) |
| PN6 | Personal context with consent | P2 | After 1.0 | Planned (designed) |
| PN7 | Skills as instructions only | P2 | After 1.0 | Planned (designed) |
| PN8 | Personal assistants within own access | P2 | After 1.0 | Planned (designed) |
| PN9 | Temporary chat | P1 | After 1.0 | Planned (designed) |
| PN10 | Export and erase | P1 | After 1.0 | Planned (designed) |
| PN11 | Retention defaults | P1 | After 1.0 | Planned (designed) |
| PN12 | Customer data never in memory | P0 | After 1.0 | Planned (designed) |

### Automations and Builder
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| AU1 | Triggers | P2 | After 1.0 | Planned (designed) |
| AU2 | Durable runs | P2 | After 1.0 | Planned (designed) |
| AU3 | Person steps with deadlines | P2 | After 1.0 | Planned (designed) |
| AU4 | Gated write steps | P0 | After 1.0 | Planned (designed) |
| AU5 | Limits and kill switch | P1 | After 1.0 | Planned (designed) |
| AU6 | Run history | P2 | After 1.0 | Planned (designed) |
| AU7 | Versions, review, rollback | P2 | After 1.0 | Planned (designed) |
| AU8 | Pilot result to automation | P2 | After 1.0 | Planned (designed) |
| AU9 | Test runs with simulated writes | P2 | After 1.0 | Planned (designed) |
| AU10 | Visual editor | P2 | After 1.0 | Planned (designed) |
| AU11 | Failure alerts | P2 | After 1.0 | Planned (designed) |
| AU12 | Several-process safety | P1 | After 1.0 | Planned (designed) |

### Agent Hub and Builder
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| AH1 | Extended template schema | P1 | After 1.0 | Planned (designed) |
| AH2 | Requirements check | P1 | After 1.0 | Planned (designed) |
| AH3 | Install flow that never goes live | P0 | After 1.0 | Planned (designed) |
| AH4 | Updates with diff | P2 | After 1.0 | Planned (designed) |
| AH5 | Organization templates with review | P2 | After 1.0 | Planned (designed) |
| AH6 | Hub and Assistants screens | P1 | After 1.0 | Planned (designed) |
| AH7 | Predefined customer agents (7) | P1 | After 1.0 | Planned (designed) |
| AH8 | Predefined staff assistants (6) | P2 | After 1.0 | Planned (designed) |
| AH9 | Signed built-in entries and provenance | P2 | After 1.0 | Planned (designed) |
| AH10 | Builder assistant: reviewable drafts only | P2 | After 1.0 | Planned (designed) |

### Hybrid model selection
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| HM1 | Data-policy constraints first | P0 | After 1.0 | Planned (designed) |
| HM2 | Per-agent qualification | P1 | After 1.0 | Planned (designed) |
| HM3 | Operator rules | P1 | After 1.0 | Planned (designed) |
| HM4 | Cost ordering | P2 | After 1.0 | Planned (designed) |
| HM5 | Fallback never crosses a forbidden tier | P0 | After 1.0 | Planned (designed) |
| HM6 | Every choice recorded in the trace | P1 | After 1.0 | Planned (designed) |
| HM7 | Staff model modes | P1 | After 1.0 | Planned (designed) |
| HM8 | Local models earn trust by passing scenarios | P2 | After 1.0 | Planned (designed) |

### Admin app (extended Studio)
| ID | Feature | Pri | Phase | State |
|---|---|---|---|---|
| AD1 | Grouped navigation: Operate, Build, Govern, Platform | P1 | After 1.0 | Planned (designed) |
| AD2 | 25 organization pages | P1 | After 1.0 | Planned (designed) |
| AD3 | Personal settings group | P1 | After 1.0 | Planned (designed) |
| AD4 | Policies with per-level values and locks | P1 | After 1.0 | Planned (designed) |
| AD5 | Trust and reliability page | P2 | After 1.0 | Planned (designed) |
| AD6 | Usage and cost, billing and plan | P2 | After 1.0 | Planned (designed) |
