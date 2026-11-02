# NorthCX Guardrails and Supervisors

Status: Draft. Describes behaviour implemented in the TypeScript prototype (`src/prototype/src/core/guardrails.ts`); the Python backend must match it.

## Interface
`Guardrail { name, checkToolCall?(call, ctx), checkReply?(reply, ctx) }` returning `{allow: true}` or `{allow: false, reason}`.

## Built-in guardrails
| Guardrail | Type | Behaviour |
|---|---|---|
| `noCardNumbers` | Rule | Denies replies containing a 13-19 digit sequence that passes the Luhn check, so order and tracking numbers are not blocked |
| `llmPolicy` | Model | A supervisor model judges the draft against written policies and returns JSON; unparseable output denies |

## Principles
1. **Fail closed.** Uncertain or malformed supervisor output blocks, and so does a supervisor that throws.
2. **Defence in depth.** Rules for exact patterns, a model for judgement, approval gates for high-impact actions.
3. **Explain every block.** Reasons are traced and fed back to the agent for rewrite.
4. **Bounded retries.** Two rewrites, then escalate.
5. **Cheaper supervisor model.** The supervisor may use a smaller model than the agent.

## Policy categories to cover
Personal data exposure, unauthorised commitments (refunds, discounts), unsupported claims, regulated advice, tone and brand, prompt-injection attempts.

## Planned extensions (S7-S11)
- **Forced-handoff topics (built, Phase 2):** a list in the agent spec (name, case-insensitive regular expressions, optional reply). A customer message that matches any topic goes straight to a person: the model is never called, the match is traced (`forced_topic`), and the handoff records which topics matched. Platform-written notices are not checked. Matching is deterministic and blunt: patterns need word boundaries to avoid false hits ("issue" contains "sue"), a false positive costs a human visit rather than a wrong answer, and patterns are limited to 300 characters. Model-based topic detection is a later option.
- **Input checks (Phase 3):** injection and abuse detection on customer messages and tool output.
- **PII detection and redaction (Phase 3):** in replies and in exported traces.
- **Full coverage monitoring (Phase 3):** every conversation scored, not a sample.
- **Policy library (Phase 3):** reusable policies, each with passing and blocking scenarios.
- **Per-tool argument policies:** limits such as maximum amounts by customer tier.
