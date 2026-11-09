# NorthCX Implementation Plan (all phases and waves)

Status: Draft for approval (2026-11-05). The working plan for building everything from the finished 1.0 release candidate to the full platform. It breaks the epics of `NorthCX_Gap-Closure-Plan.md` into **work packages** (WP) with concrete steps, files, tests, acceptance criteria, sizes, dependencies and verification labels, and lists what only the owner or an outside party can do. Update the checklist in section 14 as work lands.

**How this relates to the other plan documents**
| Document | Answers |
|---|---|
| `NorthCX_Product-Overview.md` | What the product is, layer by layer, and what is built |
| `00-reference/NorthCX_North-Gap-Analysis.md` | What is missing compared with an employee-facing platform |
| `NorthCX_Gap-Closure-Plan.md` | What to build and why: epics, designs, decisions D1 to D11, risks |
| **This document** | **How and in what order: work packages, steps, gates, estimates, external actions** |
| `NorthCX_Release-Checklist.md` | The steps to cut 1.0.0 |
| `NorthCX_Project-Status.md` | One-page snapshot |

## 1. Conventions

**Sizes** (code plus tests; calendar time depends on team size, so none is given): **S** up to about 300 lines and 15 tests; **M** up to about 1,000 lines and 50 tests; **L** up to about 2,500 lines and 120 tests; **XL** more than that, always split into work packages of L or smaller.

**Verification labels** (every work package carries one, and the release notes repeat it): **V** verified here (tests, real Postgres, browser run); **P** partly verified (fixtures or mocks, no live counterpart); **X** needs outside verification (live vendor, live model, hosting, audit).

**Definition of ready:** the design section of the epic is agreed; decisions it depends on are made (section 12); the test list is written before the code.

**Definition of done (every work package):**
1. Code, with the standing security tests green (no pasted SQL, no dangerous constructs, redirects off, CORS rules, parsers fuzz).
2. Unit tests, plus real-Postgres tests for every store (in-memory and Postgres parameterised), plus a browser step in the Studio smoke test if there is UI.
3. The full backend suite, web type-check and tests, and SDK tests pass; the load tool is re-run if the work touches the hot path (section 11).
4. Docs: Deployment Guide (every new setting), `.env.example` and compose pass-through (a test enforces both), API design narrative (the route reference is generated), feature catalog IDs, decision-log entry (numbers continue from #141), CHANGELOG, residency report entry for any new outbound address, threat-model entry.
5. The verification label is written in the CHANGELOG entry.
6. Committed as the project owner with the co-author trailer, pushed to both branches, remote SHA verified.

**Branching:** work lands on `claude/awesome-brown-o0nk5s` and `main` in small commits, one work package or sub-step each, so every commit is green on its own. Risky steps (E2 tenancy) use a short-lived branch and merge only when their isolation and performance gates pass.

## 2. Where we are: phases 1 to 6 (done)

| Phase | Delivered | Evidence | Not proven |
|---|---|---|---|
| 1 Runtime | Agent loop, typed tools, guardrails, memory, traces, HTTP API, widget, example agent | Tests; prototype parity | |
| 2 Quality and control | Agent spec, simulations and gate, Postgres stores, approvals with resume, hand-off package, versions and rollback, roles, hashed keys, audit chain, secrets, containers | 18 example scenarios; Postgres contract tests | |
| 3 Reach and knowledge | Email, SMS, WhatsApp, Telegram; knowledge, citations, crawler, file import, hybrid search; summarisation, retention, export, erasure; fallback, budgets, idempotency, signed webhooks; trace export; environments; skills, templates, connectors, scopes | Mock-provider tests | Live provider round trips |
| 4 Studio and insight | Studio (about 15 pages), insights with denominators, alerts, search and tags, journeys, languages, SSO, rollouts, review | Browser smoke test | Real-model behaviour |
| 5 Voice and assist | Voice bridge, agent assist, hand-back, multi-agent, attachments, browser SDK and widget | Simulated bridge, browser tests | A live call |
| 6 Hardening and release | Security review and threat model, load and cost tools, plain-language analytics, agent drafting, residency, status events, identity verification, abuse detection, release files, README, release candidate | 1349 backend, 27 web, 29 SDK tests; clean-checkout run | Pen test, live model, container image build, CI on GitHub |

The first web split (Studio in `src/apps/studio`, shared packages in `src/packages`) is complete. Everything below starts from that tree.

## 3. Release train and critical path

| Release | Waves and epics | Gate |
|---|---|---|
| **1.0.0** | Wave 0 | Release checklist, plus the owner's actions |
| **1.1** | Wave 1: E1, E3 (3.1 to 3.3, 3.5), E4 | Provider conformance, identity sweeps, MCP against a fake server |
| **1.2** | Wave 2: E2, then E5, E6, E16, E18; first admin app | Tenant isolation sweeps and fuzz, load gate, staff permission matrix |
| **1.3** | Wave 3: E8, E14, E15, E9, E7 | Automation safety suite, connector fixtures, workflow round trip |
| **1.4** | Wave 4: E10, E11, E12, E17, E19; ops and back-office apps | Metering idempotency, chart validation, document review |
| **Later** | Wave 5: E13, E21, E20, surfaces, mobile, marketplace | Vendor accounts, content, store review |

**Critical path:** `WP0.1 router split` → `WP0.4 shared limits` and `WP0.5 multi-replica readiness` → `E2 tenancy` → `E5 staff workspace` → `E8 automations` → `E10 metering`. Everything else hangs off that line.

**Parallel tracks** (can run side by side once their inputs exist)
- **Track A, platform core:** WP0.1 to WP0.5, E1, E3, E4, E2.
- **Track B, web:** design tokens (WP0.2), then the workspace, admin, ops and back-office apps as their backends arrive.
- **Track C, trust and docs:** API reference, compliance pack, legal templates, marketing site content.
- **Track D, owner and outside actions:** section 13; the long-lead items (penetration test, vendor accounts, audits) should start early.

## 4. Wave 0: finish 1.0 and prepare the ground

Goal: the release candidate becomes 1.0.0, and the codebase is ready to take multi-tenancy without a rewrite. Sequence: WP0.1, WP0.2, WP0.3 in order; WP0.4 to WP0.9 in any order afterwards; WP0.10 to WP0.12 in parallel with the owner.

### WP0.1 Router split and bootstrap split (size L, V) — **routers and stores done; bootstrap split pending**
**Status (2026-11-05):** done: `create_app` went from about 2,100 lines to a setup function, `server.py` from 2,516 to about 500 lines; 132 routes now live in 21 modules under `northcx/api/routers/` (each with `register(app, d)`), the request models in `northcx/api/models.py`, shared helpers in `northcx/api/common.py`, the shared-dependencies object in `northcx/api/deps.py` (fields typed `Any` for now; typing them is a follow-up); `db/stores.py` became a package of nine domain modules; guards in place: a golden route-dispatch snapshot (every route and the handler that wins for it), the layout test (600-line cap, one `register` per router, deps fields exactly match use, absolute imports only in moved packages), and the full suite (1356 passing) and the Studio browser smoke test on the result. Also done: `__main__.py` (526 lines) is now a 15-line entry point over `northcx/bootstrap/` (nine start-up steps, one module each, run in the original order over a shared namespace; the layout test covers it, and the server-start test passes). The `AppDeps` fields are now typed, and `record`, `actor`, `too_many`, `need_rel`, `need_env`, `rel_error` and `version_json` live in `northcx/api/helpers.py`; `server.py` is 424 lines with its unused imports removed. WP0.1 is complete.
**Why:** `create_app` is one function of about 2,100 lines with 131 route handlers and about 40 parameters; `__main__.py` is 526 lines of wiring; `db/stores.py` is 1,439 lines with 30 store classes. Every later epic adds routes and stores.
**Steps**
1. Introduce `northcx/api/deps.py` with an `AppDeps` dataclass holding the objects `create_app` builds today (runtime, traces, agent provider, access, audit, knowledge, insights, channels, releases, simulations, and so on). `create_app` keeps its current signature (the tests call it with keyword arguments), builds `AppDeps`, and registers routers.
2. Create `northcx/api/routers/<area>.py`, each with `def register(app, d: AppDeps) -> None` and a `ROUTES` list of `(method, path regex, permission)`. Move one area per commit, in this order (smallest and least coupled first): templates, memory, privacy, tokens, identity and keys and audit, single sign-on, email, SMS, WhatsApp, Telegram, insights, builder, simulations, versions and releases, approvals and hand-offs, knowledge, chat (last, most coupled).
3. Move each router's request bodies next to it (`northcx/api/models/<area>.py`).
4. Build `ROUTE_PERMISSIONS` by concatenating the routers' `ROUTES`; `permission_for` is unchanged.
5. Split `__main__.py` into `northcx/bootstrap/` modules by feature (database, channels, knowledge, safety, providers, events, residency, verification) each returning what `main()` needs; `main()` becomes a short composition.
6. Split `db/stores.py` into `db/stores/<domain>.py` with an `__init__` that re-exports every class, so no import elsewhere changes.
**Tests and acceptance:** the permission sweep, the generated route reference test, the security sweep and the whole suite pass unchanged after every commit; a new test fails if any file under `northcx/api` or `northcx/bootstrap` exceeds 600 lines; no behaviour change (the Studio smoke test passes against the result).
**Depends on:** nothing. **Blocks:** everything that adds routes.

### WP0.2 Design tokens into `packages/ui` (size S, V)
Move the colour and spacing tokens and base styles out of `apps/studio/app/globals.css` into `packages/ui/src/styles.css`; apps import it; dark mode and the `@source` rule for the package stay. **Acceptance:** screenshots of three pages before and after are pixel-identical in light and dark; web tests and smoke test pass.
**Status (2026-11-08):** done: the tokens, dark mode and base styles are in `packages/ui/src/styles.css` (exported as `@northcx/ui/styles.css`); `apps/studio/app/globals.css` is two import lines. Checked a stricter way than screenshots: the compiled stylesheet before and after is byte-identical (25,455 bytes), the production build carries both the light and dark tokens, and a web test guards where the tokens live. Typecheck, 28 web tests and the build pass.

### WP0.3 Locked dependencies (size S, V)
Hash-pinned lock file for the backend (`requirements.lock` and a dev lock) generated by a script (`scripts/lock.sh`); CI installs from the lock and runs `pip-audit` on it; a CI step fails when the lock is older than `pyproject.toml`; Dockerfile installs from the lock. **Acceptance:** a clean checkout installs byte-identical versions; the Threat Model residual risk 5 is updated.
**Status (2026-11-08):** done: `scripts/lock.sh` (uses `uv`) writes `requirements.lock` (37 packages) and `requirements-dev.lock` (47), universal for Python 3.12 and later, every package pinned with hashes; the fingerprint of `pyproject.toml` is stored in each lock and `tests/test_lock.py` fails when they drift (a content check instead of file dates, which git checkouts scramble); the Dockerfile installs with `--require-hashes` then the project with `--no-deps`; CI installs the dev lock and has a new `audit` job. Verified here: a fresh Python 3.12 environment built only from the dev lock passes the full suite (1356, with Postgres), and `pip-audit` reports no known vulnerabilities in either lock. The container build and the new CI jobs could not run in this sandbox; they ran on GitHub afterwards and passed (see WP0.9).

### WP0.4 Shared rate limits and budgets (size M, V)
**Design:** a `Limiter` protocol with the current in-memory implementation and a `PgLimiter` using one table, `rate_counters(key, window_start, count)`, updated with `INSERT ... ON CONFLICT DO UPDATE` and an hourly cleanup; the daily token ledger moves to a `usage_ledger` table the same way. Setting `NORTHCX_LIMITS_BACKEND=memory|postgres` (default memory for single process).
**Tests:** two server processes share one limit; the abuse burst counter and channel throttles use the shared limiter; failure of the database degrades to the in-memory limiter with a warning, never to "no limit"; load test shows under 5 percent throughput cost at the documented rate.
**Acceptance:** the Threat Model residual risk 3 is closed; Deployment Guide documents the setting.
**Status (2026-11-08):** done: `PgLimiter` and `PgUsageLedger` (`db/stores/limits.py`), migration 0029, `NORTHCX_LIMITS_BACKEND` (validated at start-up), all 25 limiter call sites now call the shared interface, and the abuse burst check counts through the shared limiter when it is on. Tests (`tests/test_shared_limits.py`): two limiters on one database share one limit; the burst check and the token budget are shared; a database failure degrades to per-process counters with one warning; old windows are deleted; and two real server processes (alternating requests) allow exactly 10 of 16 at a limit of 10. Not as the plan said: the channel per-number reply caps already counted in the database, and no new load test was run. Measured cost is about 3 ms per check (about 600 checks per second with 20 keys in flight), so the plan's 'under 5 percent throughput' target is not claimed; see the Performance document.

### WP0.5 Multi-replica readiness (size L, V)
**Design:** `NORTHCX_ROLE=all|api|worker` (default `all`, today's behaviour). Background loops (outbox flush, approval expiry, trace export, alert evaluation, inbox delivery, retention, embedding indexer, crawl scheduler) run only in `worker` and `all`. Queue claims so two workers never double-send: `claim_undelivered` on the outbox, trace-export and inbox queues using `FOR UPDATE SKIP LOCKED` plus a lease timestamp; alert state moves to an `alert_state` table; crawl jobs persist progress in a `crawl_jobs` table so any replica can show them.
**Tests:** two workers and two API replicas against one Postgres: each outbox message is sent exactly once, each alert fires once, a crawl started on one replica is visible from another, and a worker killed mid-claim has its lease expire and the work retried; an API-only replica starts no loops.
**Acceptance:** a documented topology (web replicas, API replicas, workers, pooler, Postgres) in the Deployment Guide; a two-replica job in CI.
**Status (2026-11-08):** done, with two departures from the design above. (1) Instead of per-row claims (`FOR UPDATE SKIP LOCKED`) on each queue, every background job takes a **database lease** for each pass (`job_leases`, `northcx/leases.py`); it needed no change to the three queue implementations and a worker killed mid-pass loses the job when the lease expires (two minutes). Measured: two outbox flushers without a lease sent 8 messages for 4; with the lease, exactly once each. Delivery stays at-least-once if a worker dies between sending and recording. (2) The two-replica test is part of the normal backend test run (the CI backend job has Postgres), not a separate job. Built: `NORTHCX_ROLE=all|api|worker` (validated; `api` and `worker` need the database), the loops moved out of `create_app` into `northcx/api/background.py` (`server.py` is now 349 lines), alert state and events in `alert_state`/`alert_events` (any process continues where another left off; fires once), crawl progress in `crawl_jobs` with a heartbeat that blocks a second crawl of the same source on another server, migration 0030, the topology section of the Deployment Guide. Tests (`tests/test_multi_replica.py`, 9): lease passing, expiry and one-at-a-time under contention; each outbox message sent once with two workers; an alert fires once across two evaluators and recovers; a crawl is visible from another process and blocks a second start; an API-only process starts no jobs; role validation; and two API replicas plus two workers as real processes against one database, with a conversation handled by one visible on the other. Limits: a crawl still runs in the process that started it; the embedding indexer and crawl schedules rely on idempotent writes and atomic claims rather than leases.

### WP0.6 Masked-text path for PDFs (size M, V)
New attachment mode: extract PDF text, mask personal data, send the text instead of the file; chosen per agent in the spec (`attachments: [pdf_text]`), the file mode stays opt-in with an explicit acknowledgement field. **Tests:** masking applied, scanned PDFs refused cleanly, digest unchanged for agents that do not use it. **Acceptance:** Threat Model residual risk 2 updated.
**Status (2026-11-08):** done: `attachments: [pdf_text]` (text read with the existing PDF reader, masked with the same detector the trace export uses, passed through the agent's input checks, file never sent); `pdf` needs `acknowledge_unmasked_files: true` and cannot be combined with `pdf_text`; digests unchanged for specs using neither; 5 new tests including a full chat turn. Not covered: pictures (would need OCR) and a PDF whose text is mostly an image.

### WP0.7 Generated API reference (size S, V)
`scripts/gen_api_reference.py` writes `docs/api/openapi.json` and a static HTML page from the app's schema (the live endpoint stays off). **Test:** every route in the permission table appears in the reference.
**Status (2026-11-08):** done: `scripts/gen_api_reference.py` writes `docs/api/openapi.json` (131 operations, each with `x-required-permission`; 11 marked public) and a self-contained `docs/api/index.html` (light and dark, grouped by area, request fields from the schema models); `--check` mode; two tests: the files match the code, and every entry of the permission table appears with the same permission and nothing is served unclassified. Limits: only 52 of 131 operations have a written description (the handler's docstring; the rest show the generated title), and response bodies are not described because handlers return plain dictionaries. Writing the missing descriptions and typed responses is a documentation follow-up (E0.5 in the gap plan).

### WP0.8 Webhook tester (size S, V)
`POST /v1/events/test` sends a signed sample of any event type to the configured events webhook and reports the receiver's answer; audited; rate limited.
**Status (2026-11-08):** done: `POST /v1/events/test` with `{"type": "<event type>"}` (permission `keys:manage`, six a minute per key, audited as `events.test`) sends one signed sample to the configured address and secret, marked `test` in the body (`"test": true`) and in the `x-northcx-test: 1` header, once, not stored, not retried, not in the feed; it returns `status`, the receiver's HTTP status and the time taken, and an error sentence if it failed, never the receiver's answer. 501 without an events webhook, 400 for an unknown type. 4 tests; the route snapshot, route reference and API reference were regenerated (133 routes).

### WP0.9 First CI run and container build (size S, X)
Push, then read the first GitHub run: the pgvector database service, the SDK job, the workspace web job, the compose stack job (images build and the demo starts). Fix what fails; record the result in the release checklist. **Needs:** the repository's Actions enabled.
**Status (2026-11-08):** done, checked by reading the runs through the GitHub tools. CI has run on every push to `main` (104 runs so far); the run for `89830dd` (WP0.8) passed all seven jobs: `backend` (install from the hash-pinned dev lock, the full suite against the pgvector Postgres service, the scenario gate), `audit` (`pip-audit` on both locks), `web` (install, type-check, tests, production build), `sdk`, `prototype`, `provenance`, and `stack` (`docker compose up --build --wait`: both images build from the new Dockerfiles, the demo starts, and the smoke test passes). An earlier statement in this plan and in the status document that these jobs had never run was wrong; they had. Not checked: the content of the run logs beyond job and step results, and any warnings in them.

### WP0.10 "Resolved" metric and PRD scope (size M, V, needs two owner decisions)
Adopt the PRD definition as a provisional **resolution rate** (completed, with no hand-off or reopen in the window, default 3 days) shown next to containment, labelled provisional; update the PRD, Product Definition and Success-Metrics with a post-1.0 scope section (staff workspace, multi-tenancy, billing in scope after 1.0; non-goals restated: supervised and permission-bound agents, not general-purpose autonomous agents). **Decisions needed:** the definition and the scope wording.
**Status (2026-11-08):** done with the owner's answers. Definition: no preference given, so the recommended PRD wording with a 3-day window was adopted as provisional (decision #145). Scope: multi-tenancy and the staff workspace in scope after 1.0; billing stays a non-goal until D1; autonomous agents and helpdesk replacement stay non-goals. Built: `resolutionRate` in the insights overview (`value`, `numerator`, `denominator` of mature conversations, `pending`, `windowDays`, `provisional`), `NORTHCX_RESOLUTION_WINDOW_DAYS`, the `resolution_rate` figure for plain-language analytics, a 'Resolved (provisional)' tile in Studio, PRD, Product Definition and Success-Metrics updated. Known limit: a customer returning in a new conversation is not detected (turns carry no customer link); adding a hashed customer reference to turns is the follow-up that would also give the reopen rate. 2 new tests.

### WP0.11 Real-model pass and judge calibration (size M, X, owner provides key)
A scripted procedure and checklist: run the example agents and shipped scenarios in live mode; try agent and journey drafts, plain-language analytics, the judge on a labelled sample (30 or more conversations), meaning-based search and transcription if services are available; record differences from the scripted tests; fix or document. **Output:** a "Live verification" section in the release notes and the judge's measured agreement.

### WP0.12 Owner actions to cut 1.0.0 (X)
Commission the penetration test (scope: Threat Model and Security Review, with the router split and shared limits in place); push the `v1.0.0-rc.1` tag; on completion run the "Cutting 1.0.0" steps of the release checklist.

**Wave 0 exit criteria:** WP0.1 to WP0.8 done; WP0.9 green; WP0.10 decided; WP0.11 and WP0.12 complete; the release checklist fully ticked. Then tag 1.0.0.

## 5. Wave 1: foundations (release 1.1)

### E1 Model providers and cost governance (size XL, split into WP1.1 to WP1.8)
| WP | Work | Size | Label |
|---|---|---|---|
| **1.1** | `northcx/providers/`: adapter protocol (`complete`, capabilities, price table, error mapping with `status_code`), a registry, qualified names `provider:model` (bare names use the default provider) | M | V |
| **1.2** | Move the current Claude client into `providers/anthropic.py`; `llm.py` re-exports; add an optional direct-HTTP client behind a flag so the SDK can be retired later | M | V |
| **1.3** | `providers/openai_compat.py`: translate neutral blocks to chat messages and back: `text`/`tool_use`/`tool_result` ↔ `content`/`tool_calls`/`tool` role; `input_schema` ↔ `parameters`; stop reasons; usage; timeouts; no streaming yet | L | V (fixtures, fake server), X (each real provider) |
| **1.4** | `NORTHCX_PROVIDERS_FILE`: validated YAML (name, kind, https base URL, secret reference, models, prices, capabilities); each provider added to the residency report; secrets through the secret store | M | V |
| **1.5** | Fallback chains across providers; capability check at version creation and release (an agent that needs tools on a model without them is refused) | M | V |
| **1.6** | Currency budgets (per conversation, per day) computed from prices and reported usage; insights cost from the real model mix; Studio shows currency | M | V |
| **1.7** | Experimental routing: a deterministic classifier chooses a cheaper model for simple turns; recorded in the trace; scenario type compares both | M | V, X (quality) |
| **1.8** | One conformance suite over every adapter (plain reply, tool call, round trip, parallel tools, errors, usage, cancellation) with recorded fixtures; a local fake OpenAI-compatible server run through runtime, simulations and judge | L | V |
**Status (2026-11-08):** WP1.1 and WP1.2 done: `northcx/providers/` (types, `ProviderRegistry` with `provider:model` names, `require_tools`), Claude moved to `providers/anthropic.py` with the SDK client and a direct HTTPS client (`NORTHCX_ANTHROPIC_CLIENT=http`), `llm.py` re-exports, the server builds a registry with Claude as the default; one conformance file runs over both clients (26 tests); the full suite is unchanged. Neither client has been run against the live API (no key). Remaining: WP1.3 to WP1.8.
**Proposed additions (not yet accepted):** WP1.9 to WP1.13, hybrid local, private-cloud and public-cloud selection with data-policy constraints, per-agent qualification and a routing-rules file; see `04-ai-architecture/NorthCX_Hybrid-Model-Selection.md`. WP1.7 (cost routing) would become the experimental part of this.
**Acceptance:** the existing suite passes unchanged on the Anthropic adapter; the same example scenarios pass on the fake server; budgets stop conversations in currency; a self-hosted-style server configuration works end to end in a browser run. **Depends on:** WP0.1, WP0.4.

### E3 Identity and governance (size XL, split into WP3.1 to WP3.6)
| WP | Work | Size | Label |
|---|---|---|---|
| **3.1** | Keys scoped to agents and environments: migration, key creation API and Studio form, enforcement in the access layer using the agent id from the route (a route table column says where the agent id sits); chat tokens already bind one agent | M | V |
| **3.2** | Groups: tables for groups, members and role bindings; OIDC group claims map to groups; effective permissions are the union | M | V |
| **3.3** | SCIM 2.0 server (`/scim/v2/Users`, `/Groups`) with a bearer token; create, update, deactivate (deactivation revokes sessions and keys); conformance tests from the RFC examples | L | V (spec), X (real IdP) |
| **3.4** | SAML behind `NORTHCX_SAML=1` using a maintained library: signed assertions only, audience, replay and clock-skew checks | L | P (vectors), X (real IdP) |
| **3.5** | Publish approval (two-person rule) per environment, built on reviews and the checklist | M | V |
| **3.6** | Teams, per-team budgets (needs 1.6) and the agent catalog | M | V |
**Acceptance:** sweeps generated from the route table prove an out-of-scope key is refused on every agent route; SCIM deactivation ends a person's access in one request. **Depends on:** WP0.1.

### E4 MCP client and server (size L, WP4.1 to WP4.3)
| WP | Work | Label |
|---|---|---|
| **4.1** | Thin client over HTTP (list tools, call tool, read-only resources); config lists servers (https, credential reference, allow-listed tools); remote tools register into the registry so scopes, approvals, guardrails and audit apply; default `effect: write` unless marked read-only; no stdio | V (fake server) |
| **4.2** | Read-only server: knowledge search, conversation search (permitted keys), ask insights, list approvals; API-key auth, role-filtered | V |
| **4.3** | Security tests: hostile tool descriptions and results, host and redirect rules, allow-list enforcement, size and time caps | V |

**Wave 1 exit:** release 1.1 gate; Threat Model gains the provider, identity and MCP entries; the decision log records D5, D7 and D9 outcomes.

## 6. Wave 2: multi-tenancy and the staff workspace (release 1.2)

### E2 Multi-tenancy (size XL, WP2.1 to WP2.10; the longest and riskiest item)
| WP | Work | Size | Label |
|---|---|---|---|
| **2.1** | **Spike and ADR:** benchmark the explicit-predicate path against row-level security with per-transaction settings on the load tool; decide the read-path design (the current read path avoids a transaction per statement on purpose); record the decision | M | V |
| **2.2** | `tenants` and `channel_bindings` tables; a request-scoped `TenantContext` (context variable) set from the key, token or channel binding; the store base class adds the tenant predicate in one place | L | V |
| **2.3** | Add `tenant_id` and backfill (`default`) table by table, in batches, each batch with its own isolation tests and a reversible migration: (a) keys, audit, SSO; (b) sessions, messages, facts, memories, traces, approvals, hand-offs, outbox, feedback, tags, reviews; (c) knowledge, crawl schedules, attachments; (d) channels (SMS, email, voice, verification); (e) versions, releases, rollouts, scenarios, simulation runs; (f) events, usage and the rest | XL (6 batches of M) | V |
| **2.4** | Row-level security policies and a test that removes the application predicate and still returns nothing for another tenant | M | V |
| **2.5** | Tenant configuration service: settings that are environment variables today become per-tenant data (agents, connectors, crawl hosts, SSO, channel credentials, secrets encrypted with a master key, residency region, webhooks, knowledge and embedding settings); resolution order tenant, then platform default, then environment, so single-company deployments keep working | L | V |
| **2.6** | Channel routing by binding (phone number id, bot id, SMS number, email domain, voice number); an unbound inbound call is ignored; one binding per number across tenants | M | V |
| **2.7** | Per-tenant limits, budgets and storage caps using the shared limiter (WP0.4) | M | V |
| **2.8** | Platform API under `/platform/v1` on a separate listener (tenant lifecycle, suspend, plan assignment); a platform role sees metadata only | M | V |
| **2.9** | **Gates:** isolation sweep generated from the route table (every route, tenant B's key and tenant A's ids, expect 404), isolation fuzz (random interleavings of two tenants), backfill and downgrade test, load within 10 percent of the documented figure | L | V |
| **2.10** | Threat-model section for isolation; documentation of tenancy and the single-tenant default | S | V |
**Acceptance:** all gates in 2.9 green on real Postgres; a deployment with no tenants configured behaves exactly as before. **Depends on:** WP0.1, WP0.4, WP0.5, E3.1. **Outside:** operating it as a hosted service (X).

### E5 Staff workspace backend (size XL, WP5.1 to WP5.8)
| WP | Work | Label |
|---|---|---|
| **5.1** | `audience: staff` on the agent spec (omitted from the canonical form when absent so existing digests do not change); validation that customer agents cannot use staff tools | V |
| **5.2** | `ToolContext` carries the actor's permissions; staff tools check them themselves | V |
| **5.3** | First staff tools: search knowledge, search and fetch conversations (masked, audited), ask insights, list hand-offs and approvals, draft a reply, summarise a conversation, create a report (E6) | V |
| **5.4** | `POST /v1/workspace/chat` streamed, bound to the signed-in identity; `customer_id = staff:<id>` | V |
| **5.5** | Staff and team memory namespaces with recall, edit and erase | V |
| **5.6** | `SearchProvider` framework: `search(query, identity)` returning results with source and access, per-provider timeout, reciprocal rank fusion, a provider that cannot prove access returns nothing; providers for knowledge, conversations, hand-offs | V |
| **5.7** | Staff guardrails: per-role approved models and tools, export data-loss rules (mask by default, volume thresholds needing approval), everything in the audit chain | V |
| **5.8** | `apps/workspace`: chat home, saved prompts, outputs panel, history, built on `packages/ui` | V (demo model), X (answer quality) |
**Tests:** matrix of roles by tools; customer text never treated as a staff instruction; memory isolation; tenant isolation. **Depends on:** E2, E3.

### E22 Agent Hub and predefined agents (proposed, not yet accepted; size L)
A gallery of predefined agents with an install flow (details, requirements check, tests, draft), updates, an organization-only hub and signed built-in entries; builds on the four existing templates. Work packages WP22.1 to WP22.9 and decisions are in `07-design/NorthCX_Agent-Hub-Design.md`. Depends on: WP0.1 (done); staff assistants depend on E5 to E7.

### E6 Libraries and generated outputs (size L, WP6.1 to WP6.3)
**6.1** Library items (prompt, macro, playbook, template, file) with owner, visibility (private, team, tenant), versions and usage counts, and sharing permissions; macros feed agent-assist suggestions. **6.2** Report service: CSV, HTML and Markdown first, figures computed by code, optional model narrative from aggregates only; then PowerPoint decks from a structured outline; outputs stored as expiring artifacts with download endpoints and audit. **6.3** Workspace UI for libraries and outputs. **Tests:** permissions per visibility, generated files reopened and validated, masked exports, expiry. **Label:** V.

### E16 Guardrail policy management (size M, V)
Policy library screen with allow and block cases; tenant and team policy sets; a policy cannot be enabled for production until its cases pass; versioned, reviewed and audited like agent versions; staff-side policies from 5.7 managed here. **Depends on:** E3, E5.

### E18 Support access (size M, V)
Customer-approved, time-limited sessions (default 2 hours, maximum 24), read-only by default, banner and log entry for the customer while active, revocable, every action in the tenant's audit log under the support identity. **Tests:** no access without an unexpired approval; read-only enforced on every route (generated from the route table); expiry and revocation immediate. **Depends on:** E2.

### First admin app (size L, V)
`apps/admin`: users, groups, keys with scopes, SSO and SCIM settings, roles, guardrail policies (E16), audit, usage placeholders; stricter session policy (step-up sign-in, shorter sessions). **Depends on:** E3, E16.

**Wave 2 exit:** release 1.2 gate; the penetration test should cover tenant isolation before any hosted use (X).

## 7. Wave 3: automations, connectors and analytics (release 1.3)

### E8 Automations (size XL, WP8.1 to WP8.6)
| WP | Work | Label |
|---|---|---|
| **8.1** | Tables and models: automation (trigger, steps, limits, owner, service identity), run records (inputs, steps, tokens, cost, outputs, outcome) | V |
| **8.2** | Triggers: schedule (the claim-once scheduler already used for crawls), webhook (per-automation secret), event (consumes the status-event feed exactly once), manual | V |
| **8.3** | Runner: steps are agent runs with a prompt template and a tool allow-list, or built-in actions (tag, create output, send digest, call an allowed connector); one run at a time, timeout, step cap, currency budget, concurrency per tenant | V |
| **8.4** | Safety: write steps go through the same approvals; kill switch per automation and per tenant; failures raise alerts | V |
| **8.5** | Natural-language builder: a validated draft (fixed fields, names checked against the registry), dry-run before offered, never saved by itself | V, X (model quality) |
| **8.6** | Studio and workspace screens: list, run history, edit, enable and pause | V |
**Tests:** schedule claiming across processes, overlapping runs refused, budget stop, approval inside a run, event trigger exactly once, webhook signature, draft validation against hostile descriptions, tenant isolation.

### E14 Visual workflow editor (size M, V)
Node-and-edge canvas whose graph is a view of the same validated definition: load parses the spec into a graph, save writes the spec back; validation uses the server's checks; full keyboard and list-view operation; read-only diff between versions; graph library behind one wrapper component. **Tests:** round-trip property tests (spec to graph to spec equals the spec), component tests, browser test that builds, saves and runs a workflow's scenarios.

### E15 Workspace analytics (size M, V)
Adoption, runs, success, latency and cost per team with denominators; staff usage aggregated by team by default, individual views need the audit permission and are themselves audited, small groups are not shown individually. **Depends on:** E5, E8, E1, E3.

### E9 Connector SDK, OAuth app flow and native connectors (size XL, WP9.1 to WP9.5)
**9.1** Connector SDK: a documented interface (auth, search, get, actions, pagination, rate-limit hints) so a connector is declarative YAML or a Python class. **9.2** OAuth app setup in Studio: authorization code with PKCE, tokens stored encrypted per tenant, scopes shown before approval. **9.3** First packs: a generic ticketing pack and Slack. **9.4** Salesforce Service Cloud. **9.5** Further packs declaratively (Intercom, Freshdesk, HubSpot, Shopify, Stripe, Jira, Confluence, Notion, Drive), each a small YAML pack with recorded fixtures. **Labels:** V (SDK, OAuth flow against a fake provider), P (packs from recorded fixtures), **X (each vendor against a sandbox before it may be called "verified")**. **Depends on:** E2, E4.

### E7 QA scoring and digests (size M, V, X for rubric quality)
Score every conversation (or a share) against a rubric with deterministic checks first and optional model scoring, store with the rubric version and reasons, measure agreement with sampled human re-scores, coaching notes; scheduled digests (weekly voice-of-customer, SLA sweeps) delivered by email, event webhook or Studio using E8.

**Wave 3 exit:** release 1.3 gate; connector documentation lists which connectors are verified against a vendor sandbox and which are fixture-only.

## 8. Wave 4: commercial platform and deployment (release 1.4)

### E10 Metering, plans and usage export (size M, V)
Append-only usage events per tenant (conversations, turns, tokens by model with currency cost, voice minutes, approvals, automation runs, storage), idempotent by event id, rolled up hourly; plans and feature flags using the existing enforcement points ("your plan does not include X"); usage API and invoice-ready CSV. **Outside:** a billing provider (X) and the billing unit decision (D8).

### E11 Deployment kit and ops app (size XL, WP11.1 to WP11.4)
**11.1** Helm chart and Terraform modules for AWS, Azure and GCP (managed Postgres with pgvector, object storage, secrets, ingress) with `helm lint` and `terraform validate` in CI where the tools are available (P; real clusters X). **11.2** `python -m northcx.upgrade`: pre-flight (configuration, migration dry run, backup reminder, residency check) and post-flight smoke test (V). **11.3** `apps/ops`: health, versions, migration state, queue depths (outbox, events, crawls, automations), backups, per-tenant usage; platform role only (V). **11.4** Attachments to object storage behind the store interface, with the database as the default (V).

### E12 Trust pack and developer portal (size M, V for documents, X for audits)
Control mappings of existing features to SOC 2 criteria and ISO 27001 controls, a GDPR pack (processing record, DPA template, subprocessor list generated from the residency report), AI-management mapping, HIPAA considerations note; customer-managed-key interface (a key per tenant wrapping data keys) with providers for the major key-management services and a local test provider, applied first to secrets and attachments (V interface, X each service); developer portal pages (API reference, SDK guides, sandbox recipe, webhook tester) under `src/site`.

### E17 Legal Center (size S, V)
Template documents labelled as needing counsel's review: privacy policy, terms, acceptable use, DPA template, generated subprocessor list.

### E19 Private-deployment console extras (size M, V on fixtures)
GPU and inference health through an adapter that reads common metrics text formats; tenant-scoped, size-capped log viewer with personal-data redaction on by default and a platform-role gate. **Real GPUs and inference servers: X.**

### Back-office app (size L, V)
`apps/backoffice`, served only on the internal listener under `/platform/v1`: tenants, plans, feature flags, licenses (only if D1 chooses a commercial tier), support-access requests (E18). **If D1 is open core, this app moves to a private repository.**

**Wave 4 exit:** release 1.4 gate; the compliance and legal documents reviewed by the owner and counsel.

## 9. Wave 5: reach (later)

| Item | Work | Label |
|---|---|---|
| **E13 Marketing site** | `src/site`: information architecture (product, use cases by team and industry, deployment options, security, customer stories placeholder, demo booking), static generator, accessibility and performance budgets; **content rule: no invented customers, logos, quotes, numbers or certifications** | V (build), content X |
| **E21 Demo booking** | Request form storing requests, rate limited and spam-protected, notifying by the event webhook or email, link to an external calendar | V |
| **Surfaces** | `src/surfaces/*`: Slack and Teams bots (signature verification and identity mapping, like the Telegram channel), helpdesk sidebars, browser extension | P, X |
| **E20 Office add-ins** | Outlook and Word add-ins reusing the workspace API with the user's own sign-in | P, X (store review) |
| **Native mobile SDKs** | Own repositories; the web widget in a web view is the interim answer | X |
| **Marketplace** | Connector and template catalog with signing and review | later |

## 10. Cross-cutting tracks

**Security.** Every epic adds a Threat Model entry before merge. New outbound addresses go through the SSRF checks (https, no redirects, private ranges refused) and the residency report; anything a model returns is validated against a fixed list; nothing a model drafts is saved without a person. The penetration test is commissioned in Wave 0 and repeated, scoped to tenant isolation, before any hosted service.

**Documentation.** Catalog IDs reserved in the gap-closure plan; the docs-sync tests keep the route reference, schema document, settings documentation and decision-log numbering honest; the product overview and project status are updated at every release.

**CI evolution.** Jobs: backend (pgvector service), web workspace (type-check, tests, build), SDK, prototype, provenance, compose stack. Added by this plan: lock check (WP0.3), two-replica test (WP0.5), provider conformance (E1), isolation sweeps (E2), connector fixtures (E9), Helm and Terraform validation (E11).

**Verification register.** Each release's notes list every deliverable as V, P or X, and the X items stay on the open list until closed.

## 11. Performance gates

| Gate | When | Pass criterion |
|---|---|---|
| Shared limiter | WP0.4 | Under 5 percent throughput cost at the documented rate |
| Router split | WP0.1 | No change in throughput |
| Provider layer | E1 | Adapter overhead under 5 ms per call with a fake server |
| Tenancy | WP2.9 | Within 10 percent of the documented figure |
| Workspace search | E5 | Federated search answers in under 2 seconds with one slow provider (timeout enforced) |
| Automations | E8 | A run claims and starts in under 1 second of its due time with 1,000 schedules |
The documented figures in `NorthCX_Performance.md` are updated after each gate and never lowered silently.

## 12. Decisions and when each is needed

| Decision | Needed before | Recommendation |
|---|---|---|
| "Resolved" definition and PRD scope wording | WP0.10 | Adopt the PRD definition as provisional |
| D1 open model | E10, back-office app | Decide before any billing work; if open core, private repository for enterprise code |
| D2 staff-product name | E5 UI copy, E13 | Own name, reviewed |
| D3 tenancy model | WP2.1 | Shared schema with RLS; dedicated = one database |
| D5 SAML approach | WP3.4 | Document an OIDC bridge now, library behind a flag |
| D6 first connectors | WP9.3 | Ticketing pack, Slack, then Salesforce |
| D7 MCP approach | WP4.1 | Thin own client |
| D8 billing unit | E10 | Meter all, bill on conversations and seats |
| D9 first providers | WP1.3 | OpenAI-compatible, then one more |
| D11 site and back-office location | WP0.2 onward, back-office app | This repository now; back office private if open core |

## 13. External actions register

| Action | Who | Needed by | Lead time |
|---|---|---|---|
| API key(s) for the live-model pass and each new provider | Owner | WP0.11, E1.3 | Immediate |
| Repository Actions enabled; first CI run | Owner | WP0.9 | Immediate |
| Penetration test commissioned | Owner and an outside tester | Before 1.0.0; again before hosted use | Weeks |
| Push `v1.0.0-rc.1` tag; cut 1.0.0 | Owner | End of Wave 0 | Minutes |
| Test identity provider (SAML, SCIM) | Owner | WP3.3, 3.4 | Days |
| Vendor sandbox or developer accounts (ticketing, Slack, Salesforce, others) | Owner | E9 packs labelled verified | Days to weeks |
| Hosting accounts, operations owner, backups, on-call | Owner | Managed cloud (after 1.4) | Weeks |
| Auditor and operating period (SOC 2, ISO) | Owner | After E12 | Months |
| Counsel review of legal templates and naming | Owner | E17, D2 | Weeks |
| Real customers and written permission for stories | Owner | E13 content | Open ended |
| Store accounts and review (Office add-ins, Slack and Teams apps) | Owner | Wave 5 | Weeks |
| Platform toolchains for native SDKs | Owner | Wave 5 | Open ended |

## 14. Living checklist

**Wave 0**
- [x] WP0.1 router, bootstrap and store split, typed `AppDeps`, shared helpers (design tokens move to WP0.2)
- [x] WP0.2 design tokens into `packages/ui`
- [x] WP0.3 locked backend dependencies
- [x] WP0.4 shared rate limits and budgets
- [x] WP0.5 multi-replica readiness
- [x] WP0.6 masked-text PDF path
- [x] WP0.7 generated API reference
- [x] WP0.8 webhook tester
- [x] WP0.9 first CI run and container build
- [x] WP0.10 resolved metric and PRD scope
- [ ] WP0.11 live-model pass and judge calibration (needs key)
- [ ] WP0.12 penetration test, tag, 1.0.0 (owner)

**Wave 1 (1.1)**
- [ ] E1 model providers (WP1.1 to WP1.8)
- [ ] E3 identity and governance (WP3.1 to WP3.6)
- [ ] E4 MCP client and server (WP4.1 to WP4.3)

**Wave 2 (1.2)**
- [ ] E2 multi-tenancy (WP2.1 to WP2.10)
- [ ] E5 staff workspace backend (WP5.1 to WP5.8)
- [ ] E6 libraries and generated outputs
- [ ] E16 guardrail policy management
- [ ] E18 support access
- [ ] First admin app

**Wave 3 (1.3)**
- [ ] E8 automations (WP8.1 to WP8.6)
- [ ] E14 visual workflow editor
- [ ] E15 workspace analytics
- [ ] E9 connector SDK, OAuth flow, packs (WP9.1 to WP9.5)
- [ ] E7 QA scoring and digests

**Wave 4 (1.4)**
- [ ] E10 metering, plans, usage export
- [ ] E11 deployment kit, upgrade tool, ops app
- [ ] E12 trust pack and developer portal
- [ ] E17 legal center
- [ ] E19 private-deployment console extras
- [ ] Back-office app

**Wave 5 (later)**
- [ ] E13 marketing site; E21 demo booking
- [ ] Surfaces (Slack, Teams, helpdesk, browser extension)
- [ ] E20 Office add-ins
- [ ] Native mobile SDKs; marketplace

## 15. Risks to the plan

| Risk | Effect | Response |
|---|---|---|
| The router split changes behaviour | Regressions in 131 routes | One router per commit, sweeps and the full suite green at each step, Studio smoke test at the end |
| Tenancy performance or leak | Slow reads or cross-tenant exposure | WP2.1 spike decides the read path; two layers of isolation; generated sweeps and fuzz; penetration test before hosted use |
| Provider differences hide in the adapter | Tools or usage misreported on a provider | One conformance suite for every adapter; capability flags refuse impossible configurations |
| Long-lead external items slip (pen test, vendors, audits) | 1.0 or connectors delayed | Start section 13 early; label connectors honestly |
| Scope growth | Plan never finishes | Ship each wave; every epic is useful without the next; re-plan at each wave boundary |
| Documentation drift | Plans and code disagree | The docs-sync tests; update the checklist, product overview and project status at each release |
