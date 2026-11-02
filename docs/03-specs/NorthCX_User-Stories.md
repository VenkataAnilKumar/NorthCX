# NorthCX User Stories

Status: Draft. Each story maps to catalog IDs.

## Authoring and release
| ID | Persona | Story | Acceptance | Catalog |
|---|---|---|---|---|
| US1 | Dev | Define an agent in code so I can version it with the app | Agent loads from a file and runs | A1, A2 |
| US2 | Dev | Add a typed tool so the model calls it correctly | Invalid input returns an error result, no crash | T1, T2 |
| US3 | Dev | Run scenarios in CI so regressions fail the build | Failing required scenario fails CI | Q2, Q4 |
| US4 | Dev | Roll back to a prior version in one step | Prior behaviour restored; audited | Q8, Q10 |
| US5 | Dev | Dry-run tools in tests so no real side effects occur | Intended actions recorded, not executed | T8 |
| US6 | Maya | Edit instructions without code and test them | Studio edit, simulations run, publish | U1, U3, U7 |
| US7 | Maya | Roll a change to 10% of traffic and compare | Metrics per version shown | Q11 |
| US8 | Maya | Start from a template for common intents | Working agent in under a day | A7 |
| US9 | Maya | Describe a journey in plain language | Valid journey definition produced | A6 |
| US10 | Dev | Generate a draft agent from a procedure document | Draft with tools and scenarios | A8 |

## Safety and compliance
| ID | Persona | Story | Acceptance | Catalog |
|---|---|---|---|---|
| US11 | Sam | Require approval for refunds over a limit | Run held; nothing executes | T3 |
| US12 | Sam | Block replies that leak card numbers | Draft rewritten or escalated | S4 |
| US13 | Sam | Force certain topics to a human | Topic always escalates | S7 |
| US14 | Sam | See who changed what and when | Audit log entries for versions, approvals, keys | P3 |
| US15 | Sam | Redact PII before traces leave the system | Exported traces contain no PII patterns | S9, O4 |
| US16 | Sam | Delete a customer's data | History, facts and traces removed | K8 |
| US17 | Ari | Issue scoped API keys | Key limited to its role | P2 |
| US18 | Sam | Prompt-injection attempts are blocked | Safety scenarios pass | S8 |
| US19 | Ari | Rate limit abusive clients | Excess requests receive 429 | P4 |

## Handoff and approvals
| ID | Persona | Story | Acceptance | Catalog |
|---|---|---|---|---|
| US20 | Cam | Reach a person when I ask | Handoff recorded with reason | H1 |
| US21 | Jo | See what the agent already did | Transcript, actions and summary shown | H4 |
| US22 | Jo | Return a simple remainder to the agent | Agent resumes with my notes | H7 |
| US23 | Rae | Review a held action with context | Payload and context shown | H2, U5 |
| US24 | Rae | Approve or reject quickly | Decision recorded; run resumes | R10 |
| US25 | Jo | Get suggested replies | Suggestions appear in the inbox | H6 |
| US26 | Cam | Be told when no one is available | Hours-aware message and callback option | H8 |

## Customer experience
| ID | Persona | Story | Acceptance | Catalog |
|---|---|---|---|---|
| US27 | Cam | Chat on the website and get an answer or a human | Widget returns reply and status | C1, C2 |
| US28 | Cam | Contact support by email | Reply in the same thread | C3 |
| US29 | Cam | Use SMS or a messaging app | Replies in the same conversation | C4 |
| US30 | Cam | Call and speak to the agent | Voice session resolves an intent | C5 |
| US31 | Cam | Be served in my language | Reply in the detected language | R9 |
| US32 | Cam | Not repeat myself across channels | Facts and history carried over | K2, C8 |
| US33 | Cam | Be recognised after identity verification | Account actions need verification | C9 |
| US34 | Cam | Send a photo or document | Attachment passed to the agent | C10 |
| US35 | Cam | Get answers that cite company policy | Answer shows its source | K4 |

## Insights and operations
| ID | Persona | Story | Acceptance | Catalog |
|---|---|---|---|---|
| US36 | Maya | See resolution and escalation rates | Dashboard with defined metrics | O5, O6 |
| US37 | Maya | Find why conversations fail | Failure analysis by step and tool | O7 |
| US38 | Maya | Ask a question about the data in plain language | Answer with the query shown | O8 |
| US39 | Maya | Search and tag conversations | Filters by intent, status, tag | O10 |
| US40 | Ari | Get alerted on error or policy spikes | Alert fires on threshold | O9 |
| US41 | Dev | Turn a failed production conversation into a test | Scenario created from a trace | Q5 |
| US42 | Dev | Re-run tests when knowledge changes | Simulations triggered automatically | Q7 |
| US43 | Ari | Deploy in containers on our infrastructure | Documented deployment runs | P7 |
| US44 | Dev | Receive webhooks on status changes | Event delivered with signature | P8 |
