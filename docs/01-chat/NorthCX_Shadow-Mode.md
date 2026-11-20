# Shadow mode (WP 3.4)

Status: stages 1 to 4 written 2026-11-20. **3.4a (backend) is built** and checked by `tests/test_shadow.py` (memory and Postgres). 3.4b (the Workspace Drafts screen and the widget change, S4 screen, S14) is not built: until it is, drafts are reviewed through the API. Nothing has met a real customer.

## What it is for
A company that already answers customers with people, or with another vendor's AI, can put a NorthCX agent beside them. The agent writes a reply to every customer message; a person reads it, and sends it, edits it or rejects it. The customer sees only what a person approved. Reads may run; nothing that changes something outside NorthCX runs without a person. The agreement between the agent's drafts and the people's decisions is the evidence for letting the agent answer on its own (pilot, WP 7.2).

## Research: what exists and what it means
| Found in the code | Consequence |
|---|---|
| Every customer-facing path takes the reply from `RunResult.reply`: the three chat endpoints, SMS, WhatsApp, Telegram, email (through the outbox) and voice | One place decides what the customer sees: an empty reply is never sent. SMS and email notifiers already skip an empty body; WhatsApp and Telegram share the SMS channel; voice speaks the reply live, so a shadow agent cannot be used on voice (it is refused at call start); the chat endpoints return the reply, so the widget needs a one-line change so an empty reply is not drawn as an empty bubble |
| A tool that needs approval is held as an approval; a person decides; the tool runs once; a follow-up run tells the customer (`approval_flow.py`) | Reuse it: in shadow mode every tool that is not read-only is held the same way. The follow-up reply is a draft too |
| A person who has a conversation replies from the inbox through the outbox (`handoffs`) | The outbox is how an approved draft reaches the customer; no new delivery path |
| Simulations run with `dry_run` | Shadow mode is ignored in `dry_run`, so scenarios test the agent as it will answer |
| Privacy (export, erasure, retention) works per session through the privacy backend | A new store of drafts must be in `export_session` and `erase_session` for both memory and Postgres |
| Staff agents (`audience: staff`) answer people at work, not customers | Shadow mode is for customer agents only; a staff agent with it is refused at validation |

## Requirements
| # | For | Requirement | Acceptance check |
|---|---|---|---|
| S1 | An author | An agent spec has `shadow: true` (default false). It is a customer agent only, and it is released like any change | Validation test; a spec without the field keeps its digest |
| S2 | A customer | With shadow on, no text the agent wrote is returned or sent on any path until a person approves it: chat, stream, AG-UI, SMS, WhatsApp, Telegram, email. The run returns status `in_review` and an empty reply | One test per path: the draft text appears nowhere in the response, the outbox or a notifier call |
| S3 | A company | With shadow on, a tool that is not read-only never runs in the run. It is held as an approval with the reason "Shadow mode: a person approves every action" | Test: the write tool function is not called; an approval exists; reads ran |
| S4 | A reviewer | Each draft is listed with the customer's message, the draft, the tools it used and any held action, newest last, for the conversations they may see | API and screen tests |
| S5 | A reviewer | Send as is, edit and send, or reject (with a reason from a short list and an optional note). Send and edit publish the final text to the customer once, through the outbox | Tests: exactly one outbox message; a second decision on the same draft is refused (409) |
| S6 | The agent | The conversation history holds what was actually sent: the edited text replaces the draft; a rejected draft is removed so the next turn does not build on words the customer never saw | Test on stored messages |
| S7 | A reviewer | A reviewer who edits sees the draft and the final text kept side by side in the record (the draft is kept as written) | Test |
| S8 | A customer | A draft nobody decides within the limit (default 30 minutes, `NORTHCX_SHADOW_TTL_MINUTES`) expires; the conversation is handed to a person by the existing hand-off path and the customer gets that path's message | Test, same shape as the approval expiry test |
| S9 | A company | The agreement figure: drafts sent unchanged, edited, rejected, expired, with the denominator, per agent and period (`GET /v1/shadow/summary`). Not shown as a quality score; it says how often people changed the agent's words | Test: counts and the ratio with its denominator; no figure when there are no decisions |
| S10 | An auditor | Each decision writes an audit entry (`shadow.send`, `shadow.edit`, `shadow.reject`) naming the draft and the person, with lengths and no text; the trace of the turn gets a `shadow_draft` event and a `shadow_decision` event | Audit and trace tests |
| S11 | An administrator | Only roles with the new permission `shadow:review` (reviewer, admin) may list and decide; the routes are in the permission table; a customer token cannot reach them | Route-permission and security-sweep tests |
| S12 | A data subject | Drafts are covered by export, erasure and retention for their conversation, in memory and in Postgres; the table is tenant-isolated | Privacy tests; tenant-isolation test |
| S13 | An operator | Voice refuses a shadow agent with a message that says why; simulations and regression runs ignore the flag | Tests |
| S14 | A customer on the web widget | An empty reply is not drawn as a bubble; the customer sees the typing indicator end and nothing else until the approved text arrives (the widget already collects later messages) | SDK test; size budget kept |

## Design
- **Spec and runtime.** `AgentSpec.shadow` becomes `Agent.shadow`. In `_run`, when `agent.shadow` and not `dry_run` and not a staff agent: a non-read tool call takes the approval path with the shadow reason; the final reply (any status, the held-action line and the hand-off line included) is not returned; `finish` stores it as a draft and returns `RunResult("", "in_review", ...)`. The saved history gets the draft as the assistant turn, to be replaced or removed at decision time (S6).
- **Drafts store.** A new repository, `ShadowDrafts`, with an in-memory and a Postgres version (migration 0058, tenant-scoped, row-level security): id, session id, agent id and version, customer id, trace id, the customer's message, the draft, state (`pending`, `sent`, `edited`, `rejected`, `expired`), the final text, the reasons, who decided and when, the note. Transitions are atomic, as for approvals, so two reviewers cannot both send.
- **Decision.** `ShadowFlow.decide(draft_id, action, by, text, reasons, note)`: moves the state, fixes the history, publishes `shadow_reply` to the outbox on send or edit. Edited text goes through the agent's output checks and the secret redaction before it is stored, so a person cannot send a card number or a secret by accident; a failed check refuses the edit with the reason (the person fixes it).
- **Routes.** `GET /v1/shadow/drafts?state=`, `POST /v1/shadow/drafts/{id}/decision` with `{action: send|edit|reject, text?, reasons?, note?}`, `GET /v1/shadow/summary`. New permission `shadow:review`. Additive to the Agent API.
- **Expiry.** The same sweep that expires approvals also expires drafts.
- **Channels.** SMS, WhatsApp and Telegram already skip an empty reply; email does too; their status mapping gains `in_review`. Voice refuses a shadow agent. The widget skips an empty reply.
- **Screens (3.4b).** Workspace, Inbox: a Drafts list and a review pane (customer message, draft in an editable box, tools used, buttons Send, Send with my edit, Reject with reasons), in plain words and keyboard operable.

## Architecture decisions
1. **Reuse the approval path for actions, not for replies.** A reply is not a tool call, and forcing it through `approvals` would mix two kinds of record and break the approvals screen's meaning. Drafts are their own store; actions stay approvals.
2. **Empty reply is the single gate.** Every channel already treats an empty reply as "nothing to send"; shadow mode relies on that and a test per path proves it, rather than adding a check to each channel.
3. **Edits are checked.** A person's edit is customer-facing text produced by the platform on a person's behalf; it gets the output checks.
4. **Not a quality score.** The agreement figure is counts and a ratio with its denominator. It is not a claim that the agent is right when people agree (people skim); the pilot reads it with the reasons for rejection.

## Limits and what is unverified
- The customer waits for a person. This suits a pilot where people watch the inbox; the expiry hands over to a person if nobody does.
- Nothing here has met a real customer. The agreement figure's usefulness is unverified until the pilot (WP 7.2).
- A shadow agent cannot take voice calls.

## Order of work
3.4a: spec flag and validation, runtime, store and migration, flow, routes, permission, expiry, privacy, channel statuses, voice refusal, summary, tests for S1 to S3, S5 to S13. 3.4b: Workspace Drafts screen, the widget change (S14), browser tests, and the end-to-end check on the demo stack.
