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

## Approval and webhook controls
Approved actions run once, are re-validated and re-supervised at execution time, and carry an idempotency key. Platform notices written into the conversation are produced by the platform, but they embed tool output, which remains untrusted data. Webhooks are signed with HMAC-SHA256 over the timestamp and body; receivers must verify the signature in constant time and reject old timestamps. Reviewer identity is currently a free-text name; authenticated reviewer identities and roles arrive with sprint 11.

## Handoff packages
A package holds the transcript, customer facts and action results, so it is personal data. Until roles exist (sprint 11) anyone with an API key can read it; restrict who receives that key. Forced-handoff patterns are author-supplied regular expressions: they are length-limited and applied only to messages up to 8,000 characters, but authors should avoid nested quantifiers.

## Roles (P2)
| Role | Can |
|---|---|
| admin | Manage keys, roles, settings, retention |
| developer | Create versions, run simulations, promote to non-production |
| release manager | Promote to production, roll back |
| reviewer | Decide approvals |
| viewer | Read conversations and traces within scope |

## Single sign-on (P5)
Studio supports enterprise single sign-on in Phase 4.

## Audit
Every tool call, approval decision, guardrail block and handoff is in the trace with timestamps and actor.

## Compliance mapping (target)
Support for data access and deletion requests (privacy regulations), audit trail and access controls (security frameworks), PHI-safe deployment guidance (health data). Certification is out of scope for the open-source project; deployers own it.

## Open
Pen-test plan, key rotation, data-residency options, DPA templates.
