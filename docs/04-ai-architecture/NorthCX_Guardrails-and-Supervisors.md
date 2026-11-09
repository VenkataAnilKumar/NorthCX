# NorthCX Guardrails and Supervisors

Status: **Built**. Updated: 2026-11-09. Master for: guardrails and supervisors. Describes the guardrails in the Python backend (`src/backend/northcx/guardrails.py` and `northcx/safety/`). The TypeScript prototype has the same two original guardrails as a reference.

## Interface
`Guardrail` (`guardrails.py`) checks a tool call and/or a draft reply and returns a `Verdict` (allowed, or denied with a reason). `InputGuardrail` checks the customer's message before the model sees it; `OutputGuardrail` checks what a tool returned before the model sees it.

## Built-in guardrails
| Guardrail | Type | Behaviour |
|---|---|---|
| `NoCardNumbers` | Rule | Denies replies containing a 13-19 digit sequence that passes the Luhn check, so order and tracking numbers are not blocked |
| `LLMPolicy` | Model | A supervisor model judges the draft against written policies and returns JSON; unparseable output denies |
| `PromptInjection` | Input (`safety/prompt_injection.py`) | A deliberately blunt first-line screen for messages that try to take over the agent; approvals, tool policies, scopes and supervisors are the real controls |
| `PIIDetection` | Input (`safety/pii.py`) | Detects personal data in customer input and in exported traces |
| `AbuseDetection` | Input (`safety/abuse.py`) | Abusive language, threats, repeated messages and bursts; a threat goes to a person at once |
| `ToolOutputInjection`, `ToolOutputPII` | Output (`safety/tool_output.py`) | Treat what a tool returned as untrusted: flag injected instructions and mask personal data |

## Principles
1. **Fail closed.** Uncertain or malformed supervisor output blocks, and so does a supervisor that throws.
2. **Defence in depth.** Rules for exact patterns, a model for judgement, approval gates for high-impact actions.
3. **Explain every block.** Reasons are traced and fed back to the agent for rewrite.
4. **Bounded retries.** Two rewrites, then escalate.
5. **Cheaper supervisor model.** The supervisor may use a smaller model than the agent.

## Policy categories to cover
Personal data exposure, unauthorised commitments (refunds, discounts), unsupported claims, regulated advice, tone and brand, prompt-injection attempts.

## Extensions (S7-S11), all built
- **Forced-handoff topics (built, Phase 2):** a list in the agent spec (name, case-insensitive regular expressions, optional reply). A customer message that matches any topic goes straight to a person: the model is never called, the match is traced (`forced_topic`), and the handoff records which topics matched. Platform-written notices are not checked. Matching is deterministic and blunt: patterns need word boundaries to avoid false hits ("issue" contains "sue"), a false positive costs a human visit rather than a wrong answer, and patterns are limited to 300 characters. Model-based topic detection is a later option.
- **Input checks (built):** injection screening and abuse detection on customer messages, and screening of tool output. See "Abuse detection" below.
- **PII detection and redaction (built):** masking or refusing personal data in customer input and tool results, in exported traces, conversation search and drafts; replies are covered by the `no_personal_data_in_reply` policy and the card-number rule.
- **Full coverage monitoring (built):** deterministic rules on every turn, findings, a Monitoring page and alerts.
- **Policy library (built):** five configurable policies (`tool_limit`, `forbidden_phrases`, `required_phrase`, `no_personal_data_in_reply`, `max_reply_length`), each with allow and block cases run in CI.
- **Per-tool argument policies (built in part):** `tool_limit` caps a numeric field (for example refunds above 500); limits that differ by customer tier are done with tool scopes (T6) or approval rules, not with one policy.

## Abuse detection (S8) — as built
Add `abuse_detection` to an agent's `input_guardrails` (optionally with `config`). It reads the conversation itself, so it stores nothing:

| What it notices | What happens |
|---|---|
| A threat of violence | The conversation goes to a person at once (trigger `abuse`), with a calm line, and the model is not called |
| Abusive language | The first messages are answered normally; the agent is told for that turn to stay calm, not match the tone, say what it can help with and offer a person. From the third abusive message in the conversation (`max_strikes`, default 3) it goes to a person |
| The same message sent again and again | After `repeat_limit` (default 3) the agent is told not to repeat itself and to offer a person; after twice that, it goes to a person |
| A burst of messages | More than `burst_limit` (default 8) in `burst_seconds` (default 60) gets a polite "please slow down" reply without calling the model; nothing is handed off |

Settings: `max_strikes`, `repeat_limit`, `burst_limit`, `burst_seconds`, `extra_terms` (your own words or phrases, at most 200), and `hand_off: false` to only warn the agent and never hand off. Each noticing is recorded in the trace as an `abuse` event (kinds and strike count, never counted as a guardrail block) and sent as the `conversation.abuse` status event.

**Honest limits.** It is a short word list and a few patterns: it misses subtle abuse, sarcasm and other languages unless you add terms, and it cannot judge tone, so it is deliberately cautious about handing off (ordinary anger such as "I'm furious" is not abuse). The burst counter is kept per server process. The shipped templates do not include it; add it where your channels attract abuse.
