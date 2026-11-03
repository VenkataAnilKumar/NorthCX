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

**Customer chat tokens.** A channel key is a server-side secret and must never be put in a browser or app. To let a customer chat, the company's own server calls `POST /v1/chat-tokens` with its channel key and receives a signed token (HMAC-SHA256) for one conversation: it names the conversation, the customer (set by the company's server, not the customer), and optionally the one agent it may talk to, and it expires (default one hour, between one minute and one day). The browser sends it as `Authorization: Bearer ncxc_...`. A token can only send chat messages in its own conversation and read that conversation's outbox; it cannot read traces, agents, approvals, handoffs, keys or the audit log, cannot mint further tokens, and cannot name a different customer or conversation (attempts are refused and audited, without the token). Revoking the key that minted a token ends all of that key's tokens at once. The signing secret is `NORTHCX_TOKEN_SECRET`, or is derived from `NORTHCX_API_KEY`; with neither, a random secret is used and tokens stop working at restart and across servers. Individual tokens cannot be revoked before they expire (keep lifetimes short, and use a different conversation id when a customer signs out). The demo page takes the token in the URL fragment (never sent to a server), stores it for that tab only and removes it from the address bar.

**Inbound email.** The email endpoint accepts mail only from a `channel` or `admin` key (customer tokens are refused). The sender address can be forged, so a sender is treated as a known customer only when the company's mail gateway reports `dmarc=pass` and the operator has set `NORTHCX_EMAIL_TRUST_AUTH_RESULTS=1`; otherwise the conversation is anonymous and customer facts are not loaded. A different sender can never join an existing thread. Automatic mail, mailing lists, bounces, no-reply senders and the channel's own address are never answered, and each sender gets a limited number of replies per hour, so the channel cannot be used to start a mail loop or to mail-bomb a third party. Attachments are never opened. Header injection in subjects and addresses is neutralised, and SMTP errors never include the password.

**Limits of this design.** Roles apply to the whole server: a key cannot yet be limited to particular agents or environments. There is no single sign-on or multi-factor authentication for the console (planned: single sign-on in Phase 4). The customer-facing chat uses per-conversation tokens (above) instead of a shared key.

## Audit
The trace records every tool call, guardrail block and handoff in a conversation. Separately, an append-only **audit log** records privileged actions: creating and revoking keys, saving, publishing and rolling back agent versions (including publish attempts blocked by the gate), deciding approvals, resolving handoffs, running simulations, expiring approvals, permission denials, and sampled failed sign-ins. Each entry holds who (name, role, key), what, which target, the outcome and identifiers or reasons; never conversation text, personal data or secrets.

In Postgres a trigger refuses UPDATE, DELETE and TRUNCATE on the log. Each entry also stores a hash that covers its content and the previous entry's hash, so someone with full database rights who switches the trigger off still cannot edit or remove an entry without breaking the chain, which `GET /v1/audit/verify` (and the Access page) detects and locates. The chain cannot reveal removal of the newest entries, or a rewrite of the newest entry, so copy the `head` value it returns to somewhere the database administrator cannot write (a log service or a ticket) on a schedule. If writing an audit entry fails, the request fails with an error instead of proceeding unrecorded.

## Compliance mapping (target)
Support for data access and deletion requests (privacy regulations), audit trail and access controls (security frameworks), PHI-safe deployment guidance (health data). Certification is out of scope for the open-source project; deployers own it.

## Open
Pen-test plan, key rotation, data-residency options, DPA templates.


**Tool results (indirect injection).** Text returned by tools can be written by third parties (order notes, web pages, customer-entered fields). An agent can list `output_guardrails`; each text value in a tool result is checked before the model reads it. `tool_output_injection` withholds results containing phrases that address the model (for example "ignore previous instructions", "new instructions:", `system:` lines, "do not tell the customer"); `tool_output_pii` masks (or, with `mask_pii: false`, withholds) personal data. A withheld result is replaced by a notice telling the model not to act on it and to hand off if it cannot continue; the event is recorded in the trace with the tool name. A screen that fails is treated as a denial. The phrase list is narrow by design, so it is an alarm for obvious attempts; approvals, tool policies and supervisors remain the main controls. Specs without `output_guardrails` keep their existing digests.

**Monitoring.** Every finished turn is checked by deterministic rules over its trace: escalations (a step limit or repeated supervisor rejection is a warning), guardrail hits, tool errors, the same tool called three or more times with the same input, a frustrated customer, and approval requests. This covers all conversations, not a sample, costs no model calls and sends nothing outside the platform. Findings are flags for people (`GET /v1/monitor/findings`, `monitor:read`, held by every role except `channel`); they never change what a customer is told. A rule or store that fails is logged and recorded as a `monitor_error` finding and never interrupts the conversation. Findings hold rule names and short details, not message text.

**Policy library.** Ready-made guardrails an agent spec can name, all deterministic: `tool_limit` (a numeric tool field must be within a maximum or minimum; a missing, non-numeric, boolean or NaN value is denied), `forbidden_phrases` (whole words, any case), `required_phrase` (a disclaimer whenever listed topics are mentioned), `no_personal_data_in_reply` (emails, SSNs, phone numbers, with an allow-list for the company's own addresses) and `max_reply_length`. Each ships with cases that must pass in CI (at least one allowed and one blocked), invalid configuration is rejected when the spec is built, and a blocked tool call is never run. These complement, not replace, approvals and the model-based `llm_policy`.

**Knowledge.** Documents are company-supplied but treated as untrusted text when an agent reads them: passages come back through `search_knowledge` and pass the same tool-result screens as any tool (an agent that uses knowledge should list `tool_output_injection`). Only `developer` and `admin` keys can change documents (`knowledge:write`); the `channel` role and customer tokens cannot read or write the library. Writes and deletions are in the audit log, and deleting a document removes its passages at once.

**Data rights and retention.** An administrator can export everything held for a customer, erase it, or erase a single conversation (`privacy:manage`, admin keys only; customers' tokens and every other role are refused). A session index records which conversations belong to which customer and when each was last active; export and erasure then walk everything stored for those conversations: messages, traces, outbox messages, approvals, hand-offs, monitoring findings, email threads and stored idempotent replies, plus the customer's facts. Erasure on Postgres runs in one transaction per conversation and waits for any save in progress. Conversations created before the index existed are treated as having no known customer, so they can be erased by conversation id or aged out but not found by customer id. If a conversation id was ever used by two customers, erasing either removes it. `NORTHCX_RETENTION_DAYS` erases conversations idle longer than that (checked hourly); the audit log is kept: it is tamper-evident by design and holds no message text, and privacy actions are recorded in it with a one-way reference to the customer, not the id itself. Not covered: backups, copies the company's own systems or webhook receivers hold, and the optional trace file mirror on disk beyond what erasure rewrites.

**Customer context.** Data fetched from the company's systems is treated as untrusted text: limited in count and size, stripped of nested structure, screened for instruction-like wording, and presented to the agent as data. The HTTPS endpoint is called with a signed request and a short timeout, without following redirects, and a failing system never blocks a conversation. The values are not stored with the customer's facts or written to traces; they are kept only in a short in-memory cache, and in a hand-off package when one is created.

**Long-term memory.** Notes the agent saves come from conversations, so they are screened on the way in (instruction-like wording, card numbers and passwords are refused; configured secrets are redacted) and shown back to the agent only as untrusted notes. A customer's notes are never returned for another customer. Reading requires `memory:read`, deleting requires `memory:manage` (admin), and both are audited without the customer id. Notes are included in customer export and removed by customer erasure.

**SMS channel.** The only public endpoint besides health checks and the demo page is the SMS webhook; it accepts a request only with a valid provider signature over the configured public URL (so a spoofed Host header cannot change what is verified), limits the body to 64 KB, and throttles and audits repeated forgeries. Customer identity from SMS is the signed sender number. Opt-outs (STOP) are honoured immediately, apply to replies already queued, and are kept by one-way hash through erasure. Texts that belong to no conversation are recorded under a one-way reference, not the number.

**Routing.** The routing file is operator-controlled configuration, validated at start-up. Queue names and hours appear in the Handoffs page and `GET /v1/routing` for anyone with `handoffs:read`; they hold no customer data.
