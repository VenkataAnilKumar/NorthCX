# NorthCX Simulation and Evals

Status: **Built**. Updated: 2026-11-09. Master for: simulations, scenarios, judge and the release gate. The runner, scenario format, judge, command line, stored runs, release-gate rule, API and web page are built (`src/backend/northcx/simulation`); enforcement at promotion arrives with versions (sprint 10); simulated customers and regression-from-trace are planned.

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


## As built (Phase 2, sprint 8)

### Scenario files
YAML or JSON, several scenarios per file (`---`), validated strictly: an unknown or misspelled key is an error, so a typo cannot silently check nothing. Fields: `name`, `description`, `agent`, `required` (default true; only required scenarios gate), `customer_id` and `facts`, `model` (scripted responses), `turns`, `expect`, `judge`, `trials` and `min_pass_rate`.

**Steps** (`turns`): `say` (a customer message), `decide: approve|reject` (a reviewer decides the latest pending approval, optionally for a named tool, with `by` and `note`), and `expire_approvals` (age every pending approval past the limit). Each step may carry its own `expect`.

**Checks** (per step, and across the scenario): `status`, `tools_called`, `tools_not_called`, `reply_includes`, `reply_excludes`, `reply_matches`, `guardrail_hits`, `handoff` (`none`, or a trigger and topics), `approval_state`, `expired`. Scenario-level only: `max_model_calls` (a cost guard), `model_input_includes` and `model_input_excludes` (what was actually sent to the model, for example to prove personal data was masked), `approvals` (tool and final state), and `outbox_kinds`.

**Always-on invariants.** Every scenario also checks the saved conversation: each tool call answered, history ends on an assistant turn, and no leftover supervisor feedback. A runtime regression therefore fails scenarios whose own checks pass.

### Models
- `scripted` (default, deterministic, for every commit): responses come from the scenario's `model` list. The run fails if responses are left unused or run out, so a scenario cannot drift out of step with the agent.
- `demo`: the offline keyword model, for a quick local look.
- `live`: the real model. Nondeterministic, so scenarios repeat (`trials`) and pass at `min_pass_rate`.

Scripted runs test the platform's behaviour (supervision, approvals, handoffs, history) against a fixed conversation; they do not measure model quality. Live runs do, but have not yet been exercised against the real model in this repository.

### Judge
A model scores the finished conversation 1 to 5 against a rubric (`min_score`, default 4). The conversation is passed as delimited data with an instruction to ignore anything written inside it, the reply must be strict JSON with an integer score, and any error, bad score or unparseable answer is a failed verdict. A scenario with a judge check but no judge model fails, unless `--skip-judge` is given (reported as a note). `judge_agreement` compares the judge with human labels and lists disagreements; the judge should only gate anything once agreement is acceptable on a labelled set.

### Running
```
python -m northcx.simulation examples/scenarios --specs examples --registry examples.support_agent:registry [--model scripted|demo|live] [--judge-model live] [--skip-judge] [--only TEXT] [--json report.json]
```
Exit code 0 when every required scenario passes, 1 when one fails, 2 for a loading or usage error. CI runs the scripted suite on every change.

### Example suite
Fifteen scenarios for the support agent: order lookup, small refund, refund for an in-transit order, large refund approved, large refund rejected, approval expiry, three forced-topic cases (including a word-boundary case), prompt injection, personal data masked before the model, card number never reaching the customer, repeated supervisor rejection, handoff on request, and one judge scenario. Tests confirm the gate has teeth: removing the forced topics, the reply guardrail, the input guardrails, or the approval rule each makes the suite fail.


## As built (Phase 2, sprint 9): stored runs and the release gate

**Stored runs.** Every run (API, command line with `--record`, or CI) is stored with its mode, source (`api`, `cli`, `ci`), free-form metadata (for example commit and branch), the digest of each agent that was tested, and a full per-scenario report. Each scenario result carries the scenario's own digest and the agent digest it ran against. Storage is in memory or Postgres (`simulation_runs`).

**Digests.** An agent digest is the hash of its spec; a scenario digest is the hash of its definition (not of the file it lives in). Editing either changes the digest, so earlier results stop applying to the new version.

**The gate rule** (`evaluate_gate`): an agent version satisfies the gate when every one of its required scenarios has a most recent result that (1) matches the current agent digest and the current scenario definition, (2) passed, (3) came from a `scripted` or `live` run (the offline `demo` model proves nothing, so it never counts), and (4) skipped no check. Results from different runs combine, so a partial rerun can update some scenarios. The newest result wins in both directions: a recent failure blocks the gate even if an older run passed, and a later pass clears it. An agent with no required scenarios, or without a digest, is not satisfied unless a deployment explicitly allows an empty gate.

**API.** `GET /v1/simulations/scenarios`, `POST /v1/simulations/runs` (`mode`, `only`, `skipJudge`; one run at a time, 409 if busy; runs synchronously, so use scripted mode or the command line for long suites), `GET /v1/simulations/runs`, `GET /v1/simulations/runs/{id}`, and `GET /v1/simulations/gate?agent=`. The server loads scenarios from `NORTHCX_SCENARIOS_DIR` (default: the example scenarios); without scenarios these endpoints answer 501.

**CI.** The backend job runs the scripted suite, records the run with the commit, and fails the build when a required scenario fails. Sprint 10 makes promotion check the same gate for the exact version being promoted.

**Web.** The Simulations page shows the gate per agent (satisfied or blocked, with reasons), starts a run, lists recent runs, and shows each scenario's result and failure details.

**Limits.** The server runs scenarios in its own process against fresh in-memory stores, with real example tools; a dry-run mode for tools arrives with sprint 12. Live runs were only tested with a fake model.
