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
