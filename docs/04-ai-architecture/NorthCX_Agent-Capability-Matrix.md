# NorthCX Agent Capability Matrix

Status: Draft. Summary of the Feature Catalog by capability. State: Built / Planned.

| Capability | Mechanism | Catalog | Phase | State |
|---|---|---|---|---|
| Goals and policies in natural language | Agent instructions | A1 | 1 | Built |
| Agents as code | Definition files | A2 | 1 | Built |
| Skills, journeys, templates | Definition format | A3-A7 | 3-4 | Planned |
| Draft agents from procedures | Generation | A8 | 6 | Planned |
| Multi-step tool use | Runtime loop | R1 | 1 | Built |
| Resume after approval | Approval flow + runtime | R10 | 2 | Built and tested |
| Fallback, streaming, budgets | Runtime | R5-R7 | 3 | Planned |
| Multilingual | Detection + prompts | R9 | 4 | Planned |
| Multi-agent routing | Orchestrator | R8 | 5 | Planned |
| Typed actions | Tools | T1-T3 | 1 | Built and tested |
| Secrets, dry-run, scopes, connectors | Tools | T4-T8 | 2-3 | Planned |
| Reply and tool supervision | Guardrails | S1-S6 | 1 | Built and tested |
| Forced handoff | Topic list in the agent spec | S7 | 2 | Built and tested |
| Input checks (injection, PII) | Input guardrails | S8, S9 | 3 | Early version built; tool-output checks and redaction in traces planned |
| Full monitoring, policy library | Guardrails | S10, S11 | 3 | Planned |
| Handoff and approvals | Runtime + API | H1-H3 | 1 | Built and tested |
| Handoff package and queue | Handoff service | H4 | 2 | Built and tested |
| Inbox integration, hours and routing, assist, return to agent | Handoff service | H5-H8 | 3-5 | Planned |
| Chat API and widget | Server | C1, C2 | 1 | Built and tested |
| Email, messaging, voice, SDK | Adapters | C3-C10 | 3-5 | Planned |
| Session memory and facts | MemoryStore | K1, K2 | 1 | Built (in memory) |
| Persistence | Postgres stores | K3 | 2 | Built and tested |
| Retrieval, lifecycle | Stores and tools | K4-K8 | 3 | Planned |
| Unit tests | Scripted model | Q1 | 1 | Built |
| Scenario simulations, judge, CI step, stored runs, gate rule | Simulation runner and service | Q2-Q4 | 2 | Built and tested (enforced at promotion in sprint 10) |
| Simulated customers, regression from traces, knowledge-triggered runs | Simulation runner | Q5-Q7 | 3 | Planned |
| Versions, diff, gated publish, rollback | Release service | Q8, Q10 | 2 | Built and tested |
| Environments, staged rollout | Release service | Q9, Q11 | 3-4 | Planned |
| Traces and trace API | Trace store | O1, O2 | 1 | Built |
| Export, metrics, insights, alerts | Observability | O3-O10 | 3-6 | Planned |
| Studio | Web app | U1-U8 | 4 | Planned |
| API key auth | Server | P1 | 1 | Built |
| Roles, keys, audit log, rate limits | Access control | P2-P4 | 2 | Built and tested |
| Containers, secrets, dry-run | Platform | P7, T7, T8 | 2 | Built and tested |
| General webhooks for status events | Platform | P8 | 3 | Planned (signed approval webhooks built) |
