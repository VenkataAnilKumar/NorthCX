# NorthCX Data Flow

Status: **Built**. Updated: 2026-11-09. Master for: where data goes during a conversation.

```
Customer -> Channel adapter (web, email, SMS, WhatsApp, Telegram, voice bridge)
   -> POST /v1/agents/{id}/chat (or /chat/stream)
   -> Input checks (masking, injection, abuse, forced topics)
   -> Runtime.run
        -> Memory store (history, facts) and memory service (long-term memories)
        -> Customer context from the company's systems (optional)
        -> Knowledge search (passages with citations; optional embeddings service)
        -> Model (LLM interface: Claude, through the SDK or HTTPS)
        -> Tools and connectors -> Customer systems (orders, billing)
        -> Guardrails (tool call, tool output, reply)
        -> Trace store, audit log, outbox
   <- reply, status, trace id
   -> Status events (signed webhook), hand-off delivery to the helpdesk, trace export (optional)
```

## Additional flows
- **Approval:** pending approval stored with the exact call, reviewer decides, the call runs once, the conversation resumes, audit entry written.
- **Release:** version created, simulations run, release recorded per environment, staged rollout share applied.
- **Export:** traces redacted (none, masked or full; sampled) then sent to the external backend.
- **Attachments:** checked by content and size, optionally scanned, stored with the conversation; PDFs can be sent as masked text.
- **Deletion:** a privacy request removes history, facts, memories, attachments and traces for a customer.
- **Residency:** every outbound destination is checked against the residency policy at start-up; the residency report lists what each receives.

## Data classes
| Data | Where | Sensitivity | Retention |
|---|---|---|---|
| Messages | Memory store (Postgres) | High (may contain PII) | Configurable |
| Customer facts | Memory store | High | Until deletion request |
| Long-term memories | Memory service | High | Until deletion request (not aged out by retention) |
| Attachments | Attachment store | High | With the conversation |
| Knowledge | Knowledge store | Company content | Until removed |
| Traces | Trace store | High (include tool I/O) | Configurable; redactable |
| Tool outputs | Trace, model context | High | As traces |
| Audit log | Audit store (hash-chained) | Medium (no message text) | Append-only; kept (customer references are one-way) |
| Status events | Outbox and webhook | Low (no message text) | Until delivered |
| Model prompts | Sent to the model provider | High | Per provider terms |

## Rules
- Redact known PII patterns in traces before export.
- Tools return only fields the agent needs; tool output is screened before the model reads it.
- Pending approvals include the exact call payload.
- Events and audit entries never carry message text.

## After 1.0
Staff assistants, spaces, outputs and personal memory add new flows; they are described in `../13-workspace/NorthCX_Staff-Platform-Architecture.md` (designed, not built).
