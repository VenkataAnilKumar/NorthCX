# NorthCX Decision Log

| # | Decision | Status | Notes |
|---|---|---|---|
| 1 | Project name NorthCX | Decided | Package, repo and docs renamed |
| 2 | External research confined to the Reference doc | Decided | Other docs are NorthCX-only |
| 3 | Backend language: Python backend, TypeScript web platform | **Decided** (2026-11-02) | Driven by code reuse; TypeScript prototype becomes a reference implementation |
| 15 | Web platform base: Studio shell from the visual-builder source, trace/eval screens from the observability source, knowledge screens from the knowledge source | Decided | Reference section 12; data hooks rewritten to the NorthCX API |
| 4 | Project licence Apache-2.0 | **Decided** (2026-11-02) | `LICENSE` added; contributions follow the same licence |
| 5 | Studio: adopt or build | Open | Decide at Phase 4 |
| 6 | Fail closed for supervisor and model errors | Decided | Implemented and tested |
| 7 | Approval resume in Phase 2 | Decided | Approvals stored now |
| 8 | Card-number rule uses Luhn | Decided | Avoid blocking order numbers |
| 10 | Prototype HTTP framework Hono (prototype only) | Superseded | Backend uses FastAPI (decision 3) |
| 11 | Release management is a core feature, not an add-on | Decided | Versions, rollback, gated promotion |
| 12 | Forced-handoff topics are policy, not model judgement | Decided | Always escalate |
| 13 | Assemble by copying and adapting licensed reference code, not from scratch | Decided | Policy in Code-Reuse-Policy |
| 14 | Exclude `ee`/enterprise directories and source-available code from copying | Decided | One reference project is Elastic-licensed; two others have enterprise or `ee` directories |
| 16 | Do not copy the reference agent core (about 21,000 coupled lines); keep a small NorthCX runtime and copy small separable modules | Decided | Assessment recorded in `THIRD_PARTY.md` |
| 17 | Web platform is written natively (Next.js 16, React 19, Tailwind 4) instead of copying the visual-builder source | Decided | The source is one large product tied to its own backend and a private UI package; its visual editor remains a Phase 4 reference |
| 18 | Web app reaches the backend through a same-origin proxy (`/api/northcx`) | Decided | No CORS; API key held per browser tab |
| 19 | Agent definitions are a serialisable spec (YAML for authors, JSON for storage) with tools and guardrails registered by name | **Decided**, built (`northcx/spec.py`) | Critical path for versions and Studio |
| 20 | Postgres through async SQLAlchemy with Alembic migrations | Decided | Phase 2 persistence |
| 21 | Approval results reach the customer through a callback on the original channel, with a webhook option | Decided | Phase 2 approval resume |
| 22 | Simulations: scripted model on every change, live model nightly | Decided | Testing Strategy |
| 23 | Current work merged to `main`; further work in short-lived branches | Decided | Done for Phase 1 |
| 24 | Trace and approval repositories are asynchronous interfaces with in-memory and Postgres implementations | Decided, built | Same contract tests run against both |
| 25 | Trace summaries (status, tools, event count) are stored on the trace row | Decided | Lists never load events |
| 26 | Session saves replace history atomically under an advisory lock; concurrent runs on one session are not yet protected | Decided; limitation recorded | Revisit before multi-worker deployment |
| 27 | Approval transitions are atomic conditional updates; execution is claimed before it runs, with the approval id as idempotency key | Decided, built | At-most-once in normal operation; tools must honour the key for crash safety |
| 28 | Supervisors and input validation run again when an approved action executes | Decided, built | Policy may change while waiting |
| 29 | Customer-facing results go through an outbox (poll) with optional signed webhook | Decided, built | Channel adapters later consume the same outbox |
| 30 | Platform-written notices run as trusted turns (skip customer input checks, still supervised) | Decided, built | Tool output inside them stays untrusted |
| 31 | Every escalation creates a handoff with a typed trigger and a deterministic package | Decided, built | Model-written summaries later |
| 32 | Forced topics are deterministic patterns in the agent spec and run before the model | Decided, built | False positives cost a human visit, which is the safe direction |
| 33 | Handoff resolve is a once-only atomic transition | Decided, built | Same pattern as approvals |
| 34 | Scenario files are strictly validated; scripted models must be fully used; invariants are checked in every scenario | Decided, built | A passing scenario cannot hide a drifting script or a broken history |
| 35 | A judge check without a judge model fails (or is skipped explicitly with a note) | Decided, built | Never a silent pass |
| 36 | Only `required` scenarios gate; live runs use trials and a pass rate | Decided, built | |
| 37 | A gate pass is tied to the exact agent digest and scenario definition, newest result wins, demo runs never count, skipped checks do not count | Decided, built | Prevents a stale or partial pass from releasing a changed agent |
| 38 | Simulation runs are stored with per-scenario digests; CI records its run | Decided, built | Sprint 10 enforces the gate at promotion |
| 39 | The API runs one simulation at a time, synchronously | Decided | Long live suites should use the command line until background jobs exist |
| 40 | Spec files are the baseline; versions are stored in the database and take over when released | Decided, built | First release is explicit and gated |
| 41 | Publishing needs the gate for that version's digest; rollback needs no gate | Decided, built | Rollback restores something already proven in production |
| 42 | Rolling back a rollback goes forward again; the first release can be withdrawn to the spec file | Decided, built | Simple undo semantics |
| 43 | The live agent is resolved from the release store on every request | Decided, built | Releases take effect on all processes at once |
| 44 | An unbuildable live version answers 503 rather than falling back silently | Decided, built | Rollback is the recovery |
| 45 | Conversations are not pinned to a version | Decided; revisit | Pinning arrives with environments and staged rollout |
| 9 | Contribution model: DCO vs CLA | Open | |
