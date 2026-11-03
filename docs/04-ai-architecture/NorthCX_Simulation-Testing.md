

## Regression from real conversations and knowledge changes (Q5, Q7) — as built

**Scenario drafts (Q5).** `GET /v1/sessions/{id}/scenario-draft` turns a recorded conversation into a scenario: the customer's messages (personal data masked), a scripted replay of what the model did (tool calls and final answers), and expectations about each turn (status, tools called, guardrails hit, whether it went to a person). The draft is tagged `regression` and `required: false`, so it never blocks a release until a person reviews it and sets `required: true`. Warnings say what could not be captured: a held action needs a `decide` step, a draft the supervisors rejected was not recorded, platform-written turns and other agents' turns are skipped. A draft that would not load as a scenario is refused. Replaying a draft checks that today's agent (policies, tools, guardrails) still handles the recorded conversation the same way; because the model's answers are replayed, it tests everything around the model, not the model's wording.

**Re-run on knowledge change (Q7).** `NORTHCX_RERUN_ON_KNOWLEDGE` (`off` by default, `scripted` or `live`) re-runs scenarios tagged `knowledge` after documents or sources are added, changed or deleted. Changes within `NORTHCX_RERUN_DEBOUNCE_SECONDS` (60) are batched into one run, and a change during a run schedules one more afterwards. A failing tagged scenario (required or not) raises a critical `regression_failed` monitoring finding; the run is stored with `source: regression` and the reasons. `GET /v1/regression` shows the last result. Only `live` mode can notice a changed answer, because scripted runs replay fixed model output; `live` needs a real model and costs tokens. Policy changes are covered by the release gate, which already runs on every new version.

**Tags.** A scenario may carry `tags`; they are labels only and do not change its digest, so tagging never invalidates earlier gate runs.

**Not built.** Simulated customers with personas (Q6), calibrating the judge against a real model, and re-running on tool or schema changes.
