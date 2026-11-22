# NorthCX Automations Specification

Status: **Designed**. Updated: 2026-11-09. Master for: Automations and the Builder. Requirements for Automations (FR38, epics E8 and E14): multi-step work that runs by itself, with people where needed. Catalog IDs AU1 to AU12.

## 1. What an automation is
A saved, versioned workflow with a trigger, steps and limits. A run is one execution. Runs are durable: they survive a restart and resume where they stopped.

## 2. Triggers
Schedule, webhook, platform event (for example a hand-off created or an approval decided), or manual start. Each trigger names who the run acts as.

Webhook deliveries are signed (`X-Northcx-Signature`). A delivery that also carries `X-Northcx-Event-Id` (1 to 200 visible ASCII characters) starts the routine once: the same id and body again answers `200 {duplicate: true, runId}` with the first run, the same id with a different body is refused (422), and a delivery refused before it started (for example while the routine is paused) leaves the id free. Ids are remembered for 24 hours. A webhook or event trigger can name a `when` condition over the incoming data (`input.priority == 'urgent'`) so only matching deliveries start a run.

## 3. Step types
| Step | Does |
|---|---|
| Get data | Reads from a source or connected system the owner may read |
| Assistant | Runs an assistant task with a stated instruction and sources |
| Check | A rule or a model check on a value; branches on the outcome |
| Person | Waits for a named person or group to approve, answer or review, with a deadline |
| Tool (built, WP 5.1) | Calls a named registry tool with fixed or templated arguments (`{{previous.order.id}}`, `{{input.order}}`) and passes its JSON result on. Staff tools need a permission the routine's service identity (viewer) holds; a tool that changes something needs a person step before it, and one that asks for approval for the given arguments needs that person step to name an approver role or team. A result over 4,000 characters fails the step. Details: `NorthCX_Automations-Platform.md` |
| Audit | A tool step that changes something and an alert step each write an audit entry before they act (`automation.tool`, `automation.alert`), naming the routine, run, step and tool; the actor is the service identity `automation` |
| Branch (built, WP 5.2) | `when` a condition on the previous result (`previous`), the trigger input (`input`) or an item reads true: continue, stop the run, or skip 1 to 9 steps ahead. Conditions can read values, compare, combine with and, or, not and use `len(path)`; they cannot call anything or loop. Skips only go forward, and a skip cannot jump around a person step that a change needs |
| For each (built, WP 5.2) | Runs one tool or assistant step for each item of a list (`over: previous.orders`), at most 20 (default 10). One failing item stops the run and names it; items done stay done |
| Simulate (built, WP 5.4) | Runs the scenarios of an agent that is live, in a sandbox, in `scripted` mode (no real model) or `live` mode (needs a configured model; counts against the daily budget), and returns `{total, failed, failedNames}`. The run is recorded like any test run, labelled as made by a routine. Never reaches a customer or a real system |
| Criteria (built, WP 5.5; **unverified**) | A model judges the newest production conversations of an agent (at most 20 from the last 1 to 30 days) against up to five plain-language criteria ("Replies never promise a refund before it is approved"), on masked transcripts, and returns passes, failures and unusable answers per criterion. An answer the judge gave in an unusable form is counted as unusable, never as a pass. The result always carries `calibrated: false`: the judge has not been compared with people's labels (`judge_agreement` exists; no run has been made), so use it to find conversations worth a person's look, not to gate anything. The deterministic `quality` report is the baseline to read beside it. Costs model calls (criteria times conversations, at most 100), counted against the daily budget |
| Alert (built, WP 5.4) | Raises a monitoring finding and, if the administrator set up an alert webhook, a signed delivery. The text is 5 to 200 characters of fixed wording written by staff; after a `simulate` step the names of up to five failing scenarios are added. It carries no customer data and no model text, so it needs no person step. Use a `branch` first so it fires only when something failed |
| Action | A write to a connected system; always asks a person in the first version unless the organization has allowed it for that tool |

## 4. Rules
1. An automation acts with the permissions of the person or service identity it names, never more.
2. A write never runs without an approval rule that allows it. Workflows may not call customer-facing agents in the first release (decision 165).
3. Limits per automation: runs per day, steps per run, cost per run, run time. Exceeding a limit stops the run and notifies the owner.
4. A **kill switch** stops an automation and all its running runs at once; every stop is audited. Administrators see and stop every automation from the Admin app (Build > Automations, AD7; mockup `../assets/design/59-admin-automations.png`); staff build and run their own from the Workspace (Create > Automations).
5. Publishing needs a reviewer (decided, decision 165).
6. A run that needs a person and gets no answer by the deadline ends as `expired` and does nothing further.
7. Every run records inputs, step outputs (masked), people involved, cost and result.

## 5. Requirements
| ID | Requirement | Acceptance |
|---|---|---|
| AU1 | Triggers: schedule, webhook, event, manual | Each starts a run with the right identity |
| AU2 | Durable runs with resume | A restart mid-run resumes from the last finished step |
| AU3 | Person steps with deadlines | An expired step ends the run without side effects |
| AU4 | Write steps gated by approval rules | A write without approval cannot run |
| AU5 | Limits and kill switch | Hitting a limit stops the run and notifies the owner; the switch stops all runs |
| AU6 | Run history with masked inputs and outputs | A reviewer can see what ran and why |
| AU7 | Versions, review and rollback | A prior version can be republished in one step |
| AU8 | Turn a Pilot result into an automation | The saved plan becomes an editable draft, never live by itself |
| AU9 | Test runs with writes simulated | A test run records intended writes only |
| AU10 | Visual editor (E14) | The same definition can be edited as a list or a canvas |
| AU11 | Alerts on failure | The owner is told, with the failing step and reason |
| AU12 | Several-process safety | A run is leased to one worker at a time |

## 6. Builder
The **Builder** assistant (Admin, Build group) helps an administrator or developer draft an agent or automation from a description, procedures or transcripts. It only produces reviewable drafts: nothing it writes goes live, saves itself or widens access. It runs the same checks as a hand-written definition and explains each warning. Also designed: an improvement loop that suggests changes from failed conversations, shown as a diff, never applied automatically. Decided (decision 165): the name stays Builder; in the first release it only produces reviewable drafts; proactive suggestions are off by default.

## 7. Decisions (decision 165)
A reviewer must approve publishing a workflow. Workflows may not call customer-facing agents in the first release; revisit later.
