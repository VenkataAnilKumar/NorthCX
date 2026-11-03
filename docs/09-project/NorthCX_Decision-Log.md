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
| 46 | One role per key; seven roles; every endpoint needs one named permission from a single table, and unlisted routes are refused | Decided, built | A test keeps the table complete |
| 47 | Keys store only a hash; the secret is shown once | Decided, built | |
| 48 | When authentication is on, the key's name replaces any name in the request | Decided, built | Open mode (no keys) still trusts typed names |
| 49 | The audit log is append-only in the database and hash-chained; writing it is part of the request | Decided, built | Anchor the head hash externally to detect tail removal |
| 50 | Rate limits are per process | Decided; revisit | A shared limiter is needed for many processes |
| 51 | Keys are not yet limited to particular agents or environments | Decided; revisit | With environments in Phase 3 |
| 52 | Interactive API docs are disabled | Decided | |
| 53 | Tools declare `effect`; writes default to "write" and are simulated in simulations, with real side effects only behind an explicit flag | Decided, built | |
| 54 | Secrets come from the environment or mounted files, are handed to tools by name, and are scrubbed from everything stored | Decided, built | |
| 55 | Compose binds to loopback and requires a database password, an API key and authentication | Decided, built | TLS is the operator's reverse proxy |
| 56 | The web image bakes in the backend address at build time | Decided; revisit | A runtime proxy would remove the rebuild |
| 57 | The deployer supplies tools through `NORTHCX_REGISTRY` | Decided, built | |
| 58 | Customers chat with signed, expiring, conversation-scoped tokens minted by the company's server; channel keys never go to browsers | Decided, built | |
| 59 | The customer id comes from the token, not the request | Decided, built | The company's server vouches for who the customer is |
| 60 | A token's validity depends on its minting key staying active; individual tokens are not revocable | Decided | Keep lifetimes short |
| 61 | Token signing secret derives from the bootstrap key unless `NORTHCX_TOKEN_SECRET` is set | Decided, built | |
| 62 | Email arrives as raw RFC 822 POSTed by the customer's mail gateway (no built-in IMAP/SMTP listener); replies leave over SMTP | Decided, built | Keeps the runtime out of the mail-server business |
| 63 | Sender address is a customer identity only if the trusted gateway reports `dmarc=pass`; otherwise anonymous | Decided, built | Header is ignored unless `NORTHCX_EMAIL_TRUST_AUTH_RESULTS=1` |
| 64 | A different sender never joins an existing thread; auto-mail, lists, bounces and our own mail are never answered; per-sender hourly reply cap | Decided, built | Prevents loops and mail-bombing |
| 65 | Mail from a conversation with an open handoff is recorded for the person, not answered by the agent | Decided, built | Resumes after the handoff is resolved |
| 66 | Outbox now retries with back-off and a background flush runs every 15 s | Decided, built | Failed sends are retried, never duplicated (deterministic Message-ID) |
| 9 | Contribution model: DCO vs CLA | Open | |
| 67 | Tool results are screened (`output_guardrails`) before the model reads them; failures deny; an empty list leaves spec digests unchanged | Decided, built | Indirect-injection defence; phrase list narrow on purpose |
| 68 | Monitoring is rule-based over traces for every turn (no model calls); findings are advisory and monitoring failures never affect conversations | Decided, built | |
| 69 | Policy library is deterministic and ships with executable allow/block cases; every policy needs both outcomes covered | Decided, built | |
| 70 | Model calls go through a wrapper with retries, per-call timeout, ordered fallback models and a circuit breaker; non-transient errors are never retried | Decided, built | |
| 71 | Token budgets are per run (spec `max_run_tokens`) and per server per day; exceeding either hands the conversation to a person | Decided, built | Daily count is per process |
| 72 | Chat requests accept `Idempotency-Key` (24 h, scoped to caller, agent and conversation); tool calls get per-call keys; identical writes in a turn run once; reads retry once, writes never | Decided, built | |
| 73 | Streaming sends progress and the already-checked reply in pieces; raw model tokens are not streamed because supervisors must approve a reply before a customer sees it | Decided, built | Web test console uses it |
| 74 | Knowledge is built natively on Postgres full-text search with an in-memory twin; no connector framework or vector database yet | Decided, built | The reference indexing code is coupled to its own services; assessed, not copied (THIRD_PARTY.md) |
| 75 | Documents are submitted through the API as text or Markdown, keyed by the caller's external id; unchanged content is skipped; staleness is measured from the company's own update time | Decided, built | |
| 76 | A session index links conversations to customers; export, erasure and retention walk it and every store that holds conversation data | Decided, built | Pre-index conversations are found by id or age only |
| 77 | The audit log is retained through erasure; privacy actions are logged with a one-way customer reference | Decided, built | Backups and downstream copies are out of scope and documented |
| 78 | Long conversations are compacted by replacing older turns with model-written notes at the front of the first kept customer message; failure keeps the full history | Decided, built | Off unless NORTHCX_SUMMARIZE_AFTER_TOKENS is set |
| 79 | Customer context comes from either a Python hook or a signed HTTPS endpoint, cached per customer, size-limited and screened; not stored with facts; failure means no context, not an error | Decided, built | Company values win over agent-stored facts |
| 80 | Long-term memory is built in (Postgres full-text, in-memory twin) behind a five-method `MemoryService` interface rather than adopting an external memory library first | Decided, built | An external library can sit behind the same interface later |
| 81 | The agent chooses what to remember; notes are screened, shown as untrusted data, limited to 200 per customer, and erased with the customer | Decided, built | No automatic extraction yet |
| 82 | SMS is a public webhook authenticated by the provider's signature over a configured public URL (never the request's Host); the sender number is the customer identity | Decided, built | Provider behind a two-method interface |
| 83 | STOP opt-outs persist by one-way hash through erasure; messages with no conversation are recorded under a hash, not the number | Decided, built | |
| 84 | Channel-specific style lives in the agent spec (`channel_styles`), one agent across channels | Decided, built | Replaces a shared channel-adapter refactor for now; email and SMS share patterns, not code |
| 82 | SMS is a public webhook authenticated by the provider's signature over a configured public URL (never the request's Host); the sender number is the customer identity | Decided, built | Provider behind a two-method interface |
| 83 | STOP opt-outs persist by one-way hash through erasure; messages with no conversation are recorded under a hash, not the number | Decided, built | |
| 84 | Channel-specific style lives in the agent spec (`channel_styles`), one agent across channels | Decided, built | Replaces a shared channel-adapter refactor for now; email and SMS share patterns, not code |
| 85 | Hours and queues are a validated YAML file loaded at start-up (no API editing yet); first matching queue wins by topic or trigger | Decided, built | Studio editing later |
| 86 | Outside hours the agent still answers; only the hand-off reply changes, with the next opening time | Decided, built | |
| 87 | Hand-offs reach helpdesks through a database queue with back-off (not the customer-visible outbox), via a signed webhook and a Chatwoot adapter that uses only its REST API | Decided, built | Chatwoot calls not yet tried against a live server |
| 88 | Helpdesk-to-NorthCX sync uses the existing resolve API rather than a new public webhook | Decided | Direct helpdesk webhooks and return-to-agent (H7) later |
| 89 | Traces are exported from a database queue by two exporters (Langfuse ingestion API, OTLP/HTTP JSON); the Langfuse code was read for its API contract only | Decided, built | Licence verified, nothing copied |
| 90 | Export content defaults to `masked`; `none` sends structure only; customer ids are never exported | Decided, built | Masking is pattern-based |
| 91 | One deployment, three labelled environments with separate release histories; an unreleased environment serves the next one up; dev needs no proof, staging and production need the release gate; strict promotion is optional | Decided, built | Separate deployments can share a database |
| 92 | Non-production conversations are tagged, kept out of the helpdesk inbox, and share tools and data with production unless separated by the operator | Decided, built | Documented risk |
| 93 | Scenario drafts replay recorded model output, so they test policies, tools and guardrails around the model, not its wording; drafts are never required until reviewed | Decided, built | Tags are labels and excluded from the scenario digest |
| 94 | Knowledge-change re-runs are opt-in, debounced and batched; failures raise a critical monitoring finding; only live mode can see changed answers | Decided, built | Persona-driven simulated customers (Q6) come next |
