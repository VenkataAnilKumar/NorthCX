# NorthCX Simulation and Evals

Status: Draft. Not yet implemented (`src/sim` planned).

## Scenario format
```
{ name, agent, customerId?,
  turns: ["user message", ...],
  expect: { status?, toolsCalled?, toolsNotCalled?, replyIncludes?, judge?: { rubric } } }
```

## Execution
1. Run each turn through the runtime with a fresh session.
2. Collect statuses, tool calls (from the trace) and replies.
3. Check deterministic expectations first; then optionally score with a judge model against the rubric.
4. Return pass/fail with the failing expectation and trace IDs.

## Model modes
- **Scripted model:** deterministic, runs in CI, tests runtime and guardrail logic.
- **Live model:** runs the real agent; nondeterministic, so use repeated trials and thresholds.

## Suites
Happy-path intents, policy violations (must be blocked), approval-required actions, handoff triggers, prompt-injection attempts, regression cases from production traces.

## Simulated customers (Q6)
A persona-driven simulated customer (goal, patience, honesty, adversarial intent) converses with the agent for several turns. Personas include confused, angry, evasive, multilingual and prompt-injecting customers.

## Regression from production (Q5)
A failed or escalated production trace can be turned into a scenario; real, messy phrasing is preferred over templates.

## Triggers (Q7)
Simulations re-run when instructions, tools, policies, models or knowledge sources change.

## Judge calibration (Q3)
A labelled set of conversations measures judge agreement with humans; the judge only gates CI above the agreed threshold.

## Metrics
Pass rate per scenario and suite, policy-escape count, tool-call accuracy, handoff correctness, cost per scenario.

## CI gate
A pull request fails if a required scenario fails or the live-model pass rate drops below the threshold.
