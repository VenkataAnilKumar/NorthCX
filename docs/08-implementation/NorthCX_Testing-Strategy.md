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

## Release tests
Over memory and Postgres: numbering (also concurrent), immutability, refusal of invalid, mismatched or unchanged specs, readable diffs, the gate at publish for the exact version (including a failing proof and a proof for a different version), rollback in all its forms (undo, toggle, named version, never-live version, baseline, no gate needed), live serving and caching, an unbuildable live version, agent version on traces, approvals resolved against the live agent, and the whole API flow. Mutation checks (publishing without the gate, or checking the gate for the file's digest instead of the version's) make tests fail. A browser test walks the entire flow including a restart.

## Access tests
The permission matrix is tested for every role against every kind of endpoint (allowed roles succeed, others get 403 and a denial is audited); a completeness test fails if any `/v1` route lacks a permission or the table lists a route that does not exist; identities override claimed names; keys (issue, hash-only storage, wrong character, expiry, revocation, unique names, last-admin protection, throttled last-used) over memory and Postgres; the audit chain (edits, removals, concurrent appends, pagination, filters), the database triggers and a simulated tamper by a privileged user; audit entries never contain secrets or conversation text; rate limits (bursts, refill, independence, per conversation, guessing); a restart with keys and the log in Postgres; and the key command line. Mutation checks (skipping the permission check, trusting a claimed name, accepting revoked keys) make tests fail. A browser test signs in as several roles against a Postgres-backed, authenticated server.

## Rules
- No network in unit tests.
- Any production failure becomes a regression scenario.
- Live results use thresholds (for example pass rate over N trials), not single runs.

## Judge model calibration
Before a judge gates CI, compare its verdicts to human labels on a sample set, record agreement, and re-check when the judge model changes. Deterministic assertions take priority over judge scores.

## Current coverage
Prototype tests (`src/prototype/tests/runtime.test.ts`), to be ported to pytest for the Python backend: tool execution, invalid input, approvals, handoff, history validity, guardrail rewrite and escalation, supervisor and model failure, untrusted facts.
