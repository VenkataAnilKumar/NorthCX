# NorthCX Observability

Status: Draft

## Signals
- **Traces:** one per run; events for user, model, tool call/result, guardrail, approval, handoff, reply, error.
- **Metrics:** runs by status, resolution rate, escalation rate, guardrail blocks by name, tool error rate, model latency and tokens, cost per run.
- **Logs:** structured, no PII.

## Export
Trace events map to OpenTelemetry spans (run = root span, model/tool/guardrail = children) for an external backend; the built-in store remains the source of record.

## Insights (Phase 4)
Dashboards for resolution rate, top intents, failure reasons, approval turnaround, cost.

## Privacy
Redaction applies before export; access to traces is role-restricted.
