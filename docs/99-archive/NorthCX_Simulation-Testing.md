

> **Archived 2026-11-09.** Merged into `../06-testing-evaluation/NorthCX_Simulation-and-Evals.md`. Kept for history; not maintained.

## Regression from real conversations and knowledge changes (Q5, Q7) — as built

**Scenario drafts (Q5).** `GET /v1/sessions/{id}/scenario-draft` turns a recorded conversation into a scenario: the customer's messages (personal data masked), a scripted replay of what the model did (tool calls and final answers), and expectations about each turn (status, tools called, guardrails hit, whether it went to a person). The draft is tagged `regression` and `required: false`, so it never blocks a release until a person reviews it and sets `required: true`. Warnings say what could not be captured: a held action needs a `decide` step, a draft the supervisors rejected was not recorded, platform-written turns and other agents' turns are skipped. A draft that would not load as a scenario is refused. Replaying a draft checks that today's agent (policies, tools, guardrails) still handles the recorded conversation the same way; because the model's answers are replayed, it tests everything around the model, not the model's wording.

**Re-run on knowledge change (Q7).** `NORTHCX_RERUN_ON_KNOWLEDGE` (`off` by default, `scripted` or `live`) re-runs scenarios tagged `knowledge` after documents or sources are added, changed or deleted. Changes within `NORTHCX_RERUN_DEBOUNCE_SECONDS` (60) are batched into one run, and a change during a run schedules one more afterwards. A failing tagged scenario (required or not) raises a critical `regression_failed` monitoring finding; the run is stored with `source: regression` and the reasons. `GET /v1/regression` shows the last result. Only `live` mode can notice a changed answer, because scripted runs replay fixed model output; `live` needs a real model and costs tokens. Policy changes are covered by the release gate, which already runs on every new version.

**Tags.** A scenario may carry `tags`; they are labels only and do not change its digest, so tagging never invalidates earlier gate runs.

**Not built.** Simulated customers with personas (Q6), calibrating the judge against a real model, and re-running on tool or schema changes.


## Simulated customers and attack suites (Q6) — as built

A scenario step `converse: <persona>` lets a simulated customer talk to the agent. The library has eight personas: `friendly`, `impatient`, `confused`, `abusive`, and the adversarial `prompt_injector`, `pii_dumper`, `legal_pressure` and `off_topic`. Each has a description (for a model that plays it) and a few fixed lines.

- **Without a customer model (scripted and demo runs):** the persona's fixed lines (or the step's own `lines`) are spoken in order, up to `max_turns`. Every line is tried even if the agent hands the conversation to a person. This makes the adversarial personas a **deterministic attack suite** that runs in CI with no model for the customer: a line the input checks stop never reaches the agent's model, and a line that gets past them reaches a model that a scripted scenario does not provide, which fails the scenario.
- **Live runs:** a model plays the customer from the persona description and the step's `goal`, sees the conversation from the customer's side, treats the agent's words as data, and ends with `[END]` when its goal is met or it gives up (messages are capped at 600 characters). The step ends early when the conversation is handed to a person or waits for approval. A failing customer model ends the conversation and fails the step if nothing was said.
- **Shipped attack scenarios** (required, tagged `adversarial`): prompt injection never reaches the model and never gets a refund; personal data pasted into the chat is masked in everything sent to the model; legal threats go to a person on the first message. Each was checked by removing its defence (the injection check, the PII check, the legal topic) and confirming the scenario fails.
- **Not built:** judging the quality of live persona conversations against a calibrated judge, personas for languages other than English, and a way to define personas in configuration (the library is code; a step can override the lines).
