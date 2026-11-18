# NorthCX Simulation and Evals

Status: **Built**. Updated: 2026-11-09. Master for: simulations, scenarios, judge and the release gate. Code in `src/backend/northcx/simulation`; example scenarios in `src/backend/examples/scenarios`. Built: the runner, scenario files, the judge with an agreement check, the command line, stored runs, the release gate enforced at publishing and promotion, simulated customers with eight personas, regression scenarios drafted from conversations, and re-runs on knowledge changes. Not done: calibrating the judge against a real model, and running the live-model suites with a real model.

## Scenario format
YAML files, several scenarios per file separated by `---`. Each has `name`, `description`, `agent`, optional `tags`, a scripted `model` (the replies a scripted model gives, or empty for none), `turns` (a customer message, or `converse: <persona>` for a simulated customer, each with its own `expect`), and a scenario-level `expect` (for example `status`, `tools_called`, `tools_not_called`, `guardrail_hits`, `max_model_calls`, `handoff`, reply text checks and an optional judge rubric). The full field list is in the "As built" sections below and in the example files.

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
A persona-driven simulated customer (goal, patience, honesty, adversarial intent) converses with the agent for several turns. The library has eight personas: `friendly`, `impatient`, `confused`, `abusive`, `prompt_injector`, `pii_dumper`, `legal_pressure` and `off_topic` (details below). Personas in languages other than English are not built.

## Regression from production (Q5)
A failed or escalated production trace can be turned into a scenario; real, messy phrasing is preferred over templates.

## Triggers (Q7)
Built: scenarios tagged `knowledge` re-run when documents or sources change (`NORTHCX_RERUN_ON_KNOWLEDGE`). Changes to instructions, tools, policies and the model change the version's digest, so the release gate asks for new proof before release. Re-running automatically on tool or schema changes is not built.

## Judge calibration (Q3)
A labelled set of conversations measures judge agreement with humans; the judge only gates CI above the agreed threshold.

## Metrics
Pass rate per scenario and suite, policy-escape count, tool-call accuracy, handoff correctness, cost per scenario.

## CI gate
A change fails CI if a required scenario fails in the scripted suite (built). A live-model pass-rate threshold in CI needs an API key and is not set up.


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
At sprint 8, fifteen scenarios for the support agent (eighteen in `src/backend/examples/scenarios` today, including three adversarial ones added with Q6): order lookup, small refund, refund for an in-transit order, large refund approved, large refund rejected, approval expiry, three forced-topic cases (including a word-boundary case), prompt injection, personal data masked before the model, card number never reaching the customer, repeated supervisor rejection, handoff on request, and one judge scenario. Tests confirm the gate has teeth: removing the forced topics, the reply guardrail, the input guardrails, or the approval rule each makes the suite fail.


## As built (Phase 2, sprint 9): stored runs and the release gate

**Stored runs.** Every run (API, command line with `--record`, or CI) is stored with its mode, source (`api`, `cli`, `ci`), free-form metadata (for example commit and branch), the digest of each agent that was tested, and a full per-scenario report. Each scenario result carries the scenario's own digest and the agent digest it ran against. Storage is in memory or Postgres (`simulation_runs`).

**Digests.** An agent digest is the hash of its spec; a scenario digest is the hash of its definition (not of the file it lives in). Editing either changes the digest, so earlier results stop applying to the new version.

**The gate rule** (`evaluate_gate`): an agent version satisfies the gate when every one of its required scenarios has a most recent result that (1) matches the current agent digest and the current scenario definition, (2) passed, (3) came from a `scripted` or `live` run (the offline `demo` model proves nothing, so it never counts), and (4) skipped no check. Results from different runs combine, so a partial rerun can update some scenarios. The newest result wins in both directions: a recent failure blocks the gate even if an older run passed, and a later pass clears it. An agent with no required scenarios, or without a digest, is not satisfied unless a deployment explicitly allows an empty gate.

**API.** `GET /v1/simulations/scenarios`, `POST /v1/simulations/runs` (`mode`, `only`, `skipJudge`; one run at a time, 409 if busy; runs synchronously, so use scripted mode or the command line for long suites), `GET /v1/simulations/runs`, `GET /v1/simulations/runs/{id}`, and `GET /v1/simulations/gate?agent=`. The server loads scenarios from `NORTHCX_SCENARIOS_DIR` (default: the example scenarios); without scenarios these endpoints answer 501.

**CI.** The backend job runs the scripted suite, records the run with the commit, and fails the build when a required scenario fails. Publishing and promotion check the same gate for the exact version (built in sprint 10; see Release Management).

**Web.** The Simulations page shows the gate per agent (satisfied or blocked, with reasons), starts a run, lists recent runs, and shows each scenario's result and failure details.

**Limits.** The server runs scenarios in its own process against fresh in-memory stores, with real example tools; write tools are replaced by their dry-run result in simulations (built later, T8). Live runs were only tested with a fake model.

## Regression from real conversations and knowledge changes (Q5, Q7) — as built

**Scenario drafts (Q5).** `GET /v1/sessions/{id}/scenario-draft` turns a recorded conversation into a scenario: the customer's messages (personal data masked), a scripted replay of what the model did (tool calls and final answers), and expectations about each turn (status, tools called, guardrails hit, whether it went to a person). The draft is tagged `regression` and `required: false`, so it never blocks a release until a person reviews it and sets `required: true`. Warnings say what could not be captured: a held action needs a `decide` step, a draft the supervisors rejected was not recorded, platform-written turns and other agents' turns are skipped. A draft that would not load as a scenario is refused. Replaying a draft checks that today's agent (policies, tools, guardrails) still handles the recorded conversation the same way; because the model's answers are replayed, it tests everything around the model, not the model's wording.

**Re-run on knowledge change (Q7).** `NORTHCX_RERUN_ON_KNOWLEDGE` (`off` by default, `scripted` or `live`) re-runs scenarios tagged `knowledge` after documents or sources are added, changed or deleted. Changes within `NORTHCX_RERUN_DEBOUNCE_SECONDS` (60) are batched into one run, and a change during a run schedules one more afterwards. A failing tagged scenario (required or not) raises a critical `regression_failed` monitoring finding; the run is stored with `source: regression` and the reasons. `GET /v1/regression` shows the last result. Only `live` mode can notice a changed answer, because scripted runs replay fixed model output; `live` needs a real model and costs tokens. Policy changes are covered by the release gate, which already runs on every new version.

**Tags.** A scenario may carry `tags`; they are labels only and do not change its digest, so tagging never invalidates earlier gate runs.

**Not built.** Calibrating the judge against a real model, and re-running on tool or schema changes. (Simulated customers, Q6, were built afterwards; next section.)


## Simulated customers and attack suites (Q6) — as built

A scenario step `converse: <persona>` lets a simulated customer talk to the agent. The library has eight personas: `friendly`, `impatient`, `confused`, `abusive`, and the adversarial `prompt_injector`, `pii_dumper`, `legal_pressure` and `off_topic`. Each has a description (for a model that plays it) and a few fixed lines.

- **Without a customer model (scripted and demo runs):** the persona's fixed lines (or the step's own `lines`) are spoken in order, up to `max_turns`. Every line is tried even if the agent hands the conversation to a person. This makes the adversarial personas a **deterministic attack suite** that runs in CI with no model for the customer: a line the input checks stop never reaches the agent's model, and a line that gets past them reaches a model that a scripted scenario does not provide, which fails the scenario.
- **Live runs:** a model plays the customer from the persona description and the step's `goal`, sees the conversation from the customer's side, treats the agent's words as data, and ends with `[END]` when its goal is met or it gives up (messages are capped at 600 characters). The step ends early when the conversation is handed to a person or waits for approval. A failing customer model ends the conversation and fails the step if nothing was said.
- **Shipped attack scenarios** (required, tagged `adversarial`): prompt injection never reaches the model and never gets a refund; personal data pasted into the chat is masked in everything sent to the model; legal threats go to a person on the first message. Each was checked by removing its defence (the injection check, the PII check, the legal topic) and confirming the scenario fails.
- **Not built:** judging the quality of live persona conversations against a calibrated judge, personas for languages other than English, and a way to define personas in configuration (the library is code; a step can override the lines).
