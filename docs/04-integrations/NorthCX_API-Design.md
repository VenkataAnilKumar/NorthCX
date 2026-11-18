# NorthCX API Design

Status: **Built**. Updated: 2026-11-09. Master for: the HTTP API (the generated reference is docs/api).

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
| POST | `/knowledge/sources/{id}/import` | `filename` (and optional `externalId`, `url`): the file is the body (PDF, Word, PowerPoint, Excel, HTML, Markdown, text) (`knowledge:write`) (built) |
| POST | `/knowledge/sources/{id}/crawl` | `url`, `maxPages`, `maxDepth`, `delaySeconds`, `includePaths`, `excludePaths`, `useSitemap`, `prune`: starts a background crawl of an operator-listed host; 202 with a job (`knowledge:write`) (built) |
| GET | `/knowledge/crawls`, `/knowledge/crawls/{id}` | crawl progress and outcome (`knowledge:read`) (built) |
| POST | `/events/test` | send a signed sample status event to the configured events webhook and report whether the receiver accepted it; marked as a test, not stored or retried; audited; six a minute per key (built) |
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
| GET | `/simulations/scenarios` | Scenarios and available modes (built) |
| POST | `/simulations/runs` | `{mode, only?, skipJudge?, agent?, version?}`: run scenarios (against a saved version if given) and store the result; 409 if a run is in progress (built) |
| GET | `/simulations/runs`, `/simulations/runs/:id` | Stored runs and a full report (built) |
| GET | `/simulations/gate?agent=&version=` | Whether the agent's spec file, or a saved version, passed every required scenario (built) |
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
`400` invalid body, `401` missing or invalid key, `403` the role lacks the permission, `404` unknown resource, `409` a conflict (already decided, already resolved, a run in progress, gate not satisfied), `413` body too large, `429` rate limited (with `Retry-After`), `501` a feature that is not configured, `503` the live agent version cannot be built (`agent_unavailable`; roll back), `500` internal. Error body `{error: {code, message}}`.

## Later
Built since this section was first written: server-sent events for streaming and signed webhooks for status events. Still open: consistent pagination across every list (most lists take `limit` and some `before` or `after`). The staff platform adds `/v1/workspace/*`, `/v1/hub/*` and policy routes (designed, `../13-workspace/NorthCX_Staff-Platform-Architecture.md`).


## Idempotency

`POST /v1/agents/{id}/chat` accepts an `Idempotency-Key` header (1-200 visible ASCII characters). A retry with the same key, caller, agent and conversation returns the first response unchanged with `Idempotent-Replay: true` and does not run the agent again. The same key with a different message or customer returns 422 `idempotency_key_reused`; a request still running returns 409 `request_in_progress`. Keys are kept 24 hours; a request that never finished (for example a crash) can be retried after five minutes. Failed requests (unknown agent, internal error) are not stored, so retrying them runs normally. Email deliveries are deduplicated by Message-ID instead.


## Streaming

`POST /v1/agents/{id}/chat/stream` returns `text/event-stream`. The agent's work and every supervisor check finish before the first `delta` is sent, so a customer never sees text a check could still reject; the pieces are the approved reply, split at word boundaries (joined they equal `reply` exactly). Progress events let a client show "Using lookup order…" during the wait. If the client disconnects, the turn still completes and is saved. Streaming of tokens straight from the model is not used because it would expose unchecked drafts.

## More routes (added after the first table)

| Method | Path | Purpose |
|---|---|---|
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
| WS | `/voice/stream` | the telephony bridge's connection for one call; channel key in the `Authorization` header; protocol in `../01-chat/NorthCX_Voice.md` (built) |
| GET | `/voice/calls` | recent calls with outcome, consent, languages and reply latency (`traces:read`) (built) |
| PUT | `/sessions/{id}/attachments` | `filename` query, the file as the request body: checks, stores and returns its id and details (`chat:send`; a customer's chat token only for its own conversation); chat requests then pass `attachments: [ids]` (built) |
| GET | `/sessions/{id}/attachments`, `/attachments/{id}` | list a conversation's files; download one served as an attachment with `nosniff` and a sandbox policy (`traces:read`) (built) |
| POST | `/handoffs/{id}/reply` | `text`: a person's message to the customer, delivered through the outbox as kind `person_reply` (`handoffs:resolve`) (built) |
| POST | `/handoffs/{id}/assist` | draft suggestions for the person handling the hand-off, stored with it; 20 per minute per key (`handoffs:resolve`) (built) |
| POST | `/agents/{id}/journeys/draft` | `description`: a journey drafted by the model from plain language, checked against the agent's tools; 10 per minute per key; needs `versions:create` (built) |
| POST | `/builder/draft` | `agentId`, `goal`, `sources` (1-8 of `{kind: procedure\|transcript, name, text}`, 20,000 characters each): a first draft of an agent (YAML, warnings, notes, typical questions) from procedures and conversation transcripts. Saves nothing; needs `versions:create`; 5 a minute per key |
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
| GET | `/events/types` | The status event types and which are subscribed (`audit:read`) (built) |
| GET | `/events?after=&limit=` | Poll the same status events the webhook sends; `after` is the last id seen (`audit:read`) (built) |
| GET | `/residency` | Where this deployment keeps data and every destination it sends data to, checked against the residency file (`audit:read`) (built) |
| POST | `/builder/refine` | `{current, instruction}`: a revised draft with a list of changes (built) |
| POST | `/builder/scenarios` | `{spec, examples}`: test scenarios for a draft (guarantee tests run against the draft; question tests need a live model) (built) |
| POST | `/builder/transcribe?language=` | The body is a recording; returns transcript text through the configured transcription service (built) |
| GET | `/knowledge/index` | Meaning-based search status: model, indexed and pending counts, approximate-index sizes, last error (built) |
| POST | `/knowledge/index/rebuild` | Clear every embedding and re-embed in the background (built) |
| GET, POST | `/knowledge/schedules`, `/knowledge/sources/{id}/schedule` | List and create scheduled re-crawls (built) |
| POST, DELETE | `/knowledge/schedules/{id}/enabled`, `/knowledge/schedules/{id}` | Pause or resume, and remove, a schedule (built) |
| POST | `/channels/whatsapp/templates/send` | `{phoneId?, to, template, params}`: send an approved WhatsApp template to someone who messaged first or opted in (`channel:inbound`) (built) |
| POST | `/insights/ask` | `{question, environment?}`: a plain-language question answered from the recorded figures, with filters, conversation lists and charts (built) |


Chat requests (`/chat`, `/chat/stream`) accept `environment` (`dev`, `staging`, `production`). Only keys with `simulations:run` may use dev or staging; customer tokens and channel keys always get production. Each trace records the environment that answered.

`POST /v1/templates/{id}/create-version` also accepts `saveScenarios: true`: the template's tests are saved with the version (as required scenarios only when the caller holds `scenarios:require`), and the response lists `scenariosSaved` and `scenariosSkipped`.

## Route reference

The complete machine-readable reference, with request fields and the permission each route needs, is generated from the running application: `docs/api/openapi.json` and a readable page, `docs/api/index.html` (`python scripts/gen_api_reference.py`; a test fails when they are out of date). The live schema endpoint stays switched off on the server.

<!-- routes:start (generated by scripts/gen_route_reference.py) -->

Every route that needs a key (232), with the permission it requires. Generated from the server's permission table; a test fails if this list and the code disagree.

| Method | Path (under `/v1`) | Permission |
|---|---|---|
| GET | `/agents` | `agents:read` |
| POST | `/agents/{id}/chat` | `chat:send` |
| POST | `/agents/{id}/chat/stream` | `chat:send` |
| GET | `/agents/{id}/environments` | `versions:read` |
| POST | `/agents/{id}/improve` | `versions:create` |
| POST | `/agents/{id}/journeys/draft` | `versions:create` |
| POST | `/agents/{id}/journeys/scenarios` | `simulations:run` |
| GET | `/agents/{id}/live` | `agents:read` |
| POST | `/agents/{id}/promote` | `versions:create` |
| GET | `/agents/{id}/qualifications` | `versions:read` |
| POST | `/agents/{id}/qualifications` | `scenarios:require` |
| GET | `/agents/{id}/releases` | `versions:read` |
| POST | `/agents/{id}/releases` | `versions:create` |
| POST | `/agents/{id}/rollback` | `versions:create` |
| GET | `/agents/{id}/rollouts` | `versions:read` |
| POST | `/agents/{id}/rollouts` | `versions:create` |
| POST | `/agents/{id}/rollouts/{id}/abort` | `versions:create` |
| GET | `/agents/{id}/rollouts/{id}/comparison` | `insights:read` |
| PUT | `/agents/{id}/rollouts/{id}/percent` | `versions:create` |
| POST | `/agents/{id}/rollouts/{id}/promote` | `versions:create` |
| GET | `/agents/{id}/versions` | `versions:read` |
| POST | `/agents/{id}/versions` | `versions:create` |
| POST | `/agents/{id}/versions/preview` | `versions:create` |
| GET | `/agents/{id}/versions/{id}` | `versions:read` |
| GET | `/agents/{id}/versions/{id}/checklist` | `versions:read` |
| GET | `/agents/{id}/versions/{id}/diff/{id}` | `versions:read` |
| GET | `/alerts` | `insights:read` |
| POST | `/alerts/test` | `keys:manage` |
| GET | `/approvals` | `approvals:read` |
| POST | `/approvals/expire` | `approvals:decide` |
| POST | `/approvals/{id}/decision` | `approvals:decide` |
| GET | `/attachments/{id}` | `traces:read` |
| GET | `/audit` | `audit:read` |
| GET | `/audit/verify` | `audit:read` |
| GET | `/automation-runs` | `agents:read` |
| GET | `/automation-runs/{id}` | `agents:read` |
| POST | `/automation-runs/{id}/decision` | `approvals:decide` |
| GET | `/automation-settings` | `agents:read` |
| PUT | `/automation-settings` | `keys:manage` |
| GET | `/automations` | `agents:read` |
| POST | `/automations` | `versions:create` |
| GET | `/automations-catalog` | `agents:read` |
| POST | `/automations/convert` | `agents:read` |
| POST | `/automations/draft` | `versions:create` |
| GET | `/automations/{id}` | `agents:read` |
| PUT | `/automations/{id}` | `versions:create` |
| POST | `/automations/{id}/(approve|reject|retire|pause|resume|secret)` | `releases:publish` |
| POST | `/automations/{id}/(run|hook)` | `automations:run` |
| POST | `/automations/{id}/propose` | `versions:create` |
| GET | `/automations/{id}/runs` | `agents:read` |
| DELETE | `/budgets` | `keys:manage` |
| PUT | `/budgets` | `keys:manage` |
| POST | `/builder/draft` | `versions:create` |
| POST | `/builder/refine` | `versions:create` |
| POST | `/builder/scenarios` | `versions:create` |
| POST | `/builder/transcribe` | `versions:create` |
| GET | `/catalog` | `agents:read` |
| GET | `/channels` | `agents:read` |
| POST | `/channels/email/inbound` | `channel:inbound` |
| POST | `/channels/whatsapp/templates/send` | `channel:inbound` |
| POST | `/chat-tokens` | `chat:mint` |
| GET | `/conversations/search` | `traces:read` |
| POST | `/customers/facts/{id}/remove` | `customers:write` |
| POST | `/customers/find` | `customers:read` |
| POST | `/customers/lookup` | `customers:read` |
| POST | `/customers/notes` | `customers:write` |
| POST | `/customers/notes/{id}/delete` | `customers:write` |
| POST | `/customers/reveal` | `customers:read` |
| GET | `/customers/settings` | `customers:read` |
| PUT | `/customers/settings` | `keys:manage` |
| GET | `/events` | `audit:read` |
| POST | `/events/test` | `keys:manage` |
| GET | `/events/types` | `audit:read` |
| GET | `/groups` | `keys:manage` |
| POST | `/groups` | `keys:manage` |
| DELETE | `/groups/{id}` | `keys:manage` |
| PUT | `/groups/{id}` | `keys:manage` |
| POST | `/groups/{id}/members` | `keys:manage` |
| DELETE | `/groups/{id}/members/{id}` | `keys:manage` |
| GET | `/handoffs` | `handoffs:read` |
| GET | `/handoffs/{id}` | `handoffs:read` |
| POST | `/handoffs/{id}/assist` | `handoffs:resolve` |
| GET | `/handoffs/{id}/inbox` | `handoffs:read` |
| POST | `/handoffs/{id}/reply` | `handoffs:resolve` |
| POST | `/handoffs/{id}/resolve` | `handoffs:resolve` |
| GET | `/hub/installs` | `agents:read` |
| POST | `/insights/ask` | `insights:read` |
| GET | `/insights/failures` | `insights:read` |
| GET | `/insights/gaps` | `insights:read` |
| GET | `/insights/overview` | `insights:read` |
| GET | `/insights/review-quality` | `insights:read` |
| GET | `/insights/timeseries` | `insights:read` |
| GET | `/keys` | `keys:manage` |
| POST | `/keys` | `keys:manage` |
| POST | `/keys/{id}/revoke` | `keys:manage` |
| GET | `/knowledge/crawls` | `knowledge:read` |
| GET | `/knowledge/crawls/{id}` | `knowledge:read` |
| GET | `/knowledge/documents` | `knowledge:read` |
| GET | `/knowledge/index` | `knowledge:read` |
| POST | `/knowledge/index/rebuild` | `knowledge:write` |
| GET | `/knowledge/schedules` | `knowledge:read` |
| DELETE | `/knowledge/schedules/{id}` | `knowledge:write` |
| POST | `/knowledge/schedules/{id}/enabled` | `knowledge:write` |
| GET | `/knowledge/search` | `knowledge:read` |
| GET | `/knowledge/sources` | `knowledge:read` |
| POST | `/knowledge/sources` | `knowledge:write` |
| DELETE | `/knowledge/sources/{id}` | `knowledge:write` |
| POST | `/knowledge/sources/{id}/crawl` | `knowledge:write` |
| DELETE | `/knowledge/sources/{id}/documents/{path}` | `knowledge:write` |
| GET | `/knowledge/sources/{id}/documents/{path}` | `knowledge:read` |
| PUT | `/knowledge/sources/{id}/documents/{path}` | `knowledge:write` |
| POST | `/knowledge/sources/{id}/import` | `knowledge:write` |
| POST | `/knowledge/sources/{id}/schedule` | `knowledge:write` |
| GET | `/me` | `authenticated` |
| POST | `/me/logout` | `authenticated` |
| DELETE | `/memories` | `memory:manage` |
| GET | `/memories` | `memory:read` |
| DELETE | `/memories/{id}` | `memory:manage` |
| GET | `/models/overview` | `versions:read` |
| GET | `/monitor/findings` | `monitor:read` |
| GET | `/monitor/summary` | `monitor:read` |
| GET | `/org-policies` | `agents:read` |
| POST | `/org-policies` | `versions:create` |
| POST | `/org-policies/prove` | `versions:create` |
| PUT | `/org-policies/{id}` | `versions:create` |
| POST | `/org-policies/{id}/propose` | `versions:create` |
| POST | `/org-policies/{id}/{approve|reject|retire}` | `releases:publish` |
| GET | `/org-templates` | `agents:read` |
| POST | `/org-templates` | `versions:create` |
| POST | `/org-templates/check` | `versions:create` |
| GET | `/org-templates/{id}` | `agents:read` |
| PUT | `/org-templates/{id}` | `versions:create` |
| POST | `/org-templates/{id}/propose` | `versions:create` |
| POST | `/org-templates/{id}/{approve|reject|withdraw}` | `releases:publish` |
| GET | `/policies` | `agents:read` |
| DELETE | `/privacy/customers/{path}` | `privacy:manage` |
| GET | `/privacy/customers/{path}/export` | `privacy:manage` |
| POST | `/privacy/retention/run` | `privacy:manage` |
| DELETE | `/privacy/sessions/{path}` | `privacy:manage` |
| GET | `/quality/calibration` | `traces:read` |
| GET | `/quality/coaching` | `reviews:write` |
| POST | `/quality/coaching` | `reviews:write` |
| DELETE | `/quality/coaching/{id}` | `reviews:write` |
| POST | `/quality/judge` | `reviews:write` |
| DELETE | `/quality/rubric` | `releases:publish` |
| GET | `/quality/rubric` | `traces:read` |
| PUT | `/quality/rubric` | `releases:publish` |
| GET | `/quality/scorecards` | `traces:read` |
| GET | `/regression` | `simulations:read` |
| GET | `/release-requests` | `versions:read` |
| POST | `/release-requests/{id}/approve` | `releases:publish` |
| POST | `/release-requests/{id}/cancel` | `versions:create` |
| POST | `/release-requests/{id}/reject` | `releases:publish` |
| GET | `/residency` | `audit:read` |
| GET | `/reviews/queue` | `traces:read` |
| GET | `/routing` | `handoffs:read` |
| GET | `/sessions/{id}/attachments` | `traces:read` |
| PUT | `/sessions/{id}/attachments` | `chat:send` |
| POST | `/sessions/{id}/feedback` | `feedback:send` |
| GET | `/sessions/{id}/outbox` | `outbox:read` |
| PUT | `/sessions/{id}/review` | `reviews:write` |
| GET | `/sessions/{id}/tags` | `traces:read` |
| DELETE | `/sessions/{id}/tags/{id}` | `conversations:tag` |
| PUT | `/sessions/{id}/tags/{id}` | `conversations:tag` |
| GET | `/sessions/{id}/transcript` | `traces:read` |
| GET | `/sessions/{path}/scenario-draft` | `simulations:run` |
| POST | `/simulations/runs` | `simulations:run` |
| GET | `/simulations/runs/{id}` | `simulations:read` |
| POST | `/simulations/scenarios` | `scenarios:write` |
| POST | `/simulations/scenarios/validate` | `scenarios:write` |
| DELETE | `/simulations/scenarios/{id}` | `scenarios:write` |
| GET | `/simulations/scenarios/{id}` | `simulations:read` |
| PUT | `/simulations/scenarios/{id}` | `scenarios:write` |
| GET | `/simulations/{scenarios|runs|gate}` | `simulations:read` |
| GET | `/skills` | `agents:read` |
| GET | `/templates` | `agents:read` |
| GET | `/templates/{id}` | `agents:read` |
| POST | `/templates/{id}/create-version` | `versions:create` |
| POST | `/templates/{id}/install` | `versions:create` |
| POST | `/templates/{id}/render` | `versions:create` |
| POST | `/templates/{id}/requirements` | `agents:read` |
| POST | `/templates/{id}/update` | `versions:create` |
| POST | `/templates/{id}/update-preview` | `versions:create` |
| GET | `/tenant/limits` | `agents:read` |
| GET | `/tenant/provider` | `agents:read` |
| GET | `/trace-export` | `traces:read` |
| GET | `/traces` | `traces:read` |
| GET | `/traces/{id}` | `traces:read` |
| GET | `/traces/{id}/exports` | `traces:read` |
| GET | `/usage` | `insights:read` |
| GET | `/voice/calls` | `traces:read` |
| GET | `/workspace/actions` | `workspace:use` |
| POST | `/workspace/actions/{id}/(confirm|cancel)` | `workspace:use` |
| GET | `/workspace/assistants` | `workspace:use` |
| POST | `/workspace/assistants/{id}/chat` | `workspace:use` |
| POST | `/workspace/chat` | `workspace:use` |
| POST | `/workspace/chat/stream` | `workspace:use` |
| GET | `/workspace/library-items` | `workspace:use` |
| POST | `/workspace/library-items` | `workspace:use` |
| POST | `/workspace/library-items/suggest` | `workspace:use` |
| DELETE | `/workspace/library-items/{id}` | `workspace:use` |
| GET | `/workspace/library-items/{id}` | `workspace:use` |
| PUT | `/workspace/library-items/{id}` | `workspace:use` |
| POST | `/workspace/library-items/{id}/use` | `workspace:use` |
| DELETE | `/workspace/memory` | `workspace:use` |
| GET | `/workspace/memory` | `workspace:use` |
| POST | `/workspace/memory` | `workspace:use` |
| DELETE | `/workspace/memory/{id}` | `workspace:use` |
| PUT | `/workspace/memory/{id}` | `workspace:use` |
| GET | `/workspace/outputs` | `workspace:use` |
| POST | `/workspace/outputs` | `workspace:use` |
| DELETE | `/workspace/outputs/{id}` | `workspace:use` |
| GET | `/workspace/outputs/{id}` | `workspace:use` |
| PUT | `/workspace/outputs/{id}` | `workspace:use` |
| GET | `/workspace/outputs/{id}/export` | `workspace:use` |
| GET | `/workspace/performance` | `workspace:use` |
| GET | `/workspace/search` | `workspace:use` |
| GET | `/workspace/spaces` | `workspace:use` |
| POST | `/workspace/spaces` | `workspace:use` |
| DELETE | `/workspace/spaces/{id}` | `workspace:use` |
| GET | `/workspace/spaces/{id}` | `workspace:use` |
| PUT | `/workspace/spaces/{id}` | `workspace:use` |
| GET | `/workspace/spaces/{id}/files` | `workspace:use` |
| POST | `/workspace/spaces/{id}/files` | `workspace:use` |
| DELETE | `/workspace/spaces/{id}/files/{id}` | `workspace:use` |
| GET | `/workspace/spaces/{id}/files/{id}` | `workspace:use` |
| GET | `/workspace/tasks` | `workspace:use` |
| POST | `/workspace/tasks` | `workspace:use` |
| DELETE | `/workspace/tasks/{id}` | `workspace:use` |
| GET | `/workspace/tasks/{id}` | `workspace:use` |
| POST | `/workspace/tasks/{id}/(answers|approve|pause|stop)` | `workspace:use` |
| PUT | `/workspace/tasks/{id}/plan` | `workspace:use` |

<!-- routes:end -->
