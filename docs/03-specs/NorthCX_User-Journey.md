# NorthCX User Journeys

Status: **Partly built**. Updated: 2026-11-09. Master for: user journeys (J1 to J10 built; J11 to J15 designed). Each journey lists steps, what the user feels, risks and opportunities.

## J1. Customer: order refund (happy path)
| Step | Touchpoint | System | Risk / opportunity |
|---|---|---|---|
| 1 | "Refund order 1042" in chat | Message received | Detect language and intent |
| 2 | Agent looks up the order | Order tool | Verify identity first for account actions |
| 3 | Eligibility confirmed | Policy in instructions | Cite policy |
| 4 | Refund below limit executes | Refund tool | Idempotency prevents duplicates |
| 5 | Reply checked by supervisors | Guardrails | Rewrite or escalate if rejected |
| 6 | Customer receives confirmation | Channel | Offer follow-up help |
Outcome: resolved; trace stored; metrics updated.

## J2. Customer: refund above the approval limit
1. Steps 1-3 as J1.
2. The refund rule holds the action; the run ends `needs_approval`; the customer is told a teammate will confirm and when.
3. Reviewer sees payload and context, approves.
4. The action executes once and the conversation resumes with the result; the customer is notified on the original channel.
Risk: customer waits. Opportunity: set expectations, expire and escalate stale approvals.

## J3. Customer: asks for a person
1. Customer asks, or a forced-handoff topic is detected.
2. Agent hands off with reason; customer told what happens next.
3. Inbox receives the full package; a support agent picks it up with no repeated questions.
4. Optionally the remainder returns to the agent.

## J4. Customer: email and messaging
Email thread maps to a session; replies stay in-thread; attachments are passed to the agent. Messaging follows opt-in and template rules. Handoff routes to the same inbox.

## J5. Customer: phone call
Call connects; the agent announces it is automated and obtains consent where required; speech in, speech out with barge-in; spoken confirmation before actions; DTMF fallback; handoff to a phone queue with the summary.

## J6. Developer: build and release an agent
1. Start from a template; define instructions and tools.
2. Write scenarios, including policy violations.
3. Run locally with a scripted model; then against a live model.
4. Open a pull request; CI runs required scenarios.
5. Promote to staging; then production with reviewer approval and staged rollout.
6. Watch traces and metrics; roll back if needed.

## J7. CX lead: tune from failures
1. Insights show a falling resolution rate on one intent.
2. Open failed conversations and tag the cause (missing policy, tool result, tone).
3. Edit instructions in Studio; run simulations; compare with the last release.
4. Publish to 10%; metrics improve; promote.

## J8. Compliance owner: audit
1. Request the audit log for a period.
2. Trace a disputed refund: who approved, what the agent saw, what it did.
3. Confirm retention and redaction settings; export evidence.

## J9. Reviewer: approval queue
List pending items by age and risk; open one; read payload and context; approve or reject with a note; see the downstream result.

## J10. Administrator: deploy and operate
Provision database and containers; set secrets and keys; configure roles; run health checks; set retention; upgrade with a prior-version fallback.

## After 1.0: Workspace journeys (designed, not built)
## J11. Support agent: work a hand-off with an assistant
1. Jo opens **Work > Inbox**; "Needs me" shows 3 conversations with the agent's summary.
2. She opens one; the customer panel shows masked facts; the Library suggests the refund policy.
3. She asks the care copilot in the side panel for a reply; the draft opens in the composer.
4. She edits it, sends it herself, and resolves with a note. The note and her name are audited.
5. If the copilot said "I could not find a source", the reply says so and she checks the Library.

## J12. Support agent: research a pattern in the Pilot
1. Jo opens **Pilot**, picks the escalation analyst, a space and Research.
2. The assistant asks which period and which channels; she answers with chips.
3. It writes a four-step plan with time, cost and the model tier; she approves it.
4. She works elsewhere; the run continues in the background and notifies her when done.
5. The Result tab shows a cited summary; she saves it to Outputs, shares it with the team, and turns it into a weekly automation draft.

## J13. Reviewer: decide an approval
1. A badge shows 2 approvals on **Work**. Rae opens **Approvals**.
2. She reads the exact refund, the customer context and why it needs a person.
3. She approves with a note; the conversation resumes once; the item moves to decided.

## J14. Team lead: weekly review
1. Tess opens **Team > Performance** and reads her team's figures with denominators.
2. In **Quality** she opens a low-scored sample, attaches a coaching note, and calibrates a score with another reviewer.
3. She starts a weekly automation from last week's result; a reviewer publishes it.

## J15. Administrator: set what assistants may do
1. Ari opens **Agent Hub**, installs the staff assistant for the billing team, fills its details, checks requirements, runs its scenarios.
2. A draft is created in Staging; release follows the normal rules. Nothing is live from the hub.
3. He sets who may use it and what it may see, and sets the model rule so sensitive conversations stay private.
