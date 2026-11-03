# NorthCX Testing Strategy

Status: Draft

| Level | Scope | Model | Runs |
|---|---|---|---|
| Unit | Runtime loop, tools, guardrails, stores | Scripted | Every commit |
| Contract | Store adapters, channel adapters against the interface | Scripted | Every commit |
| Simulation (deterministic) | Scenarios with assertions | Scripted | Every commit |
| Simulation (live) | Same scenarios with the real agent | Live, repeated trials | Pull requests and nightly |
| Safety | Policy-violation and prompt-injection scenarios | Live | Nightly and before release |
| Load | Throughput, latency, cost per run | Live or stub | Before release |
| Security | Dependency, licence and secret scans; pen-test | n/a | CI and per release |

## Additional test types
- **Simulated-customer runs** with adversarial personas (Q6).
- **Knowledge-change runs** triggered when sources change (Q7).
- **Regression scenarios** generated from production traces (Q5).
- **Approval and handoff flows** end to end, including expiry and double-decision.
- **Release tests:** promotion blocked on failure, rollback restores behaviour.

## Database tests
The in-memory and Postgres repositories share one contract suite (history round trip, replace semantics, facts, trace ordering and summaries, approval lifecycle, concurrent decisions). Postgres-only tests cover migrations (apply, roll back, re-apply, and agreement with the models), a simulated restart, and the server on Postgres. Locally the tests skip if no database is reachable; CI sets `NORTHCX_REQUIRE_DB=1` so a missing database fails the build.

## Approval flow tests
Run against both in-memory and Postgres stores: exactly-once execution under concurrent decisions, idempotency key, supervisor re-check at execution, invalid input at execution, tool failure, missing agent, chained approvals, model failure after execution, expiry (including races with decisions), valid saved history after every path, outbox contents, and webhook signing, retry and redelivery. Mutation checks confirmed that removing the atomic claim or the supervisor re-check makes tests fail.

## Handoff tests
Package builder (transcript, action outcomes, summary), every escalation trigger, forced topics (model never called, word boundaries, platform notices exempt, multiple topics), spec validation of topics, handoffs surviving a restart in Postgres, resolve-once under concurrency in both stores, and the queue API. A mutation check (disabling topic matching, or removing platform-notice handling) makes tests fail.

## Simulation tests
The runner is itself tested: every check type fails when its expectation is wrong, scripts must match exactly, invariants catch broken histories, the judge fails closed, trials and the required/optional gate behave as documented, the command line returns the right exit codes, and the example suite passes. Weakening the example agent (no forced topics, no reply guardrail, no input guardrails, no approval rule) must make the suite fail.

## Gate tests
The gate rule is tested for version and scenario changes, newest-result-wins in both directions, partial runs, demo versus live runs, skipped checks, missing digests, and empty gates; stored runs share a contract suite across memory and Postgres, and the gate works from runs stored before a simulated restart. Mutation checks (ignoring the agent digest, or counting demo runs) make tests fail.

**Email channel.** Parsing (plain/HTML, charsets, quoted history and signatures, threading headers, robot/list/bounce detection, unusable input, gateway vouching, header injection); sending against a real in-process SMTP server (threading and auto-reply headers, rejected recipients, no password in errors, retry exactly once through the outbox); the channel (same-thread replies, follow-ups, a different sender never joining, duplicates delivered concurrently, loop protection, per-sender limit, identity only with a trusted gateway, handoff hold and resume, injection stopped, attachments noted not read, approval results emailed in-thread); the storage contract on memory and Postgres; and the endpoint (roles, customer tokens refused, size and format errors, unconfigured, redelivery after an internal failure).

**Knowledge.** Chunking (headings, long paragraphs with and without spaces, small paragraphs merged, line endings), ids and hashing; the store contract on memory and Postgres (ranking and citations, unchanged re-submits, replaced passages, validation, deletion, freshness from the company's update time, concurrent identical uploads); the agent tool (numbered citations, stale notes, nothing-found guidance, source scoping) and a poisoned document being withheld by the tool-result screen; and the API (round trip, audit entries, per-role permissions, customer tokens refused).

**Privacy.** On memory and Postgres: export collects only the customer's conversations, facts, approvals, hand-offs and outbox; erasure removes messages, traces, outbox, approvals, hand-offs, findings, stored replies and facts and leaves other customers alone; single-conversation erasure; retention cut-offs; a conversation shared by two customers; verified email threads; the trace file mirror; and the API (audit entries carry a one-way customer reference, never the id; admin-only; invalid retention values refused).

## Release tests
Over memory and Postgres: numbering (also concurrent), immutability, refusal of invalid, mismatched or unchanged specs, readable diffs, the gate at publish for the exact version (including a failing proof and a proof for a different version), rollback in all its forms (undo, toggle, named version, never-live version, baseline, no gate needed), live serving and caching, an unbuildable live version, agent version on traces, approvals resolved against the live agent, and the whole API flow. Mutation checks (publishing without the gate, or checking the gate for the file's digest instead of the version's) make tests fail. A browser test walks the entire flow including a restart.

## Access tests
The permission matrix is tested for every role against every kind of endpoint (allowed roles succeed, others get 403 and a denial is audited); a completeness test fails if any `/v1` route lacks a permission or the table lists a route that does not exist; identities override claimed names; keys (issue, hash-only storage, wrong character, expiry, revocation, unique names, last-admin protection, throttled last-used) over memory and Postgres; the audit chain (edits, removals, concurrent appends, pagination, filters), the database triggers and a simulated tamper by a privileged user; audit entries never contain secrets or conversation text; rate limits (bursts, refill, independence, per conversation, guessing); a restart with keys and the log in Postgres; and the key command line. Mutation checks (skipping the permission check, trusting a claimed name, accepting revoked keys) make tests fail. A browser test signs in as several roles against a Postgres-backed, authenticated server.

## Operations tests
Secrets: reading from the environment and from files (both set is an error, missing and empty files, newline stripped), tool secrets versus hidden platform secrets, short secrets refused, scrubbing (overlaps, repeats, nested data, keys), and leak tests across the model's view, traces, saved history, approvals, handoff packages, replies and errors (these found and closed two leaks). Dry run: reads run and writes are simulated in runs, approvals and simulations, with a placeholder when a tool has no simulation, a safe default of "write", and an explicit command-line switch for real side effects. Readiness (including a broken store and Postgres), registry configuration errors.

Containers: the backend and web images were built and run for real (non-root, healthy, migrations present in the installed package, secrets from files, the scenario suite passing inside the image); the compose stack comes up with one command, refuses to start without required values, serves a browser session end to end through the compose network, and keeps its state across `restart` and `down` then `up`. CI repeats the stack build and a smoke test on every change. Not covered: Kubernetes, multi-process rate limiting, and a Docker Hub outage (one local build was briefly rate-limited by the registry).

## Chat token tests
Signed tokens (claims, expiry to the second, bounded lifetimes, forged or edited payloads and signatures, malformed and oversized input, correctly signed but nonsensical payloads, secret derivation); authentication (the minting key's status and role, revocation, expiry reported distinctly, tokens and keys not interchangeable, no signer); the API (minting roles and validation, a customer chatting with a token, the customer id taken from the token, scope violations audited, a token able to do nothing else, expiry and forgery, restart with a stable secret, per-conversation rate limits, open mode); and the demo page in a real browser (fragment token removed from the address bar, never sent in a URL, only the token stored). Mutation checks (trusting the body's customer, skipping the scope check, skipping the minting-key check, skipping the signature check) make tests fail.

## Rules
- No network in unit tests.
- Any production failure becomes a regression scenario.
- Live results use thresholds (for example pass rate over N trials), not single runs.

## Judge model calibration
Before a judge gates CI, compare its verdicts to human labels on a sample set, record agreement, and re-check when the judge model changes. Deterministic assertions take priority over judge scores.

## Current coverage
Prototype tests (`src/prototype/tests/runtime.test.ts`), to be ported to pytest for the Python backend: tool execution, invalid input, approvals, handoff, history validity, guardrail rewrite and escalation, supervisor and model failure, untrusted facts.
