# NorthCX Agent Capability Matrix

Status: Draft

| Capability | Mechanism | Phase | State |
|---|---|---|---|
| Natural-language goals and policies | Agent instructions | 1 | Built |
| Typed actions | Tools with Zod schemas | 1 | Built |
| Approval for sensitive actions | `requiresApproval` | 1 | Built and tested; stored in memory; resume is Phase 2 |
| Reply and action supervision | Guardrails | 1 | Built and tested |
| Human handoff | `handoff_to_human` | 1 | Built |
| Traces | Trace store | 1 | Built (in-memory/JSONL) |
| Session memory | `MemoryStore` | 1 | Built (in-memory) |
| Customer facts | `MemoryStore` facts | 1 | Built |
| Chat API | HTTP server | 1 | Planned |
| Simulation testing | Scenario runner | 2 | Planned |
| Persistent memory | Postgres adapter | 2 | Planned |
| Knowledge retrieval | Retrieval tool | 3 | Planned |
| Email/SMS/messaging | Inbox adapter | 3 | Planned |
| Trace export | OpenTelemetry | 3 | Planned |
| Studio | Definition editor | 4 | Planned |
| Insights | Metrics from traces | 4 | Planned |
| Voice | Voice adapter | 5 | Planned |
