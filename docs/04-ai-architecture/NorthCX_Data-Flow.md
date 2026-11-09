# NorthCX Data Flow

Status: **Built**. Updated: 2026-11-09. Master for: where data goes during a conversation.

```
Customer -> Channel adapter -> POST /v1/agents/:id/chat
   -> Runtime.run
        -> MemoryStore (history, facts)
        -> Model (LLM interface)
        -> Tools -> Customer systems (orders, billing)
        -> Guardrails (tool + reply)
        -> Trace store
   <- {reply, status, traceId}
```

## Additional flows
- **Approval:** pending approval stored, reviewer decides, run resumes, audit entry written.
- **Release:** version created, simulations run, promotion recorded, traffic split applied.
- **Export:** traces redacted then sent to the external backend.
- **Deletion:** request removes history, facts and traces for a customer.

## Data classes
| Data | Where | Sensitivity | Retention |
|---|---|---|---|
| Messages | Memory store | High (may contain PII) | Configurable |
| Customer facts | Memory store | High | Until deletion request |
| Traces | Trace store | High (include tool I/O) | Configurable; redactable |
| Tool outputs | Trace, model context | High | As traces |
| Model prompts | Sent to the model provider | High | Per provider terms |

## Rules
- Redact known PII patterns in traces before export.
- Tools return only fields the agent needs.
- Pending approvals include the exact call payload.
