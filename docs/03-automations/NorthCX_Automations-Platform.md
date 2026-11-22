# Automations: tool steps, conditions, events, checks (Phase 5)

Status: stages 1 to 4 written 2026-11-22. **WP 5.1 (A1 to A3, A7) is built**; the rest is not, and the plan's progress table says which work package is. Master for: what Phase 5 of `../12-project/NorthCX_Agent-Platform-Plan.md` adds to routines. The engine and its rules stay as in `NorthCX_Automations-Spec.md` and `northcx/automations.py`; the direction is in `../00-platform/NorthCX_Agent-Platform-Design.md` section 8.

## 1. Research: what the code does today
Read in this repository on 2026-11-22.
- **Steps today:** `assistant` (a live staff assistant, read-only service identity), `report`, `person`, `tag`, `notify`, `output`; at most ten per routine, forward only, one text result (`prev`, capped at 4,000 characters) passed from step to step.
- **Rules already enforced:** publishing needs a second person; a step that sends data out (`notify`) needs a `person` step earlier in the same routine; a run waits for a person without holding anything and survives a restart; limits (seconds, running at once, waiting runs, daily budget) and a kill switch.
- **Triggers today:** manual, schedule, event (NorthCX's own event feed, with a per-routine cursor so an event starts a routine at most once), and webhook (a signed request to the routine's address). The webhook trigger has no protection against the same delivery arriving twice, and every event or webhook starts a run whatever it says.
- **Tools reach agents through the registry and `Runtime.execute_tool`** (staff tools need an actor holding the tool's permission; a write tool is simulated in dry-run; a read tool is retried once). Nothing outside an agent turn calls a tool. A tool can say it needs approval for given arguments (`requires_approval`), which is how refund limits work.
- **Alerts** (`northcx/alerts.py`) raise a monitoring finding and, when the administrator set one up, a signed webhook, for rule-based metrics only. Nothing lets a routine raise one.
- **Simulations** run an agent's scenarios in a sandbox in `scripted` (no real model, no judge) or `live` mode; `/v1/agents/{id}/compare` already runs scripted tests on the live version. `simulation/judge.py` has a model judge and `judge_agreement`, which compares it with human labels; no calibration has been run.
- **Idempotency** (`northcx/idempotency.py`): a store keyed by scope and request hash, with replay and conflict answers, used by chat. Webhook triggers do not use it.
- **The canvas** (Workspace `components/flow.ts`, `FlowEditor.tsx`) already turns a routine into a graph and back with round-trip tests (E14).
- **Routines are stored as JSON definitions**, so new step kinds need no database change.

## 2. Requirements
Each says who, what, and a check that passes or fails.

| ID | For whom | Requirement | Acceptance check |
|---|---|---|---|
| A1 | A staff author | A `tool` step calls a named registry tool with fixed or templated arguments and passes its structured result on | A routine that looks up an order and saves the result runs; an unknown tool, bad arguments or a staff tool the service identity may not use are refused when the routine is saved, and again when it runs |
| A2 | A reviewer | A tool that changes something needs a `person` step on every path before it, and a tool that asks for approval for the given arguments (such as a refund over its limit) needs that person step to name an approver role or team | Tests: a write tool with no earlier person step is rejected; the same tool reachable by skipping the person step is rejected; a tool that asks for approval stops the run unless the earlier person step names an approver |
| A3 | A reviewer | A write tool call carries a key that is the same on a resume or retry, so it runs once | A test resumes a run twice and sees one write |
| A4 | A staff author | A `branch` step continues, stops or skips ahead according to a condition on the previous result, the trigger input or the current item | Tests over a table of conditions and results |
| A5 | A security reviewer | The condition language is small and total: it reads values, compares them, combines with and, or, not, and has `len`; it cannot call anything, loop, assign or run code, and a missing value is null, never an error | A property test of random expressions and values: evaluation always ends with true, false or null within a fixed number of steps; a script of hostile strings (calls, attribute tricks, huge nesting) is rejected when saved |
| A6 | A staff author | A `foreach` step runs one `tool` or `assistant` step for each item of a list from the previous result, at most 20 items, and collects the results | Tests: 21 items are refused with a message saying so; each item gets its own key; one failing item stops the run and says which |
| A7 | An operator | A result too large to pass on (over 4,000 characters) fails the step with a message, not a cut-off value | A test with a result of 4,001 characters |
| A8 | An administrator | A signed webhook delivery that carries an event id (`X-Northcx-Event-Id`) starts a routine once, however often it is sent | Tests: the same id and body twice gives one run and the second answer names the first run; the same id with a different body is refused |
| A9 | A staff author | A webhook or event trigger can name a condition on the incoming data so that only matching events start a run; others are acknowledged and recorded as ignored | Tests with matching and non-matching bodies; the audit log shows both |
| A10 | An owner of a live agent | A `simulate` step runs a live customer agent's scenarios in a sandbox and returns how many failed and which; it never talks to a customer | A scheduled routine over a deliberately broken agent reports failures |
| A11 | An administrator | An `alert` step raises a monitoring finding and the alert webhook, with fixed text written by staff, naming the routine and, after a `simulate` step, the failing scenarios; it needs no person step because it carries no customer data | A broken agent raises an alert that shows in the monitoring list; the alert text contains nothing from a model reply |
| A12 | A quality lead | A `criteria` step judges recent conversations of an agent against plain-language criteria (at most five), on masked transcripts, at most 20 conversations, and reports passes per criterion | Tests with a scripted judge: counts, an unusable judge answer counts as unusable not as a pass |
| A13 | A quality lead | Every judged result says it is unverified until a judge has been compared with human labels | The result carries `calibrated: false`; the editor and docs say so |
| A14 | A staff author | The canvas shows and edits every new step kind and gives the same definition as the YAML | Round-trip property tests over generated routines with all kinds |
| A15 | Everyone | Existing routines, their definitions and tests are unchanged | The existing automation tests pass without edits |

## 3. Design
- **Values.** A step's result is text. A `tool`, `foreach` or `simulate` step produces JSON text; `branch` and templates read it as a value. Text that is not JSON is read as a string.
- **Conditions** (`northcx/expr.py`): `previous`, `input` and (inside `foreach`) `item` are the roots; paths use `.name` and `[0]`; literals are numbers, quoted strings, true, false, null; operators `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `contains`, `and`, `or`, `not`, parentheses, and `len(path)`. At most 300 characters and 8 levels deep. No arithmetic, no calls other than `len`, no names other than the three roots. A missing path is null; comparing unlike types is false.
- **Templates in arguments and prompts:** `{{previous}}`, `{{input}}`, `{{item}}` and paths such as `{{previous.order.id}}`. An argument that is exactly one placeholder keeps its type; otherwise the value is written into the text. Values read from a model reply or a customer are data, never instructions (the existing delimiting is kept for prompts).
- **Steps:**
  - `tool`: `{id, kind: tool, tool, args}`.
  - `branch`: `{id, kind: branch, when, then, else}` where each of `then` and `else` is `continue`, `stop` or `{skip: 1..9}`. Defaults: then continue, else stop. Forward only, so a routine always ends.
  - `foreach`: `{id, kind: foreach, over, max, do}`, `over` a path to a list, `max` 1 to 20 (default 10), `do` one `tool` or `assistant` step without an id. The result is a JSON list.
  - `simulate`: `{id, kind: simulate, agent, mode}`, mode `scripted` (default) or `live` (needs a configured model and counts against the daily budget).
  - `alert`: `{id, kind: alert, severity, text}`.
  - `criteria`: `{id, kind: criteria, agent, criteria[], sample, days}`.
- **The approval rule (A2)** is checked on the whole graph of possible paths when a routine is saved: a step that needs an earlier person is acceptable only if every path to it passes a `person` step. A `branch` skip cannot jump around an approval.
- **Tool calls** go through `Runtime.execute_tool` with a service identity (`automation`, viewer role) and a key built from the run, the step and the item. The step's arguments and result are masked before they are stored in the run record. A tool error fails the step with the tool's own message.
- **Webhook and event triggers** get an optional `when`. Delivery with an event id uses the idempotency store, scope = routine plus event id, request hash = body.
- **Not built, on purpose:** triggers registered by connectors or MCP servers (no connector in this repository emits events; a system that has events calls the signed address), loops other than `foreach`, assignments, code steps, nested `foreach`, a person step inside `foreach`, any step that writes to a customer.

## 4. Architecture
- `northcx/expr.py`: parser and evaluator (pure functions, no I/O).
- `northcx/automations.py`: `validate_definition` learns the new kinds and the path analysis; `_steps` becomes a loop with a position so `branch` can skip; `Hooks` gains `tools` (what can be called), `call_tool`, `check_agent`, `raise_alert`, `judge`, `sessions` and `mask`.
- `api/routers/automations.py` supplies the hooks from the runtime, the registry, the simulation service, the alert manager and the judge; the catalogue route lists the new kinds and the callable tools with their effect.
- `alerts.py`: `AlertManager.raise_routine_alert(routine_id, severity, detail)`, built from the existing `_emit`.
- Workspace: `components/flow.ts` and `FlowEditor.tsx` gain forms and summaries for the new kinds.
- No migration, no new setting, no new dependency. New API surface: none besides the catalogue's additional fields and the webhook's event id header; both are additive.

## 5. Order of work
| Order | WP | Why here |
|---|---|---|
| 1 | 5.1 | Tool step and the approval rule over paths (the rule is built with `branch` in mind, so the path analysis lands here with only the sequential case tested, and 5.2 adds skips) |
| 2 | 5.2 | Conditions and `foreach` |
| 3 | 5.3 | Exactly-once webhook, trigger conditions (uses 5.2's language) |
| 4 | 5.4 | `simulate` and `alert` |
| 5 | 5.5 | `criteria` (blocked from being called verified until a judge is compared with human labels) |
| 6 | 5.6 | The canvas, once the kinds exist |

## 6. Known limits
- Whether a judge's verdicts match people's is unmeasured (no calibration has run): A12 and A13 are checked with a scripted judge only.
- A `live` simulate step and a `criteria` step cost model calls; they are bounded by the daily budget and by 20 conversations and 5 criteria.
- A write tool inside a routine is approved once, by a person looking at the routine's earlier result, not per call. The person step's text should say what will be done; the approver role named for tools that ask for approval is the control for amounts.
