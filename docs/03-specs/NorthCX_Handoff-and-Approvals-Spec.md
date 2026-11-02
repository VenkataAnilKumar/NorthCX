# NorthCX Handoff and Approvals Spec

Status: Draft. Catalog IDs H1-H8, S7, T3, R10.

## Handoff triggers
| Trigger | Source |
|---|---|
| Customer asks for a person | Agent calls handoff |
| Agent cannot resolve | Agent calls handoff |
| Forced-handoff topic (for example legal matters, complaints, safety) | Policy list; always escalates |
| Repeated supervisor rejection | Runtime fallback |
| Step limit or model failure | Runtime fallback |
| Customer sentiment or frustration threshold | Planned |

## Handoff package
Transcript, customer profile and facts, actions taken with results, pending or failed actions, detected intent, handoff reason and trigger, short summary, trace link, and suggested next steps (Phase 5).

## Routing
Queue by topic, language and hours (H8). Outside hours, the agent sets expectations and records a callback or ticket.

## Return to agent
A human may hand a simple remainder back to the agent with notes (H7).

## Approvals
1. A tool's rule returns a reason; the run stops with `needs_approval`.
2. The pending approval stores the exact tool, input, reason, trace and session.
3. Reviewers list pending items, see context, and approve or reject with their identity.
4. Approved: the action executes once (idempotent) and the conversation resumes with the result. Rejected: the agent explains and offers alternatives or handoff.
5. Pending approvals expire after a configured time and escalate.
6. Every decision is audited.

## Acceptance
- A handoff always includes the full package.
- A decided approval cannot be decided again.
- An approved action never executes twice.
- Expired approvals escalate.
