# NorthCX Integrations

Status: **Partly built**. Updated: 2026-11-09. Master for: connectors and integrations. Built: connectors defined as data (HTTP APIs with allowed hosts, OAuth 2, pagination, idempotent writes; `northcx/connectors.py`), the hand-off inbox (signed webhook and a Chatwoot adapter), signed status-event webhooks, channel adapters. Planned: a connector SDK, OAuth app flow and native connectors (E9; first connectors per D6: a ticketing pack, then Slack, then Salesforce) and MCP (E4).

## Integration types
| Type | Examples of systems | Mechanism |
|---|---|---|
| Orders / commerce | Order and shipment lookup | Tool |
| Billing | Refunds, invoices | Tool with approval rule |
| CRM / accounts | Customer profile | Tool |
| Helpdesk / inbox | Tickets, human queue | Channel adapter + handoff |
| Knowledge | Articles, policies | Retrieval tool |

## Connector library (T5): the plan and what was built
The plan was in-tree, tested connectors for common categories (order lookup, shipment tracking, refunds and credits, subscription changes, account profile updates, tickets, appointment booking). What was built is a connector format (YAML files that describe a REST API and its tools) with five generic starting points; see "Connector library (T5)" below. Native connectors for named products are planned (E9).

## Permissions (T6)
Tools are granted per agent and scoped per customer, so an agent can only touch the current customer's records.

## Idempotency (T4)
Writes carry an idempotency key derived from session and call; retries never duplicate effects.

## Dry-run (T8)
Tests and simulations can run tools in dry-run mode that records the intended action without executing it.

## Webhooks (P8)
Signed status events with retries and a polling feed, and a test sender (`POST /v1/events/test`); see "Status events" below.

## Embedding the customer chat
1. Your server holds a **channel key** (create it on the Access page) in its secrets store.
2. When a customer opens the chat, your server asks NorthCX for a token for that customer's conversation:
```python
import httpx
r = httpx.post("https://northcx.example.com/v1/chat-tokens",
               headers={"authorization": f"Bearer {CHANNEL_KEY}"},
               json={"sessionId": f"web-{customer.id}", "customerId": customer.id, "agent": "support", "ttlSeconds": 3600})
token = r.json()["token"]          # give this to the page, not the key
```
3. Your page sends the token with each message and polls for later messages (for example after an approval):
```js
fetch(`${API}/v1/agents/support/chat`, { method: "POST",
  headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
  body: JSON.stringify({ sessionId, message }) })
fetch(`${API}/v1/sessions/${sessionId}/outbox?after=${lastId}`, { headers: { authorization: `Bearer ${token}` } })
```
Use the same `sessionId` to resume a conversation. The customer cannot change the conversation or customer the token names. The built-in page at `/` does this with `/#token=<token>`. Allow the page's origin to call the API through your reverse proxy (NorthCX does not set cross-origin headers).

## Declaring a tool: effect, dry run and secrets
- **`effect`**: `"read"` for a tool with no side effects, `"write"` (the default, the safe assumption) for anything that changes a system. Mark only genuinely read-only tools as reads.
- **`dry_run_result`**: what a write tool returns when the platform is testing. Simulations (and the release gate's proofs) never execute write tools; they call this instead, or return a generic placeholder if you give none. Apply the same business rules in it (the example refund checks the order exists, is delivered and not over its total) so scenarios still catch rule violations. The command line's `--allow-side-effects` runs writes for real and exists only for sandboxes.
- **Secrets**: a tool reads a credential with `ctx.secret("payments_key")`, configured as `NORTHCX_SECRET_PAYMENTS_KEY` or `NORTHCX_SECRET_PAYMENTS_KEY_FILE`. Never return a credential or include it in a message; if one slips into a result or an error, the platform replaces it with `[redacted:name]` before the model, traces, saved history, approvals, handoffs or replies see it. Credentials shorter than eight characters are refused because they cannot be scrubbed safely.
- **Idempotency**: `ctx.idempotency_key` is stable for an approved action; pass it to the downstream system.
- **Supplying your tools**: write a function returning a `Registry` and set `NORTHCX_REGISTRY=your.module:function` (the container's default is the bundled example), with `NORTHCX_AGENTS_DIR` and `NORTHCX_SCENARIOS_DIR` pointing at your spec and scenario directories.

## Tool authoring checklist
Narrow scope; typed input; least-privilege credentials; idempotency key for writes; timeouts; return minimal data; approval rule for money or irreversible actions; tests with a scripted model.

## Secrets
Credentials come from environment or a secrets manager, never from prompts or traces.

## Open
Which native connectors ship in-tree and which as separate packages (E9; the first, per D6: a ticketing pack, then Slack, then Salesforce), and an MCP client and server (E4).


## Customer context (K7)

Agents often need to know who they are talking to: plan, region, account status, open orders. NorthCX asks the company's own systems once when a conversation with a known customer starts and then reuses the answer for a short time.

**Two ways to supply it** (use one):
- **Python hook:** `NORTHCX_CONTEXT_PROVIDER=package.module:function`, where the function returns an object with `async fetch(customer_id, session_id) -> dict`.
- **Signed HTTPS endpoint:** `NORTHCX_CONTEXT_URL` with `NORTHCX_CONTEXT_SECRET`. NorthCX POSTs `{"customerId", "sessionId"}` with `x-northcx-timestamp` and `x-northcx-signature` (HMAC-SHA256 over `timestamp.body`, the same scheme as webhooks, so receivers should verify both). The endpoint answers 200 with `{"facts": {...}}`. Redirects are not followed and responses over 64 KB are refused.

**Rules applied to whatever comes back:** at most 30 entries; names are letters, digits, spaces and `_ . -`; values are text, numbers or yes/no, cut at 500 characters; nested values are dropped; any value that reads like instructions to the model is dropped and noted in the trace. The agent receives the entries with the customer facts as untrusted data, and the company's values win over facts the agent stored itself.

**Behaviour:** results are cached per customer (default 300 s) and simultaneous messages share one call; a call that takes longer than the timeout (default 3 s) or fails gives no context, is remembered for 30 s so a system that is down is not hammered, and the conversation carries on (the agent can still help or hand off). Context is not saved with the customer's facts and not written to traces (only the names of the entries are); it does appear in a hand-off package so the person sees it, and is erased with that hand-off. Erasing a customer also drops their cached context. Anonymous visitors, platform messages and simulations do not fetch context.


## Human inbox (H5)

Every hand-off, with its package (summary, transcript, actions, customer facts, queue and after-hours flag), is pushed to the company's helpdesk, and its resolution is passed on. Delivery is queued in the database and retried with back-off (30 s doubling to one hour, 12 attempts), so a helpdesk outage delays the hand-off's appearance there but never loses it and never affects the customer's conversation. `GET /v1/handoffs/{id}/inbox` shows each delivery's state, attempts, reference and last error (errors never contain URLs, tokens or response bodies).

**Signed webhook (any system).** `NORTHCX_INBOX_WEBHOOK_URL` and `NORTHCX_INBOX_WEBHOOK_SECRET`. NorthCX POSTs `{"event": "handoff.created" | "handoff.resolved", "handoff": {...with package...}, "consoleUrl"}` with `x-northcx-timestamp`, `x-northcx-signature` (HMAC-SHA256 over `timestamp.body`, as for other webhooks), `x-northcx-event` and `x-northcx-delivery`. The receiver may answer `{"ref": "..."}` to name its record. Receivers should verify the signature and the five-minute window, and treat deliveries as at-least-once (the delivery id is stable).

**Chatwoot.** `NORTHCX_CHATWOOT_URL`, `_ACCOUNT_ID`, `_INBOX_ID`, `_TOKEN`. For each hand-off NorthCX finds or creates the contact (by the customer id, or "Website visitor"), opens a conversation in the chosen inbox, adds a private note with the summary, recent transcript, actions and facts, and closes the conversation when the hand-off is resolved in NorthCX. Only Chatwoot's public REST API is used (no code copied). The endpoint shapes are written from its API documentation as recalled, tested against a simulated server, and not yet run against a live Chatwoot.

**Resolving from the helpdesk.** A person who resolves the conversation in the helpdesk can mark the hand-off resolved with `POST /v1/handoffs/{id}/resolve` using a key that holds `handoffs:resolve` (for example from the helpdesk's own webhook or automation). Receiving the helpdesk's webhooks directly, and returning a conversation to the agent (H7), are not built.

**Privacy.** The package contains personal data and is sent to the helpdesk on purpose; erasing a customer removes NorthCX's queued deliveries but cannot recall copies the helpdesk holds, so the helpdesk's own deletion process applies.


## Connector library (T5)

Business systems are connected with **connector files**: YAML that describes a REST API and the tools an agent may use against it, so common integrations need no code. Five starting points ship in `src/backend/examples/connectors/` (orders, billing, accounts, helpdesk, and a CRM that shows OAuth and paging); they are generic REST shapes to adapt, not integrations with a particular product. Remove `.example` from the name, put the file in `NORTHCX_CONNECTORS_DIR`, and allow its host with `NORTHCX_CONNECTOR_HOSTS`.

```yaml
name: orders
base_url: https://api.shop.example.com/v1
auth: {type: bearer, secret: ORDERS_API_TOKEN}      # none | bearer | header (+header) | basic (+user)
tools:
  - name: orders_refund
    description: Refund a delivered order.
    method: POST
    path: /orders/{order_id}/refunds
    inputs:
      order_id: {type: string, pattern: '^[A-Za-z0-9-]{3,20}$'}
      amount: {type: number, min: 0.01, max: 10000}
    body: {amount: "{amount}"}
    response: {fields: [id, status, amount]}          # only these fields reach the model
    requires_approval: {input: amount, above: 100, reason: Refunds over 100 need approval}
    dry_run_result: {id: dry-run, status: simulated}
```

**Safety is set by the operator, not the file.** Calls go only to hosts in `NORTHCX_CONNECTOR_HOSTS` (a file naming any other host is refused at start-up), over HTTPS (plain HTTP only for localhost), without following redirects, with a time limit and a 256 KB response cap. Paths are fixed in the file: input values fill `{placeholders}` as data (URL-encoded, so `../` or `?` cannot change where a request goes) and every input is validated (type, pattern, range, allowed values, length) before any call. Credentials are looked up by name in the secret store at call time, so they are scrubbed from traces and never returned. Writes send the call's stable idempotency key as an `Idempotency-Key` header; whether the other system honours it is up to that system. Errors tell the model only what happened ("the system returned 500", "could not be reached"), never URLs, response bodies or credentials. A read that finds nothing (404) returns `{"found": false}`; a write that gets 404 is an error.

**Approvals and testing.** `requires_approval` (always, or when an input is above a number) holds the call for a person like any tool. `dry_run_result` is what simulations get instead of a real write; write tools without one return a generic placeholder. Tools from connectors are ordinary tools: they work with skills, tool scopes, output screening of results, and the policy library.

**Paging through lists.** A GET tool can set `pagination` with a `style`: `cursor` (the answer holds a marker for the next page; give `next`, the dotted path to it, and `param`, the query parameter that carries it), `page` (a page number in `param`), `offset` (a running offset in `param`) or `link_header` (the system's `Link: <...>; rel="next"` header). `items` is the dotted path to the list in the answer (omit it if the answer is the list), `size_param` and `page_size` ask for a page size, and `max_pages` (at most 10, default 5) and `max_items` (at most 500, default 100) bound the work. The tool returns `{"items": [...], "count": n, "truncated": true|false}` so the agent knows when it saw only part of a list; the `response.fields` projection applies to every item. A `Link` address is followed only if it has the same scheme, host and port as the connector and sits under its path, and the credentials go only there; anything else stops with an error. A failure on any page fails the call (no half answers), and the combined answer is trimmed to the response cap.

**OAuth 2.** `auth.type: oauth2_client_credentials` (with `token_url`, `client_id`, `client_secret`, optional `scope`, and `client_auth: basic` to send the credentials in a Basic header instead of the form) or `oauth2_refresh_token` (`token_url`, `client_id`, `refresh_token`). The values are the *names* of secrets in the secret store, never the secrets themselves; the token address must be on an allowed host (`NORTHCX_CONNECTOR_HOSTS`) and use https, like the API. The access token is fetched when first needed, kept only in memory until 30 seconds before it expires, shared by simultaneous calls (one sign-in, not eight), and fetched again once if the system answers 401. Sign-in problems reach the model only as "could not sign in (the token address returned 400)": never the response, the address or any secret. A refresh token that the provider rotates is followed in memory, but a restart goes back to the secret store's value, so providers that invalidate the old token on each use need a writable secret store, which is not built.

**Not built.** The authorization-code flow (a person signing in through a browser to connect an account), file uploads, GraphQL, per-customer credentials, and verifying a connector against a live system at start-up. Connector tools are loaded at start-up; changing a file needs a restart.

## Building an agent from your material (A8)

`POST /v1/builder/draft` (Studio: Agents → “Build an agent from your material”) drafts an agent from up to eight procedures or conversation transcripts (20,000 characters each, 60,000 in all) and a one-line goal. The result is a draft to read, edit and test; nothing is saved and nothing goes live.

- **What the model gets:** the goal, the sources, and the names and descriptions of the tools, guardrails and skills this deployment really has. Email addresses, phone numbers, card numbers and similar personal details are masked in every source before it is sent. Sources are fenced as data and the model is told to ignore any instructions in them.
- **What it can set:** instructions, tools, guardrails (all three kinds), forced hand-off topics, journeys, channel styles and languages. Nothing else is taken from it: the model choice, step and token limits, voice, attachments, routes and tool scopes are never set by a draft, and the agent id is the one you gave.
- **What is checked:** every tool and guardrail name must exist here (unknown names are removed and listed), each free-form part must validate (an invalid one is dropped, not the whole draft), the whole agent is validated against the registry, tools that change things are called out, and the standard prompt-injection input check is added if it exists. The model’s notes (what it guessed, what the documents did not cover) and typical customer questions seen in transcripts come back for you to turn into test scenarios.
- **Then:** create a version from the YAML, add scenarios, and release it through the usual checklist, review and gates. A draft is never exempt from them.
- **Recordings.** With `NORTHCX_TRANSCRIBE_URL` set, “Transcribe a recording” turns an uploaded call recording into text (`POST /v1/builder/transcribe`, the body is the audio). Audio goes only to the configured service, is recognised by content, capped at 25 MB, and is not stored; the transcript is shown for you to correct, and masked for personal details like any transcript when used for drafting. Without the setting the button reports that transcription is off.
- **Refining by conversation.** `POST /v1/builder/refine` takes the current definition and an instruction (“never promise delivery dates”) and returns a revised draft with a list of what changed. The same field limits and registry checks apply every round; settings the model may not set (model choice, limits, voice, routes, scopes) are carried over exactly as the author had them.
- **Test scenarios.** `POST /v1/builder/scenarios` takes a definition and the typical questions. Two kinds come back, and the difference is stated: platform-guarantee tests (each forced hand-off topic goes to a person without the model; a prompt-injection attempt is stopped and never reaches a write tool) are run against the draft here and only the passing ones are returned; question tests (typical customer questions with the tools the model expects to be called or not called and a judge rubric) need a live model, are optional until reviewed, and have not been run. Everything is checked with the real scenario parser; nothing is saved.
- **Not done:** speaker separation in recordings, saving drafts and tests in one step (copy them into a version and the scenario editor), and running the question tests (they need a live model).

## Status events (P8)

Set `NORTHCX_EVENTS_WEBHOOK_URL` and `NORTHCX_EVENTS_WEBHOOK_SECRET` and NorthCX sends a small signed JSON call whenever something happens that another system may care about. The same events can be polled from `GET /v1/events?after=<last id>` (role: auditor or admin), and `GET /v1/events/types` lists the types and which are subscribed.

| Type | When |
|---|---|
| `handoff.created` | a conversation was put in a hand-off queue (`handoffId`, `trigger`, `queue`, `agent`, `afterHours`, `topics`) |
| `handoff.resolved` | a person resolved a hand-off |
| `approval.requested` | a tool call is waiting for approval (`approvalId`, `tool`, `agent`) |
| `approval.decided`, `approval.expired` | a person decided, or the approval timed out and the conversation was handed to a person |
| `conversation.rated` | a customer rated a conversation (`rating`; the comment is never sent) |
| `conversation.abuse` | abuse detection noticed abusive language, threats, repetition or a burst (kinds and strike count) |
| `alert.fired` | an alert rule started firing (`rule`, `metric`, `severity`, `value`, `threshold`) |
| `version.created`, `release.published`, `release.rolled_back`, `rollout.changed` | agent lifecycle changes by staff |
| `key.created`, `key.revoked` | API key changes (ids and names, never keys) |
| `knowledge.changed` | a knowledge document or source was added, changed, imported or removed |
| `privacy.erased` | a conversation or customer was erased |

**Envelope.** `{id, type, createdAt, sessionId, data}`, sent with the same headers as reply webhooks: `x-northcx-timestamp`, `x-northcx-signature` (HMAC-SHA256 of `timestamp.body` with your secret; reject calls older than five minutes) and `x-northcx-event`. `id` is stable, so a receiver can ignore a call it has already seen. Delivery is at least once: a failed call is retried with back-off (30 seconds doubling to an hour, twelve tries) and stays visible in the feed.

**What events never contain.** Message text, replies, tool inputs and outputs, ratings' comments, API keys, phone numbers or email addresses: only ids, tool, queue and agent names, counts and outcomes, and only short plain values (nothing nested). Staff-action events are built from the audit record of the same action, so the feed cannot disagree with the audit log. Simulations and tests emit nothing.

**Not included:** every conversation start or end (use the polling traces API or insights), and per-message events.
