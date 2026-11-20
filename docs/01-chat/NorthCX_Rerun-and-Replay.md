# Edit and rerun, and session replay (WP 3.5)

Status: stages 1 to 4 written 2026-11-20. **3.5a (the rerun route) and 3.5b (the Studio replay screen with edit and run again) are built.** Checked by `tests/test_rerun.py`, unit and component tests, and the browser smoke test (`src/apps/studio/e2e/smoke.mjs`, run by CI). No CX lead has used it.

Two staff tools for understanding a conversation. Neither touches the real conversation or the customer.

## Research: what exists
| Found | Consequence |
|---|---|
| A conversation is its stored messages plus one trace per turn (`GET /v1/sessions/{id}/transcript` lists them; `GET /v1/traces/{id}` has the events) | Replay needs no new storage: it reads what is stored |
| Simulations already run an agent in a throwaway runtime (own stores, simulated writes, no outbox) | Rerun uses the same idea: a sandbox, not a branch saved in the real stores |
| `dry_run` makes every write tool simulate | A rerun cannot refund, email or change anything |
| Customer conversations are never edited (design, section on Chat) | Rerun copies and answers elsewhere; the source is read-only |

## Requirements
| # | For | Requirement | Acceptance check |
|---|---|---|---|
| E1 | A developer | Edit what the customer said at turn N and see how the agent answers, given the conversation before it | `POST /v1/sessions/{id}/rerun`; test: the model sees the history before turn N and the edited text, not the original turn |
| E2 | The customer, the company | Nothing is saved, sent or executed: the conversation, its traces, the outbox, approvals and hand-offs are unchanged; every write tool is simulated | Tests on each store; a write tool's function is not called |
| E3 | A developer | The answer comes with the original reply to compare, the tools used and the trace events | Response test |
| E4 | An administrator | Only people with `simulations:run`; a customer token and viewers are refused; a staff agent's conversation is refused; each rerun is audited with the turn and the length, not the text | Tests |
| E5 | An operator | A rerun uses the real model, so it counts against the daily token and money budget and stops when it is spent | Test with an exhausted budget |
| E6 | A developer | An unknown conversation (404), a turn that does not exist (400, says how many turns there are), and an empty or over-long message (400) are refused with what to do | Tests |
| R1 | A reviewer or developer | Step through a stored conversation one event at a time (previous, next, play, a slider), seeing the conversation build up and each step in plain words | Component tests (3.5b) |
| R2 | The customer | Replay only reads: it calls no model and no tool and sends nothing | Test: the page makes no request but reads (3.5b) |

## Design
- **Rerun** (`northcx/rerun.py`, route in `api/routers/rerun.py`): the customer's messages are the stored user messages that are text and do not start with a bracket (tool results and platform notes are not turns). Turn N is the Nth of them. The sandbox is a `Runtime` with its own in-memory stores, `dry_run=True`, no delivery, the real secrets store (so tool secrets work and stay redacted) and the real usage ledger. The agent is the live one for the environment of the conversation's first trace. The history copied is everything before the edited message.
- **Replay** (3.5b): the Studio page reads the transcript, loads each trace, merges the events in time order and turns each into a frame; the player shows the conversation up to the current frame. Pure functions for frames and for the conversation so far, tested without a browser.

## Built (3.5b)
- `GET /v1/sessions/{id}/turns` (permission `traces:read`): the customer's messages numbered the way `rerun` takes them, each with the reply it got.
- Studio, Conversations: each conversation has a **Replay** link to `/replay?session=…`. The player has Previous, Play, Next, a slider and the list of every step; the conversation builds up as the steps advance, and a step is shown as a sentence ("Used lookup order (order_id 1042)."). A customer message has **Edit and run again** for people with `simulations:run`: a box prefilled with the message, then the original reply beside what would happen now, the tools used, the steps, and the sandbox note. A customer message is tied to its turn by matching the words in order; if no match is found no button is shown rather than a wrong one.
- Replay reads stored traces only (a test checks it makes no rerun call); only the Edit and run again button calls the sandbox.

## Decision 206
A rerun is a sandbox, not a saved branch. A branch in the real stores would create a second conversation with traces that feed insights, alerts and the monitor, would need its own erasure and retention, and could be mistaken for a customer's. The cost of a sandbox is that nothing is kept: the person sees the answer and the trace and can copy what they need.

## Limits
- The copy has no customer record, memory or company context, so an answer that depends on them can differ from the live one. The response says so.
- The live agent is used, not the version the turn ran with.
- With a real model the answer may differ each time; with the demo model it does not.
- Replay shows what was stored; it cannot show an event the runtime did not record.
