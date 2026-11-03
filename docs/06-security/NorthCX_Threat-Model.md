# NorthCX threat model

Status: closed for the current build, with the accepted residual risks listed at the end. Method and results of the review that produced it are in `NorthCX_Security-Review.md`. Revisit whenever a new channel, a new way to run code, or a new outbound integration is added.

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
| Anonymous internet | can reach public routes only (`/health`, `/ready`, the demo page, the SDK scripts, SSO start/callback, the SMS webhook) |
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

Disposition: **M** mitigated, **A** accepted with the residual noted, **T** transferred to a component the operator runs.

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
| C2 | Prompt injection in third-party content (tool results, knowledge, files) | Output guardrails screen tool results; text attachments pass the input checks and are marked untrusted; customer facts and memories are labelled untrusted data | M (pictures and PDFs: A) |
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
| A2 | Flooding | Per-key, per-session, per-address and per-conversation rate limits; voice flood cut-off | M, limits are per process |
| A3 | Runaway model spend | Per-turn and daily token budgets; step and transfer limits; assist and draft endpoints rate limited | M, budgets per process |
| A4 | A slow or failing dependency | Timeouts, retries with back-off, circuit-style fallbacks, fail-closed supervision, outbox with retry | M |
| A5 | Regular-expression slowdowns | Operator patterns are checked at load; built-in patterns were timed on 8,000-character hostile input | M |

### Outbound calls
| # | Threat | Handling | Disp. |
|---|---|---|---|
| S1 | Server-side request forgery | Every outbound URL is operator configuration (webhooks, scanner, identity provider, connectors with a host allow-list), https required except localhost, redirects never followed (a test enforces it), no URL is taken from a customer or from API input | M |
| S3 | A paged list or an OAuth token address used to reach somewhere else | A `Link` address is followed only on the connector's own scheme, host, port and path (credentials never leave it); the token address must be on the operator's allowed hosts and https; page and item counts are capped; tokens live in memory only and never appear in results, traces or errors | M |
| S5 | The embeddings address used to reach somewhere else, or knowledge text sent where it should not go | The address is operator configuration only (https, no credentials or query in the URL, never followed through a redirect); error messages never include the address or the service's reply; vectors are validated (count, size, finite numbers) before they are stored; the operator chooses the service, so a self-hosted one keeps all text inside the network | M |
| S4 | The crawler used to reach internal systems or cloud metadata, or to attack a third party | Only operator-listed hosts, https, no private or link-local addresses (all resolved addresses checked on every request and redirect hop), same-host redirects only, robots.txt and delays obeyed, hard caps on pages, bytes, depth and time, rate-limited starts, audited | M |
| S6 | A forged WhatsApp webhook, or a stranger verifying the endpoint | Every POST needs a valid body signature (constant-time comparison; unsigned failures throttled and audited); verification needs the shared token and echoes only a plain challenge; the API address is operator configuration, https only, no redirects | L |
| S7 | A crafted analytics question steering the model into reading or revealing data, or inventing a figure | The model sees only the question text and the list of figure names, never data; its reply must be a small JSON query that is validated against a fixed list (unknown figure, agent or out-of-range period is refused); the figures and the answer sentence are produced by code; the question is rate limited per key and only the chosen figure is audited, not the question | L |
| S8 | Procedures or transcripts used to talk the model into drafting an agent with extra powers, or personal data leaking to the model | Sources are masked for personal details and fenced as data; the draft keeps only a fixed set of fields, so limits, model, scopes, routes, voice and attachments cannot be set; every tool and guardrail must exist in the registry; the result is only a draft and still goes through version, scenarios, checklist, review and release gates | L |
| S9 | A forged Telegram webhook; a WhatsApp media address or template used to reach somewhere else or to message people who did not ask | Telegram calls need the secret token (constant-time, throttled, audited), the bot token never appears in errors; media is fetched only from Meta hosts over https and passes the attachment checks; templates go only to approved names, to people who already wrote in or are on the operator's opt-in list, never after STOP, within the hourly limit | L |
| S10 | Event feed leaking conversation content, or a forged event receiver | Events carry only ids, names and short plain values (no text, no nested data), are built from audit records for staff actions, and are signed like reply webhooks with a replay window; the feed needs the auditor/admin role; the address is operator configuration and is in the residency report | L |
| S11 | Identity checks bypassed or abused: guessing codes, sending codes to other people, claiming to be verified | Six-digit codes from the system random source, keyed-hash storage, 5 tries, 10-minute expiry, send limits; the destination is never chosen by the agent or the customer; verification is bound to the conversation and customer and expires; the fact `identity_verified` is set only by the platform; the code is kept out of traces | M |
| S2 | A webhook receiver being forged to | Outgoing webhooks are signed with a timestamp; incoming SMS is signature checked | M |

### Supply chain and build
| # | Threat | Handling | Disp. |
|---|---|---|---|
| B1 | Vulnerable dependencies | `pip-audit` and `npm audit` clean at review; lock files for the web console and SDK; the backend has version floors, not a lock file | A |
| B2 | Compromised build | Images run as an unprivileged user with health checks; no secrets in images; licence and restricted-path checks in CI | M |

## Accepted residual risks (owner: the operator unless stated)

1. **Roles are server-wide** (I5, D4): a key cannot be limited to some agents or environments, and every role that can open traces can read conversation text. Mitigate by issuing few keys and using SSO groups.
2. **Pictures and PDFs reach the model unmasked and may carry hidden instructions** (C2, D6): enable per agent only where acceptable.
3. **Rate limits and daily budgets are per process** (A2, A3): with several replicas the effective limit is multiplied; put a shared limit at the proxy.
4. **No multi-factor authentication for API keys**: use SSO (the identity provider supplies MFA) for people; keep API keys for machines.
5. **Backend dependencies are not locked**: pin them in your build.
6. **Behind a reverse proxy**, set uvicorn's `FORWARDED_ALLOW_IPS` to the proxy address, otherwise every client appears to have the proxy's address and per-address limits apply to everyone at once.
7. **Not independently tested**: no external penetration test has been done; the review was done by the authors with automated scans and tests. Commission one before exposing the service to the public internet.
8. **Telephony fraud and denial of service** are limited by the bridge, not NorthCX.
