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

## Rules
- No network in unit tests.
- Any production failure becomes a regression scenario.
- Live results use thresholds (for example pass rate over N trials), not single runs.

## Judge model calibration
Before a judge gates CI, compare its verdicts to human labels on a sample set, record agreement, and re-check when the judge model changes. Deterministic assertions take priority over judge scores.

## Current coverage
`tests/runtime.test.ts`: tool execution, invalid input, approvals, handoff, history validity, guardrail rewrite and escalation, supervisor and model failure, untrusted facts.
