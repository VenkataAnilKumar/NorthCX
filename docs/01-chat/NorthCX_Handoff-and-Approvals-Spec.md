# NorthCX Handoff and Approvals Spec

Status: **Built**. Updated: 2026-11-09. Master for: hand-offs and approvals. Catalog IDs H1-H8, S7, T3, R10.

## Handoff triggers
| Trigger | Source |
|---|---|
| Customer asks for a person | Agent calls handoff |
| Agent cannot resolve | Agent calls handoff |
| Forced-handoff topic (for example legal matters, complaints, safety) | Policy list; always escalates |
| Repeated supervisor rejection | Runtime fallback |
| Step limit or model failure | Runtime fallback |
| Customer sentiment or frustration threshold | Planned |
| Abusive messages past a limit, or a threat | Built (abuse detection, S8) |

## Handoff package
Transcript, customer profile and facts, actions taken with results, pending or failed actions, detected intent, handoff reason and trigger, short summary, trace link, and suggested next steps (Phase 5).

## As built (Phase 2, sprint 7)
**When a handoff is created.** Whenever a run ends `escalated`: the agent calls the handoff tool (`agent_handoff`), a forced topic matches (`forced_topic`), the customer's message is blocked by an input policy (`input_blocked`), supervisors reject the agent's replies repeatedly (`supervisor_rejections`), the step limit is reached (`step_limit`), the model cannot be reached (`model_error`), or an approval expires (`approval_expired`). Added later: abuse detection (`abuse`), a used-up model budget (`budget_exceeded`) and a customer asking for a person outside the agent, for example pressing 0 on a call (`customer_request`). The reason never includes internal error text.

**The package** is built from what the platform already holds, with no extra model call: a one-paragraph summary, the trigger and reason, matched topics, the transcript (customer, agent and platform notices; supervisor feedback and tool plumbing excluded), the customer's facts, every tool call the agent attempted in the session with its outcome (succeeded, failed, held for approval, blocked by policy, not executed), and the session's approvals with their state and notes. The summary is templated, not model-written; a model summary is a later option.

**The queue.** Handoffs are `open` until a person marks them `resolved` (once; a second attempt returns 409), recording who and an optional note. API: `GET /v1/handoffs?state=&sessionId=`, `GET /v1/handoffs/{id}` (with the full package), `POST /v1/handoffs/{id}/resolve`. The web console has a Handoffs page, and the chat response carries `handoffId`.

**Built later:** queue routing by topic, trigger and hours (H8, below), the inbox integration (H5: signed webhook and Chatwoot adapter), suggested replies (H6) and return-to-agent (H7). **Still not built:** routing by language, assignment or claiming by a named person, and sentiment triggers. The package contains personal data; reading it needs the handoffs permission, resolving needs the reviewer or admin role, and resolutions are audited.

## Routing
Queue by topic, language and hours (H8). Outside hours, the agent sets expectations and records a callback or ticket.

## Return to agent
A human may hand a simple remainder back to the agent with notes (H7, built: resolving with a note hands the conversation back).

## After 1.0
In the Workspace, staff work this queue in the **Inbox** tab and decide approvals in the **Approvals** tab; the Admin app keeps the **Hand-offs** and **Approvals** pages for oversight (`../02-studio/NorthCX_Platform-Features-and-Tabs.md`, "Same name, two jobs"). Designed, not built.

## Approvals
1. A tool's rule returns a reason; the run stops with `needs_approval`.
2. The pending approval stores the exact tool, input, reason, trace and session.
3. Reviewers list pending items, see context, and approve or reject with their identity.
4. Approved: the action executes once (idempotent) and the conversation resumes with the result. Rejected: the agent explains and offers alternatives or handoff.
5. Pending approvals expire after a configured time and escalate.
6. Every decision is audited.

## As built (Phase 2, sprint 6)
**States.** `pending` to `approved` to `executing` to `executed` or `failed`; `pending` to `rejected` or `expired`. Every transition is atomic in the store, so concurrent callers cannot decide, claim or expire the same approval twice.

**Approve.** The decision is recorded (reviewer, optional note). The held call is then claimed, validated again, re-checked by the supervisors (policy may have changed while it waited) with the same context the runtime used: the channel of the turn that asked, and the customer's facts worked out as at execution time (stored facts, the company's systems, and the platform's own identity check; a stored identity claim is ignored), so a scope that held when the action was asked for still holds, and one that has lapsed refuses. What happened at execution (executed, failed, blocked, tool missing, invalid input) and the checks' own events are added to the trace of the turn that asked, so it is on record without counting as another turn, and executed with the approval id as an idempotency key that tools should use to deduplicate writes. The outcome (result or error) is stored on the approval. The agent receives a platform notice with the outcome and writes the customer-facing reply, which passes the normal reply checks. If the model call fails afterwards, the action still stands and the conversation is escalated.

**Reject.** The action is never executed; the agent receives the reviewer's note and explains the outcome, offering alternatives or a handoff.

**Expire.** A sweeper (`NORTHCX_APPROVAL_TTL_SECONDS`) or `POST /v1/approvals/expire` expires approvals pending longer than the limit, writes a handoff trace, and tells the customer a person will help. A late decision is refused (409).

**Delivery.** Each result is stored in an outbox (`GET /v1/sessions/{id}/outbox?after=`) so channels and the web console can poll, and optionally pushed to a webhook (`NORTHCX_WEBHOOK_URL` and `NORTHCX_WEBHOOK_SECRET`). Webhook bodies are signed (`X-NorthCX-Signature`: HMAC-SHA256 over `timestamp.body`, with `X-NorthCX-Timestamp`); receivers should verify the signature and reject timestamps older than five minutes. Failed pushes retry with backoff and stay in the outbox until delivered.

**Limits.** A crash between executing a tool and recording its result leaves the approval in `executing`; tools must honour the idempotency key so a manual retry is safe. The follow-up runs inside the decision request. Results also reach the customer on their channel through the channel adapters (built).

## Acceptance
- A handoff always includes the full package.
- A decided approval cannot be decided again.
- An approved action never executes twice.
- Expired approvals escalate.


## Business hours and queues (H8)

Each hand-off lands in a **queue**, chosen by the first queue whose `topics` include one of the conversation's forced topics or whose `triggers` include why the hand-off happened (`agent_handoff`, `step_limit`, `budget_exceeded`, and so on); otherwise the `default_queue`. A routing file (`NORTHCX_ROUTING_FILE`, example in `src/backend/examples/config/routing.example.yaml`) sets the time zone, default hours, holidays and per-queue hours. Hours are windows such as `mon-fri: "09:00-17:00"` (several windows and `always` are allowed; overnight windows are written as two ranges); daylight-saving changes follow the clock in the configured time zone. A file with mistakes is refused at start-up with every problem listed.

When a conversation is handed over while its queue is closed, the customer's reply gets the `after_hours_message` added, with the next opening time in the company's time zone (`{when}` is replaced by it), and the hand-off is flagged `afterHours`. The queue, the flag and the next opening time are stored with the hand-off (`GET /v1/handoffs?queue=`; `GET /v1/routing` shows each queue and whether it is open). The Handoffs page filters by queue and marks after-hours arrivals.

Not built: assigning a hand-off to a named person, service-level timers and escalation when a queue is not picked up, and per-agent or per-skill routing. Hours do not stop the agent from answering; they only change what customers are told when a person is needed.
