# NorthCX User Journeys

Status: Draft

## 1. Customer: order refund (happy path)
1. Customer opens web chat: "I want a refund for order 1042."
2. Agent calls `lookup_order`; confirms the order and eligibility.
3. Amount is below the approval threshold, so `issue_refund` runs.
4. Reply guardrails pass; agent confirms the refund.
5. Trace saved, status `completed`.

## 2. Customer: refund above threshold
1-2. As above.
3. `requiresApproval` returns a reason; the run stops (`needs_approval`).
4. Customer is told a teammate will confirm.
5. Approver sees the pending call and decides.

## 3. Customer: needs a person
1. Customer asks for a human, or the agent cannot resolve.
2. Agent calls `handoff_to_human` with a reason.
3. Human inbox receives the conversation with transcript; status `escalated`.

## 4. Platform engineer: ship an agent change
1. Edit instructions or a tool.
2. Run simulations locally; fix failures.
3. CI runs the suite on the pull request; merge gated on pass.
4. Deploy; watch traces for guardrail hits.

## 5. CX lead: tune from failures
1. Open the failed conversation trace.
2. Identify the missing policy or tool result.
3. Update instructions (Studio or code), re-run simulations, publish.
