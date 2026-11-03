# NorthCX API Design

Status: Draft

Base path `/v1`. JSON. `Authorization: Bearer <key>` (required once any key exists; see Security). Errors: `401` missing or invalid key (`token_expired` for a lapsed chat token), `403` the role lacks the permission, `429` rate limited (with `Retry-After`). `GET /` and `GET /health` are public.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness (public) |
| POST | `/chat-tokens` | `{sessionId?, customerId?, agent?, ttlSeconds?}`: mint a chat token for one conversation (channel or admin key); returns `token`, `sessionId`, `expiresAt` (built) |
| POST | `/agents/{id}/chat/stream` | Same request and access rules as chat, answered as server-sent events: `started`, `progress` (`{type: tool, name}`) while tools run, `delta` pieces of the approved reply, then `done` (the full chat response) or `error`. No `Idempotency-Key` (400) (built) |
| GET | `/memories?customerId=` | A customer's long-term memories, newest first (`memory:read`: admin, developer, release manager, reviewer; audited; 501 when memory is off) (built) |
| DELETE | `/memories/{id}?customerId=` | Forget one memory (`memory:manage`, admin only) (built) |
| DELETE | `/memories?customerId=` | Forget all of a customer's memories (built) |
| GET | `/privacy/customers/{id}/export` | Everything held for a customer as JSON: facts and, per conversation, messages, traces, outbox, approvals, hand-offs, monitoring findings and email thread (`privacy:manage`, admin only; audited) (built) |
| DELETE | `/privacy/customers/{id}` | Erase a customer's conversations, facts and everything linked to them; returns counts (built) |
| DELETE | `/privacy/sessions/{id}` | Erase one conversation (built) |
| POST | `/privacy/retention/run` | `{olderThanDays}`: erase conversations idle longer than that (built) |
| GET, POST | `/knowledge/sources` | List or create a knowledge source (`id`, `name`, optional `staleAfterDays`); `knowledge:read` / `knowledge:write` (built) |
| DELETE | `/knowledge/sources/{id}` | Delete a source and all its documents (built) |
| PUT | `/knowledge/sources/{id}/documents/{externalId}` | Add or update a document (`title`, `text`, optional `url`, `sourceUpdatedAt`); returns `created`, `updated` or `unchanged` (built) |
| DELETE | `/knowledge/sources/{id}/documents/{externalId}` | Delete a document and its passages at once (built) |
| GET | `/knowledge/documents` | List documents with freshness; `source`, `stale=true`, `limit` (built) |
| GET | `/knowledge/search` | `q`, `source`, `limit`: ranked passages with title, URL, section, `updatedAt`, `stale` (built) |
| POST | `/knowledge/sources/{id}/import` | `filename` (and optional `externalId`, `url`): the file is the body (PDF, HTML, Markdown, text) (`knowledge:write`) (built) |
| POST | `/knowledge/sources/{id}/crawl` | `url`, `maxPages`, `maxDepth`, `delaySeconds`, `includePaths`, `excludePaths`, `useSitemap`, `prune`: starts a background crawl of an operator-listed host; 202 with a job (`knowledge:write`) (built) |
| GET | `/knowledge/crawls`, `/knowledge/crawls/{id}` | crawl progress and outcome (`knowledge:read`) (built) |
| POST | `/alerts/test` | send a test alert through the real delivery path and report whether the receiver accepted it (`keys:manage`) (built) |
| GET | `/monitor/findings` | Monitoring flags, newest first; filters `rule`, `severity`, `agentId`, `sessionId`, `since`, `limit` (`monitor:read`, built) |
| GET | `/monitor/summary` | Counts per rule and severity, rule names, total (built) |
| POST | `/channels/email/inbound` | Raw RFC 822 message as the body (≤ 1,000,000 bytes), `channel:inbound` permission; returns `{status, sessionId, reason, traceId, handoffId}`; 400 unusable, 413 too large, 501 not configured (built) |
| GET | `/me` | The caller's name, role and permissions (any key) |
| GET | `/keys` | Keys (never secrets) and each role's permissions (admin) (built) |
| POST | `/keys` | `{name, role, expiresInDays?}`: create a key; the secret is returned once (admin) (built) |
| POST | `/keys/:id/revoke` | Revoke a key at once; the last admin key is protected (admin) (built) |
| GET | `/audit?limit=&before=&actor_name=&action=` | Audit entries, newest first (audit:read) (built) |
| GET | `/audit/verify` | Check the hash chain; returns `ok`, `checked`, `brokenAt`, `reason`, `head` (built) |
| POST | `/agents/:id/chat` | Send a message; body `{sessionId, message, customerId?}` |
| GET | `/traces/:id` | Fetch a trace |
| GET | `/traces?sessionId=` | List traces for a session |
| POST | `/agents/:id/versions` | `{spec | specYaml | fromBaseline, by, note?}`: save the next version (built) |
| GET | `/agents/:id/versions`, `/agents/:id/versions/:n` | List and read versions with their YAML (built) |
| GET | `/agents/:id/versions/:a/diff/:b` | Reviewable diff between two versions (built) |
| POST | `/agents/:id/releases` | `{version, by, note?}`: publish; 409 `gate_not_satisfied` with `reasons` unless the gate passes for that version (built) |
| POST | `/agents/:id/rollback` | `{by, note?, toVersion?}`: restore a previously live version or the spec file; no gate (built) |
| GET | `/agents/:id/releases`, `/agents/:id/live` | Release history; what is serving now (built) |
| GET | `/simulations/scenarios` | Scenarios and available modes (built) |
| POST | `/simulations/runs` | `{mode, only?, skipJudge?, agent?, version?}`: run scenarios (against a saved version if given) and store the result; 409 if a run is in progress (built) |
| GET | `/simulations/runs`, `/simulations/runs/:id` | Stored runs and a full report (built) |
| GET | `/simulations/gate?agent=&version=` | Whether the agent's spec file, or a saved version, passed every required scenario (built) |
| GET | `/audit` | Query the audit log (Phase 2) |
| DELETE | `/customers/:id` | Delete a customer's data (Phase 3) |
| GET | `/approvals?state=` | List approvals (built) |
| POST | `/approvals/:id/decision` | `{approved, by, note?}`: records the decision, runs the action once if approved, continues the conversation; returns the approval plus `resume` (`reply`, `status`, `traceId` or `error`). 404 unknown, 409 already decided |
| POST | `/approvals/expire` | `{olderThanSeconds}`: expire stale pending approvals and escalate (built) |
| GET | `/handoffs?state=&sessionId=` | Handoff queue (summaries) (built) |
| GET | `/handoffs/:id` | One handoff with its full package (built) |
| POST | `/handoffs/:id/resolve` | `{by, note?, returnToAgent?}`: mark resolved once (409 if already resolved); by default the agent is told what happened and carries on with the customer (built) |
| GET | `/sessions/:id/outbox?after=` | Messages sent outside a request, such as approval results (built) |

## Chat response
`{reply, status: "completed"|"escalated"|"needs_approval", traceId, pendingApprovals[], handoffId}` (`handoffId` is set when the status is `escalated`)

## Errors
`400` invalid body, `401` bad key, `404` unknown agent or trace, `429` rate limited, `500` internal. Error body `{error: {code, message}}`.

## Later
Server-sent events for streaming, webhooks for status changes, pagination for lists.


## Idempotency

`POST /v1/agents/{id}/chat` accepts an `Idempotency-Key` header (1-200 visible ASCII characters). A retry with the same key, caller, agent and conversation returns the first response unchanged with `Idempotent-Replay: true` and does not run the agent again. The same key with a different message or customer returns 422 `idempotency_key_reused`; a request still running returns 409 `request_in_progress`. Keys are kept 24 hours; a request that never finished (for example a crash) can be retried after five minutes. Failed requests (unknown agent, internal error) are not stored, so retrying them runs normally. Email deliveries are deduplicated by Message-ID instead.


## Streaming

`POST /v1/agents/{id}/chat/stream` returns `text/event-stream`. The agent's work and every supervisor check finish before the first `delta` is sent, so a customer never sees text a check could still reject; the pieces are the approved reply, split at word boundaries (joined they equal `reply` exactly). Progress events let a client show "Using lookup order…" during the wait. If the client disconnects, the turn still completes and is saved. Streaming of tokens straight from the model is not used because it would expose unchecked drafts.


| POST | `/agents/{id}/releases` | Body `{version, environment?}` (default `production`). Dev needs no proof; staging and production need the release gate for that exact version. Dev and staging need `versions:create`; production also needs `releases:publish` (built) |
| POST | `/agents/{id}/promote` | `{to: staging|production, note?}`: release what is live in the environment before it (dev, then staging), gated like any release (built) |
| POST | `/agents/{id}/rollback` | `{environment?, toVersion?}` restores something that was live before in that environment; production needs `releases:rollback` (built) |
| GET | `/agents/{id}/environments` | What is released in dev, staging and production and what each actually serves (built) |
| GET | `/agents/{id}/releases?environment=`, `/agents/{id}/live?environment=` | History and the live agent for one environment (built) |
| GET | `/sessions/{id}/scenario-draft` | A scenario drafted from a real conversation (masked), with warnings; `simulations:run`; audited (built) |
| GET | `/templates`, `/templates/{id}` | Agent templates and their parameters (built) |
| POST | `/templates/{id}/render` | `{agentId, params}`: the filled-in spec YAML, scenario YAML, missing tools and warnings; saves nothing (`versions:create`) (built) |
| POST | `/templates/{id}/create-version` | Render and save as a new version of `agentId`; refused when the deployment lacks a tool the template needs (built) |
| GET | `/catalog` | The building blocks an editor can offer: tools (effect, approval, inputs), guardrails with an example setting, input and output checks, skills (built) |
| POST | `/agents/{id}/versions/preview` | `{spec}`: every problem found, the digest, whether it equals the latest version, and what differs from production; saves nothing (`versions:create`) (built) |
| GET | `/simulations/scenarios`, `/simulations/scenarios/{name}` | All scenarios (files and saved), with `source` (`file` or `managed`), `editable`, tags and digest; the detail includes the definition and its YAML (built) |
| POST | `/simulations/scenarios/validate` | `{yaml}` or `{scenario}`: check a scenario without saving (`scenarios:write`) (built) |
| POST, PUT, DELETE | `/simulations/scenarios[/{name}]` | Create, change or delete a saved scenario (`scenarios:write`: developers and up). Creating, changing or deleting a *required* scenario, or making one required, needs `scenarios:require` (release managers, admins). File scenarios cannot be changed here; a scenario cannot be renamed; all audited (built) |
| GET | `/knowledge/sources/{id}/documents/{externalId}` | One document with its original text for editing (`text`), `textRebuilt` true when it was saved before the text was kept and had to be put back together from its passages (built) |
| GET | `/skills` | Skills available to agents, with their steps and tools (built) |
| GET | `/insights/overview`, `/insights/timeseries`, `/insights/failures`, `/insights/gaps` | Metrics with numerator, denominator and period; `from`, `to` (epoch seconds, default last 7 days, at most 366), `agent`, `environment`; timeseries takes `bucket=hour|day` (`insights:read`) (built) |
| POST | `/sessions/{id}/feedback` | `{rating 1-5, comment?}`: a customer's rating (chat token for its own conversation, channel or API key); a second rating replaces the first (`feedback:send`) (built) |
| WS | `/voice/stream` | the telephony bridge's connection for one call; channel key in the `Authorization` header; protocol in `NorthCX_Voice.md` (built) |
| GET | `/voice/calls` | recent calls with outcome, consent, languages and reply latency (`traces:read`) (built) |
| PUT | `/sessions/{id}/attachments` | `filename` query, the file as the request body: checks, stores and returns its id and details (`chat:send`; a customer's chat token only for its own conversation); chat requests then pass `attachments: [ids]` (built) |
| GET | `/sessions/{id}/attachments`, `/attachments/{id}` | list a conversation's files; download one served as an attachment with `nosniff` and a sandbox policy (`traces:read`) (built) |
| POST | `/handoffs/{id}/reply` | `text`: a person's message to the customer, delivered through the outbox as kind `person_reply` (`handoffs:resolve`) (built) |
| POST | `/handoffs/{id}/assist` | draft suggestions for the person handling the hand-off, stored with it; 20 per minute per key (`handoffs:resolve`) (built) |
| POST | `/agents/{id}/journeys/draft` | `description`: a journey drafted by the model from plain language, checked against the agent's tools; 10 per minute per key; needs `versions:create` (built) |
| POST | `/agents/{id}/journeys/scenarios` | `journey`: test scenario drafts, one per sample message (`simulations:run`) (built) |
| GET | `/auth/sso/config`, `/auth/sso/login`, `/auth/sso/callback` | outside `/v1`, no key: start and finish a single sign-on (built) |
| POST | `/me/logout` | end the caller's single-sign-on session (other keys are untouched) (built) |
| POST | `/agents/{id}/rollouts` | `version`, `percent` (1-99), `environment` (staging or production), `note`: start a staged rollout; blocked unless the candidate passes the checklist; production needs `releases:publish` (built) |
| GET | `/agents/{id}/rollouts` | history including the active one (`versions:read`) (built) |
| PUT | `/agents/{id}/rollouts/{rid}/percent` | change the share for new conversations (built) |
| POST | `/agents/{id}/rollouts/{rid}/promote` | publish the candidate to everyone through the normal gate (built) |
| POST | `/agents/{id}/rollouts/{rid}/abort` | stop; everyone keeps the current version (production needs `releases:rollback`) (built) |
| GET | `/agents/{id}/rollouts/{rid}/comparison` | the same measures for control and candidate with sample sizes (`insights:read`) (built) |
| GET | `/agents/{id}/versions/{n}/checklist` | `environment`: required checks (pass, fail, warn, info) with details, a change summary against what is live, and `ready` (`versions:read`) (built) |
| GET | `/reviews/queue` | `agent`, `environment`, `includeReviewed`, `sample`, `limit`: conversations worth reviewing with reasons (`traces:read`) (built) |
| GET | `/sessions/{id}/transcript` | transcript, traces, hand-offs, rating, tags and existing review (`traces:read`) (built) |
| PUT | `/sessions/{id}/review` | `verdict`, `handoff`, `failures[]`, `note`; replaces an earlier review; audited (`reviews:write`) (built) |
| GET | `/insights/review-quality` | correct rate, hand-off correctness, unneeded hand-offs, failures by kind (`insights:read`) (built) |
| GET | `/conversations/search` | `q`, `status`, `tag`, `language`, `handedOff`, `agent`, `environment`, `from`, `to`, `limit`: conversations with masked snippets, outcome, rating and tags (`traces:read`) (built) |
| GET, PUT, DELETE | `/sessions/{id}/tags[/{tag}]` | Read, add or remove a tag (1-40 lowercase letters, digits, - or _; at most 20 per conversation); add and remove need `conversations:tag` (reviewers, developers, admins) (built) |
| GET | `/alerts` | Alert rules, alerts firing now and recent events (`insights:read`) (built) |
| GET | `/regression` | Whether simulations re-run on knowledge changes and how the last re-run went (built) |
| GET | `/trace-export` | Whether export is on, exporters, content mode, sampling and delivery counts (`traces:read`) (built) |
| GET | `/traces/{id}/exports` | Delivery state of one trace per exporter (built) |
| GET | `/handoffs/{id}/inbox` | Where a hand-off has been sent: per connector and event, attempts, reference, last error (built) |


Chat requests (`/chat`, `/chat/stream`) accept `environment` (`dev`, `staging`, `production`). Only keys with `simulations:run` may use dev or staging; customer tokens and channel keys always get production. Each trace records the environment that answered.

`POST /v1/templates/{id}/create-version` also accepts `saveScenarios: true`: the template's tests are saved with the version (as required scenarios only when the caller holds `scenarios:require`), and the response lists `scenariosSaved` and `scenariosSkipped`.
