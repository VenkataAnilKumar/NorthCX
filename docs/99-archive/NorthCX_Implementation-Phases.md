# NorthCX Implementation Phases

> **Archived 2026-11-09.** The 1.0 phases are finished; current plan: `../12-project/NorthCX_Implementation-Plan.md`. Kept for history; not maintained.

Status: Draft. Feature IDs from `12-project/NorthCX_Feature-Catalog.md`.

| Phase | Goal | Deliverables (catalog IDs) | Exit criteria |
|---|---|---|---|
| 1 | Working agent over HTTP | A1, A2, A9, R1-R4, T1-T3, S1-S6, H1-H3, C1, C2, K1, K2, Q1, O1, O2, P1, P9, example agent | Example agent resolves, escalates and blocks correctly in tests; widget works |
| 2 | Safe to change and operate | K3 persistence, R10 approval resume, H4 handoff package, S7 forced handoff, T7 secrets, T8 dry-run, Q2-Q4 simulations and CI gate, Q8 and Q10 versions and rollback, P2-P4 roles/audit/rate limits, P7 containers | State survives restart; failing scenario fails CI; approved action completes the run; rollback works; audit log complete |
| 3 | Real channels, knowledge, hardening | C3, C4, C8, C9, H5, H8, K4-K8, T4-T6, A3, A4, A7, A10, R5-R7, S8-S11, Q5-Q7, Q9, O3, O4, P8 | Two channels and one knowledge source work end to end; traces exported and redacted; environments gate promotion |
| 4 | Non-engineers | U1-U8 Studio, O5-O7, O9, O10 insights, A5, A6 journeys, R9 multilingual, Q11 experiments, P5 SSO | CX user edits, tests and publishes an agent; insights live |
| 5 | Voice and collaboration | C5, C6, C7, C10, H6, H7, R8 | A live call resolves an intent; human assist shown in the inbox |
| 6 | Advanced and release | A8, O8, Q12, P6, security review, documentation, v1.0 | Threat model closed; v1.0 tagged |
| Later | Scale options | P10 multi-tenancy, P11 metering and billing | Decision after v1 |

Detailed workstreams, sprints and decisions for Phases 2-6 are in `NorthCX_Phase-Plan.md`.

## Dependencies
Phase 2 needs Phase 1 runtime and server. Phase 3 needs persistence and versions. Phase 4 needs persisted definitions, versions and metrics. Phase 5 needs streaming (R6). Phase 6 needs everything above.
