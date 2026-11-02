# NorthCX Implementation Phases

Status: Draft

| Phase | Goal | Deliverables | Exit criteria |
|---|---|---|---|
| 1 | Working agent over HTTP | Runtime tests, server, widget, example support agent, approval resume | Example agent resolves, escalates and blocks correctly in tests |
| 2 | Safe to change | Simulation runner, CI gate, Postgres store | Failing scenario fails CI; state survives restart |
| 3 | Real channels and knowledge | Inbox adapter, retrieval tool, trace export | Email/messaging round trip; cited answers; traces in backend |
| 4 | Non-engineers | Studio, insights | CX user edits, tests and publishes an agent |
| 5 | Voice | Voice adapter | Live call resolves an intent |
| 6 | Hardening | Security review, docs, release | Threat model closed; v1.0 tagged |

## Dependencies
Phase 2 needs Phase 1 server and runtime tests. Phase 4 needs persistent agent definitions. Phase 5 needs streaming.
