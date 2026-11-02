# NorthCX Implementation Checklist

Status: Living checklist. IDs refer to the Feature Catalog.

## Phase 1 (done in the TypeScript prototype; to be reproduced in the Python backend)
- [x] Scaffold, strict TypeScript, dependencies (P9)
- [x] Runtime, tools, guardrails, memory, traces (R1-R4, T1-T3, S1-S6, K1, K2, O1)
- [x] Unit tests (Q1)
- [x] Chat, trace and approvals API, bearer auth, widget (C1, C2, O2, H3, P1)
- [x] Example support agent
## Phase 2
- [ ] Simulation runner and scenarios (Q2)
- [ ] CI workflow and required checks (Q4)
- [ ] Judge rubric and calibration (Q3)
- [ ] Postgres store and migrations (K3)
- [ ] Approval resume (R10)
- [ ] Handoff package (H4); forced-handoff topics (S7)
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
