# NorthCX Reliability and Cost

Status: **Built**. Updated: 2026-11-09. Master for: failure handling, retries, budgets and cost. Targets are proposals to validate with load and pilot data.

## Failure modes and handling
| Failure | Handling |
|---|---|
| Model call error or timeout | Retry with backoff (bounded), then fallback models, then escalate to a human; error traced (built) |
| Model rate limit | Queue or shed load; return a graceful message; alert |
| Provider outage | Fallback models and a circuit breaker (built); fallback across providers is planned (E1) |
| Tool timeout or error | Error returned to the model; one retry for idempotent reads |
| Supervisor error | Treated as a denial (built) |
| Store unavailable | Fail the request with a clear error; do not answer without history |

## Reliability features
Built: model fallback and retries (R5), streaming (R6), token budgets (R7), idempotent writes (T4), approval expiry, and an outbox with retries for replies sent outside a request. Planned: budgets in currency and per team (E1).

## Targets (to validate)
| Metric | Proposal |
|---|---|
| Chat first-token latency (p95) | Set after a baseline with a real model (streaming is built) |
| Chat full-reply latency (p95) | Set after pilot |
| API availability | 99.9% for self-hosted reference deployment |
| Escalation on failure | 100% of failed runs reach a human path |

## Cost controls
- Step limit per run (`max_steps`) and rewrite limit (2).
- Token budget per turn and per day; escalate when exceeded (built).
- Cheaper supervisor model and summaries; shorter history via summarisation (built).
- Tokens per run recorded in traces; estimated cost reported in Insights.

## Capacity
Several server processes with roles (`api`, `worker`) share state through Postgres; background jobs are leased to one process at a time. Rate limits per key, session, address and conversation; shared across processes with the Postgres limits backend.


## As built

- **Retries:** timeouts, dropped connections, 408/409/425/429 and 5xx (including provider overload) are retried with exponential back-off and jitter (default 2 retries, capped delay). Bad requests and authentication errors are raised immediately, because another attempt or model cannot fix them.
- **Fallback models:** `NORTHCX_MODEL_FALLBACKS` lists models tried in order after the main model's retries are used up. Each answer records which model served it and whether it was a fallback (trace `llm` events).
- **Circuit breaker:** after three consecutive failures a model is skipped for 30 seconds so an outage costs one fast fallback instead of a slow failure on every turn. The last model in the chain is always tried.
- **Timeout:** each model call is limited (default 60 s) so a hung connection cannot hold a conversation.
- **Budgets:** an agent spec may set `max_run_tokens` (1,000 to 5,000,000); a turn that reaches it stops and is handed to a person. `NORTHCX_DAILY_TOKEN_BUDGET` stops all model calls for the rest of the UTC day and hands conversations to people. Both are recorded as `budget` trace events and escalate with trigger `budget_exceeded`. Token counts come from the provider's usage report.
- **Limits:** the daily count is per server process unless `NORTHCX_LIMITS_BACKEND=postgres` is set, in which case all processes share it (`usage_ledger`, built). There is no per-customer or per-currency budget yet.

### Write safety

- Every tool call receives a stable `idempotency_key` (unique to that call in that turn); tools that call external systems should pass it on so a retry cannot duplicate the action. Approved actions keep using the approval id.
- If the model repeats an identical write call within one turn, the platform answers from the first result and does not execute it again (trace event `duplicate_call`). A later turn is a new, intentional action.
- Read tools are retried once on error; write tools are never retried automatically.
- API clients should send `Idempotency-Key` on chat requests that they may retry (see API Design).

### Long conversations (summarisation)

When a conversation's saved history passes `NORTHCX_SUMMARIZE_AFTER_TOKENS` (estimated at four characters per token), the part before the last four customer messages is replaced by short notes written by the model (at most 3,000 characters, optionally by a cheaper `NORTHCX_SUMMARY_MODEL`). The notes sit at the front of the first kept customer message inside `[summary]` markers, so roles still alternate and no tool call is separated from its result. The notes are told to record order numbers, amounts and promises exactly, to treat the conversation as data and to leave out credentials. Later summaries fold earlier ones in. If the summary cannot be written (model error, empty or no smaller), the full history is kept. Redaction runs on the saved history as usual, and a `summary` trace event records the sizes. Hand-off packages show the notes to the person as "Earlier in this conversation" followed by the recent turns; the original early turns remain in the conversation's traces until erased or aged out. Simulation (dry) runs never summarise.
