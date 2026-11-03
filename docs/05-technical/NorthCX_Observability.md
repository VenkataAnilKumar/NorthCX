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


## Trace export — as built (O3, O4)

Finished conversation turns are queued and sent to an external observability backend in the background, with retries (30 s doubling to one hour, 12 attempts); a slow or failing backend never slows or breaks a conversation. Simulation runs are not exported.

**Destinations.** `NORTHCX_LANGFUSE_URL` with public and secret keys sends each trace to Langfuse's ingestion API as a trace with generations (model calls, with model and token count), spans (tool calls, with input and output) and events (guardrail hits, approvals, hand-offs, summaries, errors). `NORTHCX_OTLP_ENDPOINT` sends the same tree as OpenTelemetry spans over OTLP/HTTP JSON (`/v1/traces`) to any compatible backend, with optional headers. Either or both can be on; each is tracked and retried separately.

**What is sent (`NORTHCX_TRACE_EXPORT_CONTENT`).**
- `none`: structure only. Names of agents and tools, outcomes, counts, tokens, model, guardrail names and status. No message text, tool inputs or outputs, error text or guardrail reasons.
- `masked` (default): the above plus message, reply, tool input and output text, truncated to 2,000 characters, with email addresses, phone numbers, US social security numbers and payment card numbers masked. Configured secrets were already removed when the trace was saved.
- `full`: text kept as stored (secrets still removed), truncated to 20,000 characters. Use only where the backend is trusted with customer data.
The customer's id is never sent; conversations are identified by their random session id. `NORTHCX_TRACE_EXPORT_SAMPLE` exports a deterministic fraction of traces (the same trace is always in or out); `NORTHCX_ENVIRONMENT` labels them (`production`, `staging`).

**Visibility.** `GET /v1/trace-export` shows the configuration and delivery counts; `GET /v1/traces/{id}/exports` shows one trace's deliveries.

**Limits.** Exports are one-way (nothing is read back), per-turn rather than per-conversation, masking is pattern-based (names and free-form addresses are not detected), erasing a customer removes queued exports but cannot recall what a backend already holds, and the Langfuse and OTLP payloads are tested against simulated servers, not live ones.
