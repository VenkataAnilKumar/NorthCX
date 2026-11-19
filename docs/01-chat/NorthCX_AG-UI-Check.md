# AG-UI check (WP 3.1)

Status: stage 1 (research) of Phase 3. Written 2026-11-19. **Directional, not verified against the specification text.** `docs.ag-ui.com` could not be reached from the build environment (name not resolved); what follows comes from the project's GitHub page (MIT licence) and from search summaries of the draft specification pages. Before WP 3.2 starts, someone with access reads the pages named at the end and corrects this file.

## What the sources say
- Events are typed and streamed (run start and finish, text message start, content and end, tool call start, arguments, end and result, state, steps, custom).
- A run that needs outside input ends with `RUN_FINISHED` whose outcome is `interrupt`, carrying one or more interrupts. Each has an `id` unique within the run and an open-string `reason` (not a fixed list).
- The client starts a new run on the same thread; its input carries a `resume` array. Each entry names the `interruptId` it answers. One `resume` array must answer every open interrupt (no partial resumes). A thread with an open interrupt rejects new input without `resume`.
- The spec is a draft. The sources disagree on the wire shape: one shows a single `interrupt` object beside `outcome: "interrupt"`, another an `outcome.interrupts` array. Older agents used a custom `on_interrupt` event.

## What differs from our design (`NorthCX_Agent-Platform-Design.md`, section on Chat)
| Design said | Found | Consequence |
|---|---|---|
| A held action ends the run with an `interrupt` outcome | Matches the sources in outline | Keep |
| The interrupt reason is `tool_call` | `reason` is an open string, so a NorthCX value is allowed; the exact value is ours to choose | Use `approval_required`; record it in the endpoint's documentation |
| Resume is a new run carrying `resume` | Matches, but one `resume` must cover every open interrupt | An approval request with several held actions in one turn needs one answer for all of them, or the adapter must refuse a partial `resume` with a clear error |
| (not in the design) | Wire shape of the outcome differs between sources | Do not hard-code either until the spec page is read; write the adapter against one function that builds the finish event, covered by a test |

## What differs from how NorthCX works today
These are facts from our code, and they matter more than the spec details:
1. **The customer does not decide.** A held action is decided by staff through `POST /v1/approvals/{id}/decision`; the customer's turn ends with `pendingApprovals`. AG-UI's resume model fits only the staff surfaces (the Studio test console, the Workspace inbox), where the person at the keyboard is the approver. On the customer widget an interrupt is shown as "waiting for a person", with no resume from the customer.
2. **Our approval resumes the run on the server**, inside `flow.resolve`, and returns the follow-up reply. An AG-UI `resume` run would have to call the same code and return its events, so the decision is made once, audited once, and the tool runs once (the existing "approve twice" protection must apply to a repeated `resume`).
3. **Our stream is not token streaming.** The existing endpoint runs the whole turn and then cuts the reply into pieces (`delta`). AG-UI's text events can carry the same pieces. Real token streaming is a separate, larger change (the provider layer would have to yield tokens); it is not in the plan, and this check does not assume it.
4. **Idempotency:** the chat endpoint takes an `Idempotency-Key`; a `resume` must too, or a retry would run the tool twice.

## Requirements this adds to WP 3.2
| # | For | Requirement | Check |
|---|---|---|---|
| A1 | A staff tester in the console | A held action arrives as an interrupt with an id, the tool name, the arguments (masked) and the approval id | Contract test |
| A2 | A staff tester | Sending `resume` with approve or reject runs the same decision code as `POST /v1/approvals/{id}/decision` | Test: same audit entries and result as the REST path |
| A3 | Anyone | A repeated `resume`, or one that answers only some open interrupts, or an unknown interrupt id, is refused with a message saying what to send | Tests |
| A4 | Anyone | A `resume` from a customer token is refused (403); decision 203 | Test |
| A5 | Any client | The same run gives the same text and the same tool calls over the existing stream and over AG-UI | Replay test comparing both |

## To confirm from the specification (needs `docs.ag-ui.com`)
1. The exact field names of the finish event's outcome and its interrupts (`interrupt` object or `interrupts` array).
2. The exact name and shape of `resume` entries (`interruptId`, and what carries the answer).
3. Whether the thread must be the same and whether `runId` must change.
4. The event names and fields for text messages and tool calls in the version we will pin.
5. Whether the project publishes a JSON Schema we can test against; if so, validate the adapter's events against it in the contract test.

Sources: https://github.com/ag-ui-protocol/ag-ui (MIT); draft pages named by search results: `docs.ag-ui.com/concepts/interrupts`, `docs.ag-ui.com/spec/draft/basic/patterns/interrupt-resume`, `docs.ag-ui.com/spec/draft/events/lifecycle`, `docs.ag-ui.com/spec/draft/basic/run-input`.
