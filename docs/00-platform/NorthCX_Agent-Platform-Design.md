# NorthCX Agent Platform: Design of Chat, Studio, Integrations and Automations

Status: **Plan** (proposal, nothing here is built). Updated: 2026-11-18. Master for: the design of the four platform modules (Chat, Agent Studio, Integrations, Automations) and the Agent API and tool gateway beneath them. The staff Workspace and packaged CX agents are later products on this API and are out of scope here.

## 1. Purpose and approach

NorthCX already has a strong customer-agent engine (runtime, guardrails, approvals, versions, release gates, audit). The proposal is to **re-platform in place**: keep that core and its tests, put one Agent API and one tool gateway in front of it, and rebuild the Chat, Studio and Automations experiences and the Integrations layer on top, one module at a time. It is not a rewrite.

Principles carried over from the product definition: safe by default (fail closed), actions are explicit (typed tools, approvals, audit), everything is testable, humans stay in the loop, every external dependency sits behind an interface.

## 1a. Decisions from the owner (2026-11-18)

1. **Self-hosted for now.** The first customers run NorthCX on their own infrastructure. A managed cloud is later. Consequences: every module must run from the existing Docker Compose stack with no required cloud service; anything optional (an Activepieces sidecar, a local model) must be genuinely optional; outbound access to external servers (for example a vendor's MCP server) must be an explicit, reviewable network decision for the operator.
2. **Studio is a CX product for non-engineers.** The primary author is a CX lead or operations person, not a developer. Consequences: plain-language and graph authoring come first, YAML becomes an advanced and export view, errors and checks are written for non-engineers, and nothing a CX author needs may require editing environment variables or files. Engineers keep full code access.

Two roles result, and the design keeps them apart: the **operator** (platform engineer, sets what is allowed: hosts, servers, secrets, models, limits, once) and the **CX author** (builds and releases agents and routines within what the operator allowed).

## 2. What the research found

Verification: **repo** means read in this repository; **vendor/search** means a vendor page or a search summary (directional only); **not verified** means background knowledge.

| Topic | Finding | Source quality |
|---|---|---|
| MCP | Spec revision 2026-07-28 is final. It is stateless (no initialize handshake or session header, so any server instance can serve a request), hardens authorization (issuer validation), and formalises extensions (Tasks, MCP Apps). Tool annotations and elicitation were not confirmed. | search of MCP blog and spec pages |
| AG-UI | Typed event stream. Human approval is an **interrupt**: the run ends with `RUN_FINISHED` carrying an `interrupt` outcome (id, reason, message; reason `tool_call` references a prior tool call), and the client starts a new run with a `resume` array answering every open interrupt. | search of AG-UI docs |
| assistant-ui | MIT React chat library with tool UI and inline approvals; works with AG-UI and custom data-stream backends. Its own AG-UI runtime docs could not be reached. | GitHub page |
| Activepieces | Integrations ("pieces") are TypeScript packages with one auth definition, actions and triggers; action and trigger names are permanent because flows store them. Embedding and multi-tenant details were not confirmed. | docs via search |
| Durable approvals | Temporal models a wait for approval as a signal with a timeout, with no compute used while waiting. Limits: deterministic workflow code, and a history cap of 51,200 events or 50 MB. | Temporal docs via search |
| Competitors | Sierra Journeys and Decagon AOPs are natural-language procedures compiled to structured logic, with generation from existing procedures or transcripts; Intercom replaced Tasks with Procedures (March 2026), keeps Workflows for linear canvas flows, and simulates procedures on past conversations. | vendor pages, unverified |

## 2a. Lessons taken from the reference projects

The projects below were read for ideas only (GitHub pages and search summaries; no code was read or copied). Each lesson names the design decision it changed. "Inferred" means the lesson is my reading of a feature list, not something confirmed in code.

| Reference | Lesson | Decision it changes |
|---|---|---|
| **Sim** (workflow builder; Next.js, Zustand, TanStack Query, React Flow; 280+ integrations with triggers and actions) | An integration is a bundle of **actions and triggers**, browsed in one catalogue next to the canvas | The connection catalogue (section 5) lists triggers as well as tools; Automations and Studio both read it |
| **Hermes Agent** (one gateway process for many messaging platforms; session search with FTS5 plus summaries; cron with delivery to chat; skills improved from use) | Channels, scheduled jobs and memory share one gateway and one session model | Chat sessions stay channel-neutral (section 6); scheduled results are delivered only to staff destinations the administrator set up, never to customers (NorthCX's existing `notify` rule); skills-from-use is a Studio suggestion that goes through the normal draft, test and release path, never self-applied |
| **LobeHub** (agent config bundles role, model, skills, connectors, memory; team modes sequential, parallel, debate; reviewable editable memory; resource library) | Agent setup is one screen; memory should be visible and editable by a person | Studio's agent inspector shows model, tools from the catalogue, knowledge and memory settings together; memory view with delete stays a requirement. Team modes are **not** adopted (specialist routing already exists and supervision is simpler) |
| **LibreChat** (branching, edit and resubmit, file chat, artifacts, MCP) | Staff need to re-run a conversation from an earlier turn with a changed message | Studio test console and Pilot get edit-and-rerun from a turn (staff surfaces only; customer conversations are never edited) |
| **Agno AgentOS** (runtime exposed as an API with 50+ endpoints, SSE and websockets, JWT RBAC, OpenTelemetry) | Treat the runtime as a documented API product, not an internal detail | Agent API section 4: publish the contract (OpenAPI is already generated) and version it; every UI uses only it |
| **OpenGeni** (durable, replayable sessions; approvals; Postgres event history and audit; managed sandboxes) | Sessions should be observable, interruptible and replayable from stored events | Add **session replay** from stored trace events to Studio (also useful for simulation regression); confirms the approval and audit model |
| **Onyx** (40 to 50+ connectors; permission-aware search is paid) | Connector breadth is a buying criterion, and per-user permissions are the hard part | Integrations roadmap ranks connectors by the first customers' systems; the gateway carries the **acting identity** so a staff tool call runs with that person's rights (the `Tool.audience` and `permission` fields already model this) |
| **Cognee** (graph plus vector memory; REST, MCP, SDK) | Memory can improve by relationships, not only recall | Memory backend stays behind `MemoryStore`; trial Cognee as one implementation, not a dependency of the four modules |
| **Agenta** (prompt versions, side-by-side comparison, LLM-as-judge, OTel traces) | Compare two versions on the same cases before release | Studio release view adds a side-by-side of the live and candidate versions on the same scenarios (the improvement loop already runs both; surface it) |
| **Jan** (OpenAI-compatible local server on localhost; extensions) | A local model is just another OpenAI-compatible endpoint | No new work: the existing OpenAI-compatible provider is the path; document how to point it at a local server |
| **Intercom Fin, Sierra, Decagon** (procedures compiled to structured logic; simulate on past conversations) | Authors write plain-language procedures; the platform enforces them | Studio procedure-first authoring and simulation from past conversations (section 7) |
| **Macro, Busabase, Rerun, Eigent, Orkas, holaOS, Kuse** (inferred: shared workspaces for people and agents, desktop agent teams) | Mostly employee-side or developer-side products | Informs the later Workspace, not these four modules |

What was **not** adopted, and why: autonomous general-purpose agent behaviour (Hermes, Suna, Eigent) conflicts with the supervised, permission-bound model; team and debate modes add behaviour that is hard to test and approve; copying any project's code (the project policy records that nothing is copied).

## 2b. Product reference model: Fin, Sierra and Decagon

NorthCX is positioned as the self-hosted, inspectable counterpart of Intercom Fin, Sierra and Decagon. All three run the same loop: **teach** (plain-language procedures), **test** (simulations before launch), **deploy** (every channel), **monitor and improve** (insights, always-on quality checks, suggestions). Facts come from vendor pages and third-party reviews and are directional.

Gaps found against NorthCX (the repo column was checked in this repository):

| Gap | Reference behaviour | NorthCX today (repo) | Where it is designed |
|---|---|---|---|
| Native connectors to systems of record | All three integrate natively with helpdesks and CRMs | YAML connectors, a Chatwoot adapter, no MCP yet | Section 5 |
| Guided authoring for non-engineers | Procedures and Journeys written in plain language, generated from existing material | Drafts from procedures and recordings exist; no guided path | Section 7 |
| Plain-language quality criteria | Decagon Watchtower checks live conversations against criteria written in plain language | Quality rubric is a list of deterministic checks (`qa.py`); a model verdict is on request only | Section 7 (author-written criteria that run as model-judged checks, with the deterministic rubric kept as the baseline) |
| Segment-aware guidance | Fin Guidance sets tone and rules by segment or product line | Brand voice, forbidden phrases and per-channel styles | Section 7 (guidance sets attached to segments) |
| Scheduled and CI simulations with alerts | Decagon runs simulations on a schedule or in CI and alerts | Scenarios run in CI as a build gate (`ci.yml`); no scheduled production runs found in the simulation, regression or monitor code | Section 8: a scheduled routine that runs the live agent's scenarios and notifies a destination |
| Proactive suggestions | Fin Suggestions, Sierra monitors | "Improve this agent" on request | Section 7 (surface findings as a feed; changes still go through draft, test, release) |
| Voice | Native voice in all three | Conversation side built; speech and telephony are an operator bridge | Out of scope for the four modules; decide separately |
| Outcome pricing | Per outcome or resolution | Not built | Blocked on D1 |

Where NorthCX should not copy them: managed per-outcome SaaS (self-hosted first), closed workflows (inspectability is the edge), and opaque decisions (reviewers of those products report difficulty understanding individual decisions in real time, which NorthCX's traces and audit log are meant to answer).

## 3. Where the repo is today (anchors)

- **Tools** are `Tool` dataclasses (`northcx/agent.py`): typed input model, `effect` ("read" or "write", write by default), `requires_approval`, `dry_run_result`, audience and permission. Write tools are replaced by dry-run results when the platform is testing.
- **Connectors** (`northcx/connectors.py`, 474 lines) define HTTP tools as data: operator-set host allowlist, HTTPS only, no redirects, timeout and size caps, secrets looked up by name, idempotency keys on writes, pagination, OAuth 2 token handling.
- **Chat** streams over SSE at `POST /v1/agents/{id}/chat/stream` with events `started`, `progress`, `delta`, `error`, `done`. A held action returns status `needs_approval`.
- **Approvals** (`approval_flow.py`): a decision is recorded once, an approved action executes at most once, the customer is told through the outbox, stale approvals expire and escalate.
- **Automations** (`automations.py`, 655 lines): triggers manual, schedule, webhook, event; up to ten steps of kind assistant, report, person, tag, notify, output. `notify` is the only high-risk step and needs a `person` step earlier in the same routine. Routines never write to customers. Person steps wait up to 72 hours.
- **Studio** has a journey form editor (`components/journey-editor.tsx`, no graph), a test console, simulations and release pages. Shared code lives in `packages/ui` and `packages/api-client`.

## 4. Target architecture

```
 Chat surfaces            Studio                 Automations UI
 (widget, console,        (graph editor,         (canvas, runs)
  Pilot, channels)         catalogue, traces)
        |                       |                       |
        +-----------------------+-----------------------+
                                |
                     Agent API  (sessions, runs, events, approvals, versions)
                                |
        +-----------+-----------+-----------+--------------+
        |           |           |           |              |
     Runtime    Guardrails   Memory &     Tool gateway   Automation
     (existing) + approvals  knowledge    (new)          engine (existing)
                                              |
                  +---------------+-----------+-------------+
                  |               |                         |
            YAML connectors   MCP client            Activepieces sidecar
            (existing)        (new)                 (optional, via MCP)
```

Two new pieces, everything else exists:

1. **Agent API**: a stable, versioned HTTP surface that every module calls. Most routes already exist (`chat`, `approvals`, `releases`, `simulations`, `automations`); the work is to document the contract, add the AG-UI endpoint, and stop UIs reaching around it.
2. **Tool gateway**: one place where every tool, whatever its source, is normalised into a `Tool` so that scopes, approvals, dry-run, secrets, residency, audit and tool-output screening apply identically.

## 5. Integrations module (the tool gateway)

**Goal.** An agent can use tools from any system through one path, with no source getting a back door around safety.

**Design.**
- **ToolSource interface** with implementations: `YamlConnectorSource` (existing code, wrapped), `McpSource` (new), `WebhookSource` (signed webhooks; existing for events), and an optional `PieceSource` that reaches an Activepieces sidecar through MCP, not through a private protocol.
- **Normalisation.** Each source returns `Tool` objects. For MCP, map the tool's read-only and destructive hints to `effect` **only if the operator trusts that server**; absent or untrusted hints default to `effect="write"`. The operator can override per tool. Approval rules, scopes, `dry_run` and the idempotency key are applied by the gateway, never by the source.
- **Connections** are tenant-scoped records: source type, server URL or connector file, credential names in the secrets vault (never the value), allowed tools, per-tool effect and approval overrides, health status. Adding one is a permissioned, audited action.
- **Network safety** copies the connector rules: operator allowlist of hosts or server URLs (the MCP equivalent of `NORTHCX_CONNECTOR_HOSTS`), HTTPS only, no redirects, timeouts, response size caps, per-call and per-tenant rate limits. MCP tool results are untrusted data and pass through the existing tool-output screening before the model reads them.
- **MCP transport.** Target the stateless 2026-07-28 revision (fits multiple server replicas), keep a compatibility path for servers on the earlier revision, and use the official MCP Python SDK behind a thin interface (decision D7).
- **NorthCX as an MCP server** (later): expose read-only tools (conversation search, approvals queue, analytics) with scoped keys; write tools off by default.
- **Catalogue** in Studio: connection list, test-call button, tool list with effect and approval settings, usage and failures. Each connection lists its **triggers** (events it can start routines from) next to its tools, so Studio and Automations share one catalogue (lesson from Sim).
- **Acting identity**: a tool call carries who it acts for, so a staff tool runs with that person's rights and never more (see `Tool.audience` and `permission`).

**Self-hosted operation (decision 1).**
- **Operator versus author.** Hosts, MCP server URLs, secrets and limits are set by the **operator**, in an admin screen with audit (today they are environment variables such as `NORTHCX_CONNECTOR_HOSTS`; keep that path and add the screen). CX authors only pick from approved connections.
- **Network reality.** A self-hosted deployment may have no outbound internet. The residency report and an admin "network needs" page list every external host a connection reaches, so an operator can open exactly those. Vendor-hosted MCP servers (Zendesk, Stripe) are optional; a connection to a server inside the customer's network works the same way.
- **No required extra services.** The gateway, MCP client and connectors run inside the existing backend process. An Activepieces sidecar is an optional compose profile, off by default.
- **Upgrades** must keep stored connections working (migrations, as for the rest of the schema).

**Build versus adopt.** MCP SDK: adopt. YAML connectors: keep. Activepieces: adopt as an optional sidecar for breadth, only through the gateway. First real connectors: vendor-hosted MCP servers (Zendesk, Stripe) where they exist, otherwise YAML. Native vendor connectors need sandbox accounts and cannot be verified here.

**Tests and gates.**
- A gateway conformance suite run against every source: read tools run, write tools are held or dry-run in simulation, hints from an untrusted server are ignored, secrets never appear in results, redirects and disallowed hosts are refused.
- Extend the tenant isolation sweep to connections.
- Prompt-injection attack scenarios aimed at MCP tool output.

**Risks.** Server-supplied tool descriptions can carry injected instructions (treat as data, show them to a reviewer at connection time, pin and diff them); an MCP server changing tools after approval (hash the tool list and require re-approval on change).

## 6. Chat module

**Goal.** One conversation contract for all surfaces, with approvals and tool activity visible, and a better UI than today's test console and Pilot.

**Key design point.** In NorthCX the person who approves a held action is a **teammate**, not the end customer. So the same event shows two ways:
- **Customer surfaces** (widget, messaging channels): the reply says the request is with a teammate; the outcome arrives later through the outbox. No approval UI.
- **Staff surfaces** (Studio test console, Workspace Pilot): the interrupt is shown inline and can be resolved by the signed-in person.

**Design.**
- **AG-UI adapter**: a new endpoint (for example `POST /v1/agents/{id}/agui`) that maps the runtime's events to AG-UI. `started` to run start, `delta` to text message content, tool activity to tool call events, `done` to run finished, and a held action to `RUN_FINISHED` with an `interrupt` outcome (reason `tool_call`). Resuming after a decision is a new run carrying `resume`. The existing SSE endpoint stays for compatibility.
- **Renderers**: adopt assistant-ui for the Studio test console and Pilot (tool cards, inline approvals, attachments). Keep the dependency-free `<northcx-chat>` widget and teach it the subset of AG-UI it needs.
- **Session model** unchanged (sessions, traces, tokens, idempotency keys); add the missing channel features listed as not built (media and buttons on messaging channels) as a separate work item.
- **Trace link**: every message shows its trace so a reviewer can jump from a conversation to the steps.
- **Staff-surface extras** (Studio console, Pilot only): edit a turn and re-run from it, and replay a stored session from its trace events. Customer conversations are never edited.

**Tests.** Contract tests that replay the same runtime run through both the legacy SSE and AG-UI and compare the content; browser tests for approve, reject and expiry; the widget bundle size budget.

**Risks.** The AG-UI spec is young (verify event names and the interrupt and resume shape against the current spec before building); assistant-ui's AG-UI runtime docs were not reachable, so prototype it first.

## 7. Agent Studio module

**Goal.** A CX lead with no engineering help designs, tests and releases an agent, and an engineer can still work in code, with the two always equivalent.

**Non-engineer requirements (decision 2).**
- **Default path is guided**: start from a template or from pasted procedures or transcripts, then review a plain-language summary of what the agent will do, which tools it may use and what needs approval. YAML is behind an "Advanced" view and an export.
- **Plain-language checks**: every validation message says what to change in the author's terms (for example "this step uses a tool that can change an order, so it needs an approval rule"), never a schema path.
- **Safe defaults and guard rails in the UI**: write tools default to needing approval; a release is blocked with a clear checklist (tests passed, reviewer named); the author can always preview and test before anything is live.
- **Test in place**: type a customer message beside the editor and see the trace as steps in words; one click turns a good or bad conversation into a test.
- **Choose from what the operator allowed**: the tool and connection pickers show only approved connections; the author cannot add a new host or secret (that is the operator's job, section 5).
- **Usability gate**: the module is not done until a CX lead who has never seen the product creates, tests and releases a template-based agent in a timed, observed session without help from engineering.

**Design.**
- **One canonical definition**: the agent spec (YAML) stays the source of truth. The UI edits it through the server, and a **round-trip test** over generated definitions proves the graph view and the YAML always agree. This is the same technique already used for the Automations canvas.
- **Graph editor** on React Flow for journeys: step nodes, branch edges, a node inspector, keyboard operation, accessibility parity with the form view. The current journey form editor remains as the list view.
- **Connector picker**: tools are chosen from the gateway catalogue, with effect and approval shown, instead of typed names.
- **Procedure-first authoring** (the Sierra and Decagon pattern): write steps in plain language, compile to the structured journey deterministically, and generate from existing procedures or transcripts (already built: drafts from procedures and recordings).
- **Run panel**: run a scenario or a live test on the canvas with the trace overlaid on nodes.
- **Release path unchanged**: immutable versions, scenarios and attack suites, gate, staged rollout, rollback; add an **agent catalogue with publish approval** (two-person rule, as for policies).
- **Improvement loop** stays: it proposes a draft version and never releases. Surface its live-versus-candidate comparison as a side-by-side view on the same scenarios in the release screen.
- **Agent inspector**: one panel showing role and instructions, model, tools from the catalogue, knowledge, and a memory view with delete.

**Tests.** Round-trip property tests; browser tests for create, edit, test, release; contrast and keyboard tests (existing standing tests).

**Risks.** A visual editor that can express things the spec cannot (keep the editor a projection of the spec, never a second model); scope creep into a general workflow builder (Studio edits agents, Automations edits routines).

## 8. Automations module

**Goal.** Staff-defined routines that are safe, durable and expressive enough for real CX work (digests, triage, SLA sweeps), without changing the rule that a routine never writes to customers.

**Design.**
- **Keep the engine and its invariants**: unique-per-routine runs, leases, kill switches, daily budget, publish needing a second person, `person` approval before anything that sends data out.
- **New step kinds** (each validated by the same `validate_definition` path):
  - `tool`: call a gateway tool. Read tools run freely; **write tools require a `person` step earlier in the routine**, exactly like `notify`.
  - `branch`: conditional on a previous step's structured result (small expression language, no code execution).
  - `foreach`: bounded fan-out over a result list with a hard item cap.
- **New triggers**: connector events (for example a ticket created) arriving through signed webhooks or piece triggers, registered through the gateway and listed in the shared catalogue.
- **Delivery** of a routine's result goes only to destinations the administrator set up (the existing `notify` rule), never to customers.
- **Builders** stay: YAML, canvas (move to React Flow once Studio's is proven), and describe-it.
- **Durability**: keep the Postgres-backed waiting runs. Moving to Temporal is not needed yet: it adds an operational dependency, determinism rules and a history cap (51,200 events), and the existing person-step wait already survives restarts. Revisit only if routines need long fan-out, compensation or sub-workflows.
- **Activepieces**: use pieces as optional **step and trigger libraries through the gateway**. Do not run a second automation engine beside NorthCX's, because it would bypass the approval and audit model.

**Tests.** Extend the existing automation tests with: a write tool without a preceding person step is rejected; branch and foreach limits; a run waiting for a person survives a restart; tenant isolation for the new step kinds.

**Risks.** Expression-language scope creep (keep it tiny and total); fan-out cost (the budget and item caps apply).

## 9. Cross-cutting requirements

- **Tenancy**: connections, catalogue entries and routines are tenant-scoped; add them to the whole-route isolation sweep.
- **Secrets**: credentials only by reference to the vault; rotate without redeploy.
- **Audit and traces**: every tool call, connection change and approval is audited; tool calls carry the connection id.
- **Residency**: the residency report lists every external server a connection talks to.
- **Cost**: tool calls and model calls count against existing budgets.
- **Docs and changelog** for each step, as the project's definition of done requires.

## 10. Phasing

| Step | Work | Exit check |
|---|---|---|
| 0 | Live-model pass and fix what breaks (needs an API key); decide D1 (open versus commercial) | Shipped scenarios pass in live mode |
| 1 | Tool gateway interface, YAML source wrapped, conformance suite | Existing connector tests still pass unchanged |
| 2 | MCP source plus one real connector (Zendesk) behind approvals | Conformance suite passes against it; injection scenarios pass |
| 3 | Connection catalogue UI in Studio | Add, test and disable a connection without YAML |
| 4 | AG-UI endpoint and assistant-ui in the Studio console | Same run renders identically over SSE and AG-UI |
| 5 | Guided authoring (templates, plain-language summary and checks) then graph editor with round-trip tests | Property tests green; release flow unchanged; non-engineer usability gate passed |
| 6 | Automations: `tool` step, `branch`, connector triggers | Write-tool-needs-person rule enforced |
| 7 | MCP server exposure, widget AG-UI subset, more connectors | Scoped read-only tools only |

## 11. Open decisions

Decided: first customers self-host; Studio is for non-engineers (section 1a).

1. How far to rebuild: this plan assumes in-place re-platforming. Still to confirm.
2. D1 (open versus commercial): affects code layout (a separate enterprise directory) and whether Activepieces or other dual-licensed pieces are bought. Self-hosting makes the question sharper: what, if anything, is sold to a customer who runs it themselves.
3. Which connectors first, set by the first customers' systems.
4. Whether customer-facing surfaces should ever show approvals (this plan says no).
5. Whether to stay on the earlier MCP revision for a transition period.
6. Who the first CX author is, so the usability gate in section 7 can be run with a real person.

## 12. What is not verified

All competitor and project facts above come from search summaries and vendor pages. Nothing here has been prototyped. Before building, verify: the AG-UI interrupt and resume shape, assistant-ui's AG-UI runtime, MCP tool annotations and the 2026-07-28 authorization changes, and Activepieces embedding.

## 13. Priorities (feature review, 2026-11-18)

A review of all ten platform areas (the four modules plus knowledge and memory, testing and evaluation, observability, governance and safety, the model layer and release management), made against the two decisions in section 1a. It is based on the documents and code read in this repository, not on running the product.

**Overall.** The feature set is broad and careful, but unproven: nothing has run against a live model and no customer has used it. The priority is to stop adding breadth and prove one complete customer journey.

**Checked in the code while reviewing.**
- There is **no shadow mode** (the agent drafts, a person sends) for live customer conversations. The nearest feature is agent assist (`northcx/assist.py`): suggested replies and next steps for a person who has *taken over* a conversation.
- A **provisional resolution rate** exists (`northcx/insights.py`): a conversation counts as resolved when its last turn completed, it never reached a person and it stayed quiet for three days. The code notes it can overstate resolution because a customer's return in a new conversation is not detected.

| Area | Verdict | Do next |
|---|---|---|
| Chat | Strong channel coverage | No new channels; make web chat, email and hand-off excellent for the first pilot |
| Agent Studio | Built for engineers today | Highest product priority: the guided path (template, connect, preview, test, release) before the graph editor |
| Automations | Safe, staff-oriented | Freeze new step kinds until a pilot needs them; build only the scheduled simulation routine with alerts |
| Integrations | Largest gap | Tool gateway, MCP, and three connectors for the target market in the product definition (e-commerce and subscription): Zendesk, Shopify, Stripe |
| Knowledge and memory | Mature | Add only a "test my knowledge" check that shows questions the sources cannot answer |
| Testing and evaluation | A strength | Plain-language quality criteria; calibrate the judge once a key is available |
| Observability | Honest figures | Make resolution firm: link conversations to a customer so a return within the window counts against it; agree the definition before any outcome pricing |
| Governance and safety | Ahead of most | Document an OpenID Connect bridge (for example Keycloak or Dex) as the SAML answer; book the penetration test |
| Model layer | Works; not designed for self-hosted buyers | Keep Claude the default; write a short design for local and private models without promising equal quality |
| Release management | Excellent | Surface the side-by-side version comparison in Studio only |

**A missing area: operator experience.** For self-hosted customers, install, upgrade, backup and restore, health and logs decide whether they keep running NorthCX. Add a one-command install with a setup wizard, tested upgrades between versions, backup and restore commands, and a health page.

**Freeze or defer.** The Workspace extras (Spaces, Outputs, Library, Performance: keep, add nothing until pilot users ask); the multi-tenancy preview (not needed for one self-hosted company; frozen until the penetration test); hybrid model selection and the later staff-platform features; new channels.

**First-customer journey to build towards.** Install, connect Zendesk and Shopify, choose an order-status-and-refunds template, write procedures in plain words, run simulations, **shadow mode** (new: the agent drafts each reply and a person approves or edits it before it is sent), staged rollout, and insights showing the resolution rate.

**Order.**
1. Live-model pass when a key is available (everything else depends on it).
2. Tool gateway, MCP, and the Zendesk, Shopify and Stripe connectors.
3. Guided Studio for non-engineers, ending with the usability gate; shadow mode.
4. Operator experience: install, upgrade, backup, health.
5. Firm resolution figure and plain-language quality criteria.

Prompts for Claude Code sessions that carry out these steps are in `../12-project/NorthCX_Session-Prompts.md`.
