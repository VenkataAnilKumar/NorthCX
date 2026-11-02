# NorthCX Reliability and Cost

Status: Draft. Targets are proposals to validate with load and pilot data.

## Failure modes and handling
| Failure | Handling |
|---|---|
| Model call error or timeout | Retry with backoff (bounded); then escalate to a human; error traced. Escalation on first failure is implemented. |
| Model rate limit | Queue or shed load; return a graceful message; alert |
| Provider outage | Fallback model through the `LLM` interface (planned) |
| Tool timeout or error | Error returned to the model; one retry for idempotent reads |
| Supervisor error | Treated as a denial (implemented) |
| Store unavailable | Fail the request with a clear error; do not answer without history |

## Planned reliability features
Model fallback and retries (R5), streaming (R6), cost budgets (R7), idempotent writes (T4), approval expiry, and queue-based processing for channels with delayed replies.

## Targets (to validate)
| Metric | Proposal |
|---|---|
| Chat first-token latency (p95) | Set after streaming exists |
| Chat full-reply latency (p95) | Set after pilot |
| API availability | 99.9% for self-hosted reference deployment |
| Escalation on failure | 100% of failed runs reach a human path |

## Cost controls
- Step limit per run (`maxSteps`) and rewrite limit (2).
- Per-conversation token budget; escalate when exceeded (planned).
- Cheaper supervisor model; shorter history via summarisation (planned).
- Cost per run recorded in traces and reported in Insights.

## Capacity
Stateless runtime workers scale horizontally; state lives in the store. Concurrency limits per customer and per API key.


## As built

- **Retries:** timeouts, dropped connections, 408/409/425/429 and 5xx (including provider overload) are retried with exponential back-off and jitter (default 2 retries, capped delay). Bad requests and authentication errors are raised immediately, because another attempt or model cannot fix them.
- **Fallback models:** `NORTHCX_MODEL_FALLBACKS` lists models tried in order after the main model's retries are used up. Each answer records which model served it and whether it was a fallback (trace `llm` events).
- **Circuit breaker:** after three consecutive failures a model is skipped for 30 seconds so an outage costs one fast fallback instead of a slow failure on every turn. The last model in the chain is always tried.
- **Timeout:** each model call is limited (default 60 s) so a hung connection cannot hold a conversation.
- **Budgets:** an agent spec may set `max_run_tokens` (1,000 to 5,000,000); a turn that reaches it stops and is handed to a person. `NORTHCX_DAILY_TOKEN_BUDGET` stops all model calls for the rest of the UTC day and hands conversations to people. Both are recorded as `budget` trace events and escalate with trigger `budget_exceeded`. Token counts come from the provider's usage report.
- **Limits:** the daily count is per server process and resets at restart; with several servers each enforces the cap separately. There is no per-customer or per-dollar budget yet, and streaming is not built.
