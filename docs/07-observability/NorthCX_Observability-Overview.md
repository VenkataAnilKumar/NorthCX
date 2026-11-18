# NorthCX Observability and analytics: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** Seeing what agents do and how well: traces, metrics, analytics, alerts and monitoring, and reliability and cost.

## Built
- A trace for every run, exported to OpenTelemetry and Langfuse backends
- Metrics shown with numerator and denominator, including a provisional resolution rate; plain-language analytics questions with charts
- Alerts with delivery tracking; always-on monitoring of every turn; conversation search, tags and review with failure tagging
- Retries, fallback models, circuit breaker, timeouts and token budgets

## Gaps and next steps
- A firm resolution figure: a customer's return in a new conversation should count against it (design section 13)
- A proactive suggestions feed; session replay in Studio

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Observability.md`](NorthCX_Observability.md) | Traces, metrics, logs and export (master) |
| [`NorthCX_Reliability-and-Cost.md`](NorthCX_Reliability-and-Cost.md) | Failure handling, retries, budgets and cost |
