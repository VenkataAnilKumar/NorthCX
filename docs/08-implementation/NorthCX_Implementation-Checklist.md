# NorthCX Implementation Checklist

Status: Living checklist. IDs refer to the Feature Catalog.

## Phase 1 (done in the TypeScript prototype and reproduced in the Python backend: 29 tests)
- [x] Scaffold, strict TypeScript, dependencies (P9)
- [x] Runtime, tools, guardrails, memory, traces (R1-R4, T1-T3, S1-S6, K1, K2, O1)
- [x] Unit tests (Q1)
- [x] Chat, trace and approvals API, bearer auth, widget (C1, C2, O2, H3, P1)
- [x] Example support agent
- [x] Python backend: runtime, guardrails, stores, approvals, FastAPI server, widget, example agent (`src/backend/`)
- [x] Input checks: PII masking and prompt-injection detection, adapted from a reference project (S8, S9 early; recorded in `THIRD_PARTY.md`)
- [x] Provenance files: `NOTICE`, `THIRD_PARTY.md`, `third_party/`
- [x] Web platform (`src/web`): overview, test console with live trace, conversations and trace viewer, approvals queue, agents (read-only), settings; browser-tested end to end against the backend
- [x] Offline demo model (`NORTHCX_DEMO=1`) for trying the platform without an API key
## Phase 2
- [x] Agent spec, registries and the example agent as a spec (W1); CI workflow and restricted-path check
- [x] Apache-2.0 licence
- [ ] Simulation runner and scenarios (Q2)
- [ ] CI workflow and required checks (Q4)
- [ ] Judge rubric and calibration (Q3)
- [x] Postgres stores (sessions, facts, traces, approvals) and migrations (K3); contract tests over both implementations; CI database service
- [ ] Retention and deletion jobs (Phase 3)
- [x] Approval resume (R10): decision, exactly-once execution with idempotency key, supervisor re-check, agent follow-up, outbox with signed webhook option, expiry sweeper
- [x] Handoff package (H4), handoff queue with resolve, and forced-handoff topics (S7); web handoffs page
- [ ] Versions, diff, rollback (Q8, Q10)
- [ ] Roles, scoped keys, audit log, rate limits (P2-P4)
- [ ] Secrets handling, dry-run mode (T7, T8)
- [ ] Container image and deployment guide (P7)
## Phase 3
- [ ] Safety extensions (S8-S11)
- [ ] Retrieval tool, citations, connectors, summarisation, retention (K4-K8)
- [ ] Email, SMS/messaging, identity verification, channel styles (C3, C4, C8, C9)
- [ ] Inbox integration, hours and routing (H5, H8)
- [ ] Fallback, streaming, budgets, idempotency, webhooks (R5-R7, T4, P8)
- [ ] Trace export and redaction (O3, O4); environments (Q9); regression from traces (Q5-Q7)
- [ ] Skills, flexibility, templates, tone (A3, A4, A7, A10); connectors and scopes (T5, T6)
## Phase 4
- [ ] Studio screens (U1-U8)
- [ ] Insights, alerts, search (O5-O7, O9, O10)
- [ ] Journeys, multilingual, SSO, experiments (A5, A6, R9, P5, Q11)
## Phase 5
- [ ] Voice and consent flow (C5, C6)
- [ ] Agent assist, return-to-agent, multi-agent, attachments, SDK (H6, H7, R8, C10, C7)
## Phase 6
- [ ] Agent-assisted building, natural-language analytics, load testing, data residency (A8, O8, Q12, P6)
- [ ] Security review, licence choice, contribution guide, v1.0
