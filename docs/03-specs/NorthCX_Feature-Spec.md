# NorthCX Feature Spec

Status: Draft. Maps to PRD requirement IDs.

## F1. Agent definition (R1)
`defineAgent({ id, instructions, tools, guardrails, model, maxSteps })`. Instructions state goals and policies in natural language. Defaults: `maxSteps` 8.

## F2. Tools (R2)
`tool({ name, description, input (Zod), run, requiresApproval })`. Input is validated before running; invalid input and thrown errors are returned to the model as error results. The JSON schema sent to the model is generated from the Zod schema.

## F3. Supervision (R3)
Guardrails check each tool call (`checkToolCall`) and each draft reply (`checkReply`). Verdict is allow or deny with a reason. A denied reply is rewritten up to twice, then the conversation is escalated. An LLM supervisor that returns unparseable output denies (fails closed).

## F4. Approvals (R4)
A tool may return a reason from `requiresApproval`. The run stops with status `needs_approval`, lists the pending call, and the customer is told a teammate will confirm. Resuming after approval is a Phase 1 follow-up.

## F5. Handoff (R5)
A built-in `handoff_to_human` tool ends the run with status `escalated` and records the reason in the trace.

## F6. Traces (R6)
Each run records user, model, tool call, tool result, guardrail, approval, handoff, reply and error events with timestamps. Exposed through the API by trace ID.

## F7. Chat API and widget (R7)
`POST /v1/agents/:id/chat {sessionId, message, customerId?}` returns `{reply, status, traceId}`. `GET /v1/traces/:id` returns the trace. Optional bearer-token auth. A minimal web widget is served at `/`.

## F8. Simulations (R8)
A scenario has scripted user turns and expectations: tools called or not called, final status, reply text, and an optional judge-model rubric. Runs in CI with a deterministic scripted model or against Claude.

## F9. Memory (R9)
`MemoryStore` holds session messages and per-customer facts. Facts are injected into the system prompt. Adapters: in-memory, Postgres, Mem0.

## F10. Knowledge (R10)
A retrieval tool queries an external knowledge service (Onyx) and returns passages with sources.

## F11. Channels (R11) and voice (R14)
Chatwoot webhooks route incoming messages to the API and post replies back. Voice runs through Pipecat calling the same API.

## F12. Studio (R13) and insights (R15)
Low-code builder over the agent definition format; dashboards for resolution rate, escalations, guardrail hits, tool errors.

## Acceptance
Each feature has simulation or unit tests before it is marked done.
