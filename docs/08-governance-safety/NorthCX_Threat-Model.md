# NorthCX threat model

Status: **Built**. Updated: 2026-11-09. Master for: threats and their handling. Closed for the current build, with the accepted residual risks listed at the end. Method and results of the review that produced it are in `NorthCX_Security-Review.md`. Revisit whenever a new channel, a new way to run code, or a new outbound integration is added.

## What is being protected

| Asset | Why it matters |
|---|---|
| Customer conversations, attachments and call transcripts | contain personal data and sometimes account details |
| API keys, chat tokens, SSO sessions, channel keys | whoever holds one acts as that role |
| The audit log | the record of who changed or released what; must not be silently altered |
| Released agent definitions | an unreviewed change to an agent changes what customers are told and what actions are taken |
| Tool credentials and company-system access | refunds, orders and customer data live behind them |
| Model spend | the service can be made to cost money |
| Customers themselves | a manipulated agent can mislead or harm them |

## Who might attack, and from where

| Actor | Starting position |
|---|---|
| Anonymous internet | can reach public routes only (`/health`, `/ready`, the demo page, the SDK scripts, SSO start/callback, and the SMS, WhatsApp and Telegram webhooks, each authenticated by the provider's signature or secret token) |
| Malicious customer | holds a chat token for one conversation; controls everything they type, upload or say |
| Malicious third-party content | text in documents, knowledge pages, tool results, attachments, helpdesk notes, speech transcripts |
| Staff with a low role (viewer, reviewer, auditor) | authenticated, limited permissions |
| Staff with a high role, or a stolen high-role key | can release agents, read all conversations, manage keys |
| A compromised or misbehaving model | returns arbitrary text, including tool calls |
| A compromised connected system (identity provider, helpdesk, telephony bridge, company API) | can send crafted messages to NorthCX |
| Someone with database or host access | outside the application's control (see residual risks) |

## Trust boundaries

1. Browser or app to the API (public network; chat tokens only).
2. Telephony bridge to the API (WebSocket; channel key).
3. Studio to the API (staff keys or SSO sessions).
4. API to the model provider (conversation text leaves the platform).
5. API to company systems (connectors, context endpoint, webhooks, scanner, identity provider, helpdesk), all configured by the operator.
6. API to Postgres.
7. Operator configuration (environment, spec and scenario files) is trusted input.

## Threats and how each is handled

Disposition: **M** mitigated, **A** accepted with the residual noted, **T** transferred to a component the operator runs. Rows S6 to S10 and S12 carried an undefined **L** when they were added (2026-11-03 onward). Their handling columns list mitigations, so on 2026-11-09 they were relabelled **M** (decision 176).

### Identity and access
| # | Threat | Handling | Disp. |
|---|---|---|---|
| I1 | Calling an API route without a key, or with the wrong role | Every `/v1` route needs a permission from one table; an unlisted route is refused; completeness and role-exact sweep tests (`test_security_sweep.py`) fail the build if a route is missing or too open; 2,920 junk requests across all routes produced no server errors | M |
| I2 | Guessing or stealing keys | 256-bit random keys stored as hashes, compared in constant time, shown once, expiring and revocable; failed attempts are rate limited per address and audited (sampled) | M |
| I3 | Customer token abused for staff features or other conversations | Tokens are signed, expire, name one conversation and one agent, die with the key that minted them; a sweep test proves they reach only their own five routes; attachments, hand-offs and the voice stream refuse them | M |
| I4 | A staff key used beyond its need | Seven roles with explicit permissions; production releases need a stronger permission than dev; SSO sessions expire within 24 hours | M |
| I5 | Whole-server roles: a developer key can act on every agent and environment | Roles are not scoped per agent | A |
| I6 | SSO forgery or replay | Authorization code flow with PKCE, signed state cookie, nonce, issuer, audience, expiry and signature checks (RS256/ES256 only), role from groups, refusal when no group matches | M |
| I7 | Voice stream hijack | Channel key checked by the endpoint (the HTTP middleware does not see WebSockets); per-address limit; per-connection flood limit; browsers cannot set the header, so a web page cannot open one | M |

### Customer-facing channels
| # | Threat | Handling | Disp. |
|---|---|---|---|
| C1 | Prompt injection in a customer message | Input checks (takeover phrasing withheld, personal data masked) before the model sees text; the model's replies and tool calls pass reply/tool guardrails and, for sensitive tools, human approval | M |
| C2 | Prompt injection in third-party content (tool results, knowledge, files) | Output guardrails screen tool results; text attachments pass the input checks and are marked untrusted; customer facts and memories are labelled untrusted data | M (pictures, and PDFs in file mode: A; PDFs in `pdf_text` mode pass the input checks) |
| C3 | The model is manipulated into an unwanted action | Writes can require approval; tool scopes limit who and where; strict skills and journeys enforce order; fail-closed supervision; idempotency stops repeats | M |
| C9 | Hostile web pages or files imported as knowledge (hidden instructions, parser exploits) | Visible text only; PDFs read in a worker thread with a time limit and a page cap; sizes capped; the text reaches the model as tool results through the output checks; style-sheet-hidden text is a known gap | M / A |
| C4 | Malicious upload | Identified by content; programs, archives, Office files, SVG/HTML refused; size and count caps; optional scanner; served only as sandboxed downloads to staff | M |
| C5 | Cross-site scripting through widget or Studio | The widget and Studio render text only; no raw HTML sinks (checked); Studio sends a CSP forbidding framing, plugins and base changes | M |
| C6 | Another website calling the API from a visitor's browser | CORS is an explicit allow-list of exact https origins; tokens travel in a header, never cookies | M |
| C7 | Fake caller identity on voice | Caller ID is not trusted unless the operator turns it on | M |
| C8 | Recording without consent | Never started without a clear yes; audio is held by the operator's bridge | M / T |

### Data
| # | Threat | Handling | Disp. |
|---|---|---|---|
| D1 | SQL injection | All queries bound; a test fails if any new SQL string is built from variables | M |
| D2 | Personal data in logs, traces, audit | Secrets scrubbed from stored events; audit holds hashed references, lengths and counts, not content or file names; trace export redacts by mode | M |
| D3 | Erasure incomplete | One erase path per conversation covers messages, traces, outbox, tags, reviews, feedback, files, route, call record, rollout arm, idempotency keys; per-customer export and erasure; retention job | M |
| D4 | Staff reading conversations they should not | Any role with `traces:read` (viewer, reviewer, auditor, developer, ...) can read full conversation text | A |
| D5 | Data at rest | Relies on database and disk encryption the operator provides | T |
| D6 | Personal data in pictures and PDFs sent to the model | Not masked; per-agent opt-in | A |
| D7 | Conversation text sent to the model provider | Inherent; masking of typed personal data happens first; provider terms apply | A |

### Integrity of what is released
| # | Threat | Handling | Disp. |
|---|---|---|---|
| R1 | An untested change reaches customers | Immutable versions; required scenarios must pass on the exact version; strict mode requires staging first; publish checklist; staged rollout; one-step rollback | M |
| R2 | A change slips in unnoticed | Hash-chained audit log with an integrity check; every privileged action is audited with actor and role | M |
| R3 | Audit log tampering by an application user | No API deletes or edits entries; chain breaks are detected | M |
| R4 | Tampering with the browser SDK bundle | A test fails if the committed bundle differs from its source hash; served with `nosniff` | M |

### Availability and cost
| # | Threat | Handling | Disp. |
|---|---|---|---|
| A1 | Oversized or malformed requests | Per-endpoint body caps enforced before parsing; strict schemas; parsers fuzzed | M |
| A2 | Flooding | Per-key, per-session, per-address and per-conversation rate limits; voice flood cut-off; with `NORTHCX_LIMITS_BACKEND=postgres` the counts are shared by all server processes | M |
| A3 | Runaway model spend | Per-turn and daily token budgets; step and transfer limits; assist and draft endpoints rate limited; shared through the database under the same setting | M |
| A4 | A slow or failing dependency | Timeouts, retries with back-off, circuit-style fallbacks, fail-closed supervision, outbox with retry | M |
| A5 | Regular-expression slowdowns | Operator patterns are checked at load; built-in patterns were timed on 8,000-character hostile input | M |

### Outbound calls
| # | Threat | Handling | Disp. |
|---|---|---|---|
| S1 | Server-side request forgery | Every outbound URL is operator configuration (webhooks, scanner, identity provider, connectors with a host allow-list), https required except localhost, redirects never followed (a test enforces it), no URL is taken from a customer or from API input | M |
| S3 | A paged list or an OAuth token address used to reach somewhere else | A `Link` address is followed only on the connector's own scheme, host, port and path (credentials never leave it); the token address must be on the operator's allowed hosts and https; page and item counts are capped; tokens live in memory only and never appear in results, traces or errors | M |
| S5 | The embeddings address used to reach somewhere else, or knowledge text sent where it should not go | The address is operator configuration only (https, no credentials or query in the URL, never followed through a redirect); error messages never include the address or the service's reply; vectors are validated (count, size, finite numbers) before they are stored; the operator chooses the service, so a self-hosted one keeps all text inside the network | M |
| S4 | The crawler used to reach internal systems or cloud metadata, or to attack a third party | Only operator-listed hosts, https, no private or link-local addresses (all resolved addresses checked on every request and redirect hop), same-host redirects only, robots.txt and delays obeyed, hard caps on pages, bytes, depth and time, rate-limited starts, audited | M |
| S6 | A forged WhatsApp webhook, or a stranger verifying the endpoint | Every POST needs a valid body signature (constant-time comparison; unsigned failures throttled and audited); verification needs the shared token and echoes only a plain challenge; the API address is operator configuration, https only, no redirects | M |
| S7 | A crafted analytics question steering the model into reading or revealing data, or inventing a figure | The model sees only the question text and the list of figure names, never data; its reply must be a small JSON query that is validated against a fixed list (unknown figure, agent or out-of-range period is refused); the figures and the answer sentence are produced by code; the question is rate limited per key and only the chosen figure is audited, not the question | M |
| S8 | Procedures or transcripts used to talk the model into drafting an agent with extra powers, or personal data leaking to the model | Sources are masked for personal details and fenced as data; the draft keeps only a fixed set of fields, so limits, model, scopes, routes, voice and attachments cannot be set; every tool and guardrail must exist in the registry; the result is only a draft and still goes through version, scenarios, checklist, review and release gates | M |
| S9 | A forged Telegram webhook; a WhatsApp media address or template used to reach somewhere else or to message people who did not ask | Telegram calls need the secret token (constant-time, throttled, audited), the bot token never appears in errors; media is fetched only from Meta hosts over https and passes the attachment checks; templates go only to approved names, to people who already wrote in or are on the operator's opt-in list, never after STOP, within the hourly limit | M |
| S10 | Event feed leaking conversation content, or a forged event receiver | Events carry only ids, names and short plain values (no text, no nested data), are built from audit records for staff actions, and are signed like reply webhooks with a replay window; the feed needs the auditor/admin role; the address is operator configuration and is in the residency report | M |
| S11 | Identity checks bypassed or abused: guessing codes, sending codes to other people, claiming to be verified | Six-digit codes from the system random source, keyed-hash storage, 5 tries, 10-minute expiry, send limits; the destination is never chosen by the agent or the customer; verification is bound to the conversation and customer and expires; the fact `identity_verified` is set only by the platform; the code is kept out of traces | M |
| S12 | Abusive or flooding customers wasting staff time or pushing the agent off course | Optional `abuse_detection` input check: threats go straight to a person, repeated abuse is handed off, repetition and bursts are slowed or handed off, the agent is told to stay calm; deterministic, no storage, no model call for blocked messages; rate limits per key and per channel still apply | M |
| S2 | A webhook receiver being forged to | Outgoing webhooks are signed with a timestamp; incoming SMS is signature checked | M |

### Supply chain and build
| # | Threat | Handling | Disp. |
|---|---|---|---|
| B1 | Vulnerable dependencies | `pip-audit` and `npm audit` clean at review; hash-pinned lock files for the backend (`requirements.lock`, `requirements-dev.lock`, made by `scripts/lock.sh`), the web workspace and the SDK; CI installs from them with hashes required, a test fails when a lock is older than `pyproject.toml`, and a CI job runs `pip-audit` on both locks | M |
| B2 | Compromised build | Images run as an unprivileged user with health checks; no secrets in images; licence and restricted-path checks in CI | M |

## Accepted residual risks (owner: the operator unless stated)

1. **Roles are server-wide** (I5, D4): a key cannot be limited to some agents or environments, and every role that can open traces can read conversation text. Mitigate by issuing few keys and using SSO groups.
2. **Pictures, and PDFs in file mode, reach the model unmasked and may carry hidden instructions** (C2, D6): enable per agent only where acceptable. For PDFs the safer mode is `attachments: [pdf_text]` (WP0.6): the text is read here, personal data is masked, the text passes the input checks like a typed message and the file itself is never sent; scanned PDFs without a text layer are refused with a clear reason. File mode (`pdf`) now needs `acknowledge_unmasked_files: true` in the spec. Pictures are still sent as they are (reading text out of pictures would need OCR, which is not built).
3. ~~Rate limits and daily budgets are per process~~ — closed in WP0.4 for deployments that set `NORTHCX_LIMITS_BACKEND=postgres`: rate limits, the abuse burst check and the daily token budget are then counted in the database. The default stays per process (one server), so a multi-replica deployment must set it. Residual: the shared limiter uses fixed one-minute windows (a burst across a window edge can pass up to twice the limit), and if the database is unreachable each process falls back to its own counters with a warning.
4. **No multi-factor authentication for API keys**: use SSO (the identity provider supplies MFA) for people; keep API keys for machines.
5. ~~Backend dependencies are not locked~~ — closed in WP0.3: the container image and CI install from hash-pinned lock files. Remaining for the operator: re-lock and re-audit regularly (`scripts/lock.sh --upgrade`), since a lock only fixes versions, it does not keep them current.
6. **Behind a reverse proxy**, set uvicorn's `FORWARDED_ALLOW_IPS` to the proxy address, otherwise every client appears to have the proxy's address and per-address limits apply to everyone at once.
7. **Not independently tested**: no external penetration test has been done; the review was done by the authors with automated scans and tests. Commission one before exposing the service to the public internet.
8. **Telephony fraud and denial of service** are limited by the bridge, not NorthCX.

## Staff platform (proposed threats for the Workspace, designed 2026-11-09; none built)
These extend the sections above. Each row becomes a test when the feature is built.
| Threat | Why it matters | Planned handling |
|---|---|---|
| Customer text instructs the staff assistant (indirect injection) | Conversations, files and sources are read by assistants with the person's permissions | All such text is labelled as data; staff tools never take instructions from it; tests with hostile conversations |
| An assistant reaches more than its user | The assistant could become a way around access rules | Permissions travel with the person and are checked inside each tool; a search provider that cannot prove access returns nothing |
| Writes without a person | A plan or an automation could change systems unseen | Writes always ask first; approval rules gate automation writes; kill switch; limits |
| Leakage of customer data through outputs, memory or sharing | Saved results outlive the conversation | Masking by default; memory rejects customer personal details; outputs inherit the strictest source classification; shares are masked |
| Sensitive data reaches a public model on fallback | A cheaper or available model could be chosen under failure | Constraints are applied before ranking and to the fallback chain; recorded in the trace |
| Memory poisoning | A remembered item could steer later answers | Memory is untrusted data, never an instruction with authority; items show their origin and can be deleted; precedence keeps memory below every instruction layer |
| Personal instructions weaken company rules | A person could tell an assistant to skip a check | Fixed precedence with organization rules locked; conflicts shown as ignored |
| Web search (later) leaks queries or injects instructions | Public services and pages are outside the trust boundary | Off by default and per assistant; never in sensitive conversations or with customer data in the query; page text is data; every search audited; blocked on private deployments |
| Customers view used for browsing | A cross-channel record is a privacy risk | Leads and reviewers only by default; search by reference only; every open, reveal and edit audited; deletion removes it |
| Hub entry or skill widens access | A shared template could carry hidden powers | Placeholder filling only; requirements checked against the deployment; skills are instructions only; entries signed or reviewed |
| Cross-tenant access in the new tables | New tables multiply isolation paths | Tenant predicate in the store base class plus row-level security; isolation sweep generated from the route table |
| Runaway cost or loops | Background runs can spend unattended | Step, cost and time limits per task and per tenant; stop and ask on overrun |
