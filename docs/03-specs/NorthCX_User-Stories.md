# NorthCX User Stories

Status: Draft

| ID | Persona | Story | Acceptance criteria | Req |
|---|---|---|---|---|
| US1 | Dev | As a platform engineer, I define an agent with instructions and tools in code so that I version it with the app. | Agent runs from a TS file; typecheck passes | R1 |
| US2 | Dev | I add a tool with a typed schema so the model calls it correctly. | Invalid input returns an error to the model, not a crash | R2 |
| US3 | Sam | I require approval for refunds over a threshold so large actions are reviewed. | Run stops with `needs_approval`; nothing executes | R4 |
| US4 | Sam | I block replies that leak card numbers so PII never reaches customers. | Rejected draft is rewritten or escalated | R3 |
| US5 | Maya | I want unresolved cases handed to a human so customers are not stuck. | Handoff recorded with reason and transcript | R5 |
| US6 | Jo | I see what the agent already did so I do not repeat steps. | Trace and transcript visible on handoff | R5, R6 |
| US7 | Dev | I run simulated conversations in CI so changes cannot silently regress. | Failing expectation fails the build | R8 |
| US8 | Maya | I check why a conversation failed so I can fix instructions. | Trace shows each step and guardrail hit | R6 |
| US9 | Customer | I chat on the website and get an answer or a human. | Widget returns reply and status | R7 |
| US10 | Customer | The agent remembers me across sessions. | Customer facts appear in the next session | R9 |
| US11 | Maya | I edit policies without code. | Studio changes produce a valid agent definition | R13 |
| US12 | Customer | I reach support by email or WhatsApp. | Messages routed through the inbox integration | R11 |
| US13 | Customer | I call and speak to the agent. | Voice session uses the same agent | R14 |
| US14 | Maya | I view resolution rate and escalations. | Dashboard shows the metrics | R15 |
