# NorthCX Security and Compliance

Status: Draft. Control mapping is a plan, not a certification.

## Threats and controls
| Threat | Control |
|---|---|
| Prompt injection via customer or tool data | Supervisor, tool allow-lists, treat tool output as data, no secrets in prompts |
| Unauthorised or excessive actions | Typed tools, least-privilege credentials, approval gates, role-based permissions on every endpoint |
| Untrusted text in customer facts or tool output | Facts are labelled as untrusted data in the prompt; treat tool output as data; supervisor checks replies |
| PII leakage in replies | Reply guardrails, minimal tool outputs |
| PII in logs and traces | Redaction, retention limits, role-restricted access |
| Credential exposure | Secrets manager, never in prompts or traces |
| API abuse and key guessing | Hashed bearer keys with roles, expiry and revocation; per-key, per-conversation and failed-sign-in rate limits |
| Supply-chain risk | Pinned dependencies, licence and vulnerability scans |
| Model provider data handling | Documented data flow, provider terms reviewed per deployment |

## Access control
Roles: admin, developer, reviewer (approvals), viewer (traces). Keys are stored hashed.

## Approval and webhook controls
Approved actions run once, are re-validated and re-supervised at execution time, and carry an idempotency key. Platform notices written into the conversation are produced by the platform, but they embed tool output, which remains untrusted data. Webhooks are signed with HMAC-SHA256 over the timestamp and body; receivers must verify the signature in constant time and reject old timestamps. Reviewer identity is the signed-in key's name (a typed name is only used in open mode).

## Secrets and testing safely
**Secrets** (platform and tool credentials) come from the environment or from mounted files (`NAME_FILE`, the form Docker and Kubernetes secrets use); setting both is an error. Tool credentials are handed to a tool only when it asks for one by name. Every value that reaches the model, a trace, saved history, an approval record, a handoff package, an outbox message or a reply is passed through a scrubber that replaces known secrets, including the platform's own API keys, model key, webhook secret and database URL, with `[redacted:name]`. Tests found and closed leaks in the model's own saved turns and in handoff reasons. Limits: only values the platform knows are scrubbed (a credential a tool fetches from elsewhere is not), and a secret that appears transformed (for example base64) is not recognised.

**Dry run.** Simulations run with write tools simulated, so a scenario, a release proof or a CI run cannot change a real system by accident. Real side effects in tests require the explicit `--allow-side-effects` flag.

**Containers.** The images run as an unprivileged user, carry no secrets, and use health and readiness endpoints that expose no internals. The compose file binds to 127.0.0.1 by default, refuses to start without a database password and API key, and requires authentication. Terminate TLS in front of it.

## Handoff packages
A package holds the transcript, customer facts and action results, so it is personal data. Reading it needs the handoffs permission (viewer and above); give that role only to people who may see customer conversations. Forced-handoff patterns are author-supplied regular expressions: they are length-limited and applied only to messages up to 8,000 characters, but authors should avoid nested quantifiers.

## Release controls
A version can go live only when the release gate passes for its exact content, so an unreviewed or untested edit cannot reach customers through the API. Publishing and rollback need the release manager or admin role and are recorded in the audit log, including blocked attempts. Specs are validated against the code's tool and guardrail registry and cannot name anything that does not exist.

## Access control (built, Phase 2 sprint 11)

**Authentication.** Every `/v1` request carries `Authorization: Bearer <key>`. Keys look like `ncx_<8 hex>_<secret>`; the secret is 256 bits of randomness and only its SHA-256 hash is stored, so a database leak does not yield usable keys, and the full key is shown once when it is created. Keys can expire and can be revoked, and a revoked key stops working on the next request. A comparison failure and an unknown key look the same to the caller. `NORTHCX_API_KEY` defines a bootstrap admin key that does not depend on the database; further keys are created on the Access page or with `python -m northcx.keys create`. The last admin key cannot be revoked unless a bootstrap key exists, so an operator cannot lock themselves out.

**Open mode.** If no bootstrap key is set and no key has ever been created, the server runs without authentication and every caller is an admin named "anonymous"; it logs a warning at startup and the web console shows a banner. Set `NORTHCX_REQUIRE_AUTH=1` in any shared or production deployment to make the server refuse to start unauthenticated. Once any key exists, authentication stays on.

**Roles.** A key has exactly one role.

| Role | Can |
|---|---|
| admin | Everything, including keys and the audit log |
| release manager | Everything a developer can, plus publish and roll back agent versions |
| developer | Read agents, traces, handoffs, approvals and simulations; save versions; run simulations; try the chat |
| reviewer | Read the same things, decide approvals and resolve handoffs |
| auditor | Read the same things plus the audit log |
| viewer | Read agents, traces, handoffs, approvals, simulations and versions |
| channel | Send chat messages and read the outbox only (for channel adapters and the customer-facing chat) |

Each endpoint requires one named permission, listed in one table in the server. A route that is missing from the table is refused rather than served, and a test fails if any route is unlisted or the table lists a route that does not exist. Interactive API documentation is switched off.

**Identity replaces claimed names.** When authentication is on, the name recorded on a release, approval decision, handoff resolution or saved version is the key's name, whatever the request says. A name in the request body is only honoured in open mode.

**Rate limits** (per process, token buckets; on by default, `NORTHCX_RATE_LIMITS=off` disables them): 600 requests per minute per key, 30 chat messages per minute per conversation, and 20 failed sign-ins per minute per client address, which also stops key guessing. Over the limit the server answers 429 with `Retry-After`. Several server processes keep separate buckets, so the effective limit scales with the number of processes.

**Limits of this design.** Roles apply to the whole server: a key cannot yet be limited to particular agents or environments. There is no single sign-on or multi-factor authentication for the console (planned: single sign-on in Phase 4). The built-in chat page asks for a channel key when the server requires one; a production customer-facing chat should use short-lived per-conversation tokens (Phase 3, with the channel adapters) instead of a shared key in a browser.

## Audit
The trace records every tool call, guardrail block and handoff in a conversation. Separately, an append-only **audit log** records privileged actions: creating and revoking keys, saving, publishing and rolling back agent versions (including publish attempts blocked by the gate), deciding approvals, resolving handoffs, running simulations, expiring approvals, permission denials, and sampled failed sign-ins. Each entry holds who (name, role, key), what, which target, the outcome and identifiers or reasons; never conversation text, personal data or secrets.

In Postgres a trigger refuses UPDATE, DELETE and TRUNCATE on the log. Each entry also stores a hash that covers its content and the previous entry's hash, so someone with full database rights who switches the trigger off still cannot edit or remove an entry without breaking the chain, which `GET /v1/audit/verify` (and the Access page) detects and locates. The chain cannot reveal removal of the newest entries, or a rewrite of the newest entry, so copy the `head` value it returns to somewhere the database administrator cannot write (a log service or a ticket) on a schedule. If writing an audit entry fails, the request fails with an error instead of proceeding unrecorded.

## Compliance mapping (target)
Support for data access and deletion requests (privacy regulations), audit trail and access controls (security frameworks), PHI-safe deployment guidance (health data). Certification is out of scope for the open-source project; deployers own it.

## Open
Pen-test plan, key rotation, data-residency options, DPA templates.
