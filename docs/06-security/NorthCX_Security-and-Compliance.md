# NorthCX Security and Compliance

Status: Draft. Control mapping is a plan, not a certification.

## Threats and controls
| Threat | Control |
|---|---|
| Prompt injection via customer or tool data | Supervisor, tool allow-lists, treat tool output as data, no secrets in prompts |
| Unauthorised or excessive actions | Typed tools, least-privilege credentials, approval gates |
| Untrusted text in customer facts or tool output | Facts are labelled as untrusted data in the prompt; treat tool output as data; supervisor checks replies |
| PII leakage in replies | Reply guardrails, minimal tool outputs |
| PII in logs and traces | Redaction, retention limits, role-restricted access |
| Credential exposure | Secrets manager, never in prompts or traces |
| API abuse | Bearer keys with roles, rate limits |
| Supply-chain risk | Pinned dependencies, licence and vulnerability scans |
| Model provider data handling | Documented data flow, provider terms reviewed per deployment |

## Access control
Roles: admin, developer, reviewer (approvals), viewer (traces). Keys are stored hashed.

## Audit
Every tool call, approval decision, guardrail block and handoff is in the trace with timestamps and actor.

## Compliance mapping (target)
Support for data access and deletion requests (privacy regulations), audit trail and access controls (security frameworks), PHI-safe deployment guidance (health data). Certification is out of scope for the open-source project; deployers own it.

## Open
Pen-test plan, key rotation, data-residency options, DPA templates.
