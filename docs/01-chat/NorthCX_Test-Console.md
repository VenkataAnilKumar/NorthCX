# Studio test console (WP 3.3)

Status: built 2026-11-19; checked by unit and component tests and a real-browser run against the demo stack (`src/apps/studio/e2e/smoke.mjs`, which CI runs). Not yet tried by a CX lead.

The console (Studio, Build, Test console) lets a builder chat with an agent and see what it did. WP 3.3 adds cards, decisions on the spot, and a trace in words. It uses the existing stream and the existing approval route; no backend change.

## Requirements
| # | For | Requirement | Check |
|---|---|---|---|
| T1 | A builder | Each tool the agent used in a turn appears as a card in the conversation: its name in words (an MCP tool as "name from connection"), what it was asked with, the answer (cut to 140 characters), or "Held for a person" with the reason | `console-steps.test.ts`; component test |
| T2 | A builder who may decide approvals | A held action appears as a card saying what it would run with and why it waits, with Approve and Reject buttons; one click decides it through `POST /v1/approvals/{id}/decision`; the card then says who decided and that the customer is told | Component tests (approve, reject); browser run |
| T3 | Anyone | After a decision the customer's follow-up message appears in the conversation without a reload (fetched at once, not after the next poll) | Component test; browser run |
| T4 | A builder | If the action was decided somewhere else, or expired, the card stops offering buttons and says nothing ran from here: found at the click (the server answers 409) or within 2 seconds by checking which approvals are still pending | Component tests (409; expiry without a click) |
| T5 | Someone who may not decide approvals | The card shows no buttons and says who to ask | Component test |
| T6 | A builder | A failed decision shows the server's message and leaves the buttons so it can be tried again | Component test |
| T7 | A CX lead | The trace appears as numbered sentences ("Used issue refund (order_id 2077, amount 240).", "Held issue refund for a person: ..."), with the full event list one click away | `plainSteps` tests; browser run |

## Decision 204
The console does not adopt the assistant-ui library the design named. Cards and decisions were built with the components Studio already has; a library would add a dependency for one screen and a second set of styles. Revisit if a second screen needs the same pieces (the Workspace inbox in WP 3.4).

## Limits
- Tool cards come from the trace after the turn, so during a turn the console still shows the one-line "Using ..." status.
- Plain steps leave out internal events (model calls, memory, budgets); the full list is under "Every event".
- Expiry is noticed by polling every 2 seconds only while a card is waiting, and only for people who may read approvals.
