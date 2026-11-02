# NorthCX Product Requirements Document

Status: Draft. Feature IDs refer to `03-specs/NorthCX_Feature-Catalog.md`. Metric definitions are in `NorthCX_Success-Metrics.md`.

## 1. Goals
1. Resolve common customer requests autonomously and measurably.
2. Make agent behaviour safe, auditable and testable.
3. Let teams change and release agents with confidence.
4. Be deployable by a small team on its own infrastructure.

## 2. Non-goals (v1)
Hosted multi-tenant service, outcome-based billing, general-purpose autonomous agents, helpdesk replacement.

## 3. Definition of "resolved"
A conversation is resolved when it ends with status `completed`, the customer confirms the outcome or does not contact again about the same issue within a window (default 3 days, to validate), and no handoff or reopen occurred.

## 4. Functional requirements
Priority P0/P1/P2. "Done when" is the acceptance test.

| ID | Requirement | Pri | Phase | Catalog | Done when |
|---|---|---|---|---|---|
| R1 | Define an agent from goals, policies, tools and guardrails | P0 | 1 | A1,A2,A9 | Example agent runs from a code definition |
| R2 | Typed tools with validation; errors returned to the model | P0 | 1 | T1,T2 | Invalid input never crashes a run |
| R3 | Supervisors check replies and tool calls; fail closed | P0 | 1 | S1-S6 | Supervisor error results in denial |
| R4 | Approval gates for sensitive actions | P0 | 1 | T3,H2,H3 | Over-limit refund is held and listed |
| R5 | Handoff to a human with context | P0 | 1-2 | H1,H4 | Handoff includes transcript, actions, reason, summary |
| R6 | Per-conversation traces via API | P0 | 1 | O1,O2 | Trace retrievable by ID |
| R7 | Chat API and web widget | P0 | 1 | C1,C2 | Widget completes a conversation |
| R8 | Simulation testing with CI gate | P0 | 2 | Q2-Q4 | Failing required scenario fails the build |
| R9 | Persistent memory and customer facts | P0 | 2 | K3,K2 | State survives restart |
| R10 | Resume runs after approval decisions | P0 | 2 | R10 (runtime) | Approved action completes the conversation |
| R11 | Release management: versions, rollback | P0 | 2 | Q8,Q10 | A prior version can be republished in one step |
| R12 | Forced-handoff topics | P0 | 2 | S7 | Listed topics always escalate |
| R13 | Roles, audit log, rate limits, secrets | P0 | 2 | P2-P4,T7 | Every action is attributable |
| R14 | Knowledge retrieval with citations | P1 | 3 | K4,K5 | Answers cite sources |
| R15 | Email, SMS, messaging channels and human inbox | P1 | 3 | C3,C4,C8,H5 | Round trip on each channel |
| R16 | Environments and promotion | P1 | 3 | Q9 | Promotion requires passing checks |
| R17 | Trace export and redaction | P1 | 3 | O3,O4 | Traces appear in an external backend, PII redacted |
| R18 | Safety extensions: input checks, PII redaction, full monitoring | P1 | 3 | S8-S11 | Injection scenarios blocked |
| R19 | Model fallback, streaming, cost budgets | P1 | 3 | R5-R7 | Provider failure still serves a reply |
| R20 | Studio: editor, test console, simulations, review, approvals | P1 | 4 | U1-U8 | CX user edits, tests, publishes without code |
| R21 | Insights and alerts | P1 | 4 | O5-O7,O9,O10 | Dashboard shows defined metrics |
| R22 | Journeys and multilingual conversations | P1 | 4 | A5,A6,R9 | Journey runs in two languages |
| R23 | Experiments and staged rollout | P2 | 4 | Q11 | Traffic split with metric comparison |
| R24 | Voice channel | P2 | 5 | C5,C6 | Live call resolves an intent |
| R25 | Agent assist for humans; return-to-agent | P2 | 5 | H6,H7 | Suggested replies shown in inbox |
| R26 | Multi-agent orchestration | P2 | 5 | R8 | Router delegates to a specialist |
| R27 | Agent-assisted building; natural-language analytics | P2 | 6 | A8,O8 | Draft agent generated from a procedure |

## 5. Non-functional requirements
See `03-specs/NorthCX_Non-Functional-Requirements.md`.

## 6. Success metrics
Defined in `NorthCX_Success-Metrics.md`. Headline targets (initial, to validate): resolution rate on pilot intents at least 60%; zero policy violations reaching customers on the safety suite; correct handoff at least 95%; first agent from template in under one day.

## 7. Release criteria by phase
| Phase | Ships when |
|---|---|
| 1 | Example agent resolves, escalates and blocks correctly in tests; widget works |
| 2 | State persists; failing scenario fails CI; approvals resume; rollback works; audit log in place |
| 3 | Two channels and a knowledge source work end to end; traces exported; environments gate promotion |
| 4 | CX user publishes a tested agent in Studio; insights live |
| 5 | A live call resolves an intent |
| 6 | Security review closed; v1.0 tagged |

## 8. Dependencies
Model provider; customer-system APIs; telephony/messaging providers; database; container hosting.

## 9. Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Unauthorised or wrong actions | High | Typed tools, approvals, supervisors, simulations |
| Prompt injection via customer or tool data | High | Untrusted-data labelling, input checks, tool allow-lists |
| Quality regressions on change | High | CI gate, versioning, rollback, staged rollout |
| Cost and latency overruns | Medium | Step limits, budgets, cheaper supervisor model |
| Integration burden | Medium | Interfaces, connector library |
| Licence surprises in dependencies | Medium | Licence policy and CI scan |
| Metrics are guesses | Medium | Pilot measurement before committing targets |

## 10. Open questions
Resolution window length; which channels first for pilots; Studio build vs adopt; project licence.
