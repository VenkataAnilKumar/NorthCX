# NorthCX Observability

Status: **Built**. Updated: 2026-11-09. Master for: traces, metrics, logs and export.

## Signals
- **Traces:** one per run; events for user, model, tool call/result, guardrail, approval, handoff, reply, error.
- **Metrics:** runs by status, resolution rate, escalation rate, guardrail blocks by name, tool error rate, model latency and tokens, cost per run.
- **Logs:** structured, no PII.

## Export
Trace events map to OpenTelemetry spans (run = root span, model/tool/guardrail = children), or to Langfuse traces, for an external backend; the built-in store remains the source of record.

## Metric definitions
See `01-product/NorthCX_Success-Metrics.md` for numerators, denominators and targets.

## Alerts (O9)
Planned list: error rate, model latency, escalation spikes, guardrail-block spikes, cost per run, approval queue age. Built: six default rules (error, escalation, guardrail blocks, tool errors, fallback-model calls, slow replies; below); cost per run and approval queue age are not alert rules yet.

## Search and tags (O10)
Filter conversations by intent, status, agent version, language, tag and date; reviewers tag failure causes, which feed failure analysis (O7).

## Insights (built in Phase 4)
Figures with numerators and denominators, a provisional resolution rate beside containment, failure reasons, intent gaps, ratings, tokens and estimated cost (below). Approval turnaround is not a figure yet.

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


## Insights, alerts and search — as built (O5, O6, O7, O9, O10)

**Metrics (O5, O6).** `GET /v1/insights/overview` computes from the recorded traces, hand-offs and ratings for a period (default last 7 days, at most 366) and an environment (default production), optionally for one agent. Each rate carries its **numerator, denominator and period**, as the success-metrics rules require. Figures: conversations and turns; containment (conversations that never reached a person); escalation, approval, guardrail-block, tool-error, error and fallback-model rates; reply time (median and 95th percentile of the time the platform took per turn); tokens and, if `NORTHCX_PRICE_PER_MILLION_TOKENS` is set, an estimated cost; hand-offs by trigger, queue and topic; tools used and failing; guardrails that blocked; and customer ratings. Containment is not a resolution rate: resolution needs an agreed definition of "resolved" for each intent, so the response says so. The time series (`hour` or `day` buckets) feeds the charts.

**Customer ratings.** `POST /v1/sessions/{id}/feedback` takes a 1-5 rating and an optional comment. A customer's chat token can rate only its own conversation; one rating per conversation, a second replaces the first. Ratings are erased with the conversation.

**Failure analysis and intent gaps (O7, O6).** `/insights/failures` ranks why turns went wrong (hand-off reason, a tool that failed, a guardrail that blocked) with example traces to open. `/insights/gaps` lists knowledge searches that found nothing and what customers said just before the agent handed them over (personal data masked), which is where a new article or a new tool would help.

**Alerts (O9).** Six default rules watch the last 15 minutes of production traffic: error rate above 10% (critical), escalation above 50%, guardrail blocks above 30%, tool errors above 20%, fallback-model calls above 20%, and 95th-percentile reply time above 30 s. A rule needs at least 20 samples to fire, reminds at most once per cooldown (60 min) while still breached, and clears itself on recovery. Each event is a monitoring finding (`alert:<rule>`, `alert_cleared:<rule>`) and, if configured, a signed webhook. Rules can be replaced with a file (`NORTHCX_ALERT_RULES`). `GET /v1/alerts` shows what is firing.

**Search and tagging (O10).** `GET /v1/conversations/search` finds conversations by words said by either side, status, hand-off, rating and tag; shown text is masked. Reviewers, developers and admins can tag conversations (for example `wrong-answer`, `needs-article`) and every tag change is audited. The Insights and Conversations pages in the console use these.

**Limits.** Each query reads at most the 20,000 most recent turns of the period (the response says when it was cut). Computation is on demand, not pre-aggregated, so very large deployments will want rollup tables. Reply time is the platform's own processing time per turn, not time to first token. Alert state is in memory and re-evaluates after a restart. Satisfaction has no survey flow of its own: the company's front end asks and posts the rating.

## Plain-language questions — as built (O8)

`POST /v1/insights/ask` with `{question, environment}` (role: anyone who can read insights; 15 questions a minute per key). Example: “Did containment improve compared with last week?”

- The model receives the question and the list of figure names, and replies with a small JSON query: `metric`, `days` (1–366), `offset_days`, `agent`, `compare`, `trend`. Anything not on the list — an unknown figure or agent, a period over a year, wrong types, extra instructions — is refused. The model never sees conversation data or results, and it does not write the answer.
- Figures: containment, escalation, approval, guardrail-block, tool-error, error and fallback-model rates; conversations, turns, hand-offs, tokens, tokens per conversation; median and slowest-5% response time; average rating and ratings received; estimated cost; and ranked breakdowns of hand-offs (by trigger, queue, topic), tool calls, tool errors and guardrail blocks. `compare` adds the period just before; `trend` adds a per-day (per-hour for up to two days) series for the figures that have one.
- The reply contains `answer` (a sentence built from the numbers), the figures, and `plan`, which Studio shows as “Read as: …” so a misreading is visible. Questions the list cannot answer return `answerable: false` with the list of what can be asked.
- **Filters.** A question can be limited to a subset of conversations: `language`, `channel` (web, sms, whatsapp, email, voice; recorded on each turn from now on, so older turns have none), `handed_off`, hand-off `queue`, and a rating range (`min_rating`, `max_rating`). Each is validated (a code or name pattern, a true/false, 1–5); the filter is applied to conversations before any figure is computed, and the answer sentence says which filters were used.
- **Finding conversations.** “Which escalated chats mentioned refunds this month?” becomes a conversation search (words, status, the same filters, period, agent), returning up to 10 conversations with masked first message and last reply and a link to each. It needs the permission to read conversations (`traces:read`); a key without it still gets figures. The model never sees the conversations and writes no summary of them.
- **Charts.** An answer with a trend carries the series and Studio draws a line chart; a ranked breakdown is drawn as bars with the numbers written out. Every chart has a table version behind it.
- Not covered: arbitrary groupings and cross-tabulations, tag filters in figures (tags work in conversation search), forecasts.
