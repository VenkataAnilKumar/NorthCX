# NorthCX Automations Specification

Status: **Draft, designed 2026-11-09; not built.** Requirements for Automations (FR38, epics E8 and E14): multi-step work that runs by itself, with people where needed. Catalog IDs AU1 to AU12.

## 1. What an automation is
A saved, versioned workflow with a trigger, steps and limits. A run is one execution. Runs are durable: they survive a restart and resume where they stopped.

## 2. Triggers
Schedule, webhook, platform event (for example a hand-off created or an approval decided), or manual start. Each trigger names who the run acts as.

## 3. Step types
| Step | Does |
|---|---|
| Get data | Reads from a source or connected system the owner may read |
| Assistant | Runs an assistant task with a stated instruction and sources |
| Check | A rule or a model check on a value; branches on the outcome |
| Person | Waits for a named person or group to approve, answer or review, with a deadline |
| Action | A write to a connected system; always asks a person in the first version unless the organization has allowed it for that tool |

## 4. Rules
1. An automation acts with the permissions of the person or service identity it names, never more.
2. A write never runs without an approval rule that allows it. Customer-facing agents are not called by workflows until the owner decision on that is made.
3. Limits per automation: runs per day, steps per run, cost per run, run time. Exceeding a limit stops the run and notifies the owner.
4. A **kill switch** stops an automation and all its running runs at once; every stop is audited.
5. Publishing needs a reviewer (decision pending: who may publish).
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
The **Builder** assistant (Admin, Build group) helps an administrator or developer draft an agent or automation from a description, procedures or transcripts. It only produces reviewable drafts: nothing it writes goes live, saves itself or widens access. It runs the same checks as a hand-written definition and explains each warning. Proposed: an improvement loop that suggests changes from failed conversations, shown as a diff, never applied automatically. Open: name, first-release scope, whether proactive suggestions are on by default.

## 7. Open decisions
Who may publish a workflow; whether workflows may call customer-facing agents.
