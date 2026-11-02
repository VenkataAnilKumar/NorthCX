# NorthCX Observability

Status: Draft

## Signals
- **Traces:** one per run; events for user, model, tool call/result, guardrail, approval, handoff, reply, error.
- **Metrics:** runs by status, resolution rate, escalation rate, guardrail blocks by name, tool error rate, model latency and tokens, cost per run.
- **Logs:** structured, no PII.

## Export
Trace events map to OpenTelemetry spans (run = root span, model/tool/guardrail = children) for an external backend; the built-in store remains the source of record.

## Metric definitions
See `01-product/NorthCX_Success-Metrics.md` for numerators, denominators and targets.

## Alerts (O9)
Error rate, model latency, escalation spikes, guardrail-block spikes, cost per run, approval queue age.

## Search and tags (O10)
Filter conversations by intent, status, agent version, language, tag and date; reviewers tag failure causes, which feed failure analysis (O7).

## Insights (Phase 4)
Dashboards for resolution rate, top intents, failure reasons, approval turnaround, cost.

## Privacy
Redaction applies before export; access to traces is role-restricted.
