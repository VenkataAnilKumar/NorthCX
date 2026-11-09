# NorthCX Deployment Guide

Status: **Built**. Updated: 2026-11-09. Master for: deployment and every setting. The container images and the compose stack are built and tested (see Testing Strategy); a Kubernetes manifest is not provided.

## Quick start with containers
```bash
cp .env.example .env        # set NORTHCX_DB_PASSWORD, NORTHCX_API_KEY, and ANTHROPIC_API_KEY (or NORTHCX_DEMO=1)
docker compose up -d --build --wait
```
This builds the backend and web images, starts Postgres, applies the database migrations, and waits until all three services are healthy. The console is at http://localhost:3001 and the API at http://localhost:3000, both bound to 127.0.0.1. Sign in on the console's Settings page with `NORTHCX_API_KEY`, then create named keys on the Access page. Data lives in the `northcx-pg` volume and survives `docker compose down` (use `down -v` to delete it).

What the stack contains: **postgres** (16, with a health check), **backend** (Python, non-root, `/health` for liveness and `/ready` for readiness, which checks the database), and **web** (Next.js standalone server, non-root). The web console reaches the backend through a same-origin proxy whose address is fixed at image build time (`NORTHCX_API_URL`, default `http://backend:3000`); rebuild the web image if the backend moves.

For development, `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres` publishes the database on localhost so the backend can run from source.

## Bringing your own agents and tools
The image ships the example support agent. To run yours, build an image `FROM` it (or mount directories) that adds your code, and set `NORTHCX_REGISTRY=your.module:function` (returns the tool registry), `NORTHCX_AGENTS_DIR` (agent spec files) and `NORTHCX_SCENARIOS_DIR` (scenarios). Tool credentials are `NORTHCX_SECRET_<NAME>` or `NORTHCX_SECRET_<NAME>_FILE`.

## Environment reference
| Variable | Meaning | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` (`_FILE`) | Model key | required unless `NORTHCX_DEMO=1` |
| `NORTHCX_DEMO` | `1` uses the offline demo model (not an AI) | off |
| `NORTHCX_MEMORY` | Set to `0` to turn long-term customer memory off (the `remember` and `recall_memory` tools and automatic recall) | on |
| `NORTHCX_CONTEXT_PROVIDER` | `package.module:function` returning an object with `async fetch(customer_id, session_id) -> dict`; gives agents customer context from your systems | off |
| `NORTHCX_CONTEXT_URL`, `NORTHCX_CONTEXT_SECRET` (`_FILE`), `NORTHCX_CONTEXT_TTL_SECONDS`, `NORTHCX_CONTEXT_TIMEOUT` | Same, through a signed HTTPS call to your endpoint; cached (default 300 s) and limited to 3 s per call | off |
| `NORTHCX_API_KEY` (`_FILE`) | Bootstrap admin key | none; without any key the server is open |
| `NORTHCX_REQUIRE_AUTH` | `1` refuses to start without any key | off (compose sets it) |
| `NORTHCX_DATABASE_URL` (`_FILE`) | Postgres URL; migrations run at start | in-memory storage |
| `NORTHCX_REGISTRY` | `module:function` returning the tool registry | `examples.support_agent:registry` |
| `NORTHCX_AGENTS_DIR`, `NORTHCX_SCENARIOS_DIR` | Spec and scenario directories | the bundled examples |
| `NORTHCX_SECRET_<NAME>` (`_FILE`) | A credential for tools | none |
| `NORTHCX_TOKEN_SECRET` (`_FILE`) | Signing secret for customer chat tokens | derived from `NORTHCX_API_KEY`; random (tokens lost at restart) if neither is set |
| `NORTHCX_APPROVAL_TTL_SECONDS` | Expire approvals left undecided | never |
| `NORTHCX_WEBHOOK_URL`, `NORTHCX_WEBHOOK_SECRET` (`_FILE`) | Push approval results (signed) | none |
| `NORTHCX_MODEL_FALLBACKS`, `NORTHCX_MODEL_RETRIES`, `NORTHCX_MODEL_TIMEOUT`, `NORTHCX_DAILY_TOKEN_BUDGET` | Model reliability: fallback models in order, retries per model, seconds per call, and a per-server daily token cap | no fallbacks; 2 retries; 60 s; no cap |
| `NORTHCX_SSO_ISSUER`, `NORTHCX_SSO_CLIENT_ID`, `NORTHCX_SSO_CLIENT_SECRET` (`_FILE`), `NORTHCX_SSO_REDIRECT_URI` | Single sign-on for the Studio through any OpenID Connect provider. The redirect URI is `https://<studio host>/api/northcx/auth/sso/callback` and must be registered with the provider. All four are needed; needs `NORTHCX_API_KEY` or a database | off |
| `NORTHCX_SSO_ROLE_MAP`, `NORTHCX_SSO_DEFAULT_ROLE`, `NORTHCX_SSO_ROLE_CLAIM`, `NORTHCX_SSO_ALLOWED_DOMAINS` | Who gets which role: `group=role` pairs (the strongest matching role wins), a fallback role, the token claim holding groups, and an email-domain allow-list. Set a role map or a default role, otherwise nobody can sign in. Roles: admin, release_manager, developer, reviewer, auditor, viewer | claim `groups`; no default role; any domain |
| `NORTHCX_SSO_SESSION_HOURS`, `NORTHCX_SSO_LANDING` | Length of a sign-in (at most 24) and the Studio path that receives it | 8; `/sso` |
| `NORTHCX_ASSIST`, `NORTHCX_ASSIST_MODEL` | Suggestions for people who take over a conversation (suggested reply, next steps, key facts, cautions): `off`, `on-demand` (a button on the hand-off) or `auto` (drafted when the hand-off is created and added to the helpdesk as a private note). Suggestions are never sent to the customer by themselves | `on-demand`; the agent model |
| `NORTHCX_ATTACHMENT_SCAN_URL` | Scanning service for attachments (for example a ClamAV wrapper). Each uploaded file is posted to it; it must answer `{"clean": true}` or the file is refused. If it is unreachable the file is refused. Attachments themselves are enabled per agent in its spec (`attachments: [image, pdf, text]`) | none: files are checked by content type, size and count only |
| `NORTHCX_CORS_ORIGINS` | Websites allowed to call the API from a browser, for the SDK and widget: comma-separated exact origins (`https://www.example.com`; `http://localhost` is allowed for testing; no wildcards or paths). Calls still need a chat token; this only lets the browser make them | none: browsers on other sites are blocked |
| `NORTHCX_VOICE_AGENT`, `NORTHCX_VOICE_BRAND`, `NORTHCX_VOICE_LANGUAGE` | Phone calls: the agent that answers, how the greeting names you, and the greeting language. Switches on `wss://<server>/v1/voice/stream` for your telephony bridge (`docs/05-technical/NorthCX_Voice.md`) | off |
| `NORTHCX_VOICE_RECORDING`, `NORTHCX_VOICE_TRANSFER`, `NORTHCX_VOICE_TRUST_CALLER_ID` | `off` or `consent` (the caller is asked and recording starts only after a yes); queue-to-number transfer targets (`default=+1555...,billing=+1555...`; E.164 or `sip:`); `1` to treat the caller ID as the customer (it can be faked, so leave off unless your carrier verifies it) | no recording; callback promise instead of transfer; caller anonymous |
| `NORTHCX_EMBEDDINGS_URL`, `NORTHCX_EMBEDDINGS_MODEL`, `NORTHCX_EMBEDDINGS_API_KEY`, `NORTHCX_EMBEDDINGS_DIMENSIONS`, `NORTHCX_EMBEDDINGS_SOURCE_MODELS`, `NORTHCX_ANN_THRESHOLD` | Meaning-based knowledge search. Point at any service that speaks the common embeddings API (hosted, or one you run yourself so nothing leaves your network); https only (http for localhost). Needs Postgres with the pgvector extension (the shipped `docker-compose.yml` uses an image that has it; elsewhere an administrator runs `CREATE EXTENSION vector` once). Passages are embedded in the background; until then, and whenever the service is down, search uses keywords only. See the Knowledge design document | keyword search only |
| `NORTHCX_CRAWL_HOSTS`, `NORTHCX_CRAWL_ALLOW_PRIVATE` | Websites the knowledge crawler may read (host names, optionally with `:port`; https only, http for localhost). Nobody can crawl a host that is not listed. Addresses inside private networks are refused unless `NORTHCX_CRAWL_ALLOW_PRIVATE=1`. See the Knowledge design document | crawling off |
| `NORTHCX_RETENTION_DAYS` | Erase conversations idle longer than this many days (checked hourly, recorded in the audit log) | keep forever |
| `NORTHCX_SUMMARIZE_AFTER_TOKENS`, `NORTHCX_SUMMARY_MODEL` | Summarise the older part of a conversation once its saved history passes this estimated size (keeps the last four customer messages); optional cheaper model for the notes | off |
| `NORTHCX_EMAIL_FROM`, `NORTHCX_SMTP_URL` (`_FILE`), `NORTHCX_EMAIL_AGENT`, `NORTHCX_EMAIL_FROM_NAME`, `NORTHCX_EMAIL_TRUST_AUTH_RESULTS`, `NORTHCX_EMAIL_MAX_REPLIES_PER_HOUR` | Email channel: enabled when `NORTHCX_EMAIL_FROM` and `NORTHCX_SMTP_URL` are set; point your mail gateway at `POST /v1/channels/email/inbound` with a `channel` key | off; 10 replies/hour/sender |
| `NORTHCX_SMS_NUMBER`, `NORTHCX_SMS_ACCOUNT_SID`, `NORTHCX_SMS_AUTH_TOKEN` (`_FILE`), `NORTHCX_SMS_WEBHOOK_URL`, `NORTHCX_SMS_AGENT`, `NORTHCX_SMS_MAX_REPLIES_PER_HOUR` | SMS channel (Twilio-compatible). Enabled when the number is set; point the provider's incoming-message webhook at `NORTHCX_SMS_WEBHOOK_URL` (the exact public URL of `POST /channels/sms/twilio`, which is part of the signed data) | off; agent `support`; 20 replies/hour/number |
| `NORTHCX_WHATSAPP_PHONE_ID`, `NORTHCX_WHATSAPP_TOKEN`, `NORTHCX_WHATSAPP_APP_SECRET`, `NORTHCX_WHATSAPP_VERIFY_TOKEN` (each secret also as `_FILE`), `NORTHCX_WHATSAPP_AGENT`, `NORTHCX_WHATSAPP_MAX_REPLIES_PER_HOUR`, `NORTHCX_WHATSAPP_API_URL` | WhatsApp channel through the Meta Cloud API. Register `https://<host>/channels/whatsapp/meta` as the webhook with the verify token; incoming calls must carry the app secret signature. See the Channels document | off |
| `NORTHCX_WHATSAPP_AGENTS`, `NORTHCX_WHATSAPP_TEMPLATES`, `NORTHCX_WHATSAPP_OPTIN_FILE` | More WhatsApp settings: an agent per phone number id (several ids are allowed in `NORTHCX_WHATSAPP_PHONE_ID`), the approved template names you may send with their language, and a file of people who opted in and may receive a template before they have messaged you. See the Channels document | one number, no templates |
| `NORTHCX_TELEGRAM_TOKEN`, `NORTHCX_TELEGRAM_SECRET` (each also as `_FILE`), `NORTHCX_TELEGRAM_AGENT`, `NORTHCX_TELEGRAM_MAX_REPLIES_PER_HOUR`, `NORTHCX_TELEGRAM_API_URL` | Telegram bot channel. Register `https://<host>/channels/telegram/webhook` with `setWebhook` and `secret_token` set to the secret; every call must carry it | off |
| `NORTHCX_ANTHROPIC_CLIENT` | `sdk` (the official Anthropic SDK) or `http` (a direct HTTPS client to the same API, same request and response, errors carry the HTTP status). Use `http` to run without the SDK's own dependencies being exercised; both pass the same conformance tests | `sdk` |
| `NORTHCX_RESOLUTION_WINDOW_DAYS` | Days a conversation must stay quiet (no new turns, completed, never handed to a person) before it counts as resolved in the provisional resolution rate shown beside containment; conversations inside the window are reported as pending | `3` |
| `NORTHCX_ROLE` | `all`, `api` or `worker`. `all` serves requests and runs the background jobs (outbox retries, approval expiry, trace export, alert evaluation, human-inbox delivery, retention, meaning-search indexing, crawl schedules). `api` serves requests only; `worker` runs the jobs only and should not receive customer traffic (it still answers `/ready`). Each job pass takes a database lease first, so several workers never repeat one another's work and a worker that dies lets its lease expire. `api` and `worker` need `NORTHCX_DATABASE_URL`, and `NORTHCX_LIMITS_BACKEND=postgres` is advised | `all` |
| `NORTHCX_LIMITS_BACKEND` | `memory` or `postgres`. With `postgres`, rate limits, the abuse burst check and the daily token budget are counted in the database, so several server processes share one limit (fixed one-minute windows; if the database is unreachable each process falls back to its own counters and logs a warning, never to no limit). Needs `NORTHCX_DATABASE_URL`; costs one small database write per limited request | `memory` |
| `NORTHCX_ROUTING_FILE` | YAML file with business hours, holidays, time zone and hand-off queues (see Handoff and Approvals Spec) | one always-open queue |
| `NORTHCX_TRANSCRIBE_URL`, `NORTHCX_TRANSCRIBE_MODEL`, `NORTHCX_TRANSCRIBE_API_KEY` (`_FILE`) | Speech-to-text for building agents from call recordings. Any service with the common `POST <url>/audio/transcriptions` API (hosted, or one you run so audio stays in your network); https only (http for localhost). Recordings (mp3, wav, ogg, flac, m4a, webm, up to 25 MB) are sent there and not stored. Reported in the residency report | off |
| `NORTHCX_EVENTS_WEBHOOK_URL`, `NORTHCX_EVENTS_WEBHOOK_SECRET` (`_FILE`), `NORTHCX_EVENTS` | Status events for other systems: signed JSON calls when a hand-off is created, an approval is requested or decided, an alert fires, a release is published or rolled back, and so on (see the Integrations document). The secret must be at least 16 characters. `NORTHCX_EVENTS` limits the types. Undelivered events are retried with back-off and can also be polled from `GET /v1/events` | off |
| `NORTHCX_VERIFY`, `NORTHCX_VERIFY_VALID_MINUTES` | `1` adds two tools, `send_verification_code` and `check_verification_code`. A code is sent only to the email address (`email` fact) or phone number (`phone` fact) your own systems reported for the customer (see customer context), by the configured email or SMS channel; a correct code makes the conversation verified for the given minutes (default 30), shown as the fact `identity_verified: yes`. Needs `NORTHCX_API_KEY` or `NORTHCX_TOKEN_SECRET` and email or SMS. See the Channels document | off |
| `NORTHCX_RESIDENCY_FILE` | YAML data-residency policy: the deployment region, the regions data may be sent to, which host belongs to which region, and `strict`. Every configured destination (database, model, embeddings, exporters, webhooks, email, SMS, WhatsApp, business systems) is checked at start-up; in strict mode an unmapped or disallowed one stops the server. Reported at `/v1/residency` and in Studio (Data residency). See `examples/config/residency.example.yaml` and the Security and Compliance document | not checked |
| `NORTHCX_INBOX_WEBHOOK_URL`, `NORTHCX_INBOX_WEBHOOK_SECRET` (`_FILE`), `NORTHCX_PUBLIC_CONSOLE_URL` | Push every hand-off (with its package) and its resolution to a helpdesk as signed webhooks; the console URL becomes a link in the payload | off |
| `NORTHCX_STRICT_PROMOTION` | `1` = production accepts only versions that have been live in staging | off |
| `NORTHCX_RERUN_ON_KNOWLEDGE` (`off`, `scripted`, `live`), `NORTHCX_RERUN_DEBOUNCE_SECONDS` | Re-run scenarios tagged `knowledge` after knowledge changes; failures raise a critical monitoring finding | off; 60 s |
| `NORTHCX_SKILLS_DIR` | Directory of skill files (YAML) added to the registry at start-up | none |
| `NORTHCX_CONNECTORS_DIR`, `NORTHCX_CONNECTOR_HOSTS` | Directory of connector files (tools defined as data) and the comma-separated hosts they may call; a connector whose host is not listed is refused at start-up | none |
| `NORTHCX_TEMPLATES_DIR` | Directory of extra agent templates (YAML); a template with the id of a built-in one replaces it | built-in four |
| `NORTHCX_ALERTS` (`on`/`off`), `NORTHCX_ALERT_RULES` (YAML file), `NORTHCX_ALERT_WEBHOOK_URL`, `NORTHCX_ALERT_WEBHOOK_SECRET` (`_FILE`) | Alerts on error rate, escalation spikes, guardrail blocks, tool failures, fallback-model use and slow replies; findings always, signed webhook optionally. A webhook delivery is tried up to three times (immediately, after 1 s, after 5 s) and the outcome is shown on the Monitoring page; "Send a test alert" there (admins) checks the webhook end to end. Alert history and active alerts are kept in memory per process (findings are stored), so after a restart they start empty, and with several processes each one evaluates and sends on its own | on, six default rules |
| `NORTHCX_PRICE_PER_MILLION_TOKENS` | A blended price used to show an estimated model cost in Insights | no cost shown |
| `NORTHCX_LANGFUSE_URL`, `NORTHCX_LANGFUSE_PUBLIC_KEY`, `NORTHCX_LANGFUSE_SECRET_KEY` (`_FILE`) | Export traces to Langfuse | off |
| `NORTHCX_OTLP_ENDPOINT`, `NORTHCX_OTLP_HEADERS` (`_FILE`; `name=value,name=value`) | Export traces over OpenTelemetry OTLP/HTTP to any compatible backend | off |
| `NORTHCX_TRACE_EXPORT_CONTENT` (`none`, `masked`, `full`), `NORTHCX_TRACE_EXPORT_SAMPLE` (0 to 1), `NORTHCX_ENVIRONMENT` | What exported traces contain (default `masked`), the fraction exported (default 1), and the environment label (default `production`) | masked; all; production |
| `NORTHCX_CHATWOOT_URL`, `NORTHCX_CHATWOOT_ACCOUNT_ID`, `NORTHCX_CHATWOOT_INBOX_ID`, `NORTHCX_CHATWOOT_TOKEN` (`_FILE`) | Create a Chatwoot conversation with a private note for each hand-off and close it when resolved | off |
| `NORTHCX_RATE_LIMITS` (`off`), `NORTHCX_RATE_LIMIT_PER_MINUTE`, `NORTHCX_CHAT_PER_SESSION_PER_MINUTE`, `NORTHCX_AUTH_FAILURES_PER_MINUTE`, `NORTHCX_CHANNEL_RATE_LIMIT_PER_MINUTE` | Per-process limits; the last applies to keys with the `channel` role (your server minting chat tokens, telephony bridges), which serve many customers at once | 600 / 30 / 20 / 6000 |
| `NORTHCX_DB_POOL_SIZE` | Database connections each server process keeps (plus 10 extra under load). Keep processes x (size + 10) below Postgres `max_connections` | 20 |
| `NORTHCX_TRACE_DIR` | Also write traces to JSON lines (in-memory mode) | none |
| `PORT` | Backend port inside the container | 3000 |
| `NORTHCX_BIND`, `NORTHCX_BACKEND_PORT`, `NORTHCX_WEB_PORT` | Compose: listen address and host ports | 127.0.0.1, 3000, 3001 |

## Operating it
- **Upgrades:** pull or build the new images and run `docker compose up -d --build --wait`. Migrations apply on start and only move forward; take a database backup first. Rolling the images back across a migration needs the matching database backup.
- **Backups:** back up the Postgres volume or use `pg_dump`. Everything lives there: conversations (personal data), approvals, handoffs, versions and releases, keys (hashes), the audit log and simulation runs. Treat backups as sensitive.
- **Health:** probe `/ready` (load balancers, orchestrators); `/health` is liveness only. Logs go to standard output.
- **Scaling:** the backend is stateless apart from per-process rate-limit buckets, so run several behind a load balancer; all state is in Postgres. Two simultaneous messages in one conversation can still overwrite each other (see Knowledge and Memory).
- **TLS and exposure:** the compose file listens on loopback only. Put a reverse proxy that terminates TLS in front (and set `NORTHCX_BIND` only if you must publish directly).

## Environments
| Env | Setup |
|---|---|
| Local | One compose file starts Postgres, the backend and the Studio; model API key from the environment. The TypeScript prototype (in `src/prototype`, a reference implementation, not the product) still runs with `npm install && ANTHROPIC_API_KEY=... npm run dev` (in-memory, state lost on restart) |
| Staging/production | Container image for the server, Postgres, optional queue |

## Storage
Set `NORTHCX_DATABASE_URL` (for example `postgresql://northcx:northcx@localhost:5432/northcx`) to use Postgres; pending migrations are applied at startup. Without it the backend uses in-memory storage and logs a warning. `docker-compose.yml` starts a development Postgres. Migrations live in `src/backend/northcx/db/migrations` and are checked against the models in tests.

## Approvals and notifications
`NORTHCX_APPROVAL_TTL_SECONDS` expires approvals that wait too long (escalating the conversation); unset, approvals wait indefinitely. `NORTHCX_WEBHOOK_URL` with `NORTHCX_WEBHOOK_SECRET` pushes approval results to your system, signed with HMAC-SHA256; the receiver should verify the signature and the five-minute timestamp window.

## Releasing agent changes
Spec files provide the baseline agent. To change what customers get, save a new version, run its scenarios, publish it, and roll back if needed (see Release Management). Releases are stored in the database, so every server process serves the same version immediately; without a database they last only until restart. Back up the `agent_versions` and `releases` tables with the rest of the database.

## Agents and scenarios
The server loads agent specs from `NORTHCX_AGENTS_DIR` and scenarios from `NORTHCX_SCENARIOS_DIR` (both default to the bundled examples) and exposes the simulation API and release gate. In CI, run `python -m northcx.simulation ... --record --source ci --meta commit=$SHA` with `NORTHCX_DATABASE_URL` set so each build records its result.

## Access and keys
1. Set `NORTHCX_API_KEY` to a long random value. It is the bootstrap admin key, used to create everything else; store it in a secrets manager.
2. Set `NORTHCX_REQUIRE_AUTH=1` so the server refuses to start without any key.
3. Sign in to the web console (Settings) with the bootstrap key, open Access and audit, and create named keys with the least role that works: a `channel` key for each customer-facing channel, `reviewer` and `release manager` keys for people, `auditor` for compliance, and a `developer` key for CI. Use expiry for keys held by systems. Then keep the bootstrap key offline and revoke people's access by revoking their keys.
4. Without a bootstrap key, create the first admin key from a shell that has the database URL: `python -m northcx.keys create --name alice --role admin`. `list` and `revoke` also exist there.

Rate limits are on by default (`NORTHCX_RATE_LIMIT_PER_MINUTE`, `NORTHCX_CHAT_PER_SESSION_PER_MINUTE`, `NORTHCX_AUTH_FAILURES_PER_MINUTE`; `NORTHCX_RATE_LIMITS=off` disables them) and are per process unless you set `NORTHCX_LIMITS_BACKEND=postgres` (then all server processes share them). Put the server behind TLS; keys and customer messages travel in clear text otherwise. Copy the `head` value from the audit integrity check to an external place regularly.

## Configuration
Environment variables: model API key, server port, API keys for clients, database URL, trace export endpoint, retention settings. Secrets via a secrets manager.

## Environments
dev, staging and production are separate deployments or namespaces with separate secrets, databases and API keys. Promotion of agent versions follows the Release Management spec.

## Release steps
1. Typecheck and unit tests pass.
2. Required simulations pass.
3. Build and tag the image.
4. Deploy to staging; smoke test chat and a handoff.
5. Promote; watch error rate, escalation rate and guardrail blocks.

## Rollback
Redeploy the previous image; agent definitions are versioned so a prior version can be republished.

## Operations
Health endpoint, structured logs, alerts on error rate and model latency, regular backup and retention jobs.

## Capacity

See `NorthCX_Performance.md`: about 50 conversation turns per second per server process with Postgres on a small machine, scaling with the number of processes; use `python -m northcx.loadtest` against your own deployment before launch.

## Running several processes

One process (`NORTHCX_ROLE=all`, the default) is enough for a small deployment. To scale out or to keep background work off the request path:

```
customers / Studio ──► load balancer / proxy ──► API replicas  (NORTHCX_ROLE=api,    N copies)
                                                    │
                                                    ▼
                                              Postgres (+ a connection pooler for many replicas)
                                                    ▲
                                                    │
                                                 workers      (NORTHCX_ROLE=worker, 1 to 3 copies; no customer traffic)
```

Every process needs the same `NORTHCX_DATABASE_URL`, `NORTHCX_API_KEY` (or `NORTHCX_TOKEN_SECRET`, so chat tokens work on every replica), agent and scenario files, and `NORTHCX_LIMITS_BACKEND=postgres`. What the roles do:

| Work | Where it runs | How duplicates are avoided |
|---|---|---|
| Serving requests (chat, Studio, webhooks, channels) | `api` and `all` | The processes keep no conversation state; everything is in the database |
| Outbox retries, approval expiry, trace export, alert evaluation, human-inbox delivery, retention | `worker` and `all` | Each pass takes a database lease for that job (`job_leases`), runs, and gives it back; a worker that dies lets the lease expire (two minutes) and another takes over |
| Meaning-search indexing, crawl schedules | `worker` and `all` | Writes are idempotent, and schedules are claimed atomically |
| Alert state, alert events, crawl progress | The database | Any process shows and continues them |
| Rate limits, abuse burst check, daily token budget | The database | `NORTHCX_LIMITS_BACKEND=postgres` |

Things to know. Chat turns that ask a person to approve something wait in the database, so any replica can finish them. A crawl runs in the process that was asked to start it (an API replica when you start one from Studio) and reports progress to the database; if that process stops, its crawl stops and the job shows as running until its heartbeat goes stale after five minutes. Give workers the `/ready` check but no route from the load balancer. `tests/test_multi_replica.py` starts two API replicas and two workers against one database as part of the normal backend test run.

## Behind a reverse proxy

Terminate TLS at a proxy and keep the API on a private network. Tell uvicorn which proxy to trust so per-address limits see the real client: set `FORWARDED_ALLOW_IPS` to the proxy's address (uvicorn's own setting; the default only trusts 127.0.0.1). Without it every client appears to have the proxy's address, and one noisy client can trigger limits for everyone. With several replicas set `NORTHCX_LIMITS_BACKEND=postgres` so rate limits and daily token budgets are shared (a proxy limit in front is still a good first line of defence). Requests are capped by size per endpoint (1 MB, 11 MB for uploads); set the proxy's body limit at or above 12 MB.

## Browser smoke test

`src/apps/studio/e2e/smoke.mjs` drives a running stack in a real browser (Playwright): connecting with a key, the review queue, insights, the publish checklist, a staged rollout, the agent editor (journeys, languages) and the single sign-on landing page, then loads every main page and fails on any client error. Start the backend and the web console, then:

```bash
cd src/apps/studio && API_KEY=<admin key> WEB_URL=http://localhost:3001 API_URL=http://localhost:3000 node e2e/smoke.mjs
```

It creates one fresh conversation each run, so it can be repeated. The single sign-on round trip was also checked in a browser against a local OpenID Connect provider (sign in, role from groups, sign out, refusal of an unmapped person).
