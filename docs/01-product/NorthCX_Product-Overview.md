# NorthCX Product Overview

Status: Snapshot (2026-11-05), release candidate 1.0.0-rc.1. Describes the product as ten layers, from what users see down to how it is sold. Companion documents: `NorthCX_Product-Definition.md` (vision and pillars), `NorthCX_PRD.md`, `NorthCX_Personas.md`, `../03-specs/NorthCX_Feature-Catalog.md` (every feature with its status), `../08-implementation/NorthCX_Gap-Closure-Plan.md` (what comes after 1.0).

**Status legend used throughout:** ✅ built and tested · 🔶 partly built · 🗺️ planned (epic and wave in the gap-closure plan) · ⛔ not something this repository can deliver alone (needs an outside party).

**In one paragraph.** NorthCX is an open-source, self-hosted platform for building, testing, releasing and running supervised AI agents that talk to customers and do the work: look up an order, issue a refund, update an account, and hand over to a person when they should. It is built on the Claude API, runs on your own infrastructure, and treats every reply and every action as something to check, test and audit. Today it is customer-facing; the plan extends it to the staff who serve those customers.

---

## 1. Core product modules (what users see)

| Module | Who uses it | What it is | Status |
|---|---|---|---|
| **Customer chat** (drop-in `<northcx-chat>` widget and browser SDK) | Customers | Streaming chat with uploads, teammate replies, ratings, token renewal; also reachable on email, SMS, WhatsApp, Telegram and phone | ✅ |
| **Studio**, the operator console | CX leads, developers, reviewers, auditors, administrators | A role-aware web console with the pages below | ✅ |
| &nbsp;&nbsp;Test console | Developers, CX leads | Chat with any agent in any environment and watch each step as a trace | ✅ |
| &nbsp;&nbsp;Conversations and Review | Reviewers | Search, tag, read and judge conversations; failure tagging; a queue of the conversations most worth a look | ✅ |
| &nbsp;&nbsp;Approvals | Approvers | Actions held for a person, with the exact input; approve or reject with a note | ✅ |
| &nbsp;&nbsp;Handoffs | Support staff | The queue of conversations sent to a person, with the package (transcript, facts, actions, suggested reply) and a place to reply or resolve | ✅ |
| &nbsp;&nbsp;Knowledge | CX leads | Sources, documents, file import, website crawls with schedules, freshness flags, a "try a question" box, indexing status | ✅ |
| &nbsp;&nbsp;Simulations | Developers | Run scenarios (including attack suites), see results, edit scenarios, release gate | ✅ |
| &nbsp;&nbsp;Agents | Developers, release managers | Versions, diff, publish checklist, release, staged rollout, rollback; a form editor with live checks; build an agent from your procedures, transcripts or recordings | ✅ |
| &nbsp;&nbsp;Insights | CX leads | Containment, escalation, guardrail blocks, tool errors, latency, rating, tokens and cost, each with its denominator; conversation search; plain-language questions with charts | ✅ |
| &nbsp;&nbsp;Monitoring | Operators | Always-on findings on every turn, active alerts, alert delivery status | ✅ |
| &nbsp;&nbsp;Access and audit; Data residency; Settings | Administrators, auditors | Keys and roles, the tamper-evident audit log, where data may go, sign-in | ✅ |
| **Human inbox integration** | Support staff | Hand-offs delivered to your helpdesk (signed webhook, Chatwoot adapter) | ✅ |
| **Command-line tools** | Developers, CI | Scenario runner with gating, load test, cost estimator | ✅ |
| **Staff workspace** (chat, agents, automations, libraries, generated outputs, history) | Support reps, leads, QA, operations | The same engine pointed at staff, under each person's permissions | 🗺️ E5, E6, E8 |
| **Admin portal, developer portal, ops console, back office** | Administrators, developers, operators | See section 6 | 🗺️ |

## 2. Capability areas

Grouped by the eight pillars of the product definition.

| Pillar | What the product does | Status |
|---|---|---|
| **Act** | Typed tools with schema validation and error return; tools declared read or write (writes are simulated in tests); idempotency keys and retries for approved writes; multi-step reasoning with step limits; resume after a human decision; specialist agents that take over a conversation; skills and **journeys** with enforced step order | ✅ |
| **Trust** | Input checks, reply guardrails, a supervisor model, approval rules per tool and input, tool scopes, forced hand-off topics, identity verification by one-time code, abuse detection, fail-closed behaviour; every action traced and audited | ✅ |
| **Prove** | Scenario simulations with assertions; simulated customers with personas; judge-model scoring; regression scenarios from production traces; immutable versions; environments (dev, staging, production); publish checklist and release gate tied to the exact version; staged rollout with comparison; one-step rollback | ✅ (judge not yet calibrated with a live model: 🔶) |
| **Collaborate** | Hand-off to a person with reason and package; business hours and queue routing; suggested replies; people reply from Studio; hand-back to the agent; conversation review | ✅ |
| **Reach** | One agent definition, a writing style per channel; **six channels**; 13 languages detected offline with same-language replies; attachments (pictures, PDFs, text); voice with consent, barge-in and keypad | ✅ |
| **Know** | Knowledge with citations and freshness; customer memory with recall and erase; customer context pulled from your systems at conversation start; history summarisation | ✅ |
| **Learn** | Metrics with denominators, alerts, always-on monitoring, conversation search and tags, plain-language analytics, trace export, signed status events | ✅ |
| **Own** | Apache-2.0, self-hosted, Docker Compose, no dependency on a vendor's runtime beyond the model API (isolated behind one interface) | ✅ |

**Build helpers:** templates for common intents (order status, returns and refunds, knowledge FAQ, human triage) with their scenarios; natural-language drafts for journeys and agents (always a draft for a person to review, never saved by itself); automatic test scenarios, refinement by instruction, and transcription of recordings for drafting.

## 3. Model layer

| Aspect | Today | Plan |
|---|---|---|
| **Providers** | Claude through the Messages API, behind a single interface (`LLM.complete`); nothing else in the code depends on the SDK | 🗺️ E1: provider adapters (OpenAI-compatible hosted and self-hosted servers first), provider-qualified model names, capability flags so an impossible configuration is refused at release time |
| **Choice of model** | Per agent; separate models for the supervisor, summaries and the judge | 🗺️ Per team and per purpose, with mixed-provider fallback chains |
| **Resilience** | Retries with back-off, optional fallback model, graceful hand-off when the model is down, supervisor errors fail closed | ✅ |
| **Budgets** | Token budgets per turn and per day, step and transfer limits | 🗺️ E1: budgets in currency, per-team budgets and spend views, cheaper-model routing for simple turns |
| **Private inference** | Not available | 🗺️ Self-hosted open-weight models through the OpenAI-compatible adapter (E1, E19) |
| **Supporting model services** | Optional, operator-configured HTTP services with the common shapes: **embeddings** (meaning-based search) and **speech-to-text** (recordings); both off by default | ✅ |
| **Quality assurance** | Everything is tested with scripted and offline models | ⛔ A live-model pass and judge calibration need an API key |

## 4. Data and retrieval layer

| Area | What exists | Status |
|---|---|---|
| **Storage** | Postgres 16 with pgvector; migrations run at start; an in-memory mode for development and tests; one store interface with an in-memory and a Postgres implementation for every kind of data | ✅ |
| **What is stored** | Conversations and messages, customer facts, long-term memories, traces and trace events, approvals, hand-offs, knowledge (sources, documents, passages, vectors), attachments, feedback, tags, reviews, scenarios and runs, versions and releases, rollouts, voice call records, status events, audit log | ✅ |
| **Knowledge ingestion** | Documents by API; files (PDF, Word, PowerPoint, Excel, HTML, Markdown, text); a polite website crawler (robots.txt, sitemaps, limits, pruning, scheduled re-crawls) | ✅ |
| **Retrieval** | Keyword ranking, optional **hybrid** keyword plus meaning search (reciprocal rank fusion), automatic approximate index for large bases, an optional embedding model per source, numbered citations, freshness flags, falls back to keywords if the embedding service is down | ✅ |
| **Customer context** | Facts reported by your own systems at conversation start (Python hook or signed HTTPS endpoint), treated as the source of truth and as untrusted text | ✅ |
| **Memory** | Session memory, summarisation for long conversations, customer memories with recall and erase | ✅ |
| **Privacy** | Export, erase and retention per customer and per conversation across every store | ✅ |
| **Search across other systems, staff memory, team libraries** | Not available | 🗺️ E5 (permission-aware search framework), E6 (libraries), E9 (connectors) |

## 5. Agent runtime and orchestration

The runtime is one loop with the same semantics in production, in tests and in simulations.

1. **Intake:** load history, facts, context and memories; if a person has the conversation, keep the message for them and stay quiet.
2. **Input checks:** personal-data masking, takeover phrasing, abuse and burst detection, forced hand-off topics, language handling.
3. **Model step:** the agent's instructions, skills and journeys, with tool schemas; the model proposes text or tool calls.
4. **Tool-call checks:** scopes, argument policies, journey order, approval rules; a call needing approval is stored with its exact input and the conversation pauses.
5. **Tool execution:** typed, retried when safe, secrets redacted, results screened before the model reads them.
6. **Reply checks:** rules plus an optional supervisor model; failure replaces the reply with a hand-off.
7. **Finish:** valid saved history on every exit path, trace, monitoring, outbox message, status events.

| Orchestration feature | Status |
|---|---|
| Specialist agents and transfers within a turn, with limits | ✅ |
| Approvals that resume the conversation exactly once, expiry that hands off | ✅ |
| Versioned agents (immutable), environments, staged rollout, rollback | ✅ |
| Background work: outbox retries, indexing, crawl schedules, alert evaluation, retention | ✅ |
| User-defined automations (schedule, webhook, event triggers; multi-step runs; run history) | 🗺️ E8 |
| Staff agents under the actor's permissions | 🗺️ E5 |
| Visual workflow editor over the same definitions | 🗺️ E14 |
| Routing simple turns to cheaper models | 🗺️ E1 |

## 6. Portals and surfaces

The full map, with epics and dependencies, is section 10 of the gap-closure plan. Summary:

| Surface | Audience | Status |
|---|---|---|
| Customer chat widget and SDK; email, SMS, WhatsApp, Telegram, voice | Customers | ✅ |
| **Studio** (operator console) | Operators | ✅ |
| Hand-off delivery to your helpdesk | Support staff | ✅ |
| Staff workspace; agent and automation builder with visual editor | Staff, builders | 🗺️ |
| Admin portal (users, groups, SSO, SCIM, roles, agent catalog, guardrail policies, connectors, usage, cost, audit) | Administrators | 🔶 keys, roles, SSO settings and audit exist; the rest 🗺️ |
| Developer portal (API reference, SDK guides, MCP, webhooks, sandbox) | Developers | 🔶 docs and a keys screen; portal 🗺️ |
| Analytics and observability dashboard | CX leads, operators | 🔶 conversation insights exist; adoption, runs and cost per team 🗺️ |
| Trust Center and Legal Center | Customers, auditors | 🔶 threat model and security review exist; centers 🗺️; reports need an auditor ⛔ |
| Deployment and ops console | Private-deployment operators | 🔶 health and residency pages; the rest 🗺️ |
| Internal back office (tenants, licenses, flags, support access) | The vendor | 🗺️ |
| Marketing site | Prospects | 🗺️ (README landing page exists) |
| Slack and Teams bots, Outlook and Word add-ins, browser extension, helpdesk sidebars, native mobile SDKs | Staff, developers | 🗺️; vendor accounts, store review and toolchains needed ⛔ |

## 7. Security and governance

| Area | What exists |
|---|---|
| **Identity and access** | Seven roles (administrator, release manager, developer, reviewer, auditor, viewer, channel); hashed keys with expiry and revocation; single sign-on with OpenID Connect and group-to-role mapping; customer chat tokens limited to one conversation; one-time-code identity verification for sensitive actions; per-tool scopes (identified customers, facts, channels) ✅. SAML, SCIM, groups and keys scoped to specific agents 🗺️ E3 |
| **Supervision** | Input checks, reply guardrails, supervisor model, approval rules per tool and input, forced hand-off topics, abuse detection, token budgets, fail-closed behaviour ✅ |
| **Audit and evidence** | Append-only, hash-chained audit log; per-run traces; release records tied to exact versions; signed status events ✅ |
| **Privacy** | Personal-data masking on input, tool output and exports; export, erase and retention; customer memories with recall and erase ✅ |
| **Data residency** | A policy file of allowed regions and a host-to-region map, checked at start-up (strict mode refuses to start); a report of every destination and what it receives ✅; per-tenant regions 🗺️ E2 |
| **Hardening** | Request size limits, security headers, CORS allow-list, SSRF controls on every outbound address (https, no redirects, private ranges refused), secrets scrubbed from everything stored, rate limits per key, session, address and conversation ✅; standing security tests (no pasted SQL, no dangerous constructs, redirect and CORS rules, parser fuzzing) ✅ |
| **Assessment** | Threat model and security review by the authors, with automated scans ✅; **independent penetration test ⛔ not done** |
| **Known limits (stated, not hidden)** | Rate limits and budgets are per process unless the Postgres limits backend is turned on; pictures and PDFs reach the model unmasked unless the masked-text option (🗺️ E0.4) is used; roles are server-wide; no multi-factor for API keys (use SSO) |
| **Compliance** | Controls exist and are documented; **SOC 2, ISO 27001/42001 and HIPAA need audits and an operating period ⛔**; documentation packs and customer-managed keys 🗺️ E12 |

## 8. Deployment options

| Option | What it is | Status |
|---|---|---|
| **Single host, Docker Compose** | Backend, Studio and Postgres with pgvector; one company, one region; the five-minute demo with an offline demo model; from-source run for development | ✅ |
| **Your own infrastructure** | The same containers on your servers or cloud account, with your database, secrets and network rules; data residency policy enforces where data may go | ✅ (by hand; no packaged chart) |
| **Dedicated single-tenant** | The same code with one tenant and optionally its own database | 🗺️ E2 |
| **Multi-tenant managed cloud** | Hosted by the vendor, tenant isolation by row-level security, per-tenant configuration, limits and usage | 🗺️ E2, E10; operating a service ⛔ |
| **Customer cloud account (VPC)** | Helm chart and Terraform modules for AWS, Azure and GCP, upgrade tool, ops console | 🗺️ E11; real clusters ⛔ |
| **On-premises or air-gapped** | With self-hosted models behind the OpenAI-compatible adapter, no outbound calls | 🗺️ E1, E11, E19 |

Capacity figures and the load tool are in `../08-implementation/NorthCX_Performance.md`; they were measured with a scripted model and say so. Real deployments depend mostly on model latency.

## 9. Integrations and ecosystem

| Kind | Supported today | Planned |
|---|---|---|
| **Channels** | Web widget and SDK; email (SMTP out, inbound mail API); SMS (Twilio-compatible); WhatsApp (Meta Cloud API); Telegram (Bot API); voice (a WebSocket bridge to any telephony provider) | Other messaging apps; sending media and buttons |
| **Helpdesk and inbox** | Signed webhook, Chatwoot adapter, hand-back from the helpdesk | Native vendor sidebars and connectors 🗺️ E9, E13 |
| **Business systems** | Declarative HTTP connectors in YAML (host allow-list, pagination, OAuth 2), five starting points (orders, billing, accounts, CRM, helpdesk), Python tools, customer context hook | Native connector packs for the common CX stack; connector SDK; OAuth setup in Studio 🗺️ E9 |
| **Tool protocol** | None yet | MCP client and server 🗺️ E4 |
| **Identity** | OpenID Connect single sign-on | SAML, SCIM 🗺️ E3 |
| **Observability and events** | Trace export (OpenTelemetry, Langfuse), alert webhooks, signed status events with a polling feed | Generated API reference and webhook tester 🗺️ E0 |
| **Model and AI services** | Claude; optional embeddings and speech-to-text services over common API shapes | OpenAI-compatible and self-hosted models 🗺️ E1 |
| **Developer ecosystem** | Open source (Apache-2.0), contribution guide and code of conduct, templates and skills, scenario files, CI recipe, browser SDK | Developer portal, sandbox tenant, connector and template marketplace 🗺️ |

## 10. Go-to-market pieces

| Piece | What exists | What is missing |
|---|---|---|
| **Positioning** | "An open-source platform for supervised customer-experience agents that resolve issues end to end, on infrastructure the company controls" (product definition) | A decision on naming the staff product (D2 in the gap-closure plan) |
| **Target market** | Mid-size and large companies with real support volume and engineering capacity; platform teams inside larger enterprises; first focus on e-commerce, subscription and service businesses (product definition) | Customer discovery to test it |
| **Personas** | CX lead, platform engineer, compliance owner, support agent, reviewer, administrator, end customer (`NorthCX_Personas.md`) | Real interviews |
| **Packaging** | Open core and self-host recommended for v1; managed cloud, outcome-based billing and commercial add-ons kept open as options (`NorthCX_Pricing-Model.md`) | Decision D1 (what is open and what is commercial); a trusted definition of "resolved" before outcome pricing |
| **Landing page** | The README: banner, feature overview, real Studio screenshots, flow diagram, safety Q&A, five-minute demo, honest status | A marketing site with product, use cases by team and industry, deployment options, security, demo booking 🗺️ E13, E21 |
| **Proof** | Honest status, release checklist, threat model, security review, a clean-checkout verification | **Customer stories: none yet** and none will be invented; a penetration test; compliance reports ⛔ |
| **Trial path** | Offline demo model needs no API key; five-minute Docker Compose start; templates and scenarios | A hosted sandbox 🗺️ E2, E12 |
| **Trust assets** | Threat model, security review, residency report, hash-chained audit, limits stated openly | Trust Center and Legal Center pages 🗺️ E12, E17 |
| **Community** | Contribution guide, code of conduct, security policy, changelog, decision log | A public roadmap page, a discussion forum, a connector and template marketplace |
| **Success measures** | Containment, escalation, satisfaction, guardrail blocks, cost per conversation (`NorthCX_Success-Metrics.md`) | A trusted, audited definition of "resolved" |

**Claims policy.** Marketing and sales material states only what the repository can back up, labels each item built, partly built or planned, and carries no invented customers, logos, quotes, benchmarks or certifications.

---

## Where each layer stands

| # | Layer | State at 1.0.0-rc.1 | Next |
|---|---|---|---|
| 1 | Core product modules | Customer chat and Studio complete | Staff workspace |
| 2 | Capability areas | All eight pillars built | Staff-side capabilities |
| 3 | Model layer | Claude only, tokens only | Multi-provider, currency budgets, private inference |
| 4 | Data and retrieval | Complete for the customer-facing product | Cross-system, permission-aware search |
| 5 | Agent runtime | Complete | Automations, staff agents |
| 6 | Portals and surfaces | Studio plus customer channels | Admin, developer, ops, back office, marketing, embedded |
| 7 | Security and governance | Strong controls, documented limits | Pen test, tenant isolation, SAML and SCIM, compliance packs |
| 8 | Deployment | Single host with Compose | Tenancy, charts, ops console |
| 9 | Integrations | Channels, helpdesk, YAML connectors, exports | MCP, native connectors |
| 10 | Go-to-market | README landing page, honest status | Marketing site, trust center, decisions D1 and D2 |
