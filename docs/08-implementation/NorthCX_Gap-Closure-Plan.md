# NorthCX Gap-Closure Plan

Status: **Plan**. Updated: 2026-11-09. Master for: the epic designs and plan decisions D1 to D11 (the work packages are in `NorthCX_Implementation-Plan.md`). Written 2026-11-05. Turns `00-reference/NorthCX_North-Gap-Analysis.md` into an implementation plan: what to build, in what order, how each piece is designed, how it is proven, and what needs a person or an outside party. The work packages, steps and checklist that implement it are in `NorthCX_Implementation-Plan.md`. Sizes are estimates; the first milestone is detailed enough to start, later ones are outlines to be re-planned when they begin.

## 1. What this plan covers

The gap analysis concludes that NorthCX has a strong **customer-facing** agent engine and is missing four things: a **staff-facing workspace**, **enterprise connectors and identity**, **multi-tenancy and billing**, and **flexible deployment**. This plan keeps the engine untouched and adds those layers in an order that never puts a later layer on an unfinished earlier one.

**Out of scope for this repository's build, and why** (each is listed again in section 13 with what is needed):
SOC 2 / ISO audits, the independent penetration test, a hosted managed cloud, native iOS and Android apps, and anything that needs a vendor account, a signed contract or real customers. The plan prepares the ground for them (documentation packs, Helm and Terraform skeletons, a vendor-neutral design) but does not claim them.

## 2. Principles (unchanged from the project so far)

1. **Safety and testability before reach.** Every new surface goes through the same machinery: roles, approvals, guardrails, audit, residency, scenarios. Nothing gets a back door because it is "internal".
2. **Each step ships complete:** code, tests (including the standing security tests), docs, decision-log entry, catalog IDs, CHANGELOG, `.env.example`, compose pass-through, residency report entry, threat-model entry, Studio UI where it has one, and a verified push to both branches.
3. **No dependency on a reference project's SDK or library.** Ordinary infrastructure libraries are fine; protocol clients are written thin and isolated (as the model SDK is behind `llm.py`).
4. **Honest labelling.** Each deliverable is marked *verified here* (tests, real Postgres, browser run), *partly verified* (fixtures or mocks only), or *needs outside verification* (live vendor, audit, hosting). Release notes repeat that label.
5. **Self-hosted single-tenant stays the default.** Every new capability must work with the current one-company deployment; tenancy, cloud and commercial features are additive and off unless configured.

## 3. Decisions needed before building (with recommendations)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | **Open model.** The project is Apache-2.0; anyone may host it. What is open, what (if anything) is commercial? | Fully open; open core with a separately licensed enterprise directory; source-available | Decide before billing and managed cloud are built. If open core, put enterprise code in a clearly separate directory from day one (the reuse policy already forbids copying other projects' enterprise directories, so the project should hold itself to the same line) |
| D2 | **Naming of the staff product.** The gap analysis suggests positioning copying another vendor's product name. | Own name ("NorthCX Copilot" / "Workspace"); the suggested phrasing | Own name; get the naming reviewed by someone qualified (not legal advice from this plan) |
| D3 | **Tenancy model.** | Shared schema with a tenant column and row-level security; schema per tenant; database per tenant | Shared schema + RLS for the managed multi-tenant cloud; the existing single-company deployment is simply tenant `default`; "dedicated" = one database per customer using the same code (section 6, E2) |
| D4 | **First staff surface.** | Studio workspace page; Slack/Teams bot; helpdesk sidebar | Studio workspace first (fully testable here), then Slack, then helpdesk sidebars |
| D5 | **SAML.** Hand-written signature verification is a security risk; a library needs the system `xmlsec` library. | Library (`python3-saml`); require an OIDC bridge (Keycloak/Dex) and document it | Document the bridge now (zero risk), add the library behind a feature flag in E3 |
| D6 | **First native connectors** (needs sandbox accounts to verify). | Zendesk, Salesforce, Intercom, Freshdesk, HubSpot, Shopify, Stripe, Jira, Slack, Teams, Drive... | MCP client first (breadth, no per-vendor code), then Zendesk and Slack, then Salesforce. Pick by what your first customers use |
| D7 | **MCP implementation.** | Official SDK; a thin own client | Thin own client over HTTP (the subset needed: list tools, call tool, resources read-only), isolated like the model SDK |
| D8 | **Billing unit.** | Per conversation, per resolution, per seat, per token | Meter all of them; bill on conversations and seats first. "Resolved" needs an agreed definition (today the product reports *containment* and says so) |
| D9 | **Which model providers first.** | OpenAI-compatible (covers many hosts and self-hosted servers) then others | OpenAI-compatible adapter first, then one more |
| D10 | **Web layout.** | One app with route groups; several apps with shared packages in one repository; separate repositories per app | Several apps with shared packages in one repository (decided; the split is done for Studio and the shared packages); back office and ops console as their own apps, the back office on an internal network with its own `/platform/v1` API prefix on a separate listener |
| D11 | **Where the marketing site, Trust Center and back office live.** | Same repository; separate repositories | Marketing, trust, legal and developer portal under `src/site` in this repository for now; the back office in this repository until D1 is decided, then in a private repository if the project goes open core |

**Status (2026-11-09):** D2 decided (working name NorthCX Workspace; an own name, not the other vendor's). D3, D5, D6, D7, D8 and D9 accepted as the implementation plan recommends and locked in when their work packages start (decision 170); for D6 that is a ticketing pack, then Slack, then Salesforce, with MCP (E4) in Wave 1. D4 superseded: the first staff surface is a separate Workspace app, not a Studio page (decisions 153 to 168). D10 and D11 decided (decision 140). D8's note on "resolved": a provisional resolution rate is now reported beside containment. **D1 is open.**

## 4. How the work is organised

Epics are grouped in **waves**; each wave ends in a tagged release with the full verification run. Within a wave, epics with no arrow between them can proceed in either order.

```
Wave 0  Finish 1.0 and prepare the ground
        E0 groundwork (split server.py, lockfile, shared limits, PDF masking option,
           web apps split into apps and shared packages, multi-replica readiness)
        -- live-model pass, pen test, tag, 1.0.0 (need you / outside)

Wave 1  Foundations                                     -> release 1.1
        E1 model providers + currency budgets
        E2 multi-tenancy (tenant config, isolation, RLS)
        E3 identity and governance (agent-scoped keys, groups, SCIM, SAML flag, publish approval)
        E4 MCP client and server                        (needs E1 for provider-neutral tool shapes; independent of E2)

Wave 2  Staff workspace                                 -> release 1.2     (needs E2, E3)
        E5 workspace chat, staff memory, permission-aware search
        E6 libraries and generated outputs
        E7 QA scoring and digests (first users of E8)
        E16 guardrail policy management, E18 support access (portals, section 10)

Wave 3  Automations and connectors                      -> release 1.3     (E8 needs E5; E9 needs E2, E4)
        E8 automations
        E9 connector SDK, OAuth app flow, native connectors
        E14 visual workflow editor, E15 workspace analytics (portals, section 10)

Wave 4  Commercial and deployment                       -> release 1.4     (needs E2)
        E10 metering, plans, usage export
        E11 deployment kit (Helm, Terraform skeleton, ops console, upgrade tool)
        E12 trust pack (compliance documents, customer-managed keys design, developer portal)
        E17 legal center, E19 private-deployment console extras (portals, section 10)

Wave 5  Reach                                           -> later
        E13 marketing site and demo booking (E21); Slack/Teams/helpdesk surfaces; E20 Office add-ins; browser extension; native mobile; marketplace
```

New catalog IDs are reserved per epic (section 11). Decision-log entries continue from #138.

## 5. Wave 0: finish 1.0 and prepare the ground

### E0. Groundwork (all verifiable here)
| Task | Why | Done when |
|---|---|---|
| **E0.1 Split `server.py`** (2,500 lines, 118 permission-checked routes) into router modules by area (chat, approvals, handoffs, knowledge, insights, releases, privacy, builder, channels, admin) without changing behaviour | Every later epic adds routes; one 2,500-line file will not survive another 60 | The permission sweep tests and the whole suite pass unchanged; the route table is generated from the routers; no file over about 600 lines |
| **E0.2 Lock dependencies** (a hash-pinned lock file for backend, `npm ci` already locks the web and SDK) and a CI check that fails when the lock is stale | Known limit 5 | CI installs from the lock; a script regenerates it; `pip-audit` runs on the lock |
| **E0.3 Shared rate limits and budgets** (Postgres-backed counters, atomic upsert, with the in-memory limiter kept for single process) | Known limit 3; required before any multi-replica or multi-tenant deployment | Two server processes share one limit in a test; load test shows under 5 percent throughput cost at the documented rate |
| **E0.4 PDF text path with masking** (extract text, mask personal data, send as text) as an option per agent, instead of sending the PDF itself; images stay opt-in with an explicit acknowledgement in the spec | Known limit 2 | New attachment mode with tests; the Threat Model entry is updated from "unmasked" to "masked text option" |
| **E0.5 Publish the API reference** generated from the app's schema into `docs/` (the live docs endpoint stays off) | Gap analysis, developer portal | A script produces the reference; a test checks it covers every route in the permission table |
| **E0.6 Webhook tester** generalising the alert test: `POST /v1/events/test` sends a signed sample of any event type to the configured webhook | Developer experience; used by the portal later | Test and audit entry |
| **E0.7 Split the web code into apps and shared packages** (decision D10; **done for Studio and the two shared packages**, later apps are created when their first feature arrives): `src/apps/studio` (today's `src/web`), shared `src/packages/ui` and `src/packages/api-client`, managed as npm workspaces; later apps (`workspace`, `admin`, `ops`, `backoffice`) are created only when their first feature arrives; marketing, trust, legal and developer portal live in `src/site`; embedded surfaces in `src/surfaces/*` | The staff workspace, admin portal, ops console and back office have different audiences, auth policies, traffic and shipping rules (the back office must never be in a customer bundle; the ops console only in private deployments). The code is about 3,000 lines now, so extracting the shared parts is cheap | No behaviour change: the web tests, type-check, production build and browser smoke pass before and after; CI, compose and docs updated; no app imports another app, only packages |
| **E0.8 Multi-replica readiness** | The API is mostly stateless but several parts are per process: rate limits and abuse counters (E0.3), background loops that run in every copy (outbox retries and alert evaluation can duplicate), alert state and crawl job status held in memory, attachments in the database, sticky voice and streaming connections | A setting to run the background loops only on dedicated workers; claims on the outbox and export queues; alert state in the database; documented topology (web, API replicas, workers, pooler, Postgres); a two-replica test in CI that sends each outbox message once and fires each alert once |

**Not mine to do, needed to call it 1.0:** live-model pass, judge calibration, penetration test, tag push (see the release checklist).

## 6. Wave 1: foundations

### E1. Model providers and cost governance
**Goal:** run agents on Claude, any OpenAI-compatible server (hosted or self-hosted), or a mix; budget in currency; route simple work to cheaper models.

**Design** (follows `04-ai-architecture/NorthCX_Model-Providers.md`)
- Neutral request/response types stay as they are (Claude block shapes). A **provider adapter** translates at the edge.
- `northcx/providers/`: `base.py` (adapter protocol, capability flags, error mapping with `status_code`), `anthropic.py` (the current SDK path, plus an optional direct-HTTP client to retire the SDK later), `openai_compat.py` (chat-completions with tools: `tool_use` ↔ `tool_calls`, `tool_result` ↔ `tool` messages; streaming off for now), `registry.py`.
- **Qualified model names** `provider:model` (`anthropic:claude-...`, `local:llama-3-70b`); a bare name uses the default provider, so existing specs keep working and agent digests do not change.
- **Providers config** (`NORTHCX_PROVIDERS_FILE`, YAML): name, kind, base URL (https; http only for localhost), credential secret reference, models with `input_per_million` / `output_per_million` prices, capabilities (tools, parallel tools, max context). Validated at start; added to the residency report (each provider is a data flow).
- **Fallback chains may mix providers.** Capability check at release time refuses an agent that needs tools on a model without them, instead of failing in a conversation.
- **Currency budgets:** per conversation and per day in currency (alongside tokens), computed from the price table and the usage the adapter reports; per-team budgets arrive with E3. Insights cost uses the real model mix (today it is one blended price).
- **Routing (experimental):** an optional agent setting that picks a cheaper model for turns a deterministic classifier calls simple (short, no tool history, knowledge-style question), with the choice recorded in the trace and a scenario type that compares both. Off by default.

**Tests and acceptance**
- One **conformance suite** parameterised over adapters (plain reply, tool call, tool-result round trip, parallel tools, error mapping, usage, cancellation) run with recorded HTTP fixtures through `httpx.MockTransport`; the existing suite passes unchanged on the Anthropic adapter.
- A local fake OpenAI-compatible server (small test double) exercised end to end through the runtime, simulations and the judge.
- Budget tests in currency, mixed fallback chains, residency report lists providers.
- *Verified here:* everything above with fixtures and a fake server. *Needs outside verification:* each real provider with a real key (the live-model pass extends to each).

**Size:** L (about 2,000 lines plus about 90 tests).

### E2. Multi-tenancy
This is the largest engineering item. It touches **38 tables, 30 store classes and every route**, and it moves configuration from the process environment into per-tenant data.

**Design**
- **Tenant identity.** New `tenants` table (id, name, plan, region, state). Every API key, SSO configuration, channel binding and webhook secret belongs to a tenant. Chat tokens carry the tenant. Inbound channel calls are resolved to a tenant by what they are addressed to (WhatsApp phone number id, Telegram bot id, SMS number, email domain, voice agent number) through a `channel_bindings` table.
- **Data isolation, two layers.** (1) Every tenant-owned table gets `tenant_id` (migration backfills the existing data as tenant `default`) and every store query is written through a base-class helper that adds the predicate, so a missing filter is a code-review-visible mistake in one place rather than 118 places. (2) **Row-level security** as defence in depth: `FORCE ROW LEVEL SECURITY` with policies on `current_setting('app.tenant_id')`, set per transaction with `set_config(..., true)`. Note the performance trade: the current read path avoids a transaction per statement (a deliberate optimisation); tenant-scoped reads need either a short transaction or the explicit predicate only. Acceptance includes a load-test comparison (section 11).
- **Tenant configuration service.** The settings that are environment variables today and must become per tenant: agents directory, connectors, crawl host allow-list, SSO provider, channel credentials, secrets (encrypted with a master key; KMS-backed later in E12), residency region, alert and event webhooks, knowledge and embedding settings. Platform-wide settings stay in the environment (database URL, provider catalog, master key, global caps). The resolution order is tenant value, then platform default, and the single-tenant deployment keeps working with environment values only.
- **Per-tenant limits** (shared limiter from E0.3): requests, tokens in currency (E1), concurrent crawls, storage.
- **Tenant admin vs platform admin.** A platform role can create and suspend tenants and sees only metadata; it cannot read conversations. Platform routes live under their own prefix (`/platform/v1`) served on a separate listener that can be firewalled, so a customer-facing deployment cannot expose them by mistake. A suspended tenant's keys and tokens stop working immediately.
- **Residency per tenant:** the residency policy becomes tenant data; a tenant in region `eu` cannot be configured with a provider or connector host mapped outside its allowed regions.
- **Dedicated deployments** use the same code with one tenant and, if wanted, one database; no separate code path.

**Tests and acceptance** (the hard part, so it is specified first)
- **Isolation sweep:** for every route in the permission table, create resources as tenant A, call with tenant B's key and ids, and assert 404 (not 403, so existence does not leak). The test is generated from the route table, so a new route without a case fails.
- **Isolation fuzz:** random interleavings of two tenants' conversations, searches, exports and erasures; assert no row, trace, memory, knowledge passage, audit entry or outbox message crosses.
- **RLS test:** with the application predicate deliberately removed from a store method, RLS still returns nothing for the wrong tenant.
- **Webhook and channel routing:** the same phone number id cannot be bound to two tenants; an unbound inbound call is ignored, not guessed.
- **Backfill test:** upgrade a database seeded by the current release; all data is reachable as tenant `default`; downgrade works.
- **Performance gate:** throughput within 10 percent of today's documented figure at the same settings.
- **Threat model** gains a tenant-isolation section; the standing security tests include the sweeps above.
- *Verified here:* all of it on real Postgres. *Needs outside verification:* operating it as a hosted service (backups per tenant, noisy-neighbour behaviour at real scale).

**Size:** XL (about 4,000 lines plus about 150 tests, and the longest migration so far). **Sequencing:** do this before any connector that stores credentials or any staff feature that stores personal workspace data.

### E3. Identity and governance
| Task | Design | Verified here |
|---|---|---|
| **E3.1 Keys scoped to agents and environments** | `api_keys` gains `agents` and `environments` lists; the access layer reads the agent id from the route and refuses out-of-scope calls; chat tokens already bind one agent | Yes (route sweep generates cases) |
| **E3.2 Groups** | Groups with members and role bindings; OIDC group claims map to them (exists for roles; generalise); a user's effective permissions are the union | Yes |
| **E3.3 SCIM 2.0 server** | `/scim/v2/Users` and `/Groups` with a per-tenant bearer token; create, update, deactivate; deactivation revokes sessions; conformance test against the RFC examples | Yes against the spec; partly against real IdPs |
| **E3.4 SAML (flag)** | Behind `NORTHCX_SAML=1` using a maintained library (D5); SP-initiated, signed assertions only, audience and replay checks, clock skew; until then the docs describe an OIDC bridge | Partly (library test vectors; a real IdP needs an outside check) |
| **E3.5 Publish approval ("two-person rule")** | A release to production can require approval by a different person than the author; builds on reviews and the publish checklist; configurable per environment | Yes |
| **E3.6 Per-team budgets and an agent catalog** | Teams own agents and a currency budget (E1); the catalog lists agents with owner, version, status and usage | Yes |

**Size:** L (about 2,000 lines plus about 100 tests).

### E4. MCP client and server
- **Client:** `mcp_servers` in tenant config (https URL, credential reference, allow-listed tool names, default `effect: write` unless the server marks a tool read-only, approval rules per tool as for any tool). Remote tools are registered into the registry with their schemas, so scopes, approvals, guardrails, output screening and the audit trail apply unchanged. Transports: HTTP only; **no stdio** (a subprocess launched from configuration is an arbitrary-code risk). Hosts go through the residency policy and the SSRF checks used for connectors.
- **Server:** exposes a small read-only set first (knowledge search, conversation search for permitted keys, ask insights, list approvals) authenticated with NorthCX API keys and filtered by the caller's role. Write capabilities (decide an approval) wait until the read set has been through review.
- **Tests:** an in-process fake MCP server; schema translation, errors, timeouts, hostile tool descriptions and results (screened as untrusted data), no stdio, allow-list enforced.
- **Size:** M (about 1,200 lines plus about 60 tests). *Partly verified:* real MCP servers differ in details.

## 7. Wave 2: the staff workspace

The product shift: the same engine, a different audience. A **staff principal** (a signed-in person with a role) talks to agents with **staff tools**, under the permissions of that person.

### E5. Workspace chat, staff memory and permission-aware search
*(Since 2026-11-09 the user-facing design of the Workspace, the Pilot and personal intelligence is in `../07-design/NorthCX_Platform-Features-and-Tabs.md` and the specifications in `../03-specs/`; this section keeps the backend design.)*
- **Audience field.** `AgentSpec` gets an optional `audience: staff` (removed from the canonical form when absent, so existing digests are unchanged). Staff agents may use staff tools; customer agents cannot be given them (validated at version creation).
- **Tool context carries the actor.** `ToolContext` gains the caller's permissions, so every staff tool checks them itself ("search conversations" requires `traces:read`; "export" requires the export permission). A staff agent therefore can never do more than the person using it.
- **Staff tools (first set):** search knowledge, search conversations (masked), get a conversation (masked, audited), ask insights (E-O8, exists), list hand-offs and approvals, draft a reply, summarise a conversation, create a report (E6). Each tool is read-only except the ones that create an output.
- **Endpoint and UI:** `POST /v1/workspace/chat` (streamed like customer chat, bound to the signed-in identity; `customer_id = staff:<id>` for memory), and a **Workspace** home in Studio: chat, saved prompts from libraries (E6), recent outputs.
- **Staff memory:** namespaces `staff:<id>` (private) and `team:<id>` (shared), using the existing memory service with the existing recall and erase paths; shown and editable in Studio.
- **Permission-aware search framework.** A `SearchProvider` protocol: `search(query, identity) -> results with source and access`. Providers: knowledge, conversations, hand-offs, and later connectors (E9). Results fuse with the existing reciprocal rank fusion, each provider has a timeout, and **a provider that cannot prove the caller's access returns nothing**. This is the foundation for "why are refunds up this week?" across systems.
- **Staff guardrails:** per-role approved models and tools; export data-loss rules (mask by default, volume thresholds that require approval); everything in the audit log with the same hash chain.
- **Tests:** a staff agent cannot call a tool its caller lacks permission for (matrix over roles x tools); staff tools masked like conversation search; prompt-injection scenarios against staff tools (a customer message containing instructions must not reach staff tools as commands); memory isolation between staff and teams; tenant isolation (E2).
- **Size:** L (about 2,500 lines plus about 120 tests). *Needs outside verification:* quality of staff answers with a live model.

### E6. Libraries and generated outputs
- **Libraries:** `library_items` (type: prompt, macro, playbook, template, file; owner; visibility private, team or tenant; versions; usage counts) with sharing permissions; macros feed agent-assist suggestions (H6); a skill catalog view over existing skills with versions, owners and usage.
- **Outputs ("applications"):** a report service that produces **CSV, HTML and Markdown** first (figures computed by code from insights; narrative text optional and written by the model from aggregates only, never from conversation text), then **decks** (PowerPoint via an ordinary library) built from a structured outline. Outputs are stored as expiring artifacts with download endpoints, audit entries, DLP rules from E5, and a "regenerate" action. No output contains anything a figure endpoint would not show the same person.
- **Tests:** permissions per visibility level, generated files validated by reopening them, masked exports, expiry, tenant isolation.
- **Size:** M-L (about 2,000 lines plus about 90 tests).

### E7. QA scoring and digests
- **QA scoring job:** every conversation (or a configured share) scored against a rubric, stored in `conversation_scores` with the rubric version and reasons; sampled human re-scores measure agreement (calibration, as the judge already does); coaching notes per agent or per team. Deterministic checks (policy phrases, required steps from journeys, response time) run without a model; model scoring is optional.
- **Digests:** scheduled insight summaries (weekly voice-of-customer, SLA sweeps) delivered by email, event webhook or Studio, built on E8.
- **Size:** M (about 1,200 lines plus about 60 tests). *Needs outside verification:* rubric quality with a live model.

## 8. Wave 3: automations and connectors

### E8. Automations
- **Model:** an automation has a trigger, steps and limits. **Triggers:** schedule (the claim-once scheduler already used for crawls and schedules), webhook (per-automation secret), event (consumes the status-event feed), manual. **Steps:** run an agent with a prompt template and a tool allow-list, or a built-in action (tag conversations, create an output, send a digest, call an allowed connector). **Limits:** one run at a time per automation, timeout, step count, currency budget (E1), owner, and the permissions it runs with (a named service identity limited to what the owner granted).
- **Safety:** write steps go through the same approvals as anywhere else; a kill switch per automation and per tenant; every run recorded (inputs, steps, tokens, cost, outputs, outcome) and visible in Studio; failures alert through the existing alerting.
- **Natural-language builder:** description to a validated automation draft (same pattern as journeys and agent drafts: fixed fields, names checked against the registry, never saved by itself, tests run in dry-run before it is offered).
- **Tests:** schedule claiming across processes, overlapping runs refused, budget stop, approval gate in a run, tenant isolation, webhook signature, event trigger exactly-once, draft validation (hostile descriptions).
- **Size:** L (about 2,500 lines plus about 110 tests).

### E9. Connector SDK, OAuth app flow and native connectors
- **Connector SDK:** a small documented interface (auth, search, get, actions, pagination, rate-limit hints) so a connector is either **declarative YAML** (extends the existing connector format) or a Python class for APIs that need code. Each connector declares its tools, its search provider (E5) and the access model it can honour.
- **OAuth app setup in Studio:** authorization-code flow with PKCE for the tenant admin, tokens stored encrypted per tenant (master key now, KMS in E12), refresh handled by the existing OAuth code, scopes shown to the admin before approving.
- **Native connectors, in this order (confirm with D6):** a generic ticketing pack (Zendesk-style) and Slack first, then Salesforce Service Cloud, then others declaratively (Intercom, Freshdesk, HubSpot, Shopify, Stripe, Jira, Confluence, Notion, Drive).
- **Verification:** contract tests from **recorded fixtures** for each vendor, a replay server, rate-limit and pagination cases, token refresh. **No connector is labelled "verified" until it has run against a vendor sandbox**; the connector docs state which ones have.
- **Size:** L per first connector, then S-M each (about 600 lines plus about 25 tests each).

## 9. Wave 4: commercial and deployment

### E10. Metering, plans and usage export (P11, depends on E2)
- **Usage events** (append-only, per tenant): conversations, turns, tokens by model with currency cost, voice minutes, approvals, automations runs, storage. Rolled up hourly; exposed through the API and an invoice-ready CSV. Idempotent by event id.
- **Plans and feature flags:** a plan lists limits and enabled features; enforcement points exist already (limits, budgets), so this is configuration plus a clear error ("your plan does not include X").
- **"Resolved" definition:** until a definition is agreed (D8) billing uses conversations and seats; the insights pages keep reporting *containment* and say so.
- **Provider integration** (a payments or billing service) is a separate, later task and needs an account; the plan stops at an export other systems can read.
- **Size:** M (about 1,500 lines plus about 70 tests).

### E11. Deployment kit
- **Helm chart and Terraform skeletons** for AWS, Azure and GCP (managed Postgres with pgvector, object storage, secrets, ingress), `docker-compose` kept for single host. **Partly verifiable here:** `helm lint`/`template` and `terraform validate` if the tools are available; real clusters need an outside check.
- **Upgrade tool:** `python -m northcx.upgrade` with pre-flight (config validation, migration dry run, backup reminder, residency check) and a post-flight smoke test.
- **Ops console:** health, version, migration state, queue depths (outbox, events, crawls, automations), backup status, per-tenant usage (platform admin; no conversation access).
- **License keys** only if D1 chooses a commercial tier.
- **Size:** M (about 1,500 lines of code plus the charts and modules).

### E12. Trust pack and developer portal
- **Compliance documents (documentation work, not certification):** control mapping of existing features to SOC 2 criteria and ISO 27001 controls, a GDPR pack (processing record, a DPA template, a **subprocessor list generated from the residency report**), an AI-management mapping, and a HIPAA considerations note. A trust-center page generated from them.
- **Customer-managed keys:** design and an envelope-encryption interface (a key per tenant wrapping data keys) with providers for the major KMS services and a local test provider; applied first to stored secrets and attachments, then considered for message bodies. *Verified here:* the interface and the local provider; *outside:* each KMS.
- **Developer portal:** the generated API reference (E0.5), SDK guides, a sandbox tenant recipe and the webhook tester (E0.6) as a static site in the repository.
- **Size:** M (mostly documents, about 800 lines of code).

## 10. Portals and surfaces

The target set is ten portals and surfaces. This section maps each to the epics that deliver it, lists the **eight additions** that were not yet in the plan (E14 to E21), and says what can be verified here. Nothing below changes the principle that every surface goes through roles, approvals, audit and residency.

### 10.1 Map of the ten

| # | Portal or surface | Delivered by | Wave | Verified here? |
|---|---|---|---|---|
| 1 | **Marketing site** (product, use cases by team and industry, deployment options, security, customer stories, demo booking) | E13 with E21 | 5 | Static site and demo-request flow: yes. Customer stories: **only with real customers and their permission** |
| 2 | **End-user workspace** (chat, agents, automations, libraries, apps, history) | E5, E6, E8 | 2 and 3 | Yes, against the offline demo model; answer quality needs a live model |
| 3 | **Agent and automation builder** (natural-language plus visual workflow editor) | E8 (natural language) and **E14** (visual) | 3 | Yes |
| 4 | **Admin portal** (users, groups, SAML/OIDC, SCIM, roles, agent catalog, guardrail policies, connectors, usage, cost, audit) | E3, E9, E10, **E16** | 1 to 4 | Yes, except SAML and SCIM against a live identity provider |
| 5 | **Developer portal** (APIs, SDKs, MCP, webhooks, keys, sandbox, docs) | E0.5, E0.6, E4, E12 | 0, 1, 4 | Yes; the sandbox tenant needs E2 |
| 6 | **Analytics and observability dashboard** (adoption, runs, success, latency, cost per team) | E7, E10, **E15** | 3 | Yes |
| 7 | **Trust Center and Legal Center** | E12 and **E17** | 4 | Pages and generated sub-processor list: yes. Compliance reports need an auditor; legal texts need counsel |
| 8 | **Deployment and ops console** (health, upgrades, GPU usage, logs) | E11 and **E19** | 4 | Health, versions, migrations, queues: yes. GPU usage only against fixtures |
| 9 | **Internal back office** (tenants, licenses, feature flags, support access) | E2, E10, E11 and **E18** | 1 to 4 | Tenants, flags, support access: yes. Licenses depend on D1 |
| 10 | **Embedded surfaces** (Slack and Teams bots, Outlook and Word add-ins, browser extension) | E13 surfaces, **E20** | 5 | Browser extension: partly. Bots and add-ins need vendor accounts and store review |

**Since 2026-11-09:** rows 2 and 3 are the **Workspace** app (Pilot, Assistants, Automations and the other tabs) and the Builder; row 4 is not a separate portal but the **Admin** app, which is the Studio extended (25 organization pages under six left items). The final design is `../07-design/NorthCX_Platform-Features-and-Tabs.md`.

### 10.2 The additions

**E14. Visual workflow editor (agents and automations)** *(Wave 3, depends on E8; size M, about 1,500 lines plus about 60 tests)*
- A node-and-edge canvas for journeys and automations. **The graph is a view of the same validated definition, never a second format:** loading parses the existing spec into a graph, saving writes the same spec back, so versions, digests, scenarios and release gates are unchanged.
- Node types follow the spec: trigger, agent step, tool step, approval gate, built-in action, branch, hand-off, end. Validation runs as you edit (unknown tools, strict-order conflicts, unreachable steps, missing approval on write steps) using the server's own checks.
- Accessible by design: every action also works from the keyboard and a list view; read-only diff view between versions; undo and redo.
- Uses an ordinary open-source graph library (MIT or similar) behind one wrapper component, so it can be replaced.
- Tests: round-trip property tests (spec to graph to spec equals the spec), component tests, browser tests that build a workflow, save a version and run its scenarios. *Verified here.*

**E15. Workspace analytics** *(Wave 3, depends on E5, E8, E1; size M, about 1,200 lines plus about 50 tests)*
- Dashboard for **adoption** (active staff, sessions, saved prompts used), **runs** (automation and agent runs, success rate, failures with causes), **latency** and **cost per team** (from the currency usage of E1 and the team model of E3), with every figure showing what it is a share of, as in Insights.
- Staff usage is personal data: the default view is aggregated by team, individual views need the audit permission and are themselves audited, and retention follows the tenant's privacy settings.
- Tests: figures computed from fixtures, aggregation thresholds (small groups are not shown individually), tenant isolation. *Verified here.*

**E16. Guardrail policy management** *(Wave 2, depends on E2, E3; size M, about 1,500 lines plus about 70 tests)*
- A policy library screen: the shipped policies with their allow and block cases, tenant and team policy sets, and **a policy cannot be switched on for production until its test cases pass** (the library already carries the cases). Changes are versioned, reviewed and audited like agent versions, and appear in the release checklist.
- Staff-side policies from E5 (export rules, per-role approved models and tools) are managed here too.
- Tests: enabling and disabling with and without passing cases, versioning, isolation, audit. *Verified here.*

**E17. Legal Center** *(Wave 4, with E12; size S)*
- Pages and **template** documents: privacy policy, terms, acceptable use, a DPA template, the subprocessor list generated from the residency report. Every template is labelled as a starting point that **needs review by qualified counsel**; the product never presents them as legal advice or as agreed terms.
- Verified here: generation, versioning, publishing. Not verifiable here: legal sufficiency.

**E18. Support access** *(Wave 2, depends on E2; size S-M, about 800 lines plus about 40 tests)*
- A platform support person can enter a tenant only through a **customer-approved, time-limited session** (default 2 hours, hard maximum 24), read-only unless the customer grants more, shown to the customer while active (banner and a log entry), revocable at any time, and every action recorded in the **tenant's** audit log under the support identity.
- Tests: no access without an unexpired approval, expiry and revocation take effect immediately, read-only is enforced on every route (generated from the route table), the tenant sees every action. *Verified here.*

**E19. Private-deployment console extras** *(Wave 4, depends on E11, E1; size M, about 1,200 lines plus about 50 tests)*
- **GPU usage and inference health** through an adapter that reads the metrics endpoint of the inference server and node exporter in common text formats; **logs** through a structured, tenant-scoped, size-capped viewer with personal-data redaction on by default and access limited to a platform role.
- Verified here: adapters and the viewer against fixtures and generated logs. **Not verifiable here:** real GPUs and real inference servers.

**E20. Outlook and Word add-ins** *(Wave 5, depends on E5, E9; size M)*
- Web apps plus manifests that reuse the workspace API with the user's own sign-in and permissions: summarise a thread, draft a reply, insert a cited policy answer, send a document to a library.
- The web parts can be built and tested here; **loading them in Office, tenant admin approval and store review need Microsoft accounts**, so they are never labelled verified until run there.

**E21. Demo booking** *(Wave 5, with E13; size S)*
- A request form on the marketing site that stores the request, is rate limited and spam-protected, and notifies through the event webhook or email; scheduling itself is a link to an external calendar tool you choose.
- Verified here: the form, storage and notification.

**Marketing content rule (E13).** The site states only what the repository can back up. It carries **no invented customer stories, logos, quotes, numbers or certifications**; the stories section ships as a placeholder with a documented way to add real ones with written permission.

### 10.3 Dependencies in one line each
- The admin portal, back office, workspace, developer sandbox and support access all need **multi-tenancy (E2)** and **identity (E3)**; build those first.
- The visual editor needs **automations (E8)**; workspace analytics needs **E5, E8** and **currency usage (E1)**.
- Policy management needs **E3** and the staff guardrails of **E5**.
- Embedded surfaces need the **workspace API (E5)** and, for vendor surfaces, **vendor accounts**.

## 11. Cross-cutting requirements

| Area | Rule |
|---|---|
| **Migrations** | Continue the numbered series (next is 0029); every migration is reversible, tested on a database seeded by the previous release, and the migration/model equivalence test stays green |
| **Tests** | Standing security tests extend with each epic (no pasted SQL, no dangerous constructs, redirects off, CORS, parsers fuzz). New: generated **tenant-isolation sweeps** from the route table. Real-Postgres tests for every store (the existing in-memory plus Postgres parameterisation) |
| **Performance** | The load tool is the gate: E0.3, E2 and E5 each re-run it; the documented figures in `NorthCX_Performance.md` are updated, never silently lowered |
| **Security** | Threat-model entries per epic before merge; new outbound hosts go through the SSRF checks, https, no redirects, and the residency report; anything a model returns is validated against a fixed list; nothing a model drafts is saved without a person |
| **Docs** | Feature catalog IDs, decision log, Deployment Guide (every new setting), `.env.example`, compose pass-through, CHANGELOG, README status. Reserved catalog IDs: E1 `M1-M5`, E2 `P10`, E3 `P12-P17`, E4 `T11-T12`, E5 `W1-W5`, E6 `W6-W8`, E7 `O11-O12`, E8 `X1-X5`, E9 `T13-T16`, E10 `P11`, E11 `P18-P20`, E12 `P21-P23`, E13 `P28-P29`, E14 `X6-X7`, E15 `O13-O14`, E16 `S12-S14`, E17 `P24`, E18 `P25`, E19 `P26-P27`, E20 `C11`, E21 `P30` |
| **Studio** | Each epic ships its UI with accessible components (table versions of charts, keyboard use) and a browser smoke step in `e2e/smoke.mjs` |
| **Versioning** | Wave releases are 1.1 to 1.4; each ships release notes that restate what is verified here, partly verified, and not verified |

## 12. Milestones and the first slice

| Release | Contents | Gate |
|---|---|---|
| **1.0.0** | Wave 0 hardening plus the items only you can do (live-model pass, penetration test, tag) | The release checklist |
| **1.1** | E1, E3, E4 (E2 may follow immediately) | Conformance suite on all adapters; keys, groups and SCIM sweeps; MCP client against a fake server |
| **1.2** | E2 then E5, E6, E7, E16, E18 | Tenant-isolation sweeps and fuzz; load-test gate; staff-tool permission matrix; policy and support-access sweeps |
| **1.3** | E8, E9, E14, E15 | Automation safety suite; connector contract tests; honest connector labels; workflow round-trip tests |
| **1.4** | E10, E11, E12, E17, E19 | Metering idempotency; Helm/Terraform validation; compliance and legal documents reviewed by the owner and counsel |

**Reordering from the gap analysis's "MVP", and why.** The gap analysis puts managed cloud, the staff workspace, two vendor copilots, three connectors, SAML/SCIM and metering in one stage. This plan splits them: the model layer and identity pieces are cheap and unlock the rest; tenancy comes **before** anything that stores per-customer credentials or workspace data; the workspace needs tenancy and actor-aware tools; vendor copilots and connectors wait for the connector SDK so each vendor is a small pack, not a project.

**First slice (milestone 1.1 start), in order**
1. E0.1 split `server.py` into routers (no behaviour change) and E0.2 lock file. *Gate: suite unchanged.*
2. E0.3 shared rate limits. *Gate: two-process test; load figure.*
3. E1 provider interface, capability flags and the conformance suite with the Anthropic adapter first; then the OpenAI-compatible adapter against the fake server; then the providers file, qualified names and residency entries.
4. E1 currency budgets and mixed fallback chains.
5. E3.1 agent- and environment-scoped keys (smallest identity change, highest value).
6. E0.4, E0.5, E0.6, then E0.7 (web split) and E0.8 (multi-replica readiness).
7. E4 MCP client, then server (read-only).

Each step ends with the full backend suite, the web checks, a real-Postgres run, and a verified push to both branches.

## 13. What needs you or an outside party

| Item | What is needed |
|---|---|
| Live-model pass and judge calibration | An API key for each provider you want verified (also needed for every new provider adapter) |
| Penetration test | An outside tester, scoped by the Threat Model and Security Review; the tenant-isolation work in E2 should be in scope before it is exposed as a service |
| Vendor connectors (E9) | Sandbox or developer accounts for each vendor, and for marketplace listings the vendor's review |
| SAML (E3.4) | A test identity provider |
| Managed cloud (D1, E2, E10, E11) | Hosting accounts, an operations owner, backups, on-call; the code can be ready, the service is an organisation, not a repository |
| SOC 2 / ISO / HIPAA | An auditor and a period of operation; this plan only produces the documents and controls they will ask about |
| Native iOS and Android SDKs | Platform toolchains and devices; the web widget in a WebView is the interim answer |
| Billing provider | An account and a decision on D8 |
| Naming, open model, trademarks | D1 and D2, with qualified advice |
| Customer stories, logos, quotes (marketing) | Real customers and their written permission |
| Legal Center texts | Review by qualified counsel; compliance reports need an auditor |
| GPU and inference views (E19) | Real GPUs and an inference server to verify against |
| Outlook and Word add-ins (E20) | Microsoft accounts, tenant admin approval and store review |

## 14. Risks

| Risk | Mitigation |
|---|---|
| **Tenant isolation bug leaks data** | Two-layer isolation (application predicate plus row-level security), generated sweeps and fuzz, a penetration test scoped to it before any hosted use |
| **Performance regression from tenancy** | Load-test gate at each step; the explicit-predicate path can replace per-transaction settings if needed |
| **Scope growth** (this is a multi-year plan) | Each wave ships on its own; each epic is useful without the next; re-plan at each wave boundary |
| **Staff tools widen the attack surface** | Actor-aware tool context, role matrix tests, customer text never treated as staff instructions, same approvals and audit |
| **Connector claims outrun verification** | Labels per connector; "verified" only after a vendor sandbox run |
| **Open-source vs commercial conflict** | Decide D1 before E10 and E11; keep any enterprise code in a separate directory |
| **Maintainability** | E0.1 first; file-size and test-count discipline; the decision log keeps the reasons |

## 15. Definition of done for any epic

Tests (unit, real-Postgres, standing security) pass; the full backend suite, web and SDK checks pass; Studio smoke passes where there is UI; docs, catalog, decision log, CHANGELOG, `.env.example`, compose and residency report updated; threat-model entry added; the verification label (verified here / partly / outside) is written in the release notes; the change is pushed to both branches and the remote SHA verified.
