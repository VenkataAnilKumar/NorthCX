# NorthCX Guardrails and Supervisors

Status: Draft. Describes `src/core/guardrails.ts`.

## Interface
`Guardrail { name, checkToolCall?(call, ctx), checkReply?(reply, ctx) }` returning `{allow: true}` or `{allow: false, reason}`.

## Built-in guardrails
| Guardrail | Type | Behaviour |
|---|---|---|
| `noCardNumbers` | Rule | Denies replies containing a card-number-like digit sequence |
| `llmPolicy` | Model | A supervisor model judges the draft against written policies and returns JSON; unparseable output denies |

## Principles
1. **Fail closed.** Uncertain or malformed supervisor output blocks.
2. **Defence in depth.** Rules for exact patterns, a model for judgement, approval gates for high-impact actions.
3. **Explain every block.** Reasons are traced and fed back to the agent for rewrite.
4. **Bounded retries.** Two rewrites, then escalate.
5. **Cheaper supervisor model.** The supervisor may use a smaller model than the agent.

## Policy categories to cover
Personal data exposure, unauthorised commitments (refunds, discounts), unsupported claims, regulated advice, tone and brand, prompt-injection attempts.

## Gaps
Input-side checks, per-tool argument policies, rate limits, and a policy test suite are planned.
