# NorthCX Phase Plan (Phases 2-6)

> **Archived 2026-11-09.** The 1.0 phases are finished; current plan: `../08-implementation/NorthCX_Implementation-Plan.md`. Kept for history; not maintained.

Status: Draft for review. Feature IDs refer to `03-specs/NorthCX_Feature-Catalog.md`; reuse sources and paths are in `00-reference/NorthCX_Reference.md` (sections 10-12). Sprint numbers match `NorthCX_Sprint-Plan.md`; durations are placeholders until velocity is measured.

## 1. Where we start
Phase 1 is done: Python runtime, supervisors, input checks, approvals (stored, not resumed), traces, HTTP API, widget, example agent, offline demo model, and a Next.js platform (overview, test console, conversations, approvals, agents, settings). State is in memory. 31 backend and 6 web tests pass; the web flow is browser-tested.

## 2. Critical path
```
Agent specs (declarative definitions)  ->  Versions & rollback  ->  Release gating  ->  Studio editor
Persistence (Postgres)                 ->  Approval resume, audit, handoff package, simulations history
Simulation runner                      ->  CI gate  ->  Required scenarios for promotion
```
Two designs unlock most later work and should be settled first:
1. **Agent spec:** a serialisable definition (instructions, tool references, guardrail references, model, limits) that is separate from Python code. Tools and guardrails are registered by name, so a definition can be stored, versioned, diffed, edited in Studio and run.
2. **Persistence layer:** one Postgres schema owned by the backend, with migrations.

## 3. Phase 2: Safe to change and operate

Goal: a team can change an agent, prove it still works, release it, undo it, and see who did what.

### Workstreams
| ID | Workstream | Catalog | Key tasks | Acceptance |
|---|---|---|---|---|
| W1 | Agent spec and registry | A1, A2 | Spec schema; tool and guardrail registries; load from file; example agent as a spec | Spec round-trips to JSON; same behaviour as code-defined agent in tests |
| W2 | Persistence | K3 | Postgres models and migrations; Postgres stores for sessions, messages, facts, traces, approvals; in-memory stores remain for tests; CI runs against a real database | State survives restart; store contract tests pass for both implementations |
| W3 | Approval resume | R10, H2, H3 | Persist pending call and session; approve executes once (idempotent) and the run continues to a final reply; reject records a reason and the agent responds; expiry job escalates; webhook or channel callback delivers the result | Approved refund executes exactly once; double decision rejected; expired approval escalates |
| W4 | Handoff package and forced topics | H4, S7 | Package builder (transcript, facts, actions, summary, trigger); policy list that escalates before the agent answers; handoffs table; web view | Every handoff has a complete package; listed topic always escalates |
| W5 | Simulation runner | Q2, Q3, Q4 | Scenario format; scripted-customer runner; assertions (status, tools called or not, reply text); judge with rubric; run API and CLI; results stored; web page | Failing scenario returns non-zero; results visible per run |
| W6 | Versions and rollback | Q8, Q10 | Immutable versions from specs; diff; publish; rollback; release records; API and web page | Rollback restores exact prior behaviour; every release recorded |
| W7 | Operations | P2, P3, P4, P7, T7, T8 | Hashed scoped keys and roles; audit log; rate limiting; secrets from environment; tool dry-run mode; Dockerfiles and compose; CI workflow | Key limited to its role; every approval, release and key change audited |
| W8 | Web additions | U3, U5, H4 | Simulations, releases, audit and handoff views; approval feedback after resume | Browser test covers each new page |

### Order and sprints
| Sprint | Work | Depends on |
|---|---|---|
| 4 | W1 agent spec and registries; W7 CI workflow (tests, type checks, build, licence path check) | none |
| 5 | W2 persistence and stores | W1 |
| 6 | W3 approval resume | W2 |
| 7 | W4 handoff package and forced topics | W2 |
| 8 | W5 simulation runner and judge | W1 |
| 9 | W5 CI gate and stored results; W8 simulations page | W2, W5 |
| 10 | W6 versions, diff, rollback | W1, W2 |
| 11 | W7 roles, scoped keys, audit log, rate limits | W2 |
| 12 | W7 containers, secrets, dry-run; W8 releases and audit pages | W6, W7 |

### Exit criteria (status at the end of sprint 12: all met)
- State survives restart; schema migrates forward cleanly. **Met** (Postgres stores, six migrations, restart tests, container restart test).
- Approved action completes the conversation; expired approvals escalate. **Met**.
- A failing required scenario fails CI and blocks promotion. **Met** (CI step and the gate at publish).
- Rollback works and is audited. **Met**.
- A fresh clone starts the whole stack with one compose command. **Met** (verified here with locally built images; CI verifies a clean build).

### Risks
| Risk | Response |
|---|---|
| Resume semantics are subtle (duplicate execution, stale context) | Idempotency keys; state machine for approvals; dedicated tests |
| Spec design too rigid for later skills and journeys | Version the spec schema; leave extension fields; review with Studio needs |
| Judge unreliable | Deterministic assertions first; calibrate against labelled set before gating |
| Two data owners (backend and web) | Web reads and writes only through the backend API |

## 4. Phase 3: Real channels, knowledge, hardening

Goal: real customers on real channels, grounded answers, safer and more reliable runs.

| ID | Workstream | Catalog | Key tasks | Reuse |
|---|---|---|---|---|
| W9 | Safety extensions | S8-S11 | Input checks for tool output; PII redaction in traces and replies; always-on monitoring; policy library with tests | Extend adapted input checks; evaluate rule-engine source |
| W10 | Reliability | R5-R7, T4 | Model fallback and retries; streaming; token and cost budgets; idempotent writes | Model-layer patterns from reference |
| W11 | Knowledge | K4-K8 | Retrieval tool with citations; source connectors and freshness; history summarisation; retention and deletion | Indexing and connector modules (permissive paths only) |
| W12 | Memory service | K2, K6 | Long-term facts through a memory adapter | Memory library behind `MemoryStore` |
| W13 | Channels and inbox | C3, C4, C8, C9, H5, H8 | Email and messaging adapters; identity verification; hours and routing; inbox integration through its API | Inbox project used through API |
| W14 | Observability | O3, O4 | Trace export with redaction | Open trace backend, API only |
| W15 | Environments and regression | Q5-Q7, Q9 | dev/staging/production; promotion with checks; scenarios from production traces; re-runs on knowledge change | none |
| W16 | Skills and templates | A3, A4, A7, A10, T5, T6 | Skills in the spec; templates; connector library; tool scopes | none |

Sprints 13-21: safety, reliability, knowledge, memory, email, messaging and identity, observability, environments, skills.
Exit: two channels and one knowledge source work end to end; traces exported and redacted; promotion gated by environments.
Risks: provider terms for messaging and email; PII in knowledge sources; connector licence and quality (assess each before copying).

## 5. Phase 4: Non-engineers
Workstreams: Studio editor, test console upgrades, simulations and review views, knowledge screens, publish flow (U1-U8); Insights (O5-O7, O9, O10); journeys and multilingual (A5, A6, R9); experiments (Q11); single sign-on (P5).
Depends on: agent spec, versions, simulations, persistence.
Sprints 22-27. Exit: a CX user edits, tests and publishes an agent without code; dashboards use the Success Metrics definitions.
Open: build the editor natively or adapt reference editor patterns.

## 6. Phase 5: Voice and collaboration
Voice adapter and consent flow (C5, C6); agent assist and return-to-agent (H6, H7); multi-agent routing (R8); attachments and client SDK (C10, C7).
Depends on: streaming (R6), inbox integration, latency budget.
Exit: a live call resolves an intent; assist suggestions appear in the inbox.
Risks: latency, telephony costs, recording-consent rules by jurisdiction.

## 7. Phase 6: Advanced and release
Agent-assisted building (A8); natural-language analytics (O8); load and cost testing (Q12); data residency (P6); security review; documentation; v1.0.
Exit: threat model closed; load targets met; release candidate signed off.

## 8. Cross-cutting working agreements
- **Definition of done:** tests (unit, contract, scenario), docs updated, audit entries for privileged actions, trace coverage, accessibility check for web changes.
- **CI on every change:** backend tests and type checks, web tests and build, licence scan, path allow-list that rejects copied files from restricted directories, dependency vulnerability scan.
- **Reuse rule:** read before copying; record in `THIRD_PARTY.md`; copy only separable modules; otherwise build.
- **Review gates:** any change to supervision, approvals or audit needs a second reviewer.
- **Metrics:** track simulation coverage and release lead time from Phase 2 onward.

## 9. Decisions (all accepted 2026-11-02)
| # | Decision | Recommendation |
|---|---|---|
| 1 | Agent spec format (YAML or JSON, with Python only for tool code) | YAML for authors, JSON stored |
| 2 | Postgres access layer | Async SQLAlchemy with Alembic migrations |
| 3 | Approval resume delivery: webhook, channel callback, or polling | Callback through the original channel, webhook as option |
| 4 | Project licence | Apache-2.0 |
| 5 | Where simulations run in CI (scripted always; live model nightly) | As stated |
| 6 | Whether to merge current work to `main` first | Yes, then work in short-lived branches (done) |

## 10. Milestones
| Milestone | Contents | Target |
|---|---|---|
| M1 | Phase 2 complete | After sprint 12 |
| M2 | Pilot-ready: channels, knowledge, safety | After sprint 21 |
| M3 | Studio beta | After sprint 30 |
| M4 | Voice and collaboration | After Phase 5 |
| M5 | v1.0 | After Phase 6 |
