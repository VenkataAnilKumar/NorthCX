# NorthCX Agent Runtime

Status: Draft. Describes `src/core/runtime.ts` as scaffolded.

## Concepts
| Concept | Definition |
|---|---|
| Agent | `defineAgent({id, instructions, tools, guardrails, model, maxSteps})` |
| Tool | Zod-validated function with optional `requiresApproval` |
| Guardrail | Supervisor with `checkToolCall` and/or `checkReply` |
| Session | Message history identified by `sessionId` |
| Run | One user message processed to a final reply |
| Trace | Ordered event log for a run |

## Run loop
1. Load session history and customer facts; append the user message.
2. Build the system prompt: instructions, customer facts, handoff rule.
3. Call the model with tool specs plus the built-in `handoff_to_human` tool.
4. If the model returns text only: run reply guardrails. Allowed, return it. Rejected, append a supervisor message and retry (max 2 rewrites), then escalate.
5. If the model returns tool calls, for each call in order: record it; handoff ends the run as `escalated`; unknown tool or invalid input returns an error result; tool guardrails may block; `requiresApproval` stops the run as `needs_approval`; otherwise execute and return the result (errors are returned, not thrown).
6. Append tool results and loop. After `maxSteps`, escalate.
7. Save history and trace; return `{reply, status, traceId, pendingApprovals}`.

## Statuses
`completed`, `escalated`, `needs_approval`.

## Design rules
- The runtime depends only on the `LLM` interface; a scripted model is used in tests.
- Tool errors never crash a run; the model sees them and can recover.
- Blocking decisions always include a reason that is traced.
- Every exit path saves history and the trace.

## Known gaps
- Resuming after approval is not implemented.
- A blocked tool call is not retried with guidance beyond the error result.
- Parallel tool execution is sequential.
- Streaming responses are not supported.
