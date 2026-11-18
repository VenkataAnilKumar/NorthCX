# NorthCX Implementation Checklist

> **Archived 2026-11-09.** The 1.0 checklist is complete; the living checklist is section 14 of `../12-project/NorthCX_Implementation-Plan.md`. Kept for history; not maintained.

Status: Living checklist. IDs refer to the Feature Catalog.

## Phase 1 (done in the TypeScript prototype and reproduced in the Python backend: 29 tests)
- [x] Scaffold, strict TypeScript, dependencies (P9)
- [x] Runtime, tools, guardrails, memory, traces (R1-R4, T1-T3, S1-S6, K1, K2, O1)
- [x] Unit tests (Q1)
- [x] Chat, trace and approvals API, bearer auth, widget (C1, C2, O2, H3, P1)
- [x] Example support agent
- [x] Python backend: runtime, guardrails, stores, approvals, FastAPI server, widget, example agent (`src/backend/`)
- [x] Input checks: PII masking and prompt-injection detection, written for NorthCX (an early adapted version was rewritten from scratch; see `THIRD_PARTY.md`) (S8, S9)
- [x] Provenance files: `NOTICE`, `THIRD_PARTY.md`, `third_party/`
- [x] Web platform (now `src/apps/studio`): overview, test console with live trace, conversations and trace viewer, approvals queue, agents (read-only), settings; browser-tested end to end against the backend
- [x] Offline demo model (`NORTHCX_DEMO=1`) for trying the platform without an API key
## Phase 2
- [x] Agent spec, registries and the example agent as a spec (W1); CI workflow and restricted-path check
- [x] Apache-2.0 licence
- [x] Simulation runner, scenario format, 18 example scenarios (3 adversarial), command line, judge and agreement check (Q2, part of Q3)
- [x] CI runs the scripted suite and fails on a required scenario (first part of Q4)
- [x] Stored simulation runs, release-gate rule, simulation API and web page, CI records its run (sprint 9)
- [x] Gate enforced when publishing a version (sprint 10)
- [ ] Calibrate the judge against human-labelled conversations with a real model (Q3)
- [x] Postgres stores (sessions, facts, traces, approvals) and migrations (K3); contract tests over both implementations; CI database service
- [x] Retention and deletion jobs (K8): export, erase and hourly retention purge across every store
- [x] Approval resume (R10): decision, exactly-once execution with idempotency key, supervisor re-check, agent follow-up, outbox with signed webhook option, expiry sweeper
- [x] Handoff package (H4), handoff queue with resolve, and forced-handoff topics (S7); web handoffs page
- [x] Immutable versions, diff, gated publishing, rollback, release history, live-agent serving, agent version on traces (Q8, Q10); web page for versions and releases
- [x] Roles, hashed API keys, tamper-evident audit log, rate limits (P2-P4); Access page; key command line
- [x] Secrets handling with redaction, and dry-run mode for write tools (T7, T8)
- [x] Container images, one-command stack, health and readiness endpoints, deployment guide (P7); CI builds and smoke-tests the stack
## Phase 3
- [x] Customer chat tokens: per-conversation, expiring, revocable, scoped to one conversation, customer and agent; demo page uses them
- [x] Safety extensions (S8-S11): input checks, PII masking, always-on monitoring, policy library with tests; abuse detection added later
- [x] Retrieval tool, citations, connectors, summarisation, retention (K4-K8); hybrid meaning-based search, file import and crawling added later
- [x] Email channel (C3); SMS, WhatsApp and Telegram (C4); channel styles (C8); identity verification by one-time code (C9)
- [x] Inbox integration, hours and routing (H5, H8)
- [x] Fallback, streaming, budgets, idempotency (R5-R7, T4); signed reply webhooks and status events (P8). Budgets are in tokens; currency budgets are planned (E1)
- [x] Trace export and redaction (O3, O4); environments (Q9); regression from traces (Q5-Q7)
- [x] Skills, flexibility, templates, tone (A3, A4, A7, A10); connectors and scopes (T5, T6)
## Phase 4
- [x] Studio screens (U1-U8); role-based views (U8) are an early version
- [x] Insights, alerts, search (O5-O7, O9, O10); Monitoring page and alert delivery tracking added later
- [x] Journeys, multilingual, SSO, experiments (A5, A6, R9, P5, Q11)
## Phase 5
- [x] Voice and consent flow (C5, C6), tested through a simulated telephony bridge; **not yet run on a live phone call**
- [x] Agent assist, return-to-agent, multi-agent, attachments, SDK (H6, H7, R8, C10, C7)
## Phase 6
- [x] Agent-assisted building, natural-language analytics, load testing, data residency (A8, O8, Q12, P6)
- [x] Security review and threat model (independent penetration test still to do)
- [x] Licence choice (Apache-2.0), contribution guide, code of conduct, changelog, dependency licence check
- [ ] v1.0.0 (release candidate `1.0.0-rc.1` tagged; final after penetration test and real-model pass)

## Still open for 1.0
- [ ] Calibrate the judge with a real model (Q3), and run the live-model pass
- [ ] Independent penetration test
- [ ] Push the `v1.0.0-rc.1` tag; cut 1.0.0 (see `NorthCX_Release-Checklist.md`)
- [ ] Prove the voice channel on a live call and each messaging channel against its live provider (FR24, FR15 acceptance)

## After 1.0
Planned in `NorthCX_Gap-Closure-Plan.md` (model providers, multi-tenancy, identity, staff workspace, automations, connectors, metering, deployment kit).
