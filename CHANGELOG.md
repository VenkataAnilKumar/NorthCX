# Changelog

All notable changes. The format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [Semantic Versioning](https://semver.org/). Detailed design decisions are numbered in `docs/12-project/NorthCX_Decision-Log.md`.

## [Unreleased]

### Fixed (Phase 6 review, 2026-11-22)
- `python -m northcx backup` and `restore` report a wrong database password, address or refused connection as one plain line (never the password) instead of a traceback.

### Fixed (first local-model pass, 2026-11-22)
- OpenAI-compatible providers send `tool_choice: "auto"` whenever they send tools (some local servers ignore the tools without it) and send an empty string, not null, as the content of an assistant turn that only called a tool (llama-cpp-python rejects null).
- The Models page shows a provider's declared tier (`where:` in the providers file) when no routing rules file is set; it showed `public-cloud` before.
- The local-models guide records the first pass: Qwen2.5 3B on llama-cpp-python passed 8 of 18 shipped scenarios and is not qualified.

### Added (Phase 6, WP 6.6, 2026-11-22)
- `GET /v1/insights/overview` also returns `resolutionFirm`: the resolution rate with returns counted against it (a conversation is not resolved when the same customer started another within the window), with its numerator, denominator, `reopened` and `checkable` (conversations whose customer is known). `resolutionRate` is unchanged. The Insights page shows both. Additive.

### Added (Phase 6, WP 6.4, 2026-11-22)
- `GET /v1/system/health` (permission `keys:manage`) and Studio, Platform, System health: the database, the schema revision against the one this version expects, the model providers, each channel and alert delivery, each shown as working, not working or not set up with what to do. It calls no model and sends nothing. Additive.

### Added (Phase 6, WP 6.1, 2026-11-22)
- `scripts/setup.py`: one command writes a working `.env` with a generated database password, admin key and token secret, for the demo model, an Anthropic key or a local model server (it writes `config/providers.yaml`). `--check` says what is wrong with an existing `.env`. It never overwrites a `.env` without `--force`, and never prints a secret. The compose backend now mounts `./config` at `/config` (read-only) and knows `host.docker.internal`, so a server on the same machine can be used. The README and deployment guide use the script; the CI stack job starts from its output and reports the time to the first answer.

### Tests (Phase 6, WP 6.2, 2026-11-22)
- Upgrade tests: databases created at seven earlier schema revisions, with a row in every table, are upgraded to the current schema in CI; no row may be lost and the result must match the code's models. No behaviour change.

### Added (Phase 6, WP 6.3, 2026-11-22)
- `python -m northcx backup --out FILE` and `python -m northcx restore FILE [--replace]`: the whole database in one file, read in a single snapshot, with a checksum for every table. Restore refuses a damaged file, a backup from a newer version, and a database that already holds data (unless `--replace`), then upgrades to the current schema; the audit hash chain survives. The backup holds personal data and is not encrypted. The meaning-search index is not saved. The deployment guide has the Docker Compose commands.

### Tests (Phase 6, WP 6.5, 2026-11-22)
- Tests prove that the production compose setup does not start without sign-in: the server exits with the instruction when sign-in is required and no key exists, the compose backend requires an API key and sets `NORTHCX_REQUIRE_AUTH`, and compose refuses an empty `.env`. No behaviour change.

### Docs (Phase 6 design, 2026-11-22)
- `docs/11-operations/NorthCX_Operator-Experience.md`: stages 1 to 4 for the setup wizard, upgrade tests, backup and restore, a health page, sign-in by default and a firmer resolution figure. Nothing built yet.

### Fixed (Phase 5 review, 2026-11-22)
- A routine's tool step that changes something now writes an audit entry (`automation.tool`) before it acts, and an alert step writes `automation.alert`.
- The Workspace browser smoke no longer fails about 1 run in 10: its output title ended in a 13-digit number that the platform masked as a card number.

### Added (Phase 5, WP 5.6, 2026-11-22)
- Workspace, Automations: the canvas edits the tool, condition, for-each, check-an-agent, judge-conversations and alert steps and a condition on webhook and event triggers, and warns when a step that changes something has no person step before it on every path. `GET /v1/automations-catalog` also lists `agents`. The describe-it drafter still writes only report, assistant, person, tag, notify and output steps; a draft that uses another kind is sent back and then reported. The Automations page intro now describes all step kinds.

### Added (Phase 5, WP 5.5, 2026-11-22)
- Routines have a `criteria` step: recent production conversations of an agent (at most 20) are judged by a model against up to five plain-language criteria, on masked transcripts, with passes, failures and unusable answers counted per criterion. **The judge is not yet compared with people's labels, so every result says `calibrated: false`.** Existing routines are unchanged.

### Added (Phase 5, WP 5.4, 2026-11-22)
- Routines have a `simulate` step (run the scenarios of a live agent in a sandbox, `scripted` or `live`) and an `alert` step (a monitoring finding and the alert webhook, with fixed wording written by staff). A scheduled routine of simulate, a branch on `previous.failed > 0`, and alert watches a live agent. Simulation runs started by a routine have source `automation`. Existing routines are unchanged.

### Added (Phase 5, WP 5.3, 2026-11-22)
- A signed webhook delivery that carries `X-Northcx-Event-Id` starts its routine once: the same id sent again answers `{"duplicate": true, "runId": ...}` and starts nothing (ids are remembered for 24 hours; the same id with a different body is refused with 422). Webhook and event triggers can name a `when` condition over the incoming data; deliveries that do not match are acknowledged (`{"ignored": true}`) and recorded. Deliveries without an event id behave as before.

### Added (Phase 5, WP 5.2, 2026-11-22)
- Routines have a `branch` step (continue, stop, or skip ahead depending on a condition on the previous result, the trigger input or the current item) and a `foreach` step (one tool or assistant step for each item of a list, at most 20). Conditions can read values, compare and combine them; they cannot call anything or loop. The rule that a change needs a person step first now follows every path, so a skip cannot go around the approval. Existing routines are unchanged.

### Added (Phase 5, WP 5.1, 2026-11-22)
- Routines have a `tool` step: it calls a registry tool with fixed or templated arguments (`{{input.order}}`, `{{previous.id}}`) and passes the JSON result on. A tool that changes something needs a person step before it; a tool that asks for approval for the arguments (a refund over its limit) needs that person step to name an approver role or team. The catalogue (`GET /v1/automations-catalog`) lists `tool` among the kinds and the tools a routine may call. Existing routines are unchanged.

### Docs (Phase 5 design, 2026-11-22)
- `docs/03-automations/NorthCX_Automations-Platform.md`: stages 1 to 4 for tool steps, conditions, exactly-once webhooks, simulation checks with alerts, and plain-language criteria. Nothing built yet.

### Changed (Phase 4 review, 2026-11-22)
- Studio: the model tier names are defined once; the Studio browser smoke checks the editor's model list and journey graph.

### Docs (Phase 4, WP 4.8, 2026-11-22)
- `docs/02-studio/NorthCX_Usability-Gate.md`: the timed, observed script for a CX lead to create, test and release a template agent unaided. It has not been run.

### Added (Phase 4, WP 4.7, 2026-11-22)
- Studio, agent editor: "Show as a graph" on each journey. It is a view of the same journey as the form and the YAML (nothing stored separately); steps can be moved, added and removed there. No API change.

### Added (Phase 4, WP 4.6, 2026-11-22)
- Studio, agent editor: the Model field is a list of the configured models with their tier, and shows the recorded qualification result for the chosen model on this agent ("Qualified on …", "Did not qualify", or "Not qualified yet"). No API change. Results appear only after a real-model qualification run, which has not been made.

### Added (Phase 4, WP 4.5, 2026-11-22)
- `POST /v1/agents/{agent_id}/compare` (permission `simulations:run`): the same scripted tests on what is live and on a saved candidate version, each test's result on both, a verdict in a sentence and what differs. Studio: a Compare page (also "Compare with live" on each unreleased version) and a new Release requests screen (Build, Release requests) for the two-person release rule, which existed in the API but had no screen; the Agents page shows how many requests wait for approval. The release flow is unchanged.

### Tests (Phase 4, WP 4.4, 2026-11-22)
- A pinned test for the three ready-made customer agents (order status, returns and refunds, delivery problems). No new behaviour; qualification on a real model is still outstanding.

### Added (Phase 4, WP 4.3, 2026-11-22)
- `POST /v1/agents/{agent_id}/try` (permission `simulations:run`): answer one customer message with an agent definition that has not been saved, after the conversation so far, in a sandbox (nothing is saved or sent, every write is simulated, the model use counts against the daily budget). The response has the steps and a test made from the exchange. The guided setup page has a "Try it" step with it; every conversation in Studio has "Save as a test".

### Added (Phase 4, WP 4.1, 2026-11-22)
- Studio, Build, Guided setup (`/guided?agent=…`): choose an agent (or start from a template or your own material), connect tools, write procedures, read a plain summary of what the agent will do, and save a version, one step at a time. The version preview (`POST /v1/agents/{id}/versions/preview`) returns `summary` (a list of sentences); the tool catalogue (`GET /v1/catalog`) returns each tool's `audience`. Both are additions. The editor's and the guided page's tool picker show only tools that fit the agent's audience.

### Added (Phase 4, WP 4.2, 2026-11-22)
- New optional field `approvals.always` in an agent definition: tools whose every call waits for a person, in addition to any rule the tool has. The editor adds a tool that changes things to it as soon as it is added, and warns when one runs without a person. Definitions without it keep their digests.
- Messages in plain words: the checks on a definition (17 kinds), the release gate's reasons, the release checklist details and the field errors now say what is wrong and what to change, with no field paths or developer terms (for example "The tool 'nope' does not exist here. Pick one from the list or remove it."). Clients that matched the old text must match the new; the codes and structure of the responses are unchanged.

### Documentation (Phase 4 design, 2026-11-22)
- `docs/02-studio/NorthCX_Guided-Studio.md`: Phase 4 (Agent Studio for non-engineers) through stages 1 to 4: what exists, a six-step guided journey, eleven requirements with acceptance checks, the design (a screen over the existing engines; a new `approvals.always` field; plain-language checks), the order of work and what is blocked. Nothing is built yet.

### Fixed (2026-11-22)
- CI now runs the Studio, Workspace and chat-widget browser tests (Playwright, pinned at 1.63.0, a dev-only dependency) against the Postgres-backed stack in the `stack` job. Earlier notes said CI ran them; it did not. One Studio test assumed an input key order that Postgres does not keep; it no longer does.
- An approval or a shadow-mode draft that came from a staging or dev conversation is resolved against the agent of that environment, and the follow-up run stays in it (before, always production).
- The AG-UI resume run's final event carries `choices` like a message run's.
- The Workspace menu's waiting counts (Approvals, Drafts) update after a decision, without a reload.

### Added (Phase 3, WP 3.6b, 2026-11-20)
- The chat widget shows the options an agent offered (`choices` in the reply) as buttons under the reply. Choosing one sends its words like a typed message; typing instead clears them. The widget bundle grew from 12,710 to 13,294 bytes (5,199 gzipped); a new test keeps it at or under 16,384 bytes.

### Added (Phase 3, WP 3.6a, 2026-11-20)
- Choices: an agent that lists the new built-in tool `offer_choices` can offer 2 to 10 short options with its reply. The chat, stream and AG-UI results and the outbox payloads carry `choices` (a list; empty when none). The options are checked with the reply, kept in the stored conversation, and not offered on a hand-off, a held action or a shadow draft. WhatsApp sends reply buttons (up to three) or a list; Telegram an inline keyboard whose taps are acknowledged and read as the customer's message; SMS and email a numbered list in the text. Tested against fakes and mock servers only. The web widget's buttons are WP 3.6b. See `docs/01-chat/NorthCX_Choices-and-Media.md`.

### Documentation (Phase 3, WP 3.6 design, 2026-11-20)
- `docs/01-chat/NorthCX_Choices-and-Media.md`: WP 3.6 re-scoped. The widget will not speak AG-UI and media sending is not built, because neither has a user who needs it now (decision 207); the work is a built-in `offer_choices` tool whose options appear as buttons on the web widget, WhatsApp and Telegram and as a numbered list on SMS and email, and a measured size limit for the widget (16,384 bytes; it is 12,710). Nothing is built yet.

### Added (Phase 3, WP 3.5b, 2026-11-20)
- Studio, Conversations: a **Replay** link opens `/replay`, a player that steps through a stored conversation one event at a time (previous, play, next, slider, list of steps), with each step as a sentence. People who may run simulations can **Edit and run again** on a customer message and see the original reply beside the sandbox answer. New `GET /v1/sessions/{id}/turns` lists the customer's messages with their turn numbers and replies. Reading only: replay never calls the agent.

### Added (Phase 3, WP 3.5a, 2026-11-20)
- `POST /v1/sessions/{session_id}/rerun` (permission `simulations:run`): answer an edited customer message after the conversation that came before it, in a sandbox. Nothing is saved or sent, every write is simulated, and the model use counts against the daily budget. The response has the original reply for comparison, the tools used and the trace events. Studio screens follow in WP 3.5b. See `docs/01-chat/NorthCX_Rerun-and-Replay.md`.

### Added (Phase 3, WP 3.4b, 2026-11-20)
- Workspace, Work, Drafts: the screen for shadow mode. A reviewer sees what the customer wrote and the agent's reply in a box, and sends it as is, sends their own edit, or rejects it with plain reasons and a note; the agreement summary shows its numbers; tabs show decided drafts. The chat widget draws no empty bubble for a reply a person has not approved yet and shows the approved text when it arrives (the status `in_review` is part of the SDK's types). The Work sub-tabs are now Inbox, Approvals, Drafts and Customers for people who may review drafts.

### Added (Phase 3, WP 3.4a, 2026-11-20)
- Shadow mode: an agent spec can set `shadow: true` (customer agents only). The agent still reads and drafts, but no reply is returned or sent (the response has an empty reply and status `in_review`) and every tool that changes something is held as an approval ("Shadow mode: a person approves every action"). A person with the new `shadow:review` permission (reviewer, admin) sends, edits or rejects each draft: `GET /v1/shadow/drafts`, `POST /v1/shadow/drafts/{id}/decision`, `GET /v1/shadow/summary`. A send reaches the customer once through the outbox. Drafts nobody reviews expire after `NORTHCX_SHADOW_TTL_MINUTES` (default 30) and the conversation goes to a person. New table `shadow_drafts` (migration 0058), covered by export and erasure. Voice refuses a shadow agent; simulations ignore the flag. The Workspace screen and the widget change are WP 3.4b. See `docs/01-chat/NorthCX_Shadow-Mode.md`.

### Documentation (Phase 3, WP 3.4 design, 2026-11-20)
- `docs/01-chat/NorthCX_Shadow-Mode.md`: shadow mode (the agent drafts, a person sends) for customer agents: what exists in the code and what it implies, 14 requirements with checks, the design and four decisions. Nothing is built yet.

### Added (Phase 3, WP 3.3, 2026-11-19)
- Studio's test console shows each tool the agent used as a card, a held action as a card with Approve and Reject (one click decides it through the existing approvals route; a decision made elsewhere or an expiry is noticed and the buttons go away), and the trace as numbered sentences with the full event list one click away. No backend change. See `docs/01-chat/NorthCX_Test-Console.md`.

### Added (Phase 3, WP 3.2, 2026-11-19)
- `POST /v1/agents/{agent_id}/agui`: a run as AG-UI events beside `chat/stream` (which is unchanged). A held action ends the run with an `interrupt` outcome; staff with `approvals:decide` answer by sending `resume`, which makes the same decision as the approvals route. A customer token cannot resume. The field names of the interrupt and resume are not confirmed against the specification. See `docs/01-chat/NorthCX_AG-UI-Endpoint.md`.

### Documentation (Phase 3, WP 3.1, 2026-11-19)
- `docs/01-chat/NorthCX_AG-UI-Check.md`: what the AG-UI interrupt and resume model says, where it differs from our design and from how approvals work today, and five requirements for the AG-UI endpoint (WP 3.2). Directional only: the specification site could not be reached, and the wire shape differs between the sources.

### Added (Phase 2, WP 2.6, 2026-11-19)
- The residency report (`GET /v1/residency`, Studio's Data residency screen) now also lists every model in the providers file with its own address (a local or private-cloud model is a destination too) and every routine destination. The Claude entry is not listed twice when the providers file names it. New `docs/11-operations/NorthCX_Network-Needs.md`: every address a server may contact and the setting that controls it, checked by a test against the report.

### Added (Phase 2, WP 2.4, 2026-11-19)
- `GET /v1/catalog`: each tool has a new `connection` field (the MCP connection it comes from, otherwise `null`). `GET /v1/automations-catalog`: new `triggerInfo` (type, label, description; the event trigger also lists its events); `triggers` is unchanged. Studio's agent editor groups tools by source and connection; the Workspace routine editor describes the chosen trigger. See `docs/04-integrations/NorthCX_Integration-Catalogue.md`.

### Documentation (hybrid models, 2026-11-18)
- The product is hybrid (decision 198): local and cloud models side by side, each qualified per agent; Claude is one cloud option. New `docs/09-models/NorthCX_Local-Models-Guide.md` (providers file, plain-http rule, qualification through the server; not yet run against a real local server). README, Product Definition (principle 6), Agent Platform design (decision 3, phases 0a and 0b), Models overview, Model-Providers (a stale "not built" line), Project Status, session prompts and CLAUDE.md updated.

- Agent interface references: `docs/00-reference/NorthCX_Agent-UI-References.md` lists commercial and open-source agent interfaces by kind (customer chat, builder studios, general chat apps, agent-in-the-loop, quality and observability) and maps them to NorthCX's screens.

### Documentation (implementation plan, 2026-11-19)
- `docs/12-project/NorthCX_Agent-Platform-Plan.md`: phases 0 to 7 with work packages, exit checks and what each needs from outside, and the seven-stage process every phase follows (research, requirements, design, architecture, implementation, review, test). Linked from the design, Roadmap, Project Status, the docs index and CLAUDE.md.
- Quality bar in `CLAUDE.md` and the plan (owner's instruction): no vague or dead requirements, no dead code or placeholders, no fake behaviour or invented figures, no filler; a feature is built only when it works end to end with tests; every pull request says what was verified.
- Engineering rules in `CLAUDE.md`: one work package per pull request; additive or versioned changes and tested upgrades; no single-provider assumptions; privacy, observability and measurement in every change; justified dependencies; plain, accessible screens; blocked work recorded, never faked.

### Added (Phase 1, WP 1.2, 2026-11-19)
- Each tool records its source (`registry`, `connectors`, `verification`, `knowledge`, `memory` or `staff`), shown in the tool catalogue (`GET /v1/catalog`, new `source` field) and on each `tool_call` trace event. Tools register through `Registry.add_tools(source, tools)`, which refuses a taken name and names both sources. `tool_fingerprint(tool)` hashes a tool's definition (not its code or credentials). No other behaviour changes.

### Tests (2026-11-19)
- `test_runtime_moments_are_events_with_ids_and_no_message_text` failed in CI for a few minutes while the clock's epoch contained the digits of the test order number ("1042") in an event's `createdAt`. The check now leaves the time out and the test pins an epoch in that window, so it no longer depends on when it runs.

### Added (Phase 2, WP 2.3b, 2026-11-19)
- Studio: a Connections screen (Build, Connections) for MCP connections. Anyone who can read versions sees the allowed hosts and each connection's state; an administrator can add a connection (labelled fields with help text), review a server's tools (each marked "Only reads" or "Can change things: waits for a person", with what was left out and why), approve the ticked tools, check for changes (in plain sentences), switch a connection off or on, change trust, and delete it after a second click. When no host is allowed the screen says what to ask for instead of showing a form that cannot work. New `@northcx/api-client` functions for the connection routes.

### Added (Phase 2, WP 2.3a, 2026-11-19)
- MCP connections work through the API (the Studio screen is WP 2.3b). Migration 0057 adds `mcp_connections` (tenant-isolated). `GET/POST /v1/connections`, `GET/PUT/DELETE /v1/connections/{id}` and `POST /v1/connections/{id}/review|approve|check`: an administrator (`keys:manage`) adds a connection (a name that prefixes its tools, an address on the allowed hosts, an optional credential that names a tool secret, trusted or not), reviews what the server offers, approves chosen tools (each with the fingerprint seen; a tool changed since is refused), checks for changes, and switches it off. Approved definitions are stored and registered at start-up and every 30 seconds without asking the server; every call checks the connection is still on and the tool unchanged, so agents built earlier are stopped too. New setting `NORTHCX_MCP_HOSTS` (allowed hosts, also in the residency report). Audit entries `connection.*`. Limits: the default tenant only (the tool registry is shared), agent files cannot name MCP tools, and the catalogue lists MCP tools to the default tenant only.

### Added (Phase 2, WP 2.2, 2026-11-19)
- Trust rules for MCP tools (library level, as WP 2.1): `McpSource(approved=...)` offers only the tools the operator approved whose definition (name, description, input schema, read or write class) is unchanged, and reports added, changed and removed tools; a connection with no approved list offers nothing, and `review()` shows what the server has. A description or input text that reads as an instruction to the model is never offered. New `Tool.untrusted_output`: the runtime screens such a tool's results and error text for instructions to the model even when the agent configured no output guardrail, and does the same for the result of an approved action. Behaviour for every other tool is unchanged. Threat-model row S13.

### Added (Phase 2, WP 2.1, 2026-11-19)
- The MCP client and source (library level; nothing is wired to the server or configurable yet, that is WP 2.3): `northcx/mcp_client.py` wraps the official MCP Python SDK and applies the operator's rules (https, allowed hosts, no redirects, timeout, result size cap, rate limit, credential looked up per call); `northcx/mcp_source.py` turns a server's tools into NorthCX tools named `<connection>__<tool>` that check arguments against the server's own schema, and treats every tool as a write that waits for a person unless the connection is trusted and the server says the tool only reads. `northcx/tool_source.py` adds the `ToolSource` interface with the YAML connectors as its first source. New source label `mcp`. New dependencies: `mcp`, `mcp-types` and their packages (see `THIRD_PARTY.md`), an exception to decision 199 granted by the owner.

### Documentation (Phase 2 design, 2026-11-19)
- `docs/04-integrations/NorthCX_MCP-Integration.md`: Phase 2 research (the MCP 2026-07-28 revision and the official Python SDK), requirements M1 to M12, design, architecture and work packages. Decisions 200 to 202. WP 2.5 (vendor connectors) recorded as blocked: no vendor sandbox accounts. The MCP annotation and authorization points are no longer "not confirmed" in the research notes (read from the specification source; the wording is to be confirmed before use).

### Documentation (Phase 1 open issues, 2026-11-19)
- `docs/12-project/NorthCX_Agent-Platform-Plan.md` sections 5 and 6 record what Phases 1 and 0 left open (Phase 1: acting identity, the `ToolSource` interface, the streaming chat contract, limits of the stability check, descriptive response models, review by a person; Phase 0: the local-model pass, the cloud-model pass, D1 and the penetration test, staff tools that need approval, tool error text) and where each resumes.

### Fixed (Phase 1 review, 2026-11-19)
- The API stability check now also reports a route that needs another permission and a request that enforces a new or stricter limit (maximum or minimum length, count or value, or a pattern); `GET /v1/catalog` works out each tool's input names and fingerprint once instead of on every request (about half the cost of building it for 300 tools); the runtime looks a tool up once per call; the typed responses are also checked against Postgres-backed stores in CI.

### Added (Phase 1, WP 1.6c, 2026-11-19)
- Response models for the last 12 JSON operations (managed scenario create, update and delete; qualifications; event feed and test; hand-off assist; agent improve; journey drafts; attachment upload): 60 of 61 Agent API operations are typed. Only the streaming chat (server-sent events) is not. Attachment list items are now typed too (additive). Responses are unchanged.

### Added (Phase 1, WP 1.6b, 2026-11-19)
- Response models for 29 more Agent API operations (agents, versions, releases, rollouts, simulation scenarios, gate and runs, scenario drafts, feedback, review): 48 of 61 are now typed and covered by the stability rule. Responses are unchanged.

### Added (Phase 1, WP 1.6a, 2026-11-19)
- Response models for 19 Agent API operations (chat, approvals, hand-offs, traces, outbox, attachments list, tags, transcript, event types) in `northcx/api/responses.py`, shown in `docs/api/openapi.json` and recorded in the contract snapshot; the `/v1` stability rule now also covers these responses (no field removed, retyped or made optional). Responses are unchanged: the models describe them and do not filter them.

### Changed (Phase 1 follow-up, 2026-11-19)
- `GET /v1/catalog` tools now include `fingerprint` (a hash of the tool's definition). The api-client types `source` and `fingerprint` as always present.

### Added (Phase 1, WP 1.1, 2026-11-19)
- The Agent API contract: `docs/api/agent-api-v1.json` (61 operations: permission, parameters, request body) and the stability rule for `/v1` (add only; never remove, retype or newly require) in the API Design document. `scripts/gen_agent_api_contract.py` writes the snapshot and refuses a breaking change; `tests/test_agent_api_contract.py` checks it. Responses are untyped today and are not covered.

### Tests (Phase 1, WP 1.4, 2026-11-19)
- `tests/test_tool_conformance.py`: the runtime's guarantees for any tool source (input validated, scope blocks, approval held then run once with the approval id as key, dry-run in simulation, a repeated write runs once, secrets redacted, instructions in results withheld), run against the YAML connector source and a Python source. A new source (the MCP client) adds one fixture.

### Documentation (Phase 1, 2026-11-19)
- `docs/04-integrations/NorthCX_Tool-Gateway.md`: Phase 1 research, requirements G1 to G6, design and architecture. The runtime already applies approvals, scopes, dry-run, secrets and output screening to every tool, so a separate gateway layer is dropped (WP 1.3 folded into the conformance suite, WP 1.4); WP 1.5 deferred; the plan's Phase 1 table revised.

### Documentation (code reuse, 2026-11-19)
- Decision 199: reference code may be copied and rebranded for NorthCX, with no dependency on the source project. Rebranding keeps the licence and copyright notices, in one folder per source project, `third_party/<source>/` (LICENSE, NOTICE) with one "Adapted from" line in `THIRD_PARTY.md`, not in a header in every file and not listing files or features; only permissively licensed code read from the project's own LICENSE file may be copied, never AGPL or GPL, source-available or custom licences, or `ee` and `enterprise` directories. Updated: Code Reuse Policy, `CLAUDE.md`, `CONTRIBUTING.md`, `THIRD_PARTY.md`, `NOTICE`, the reference documents and the session prompts. Files copied from Apache-2.0 projects get one short "Modified from" line; existing notices inside source files stay. Nothing has been copied yet.

### Changed (2026-11-19)
- Studio: the six placeholder pages (Systems, Connectors, MCP servers, Notifications, Usage and limits, Security and sessions) are gone from navigation, with the `/soon` route, the Profile page's placeholder for personal intelligence, the unused `ComingSoon` component and the navigation's "soon" badge. Each returns when its work package ships (plan WP 0.6).
- Simulations: `python -m northcx.simulation --model live` (and `--judge-model live`) now uses the configured models, local and cloud, from `NORTHCX_PROVIDERS_FILE` and, if set, `ANTHROPIC_API_KEY`, as the server does; before, it used Claude only. The server and the command line share one provider setup (`northcx/providers/setup.py`). Server start-up messages are unchanged, except that a wrong `NORTHCX_ANTHROPIC_CLIENT` now starts with "Configuration error:" like the others.

### Fixed (2026-11-19)
- Tenancy preview: chat tokens minted by a suspended tenant's keys kept working until they expired; they are now refused at once, as the keys are. The tenant isolation threat model said this already held; it now does, with a test.
- Approvals: why an approved action ran or not was kept only on the approval record; the outcome and the execution-time checks' events are now added to the trace of the turn that asked. A turn's length in Insights now ends at its reply, so the later record does not change latency figures.

### Fixed (2026-11-18)
- Approvals: an approved action was refused at execution when its tool scope limited it to a channel or to verified customers, because the re-check ran without the turn's channel and without the facts the runtime works out live. The re-check and the tool now get the same context (channel from the held turn's trace; facts from the store, the company's systems and the platform's identity check as at execution). Regression tests added, including that a verification that lapsed before approval still blocks.
- Container images: the Studio and Workspace images each build only their own app (`npm run build -w <app>`). They ran the root build, which builds both apps, but each image holds only one, so `docker compose up --build` (and the CI `stack` job) failed since 2026-11-09.

### Documentation (restructure by platform area, 2026-11-18)
- Documents reorganised by platform area (decision 197): `docs/00-platform/`, `01-chat/` to `10-releases/`, `11-operations/`, `12-project/`, `13-workspace/`; `00-reference/` and `99-archive/` unchanged in role. Moves only, history kept, every internal and code reference updated; the tests and generators that read documents use the new paths.
- Area overviews: a one-page `NorthCX_<Area>-Overview.md` in each area folder (built, gaps, documents). `docs/README.md` rewritten around the areas. The named research behind the Agent Platform design moved to `docs/00-reference/NorthCX_Agent-Platform-Research.md` so documents outside `00-reference/` name no other companies' products; the design keeps the conclusions. Competitive analysis: how each loss scenario is answered (section 9), with the named competitor landscape in `docs/00-reference/NorthCX_Competitor-Landscape.md`. Status corrections: the Feature Catalog's section 12 states, the Product Definition's "designed, not built" line, Project Status and Roadmap now say what changed since 2026-11-09 and where to check.

### Documentation (staff platform design, 2026-11-09)
- Designed and documented, not built: the staff Workspace (six left items with sub-tabs), the Pilot, Assistants and the Agent Hub, Builder, Automations, personal intelligence, hybrid model selection, and the regrouped Admin app (25 organization pages, six left items with sub-tabs). New specifications for the Workspace, Pilot, personal intelligence and automations; a staff platform architecture; feature catalog section 12 (77 planned features); requirements FR35 to FR41; personas, stories, journeys, threat model, non-functional requirements, testing and design system updates; 59 mockups; decisions 153 to 171.
- UI and UX design approved: glass surfaces, one accent colour, a floating six-item rail that can be collapsed to icons or hidden in full window mode, original tab icons, AA contrast rules (`docs/02-studio/NorthCX_UI-UX-Design-Proposal.md`, six mockups).

### Added (Admin: Trust and reliability, Organization settings)
- Admin **Channels** (new `GET /v1/channels`: which channels are on and where each receives messages, never a credential), **Memory** and **Privacy and data** (a person's own assistant notes: view, delete, download; how long outputs and run history are kept) are live. 274 routes.
- Two Admin pages that were placeholders now read live server state: **Trust and reliability** (residency, alerting and delivery, monitoring findings, the customer-view and automation switches) and **Organization settings** (identifier, model provider, limits and where each comes from, switches). Studio's Automations tab opens the Workspace; the Workspace nav no longer marks built tabs as "soon". Screenshots retaken.

### Added (Phase 10: Library items)
- Secrets vault and per-tenant model providers (WP2.5): with `NORTHCX_MASTER_KEY` set, the platform operator can store a tenant's secrets (sealed with AES-256-GCM, tied to the tenant and the secret's name, never shown again; migration 0056) and give a tenant its own model provider (an OpenAI-compatible service at a public https address, its key held as a secret). That tenant's conversations use its provider and never fall back to the platform's; everyone else is unchanged. The master key can be changed with `NORTHCX_MASTER_KEY_PREVIOUS` and a re-seal call. A tenant can see whether it has its own provider (never the key). Connectors, SSO and channel credentials are still platform-wide.
- The Builder's improvement loop: `POST /v1/agents/{id}/improve` investigates how the live agent is failing (hand-off triggers, failed tools, blocked replies, reviewer marks, a few masked examples), has the Builder propose a change to the fields it may change, runs the agent's scenarios against the live version and the proposal side by side, and on request saves the proposal as a draft version for a reviewer. It never releases anything. The agent page in Admin has an "Improve this agent" panel.
- Sharing with a team: outputs, spaces and library items can be private, shared with a team, or shared with everyone. A team is the first group (alphabetically) the owner was signed in under when they shared it; people in that team see it, people in other teams and people in no team do not, and someone in no team cannot share with a team. Administrators can always see it. No migration (kept with the item).
- Routines: a `person` step can say who must answer (`approver: {role: admin}` or `{group: billing}`), and a `notify` destination can be an email address (`name=mailto:...`) sent through the server's own mail settings, still only after a person approved. The Pilot's Do style can also propose a coaching note. PDFs in Spaces are read for their text (scans are refused) and only the masked text is kept.
- Pilot styles Think and Do. Think works through a question carefully, checks each claim against what the tools returned and ends with what it could not verify. Do can propose three actions (tag a conversation, add a staff note about a conversation's customer, save an output) but changes nothing: each shows as a proposal the person confirms, which runs it as them with their permissions checked at that moment, or cancels; a proposal lapses after 30 minutes and ten may wait at once. Migration 0055.
- Files in Spaces: plain-text files (.txt, .md, .csv, .json, .log; ten per space, 200,000 characters each) kept in a space, masked for customer personal data as they are stored, and read by the Pilot as data (never as instructions) when you work in that space. They go with the space. Migration 0054.
- Performance by team: when a hand-off is resolved or an approval decided, the team the person was signed in under is recorded (migration 0053), and the Team card shows figures by team; a team with fewer than five items is grouped under "Other teams" so a small team cannot single anyone out.
- Library items (E6 6.1): prompts, macros, playbooks and canned answers staff keep for reuse, private or shared, with the last 20 versions, tags, a use counter and search; text is masked for customer personal data before it is stored. The Inbox suggests the macros and canned answers that fit a conversation's customer messages and shows the text to copy (nothing is sent from the Workspace). Migration 0052. The Workspace Library page has a "Saved items" tab.

### Added (Phase 9: Automations finished)
- A routine can ask a person (`person` step): it stops and waits (up to 72 hours, five waiting runs per routine), nothing runs and no time is counted. A different person with the right to decide approvals approves or refuses it; the person who started the run cannot. Approving continues from the next step, refusing ends the run, and a run nobody answers ends instead of waiting for ever. The switch, pause and budget still stop a run that was waiting. Waiting runs are on the Automations page.
- Steps that write: `tag` (tags the conversation an event names, saved as `auto-<tag>`) and `notify` (sends the result to a destination the administrator set up in `NORTHCX_AUTOMATION_DESTINATIONS`, signed). A `notify` step is accepted only when a `person` step comes before it in the same routine, so a person approves before anything goes out. A routine still never writes to customers.
- Describe it: `POST /v1/automations/draft` turns a request in words into a routine, checked by exactly the code that checks a hand-written one and walked through as a dry run that calls nothing. The model gets one chance to fix a rejected draft; nothing is ever saved by it. It respects the daily budget.
- Canvas editor: the routine drawn as a line of cards (trigger, then steps), edited from the keyboard (arrows to move, Alt with arrows to reorder, Delete to remove), with a list view and a form per step. It edits the same definition as the YAML view, converting through the server, and a round-trip test over generated routines shows the drawing and the definition always agree.


- Platform API (WP2.8): a separate listener under `/platform/v1` with its own key (`NORTHCX_PLATFORM_KEY`, off by default, on `127.0.0.1:3100` unless changed) to create, suspend and resume tenants, assign a plan, set limits and bind channel addresses. It has no route to a tenant's data, and every change also lands in that tenant's own audit log under the actor `platform`. A suspended tenant's keys stop working at once.
- Per-tenant limits (WP2.5, WP2.7): a ceiling on all of one tenant's requests together, a cap on saved Outputs, and a retention period that overrides the platform's, each resolved tenant first, then platform default, then none. A tenant can read its limits at `/v1/tenant/limits` and cannot raise them.
- The whole-route-table isolation sweep (WP2.9): the real server over a database with two tenants; tenant A creates data on every feature, then tenant B calls every route with A's real ids. Nothing of A's may appear and A's data must be unchanged. It found and fixed a real leak: a chat token minted by a tenant's key opened its conversation in the default tenant.
- The load gate (WP2.9): `tests/tenancy_load.py` compares reads with and without row-level security; enforced with `NORTHCX_LOAD_GATE=1` against a 15 percent limit (measured about 0 to 2 percent on the reference workload).

### Added (Phase 7c: more Automations, and model-based Quality)
- Automations: a fourth trigger, an event from the status feed (for example a hand-off was created). Each routine keeps its own place in the feed and moves it forward before starting anything, so an event starts a routine at most once, a new routine never replays history, and an event that could not start (the routine is busy) is taken on the next pass. A new step kind saves the previous result as a shared Output, which makes a scheduled digest: figures, a staff assistant to write it up, and a saved output. Examples for a weekly digest and an event routine are on the page.
- Quality: ask the model for a verdict on a conversation (`POST /v1/quality/judge`). It reads the masked transcript only, is told the conversation is data, must answer in a fixed shape, respects the daily budget, and is stored apart from a person's review (migration 0051). Calibration now also shows how often the model and reviewers agree, with the disagreements.

### Added (Phase 7b: Customers by order number)
- Find a customer by order number (`POST /v1/customers/find`): exact matches in the last 180 days of conversations, shown by customer reference only (never the identifier), audited under a one-way hash of the order number. Open a match by its conversation (`sessionId`) for the same masked record; notes and fact removal accept the same. The Customers page has the order number box.

### Added (Phase 7a: Outputs and Spaces, and the open items)
- Outputs (E6): keep a result (note, answer, report, table, digest) with versions (the last 20), private or shared, expiring after 90 days by default, with masked HTML, Markdown and text downloads (CSV for tables), every export audited. Customer personal data is masked before anything is stored. The Pilot has a "Save to Outputs" button.
- Spaces: a named piece of work with instructions the Pilot follows when you work in it (they guide it and never give it more access), private or shared; deleting a space keeps its outputs. Migration 0050. The Workspace Outputs and Spaces pages replace the placeholders.
- Open items fixed: a routine's webhook secret is derived from the server's signing secret and a per-routine nonce instead of being stored, so a database leak does not reveal it (replacing it, or changing the token secret, invalidates the old one); a Customers lookup now asks the database for only that customer's conversations.

### Added (Phase 6c: Automations)
- Automations (E8): routines with a trigger (manual, schedule or webhook) and up to ten steps. A step is a live staff assistant (read-only, run as a read-only service identity) or a built-in report (performance, quality). No step writes to customers or outside systems, and a routine cannot name a customer-facing agent (decision 165). Results pass from step to step; the previous result and the trigger's input reach the assistant as marked data, never as instructions.
- Safety: publishing needs a second person with the release permission; a published routine can be paused on its own; an administrator can stop every routine in the organization (running ones stop at their next step); a run stops when the daily budget is used up, at its time limit, or when switched off; one run of a routine at a time and three per organization; every action is audited.
- Triggers: manual (`automations:run`), schedule (claimed once per interval across processes), and webhook (needs a key that may run routines, such as the new narrow `trigger` role, and an HMAC signature with the routine's own secret, which can be replaced).
- Run history with each step's result. Migration 0049. The Workspace Automations page replaces the placeholder. Not built: the event trigger, the describe-it builder, the visual canvas, a person step, and steps that write anywhere.

### Added (Phase 6b: Customers)
- Customers (decision 158): look up one customer by the identifier your company uses (in a request body, never a URL) and see a masked cross-channel view: timeline of conversations with channel, agent, hand-offs, ratings and reviews; satisfaction; the facts agents may use, each with who added it and when; and staff notes. Showing the identifier needs a written reason that is logged; every open, reveal, note and fact removal is audited by a one-way customer reference. Leads, reviewers, release managers and administrators have it by default (`customers:read`, `customers:write`); an administrator can switch it off for the organization. An export includes the notes and an erasure removes them. Migration 0048. The Workspace Customers page replaces the placeholder. Search by order number is not built.

### Added (Phase 6: Performance and Quality)
- Performance (E15): `GET /v1/workspace/performance` gives a person their own figures and the team's (hand-offs resolved, approvals decided, typical and slowest times, what is waiting, out-of-hours), each with what it counts. Per-person rows need the audit permission, are audited, and handlers with fewer than five items are folded into "Others". The Workspace Performance page replaces the placeholder.
- Quality (E7): a rubric of deterministic checks with weights, a pass mark and a sampling share (kept in the per-tenant settings, versioned, changed only by someone who may publish); scorecards over a period with averages by agent and by check and the lowest scores; calibration against reviewers' verdicts; coaching notes screened for personal data and erased with the conversation (migration 0047). The Workspace Quality page replaces the placeholder. Model-based scoring and scheduled digests are not built.

### Added (Phase 5c: closing the Phase 5 gaps)
- Four more predefined customer agents (appointments, plan changes, complaints, front door), each with six test scenarios, and four staff assistants as Hub entries (hand-off assistant, shift briefing, conversation analyst, policy guide). The staff tools are now known to the agent registry; a customer agent still cannot use them.
- Workspace Assistants catalog: `GET /v1/workspace/assistants` lists live staff assistants with the tools this person may use; `POST /v1/workspace/assistants/{id}/chat` runs one for them, limited to their permissions and the staff policy, audited, with temporary chats supported.
- Usage by model and by team, and daily budgets set from the Models page (`PUT` and `DELETE /v1/budgets`; a money limit needs prices); migration 0044 (`usage_dims`, `tenant_settings`, `api_keys.groups`).
- Organization policies (E16): proven with their own allow and block cases, proposed, approved by a second person, then locked and applied to every customer agent (or named ones); a change is a new version and the one in force stays in force until approved. Migration 0045; the Admin Policies page has an Organization tab with the editor.
- Organization templates (WP22.5): an organization's own Hub entries, checked, proposed and published only after a second person approves; migration 0046; a "My organization" tab in the Hub.
- Signed built-in templates (WP22.9): each built-in is signed with Ed25519; the Hub shows verified, changed or unsigned, and a built-in that no longer matches its signature cannot be installed. `scripts/sign_templates.py` makes the key and signs. The key shipped now is a development key: generate your own before a release.

### Added (Phase 5: Agent Hub and the Admin pages)
- Agent Hub backend (E22): templates carry audience, category, channels, version, notes and what they can see and do; a requirements check against this deployment (tools, knowledge, channels, tests, model rules); install creates a draft, saves and runs the template's scenarios and records where the agent came from (migration 0043); an update shows what the template changed and what people changed locally, then creates a new draft without merging anything for you. Three new predefined customer agents, each with six scenarios: billing and invoices, delivery problems, account help.
- Admin pages that were placeholders are real: Agent Hub (browse by category, requirements, installed and updates), Models and budgets (providers, tiers, prices without keys, the data policy and rules, qualification, spending against limits), People and groups (groups, roles, members, identity provider names), Policies (the policy library with its allow and block cases, read-only), Usage and billing (tokens and spending per agent and day, per tenant), and Builder opens the existing drafting page.
- New read APIs: `/v1/models/overview`, `/v1/usage`, `/v1/policies`, `/v1/hub/installs`, and the requirements, install and update routes under `/v1/templates/{id}`.

### Added (Phase 4: staff backend and the Pilot)
- Staff agents: `audience: staff` on the agent spec (omitted from the canonical form when absent, so existing digests do not change); a customer agent cannot be given a staff tool and a staff agent only staff tools; staff tools name the permission they need and the runtime refuses the call unless the signed-in person holds it.
- Staff tools (masked and audited, none can send, decide or change anything): search and read conversations, list hand-offs and approvals, insights, summarise, draft a reply (never sent), search the knowledge, and the person's own working notes.
- `POST /v1/workspace/chat` and `/stream`: the Pilot for Quick answer, bound to the signed-in person, per-person chats, cited sources, staff chats kept out of customer figures (environment `workspace`).
- Research tasks (`/v1/workspace/tasks`, migration 0042): questions (at most three), a plan the person edits and approves, a step-by-step run that survives closing the browser, pause and stop between steps, step and token limits, a versioned cited result. Tasks belong to their owner and are tenant-isolated.
- One search across knowledge, conversations and hand-offs (`/v1/workspace/search`): reciprocal rank fusion, only the sources the person may use, each result says why it is visible, a slow source is named and skipped.
- Staff memory (`/v1/workspace/memory`): the person's own working notes with edit and erase; customer details, secrets and instructions are rejected; per-chat switches for memory and temporary chats that keep nothing.
- `NORTHCX_WORKSPACE_POLICY_FILE`: tools per role, the model and a rows-per-call limit for staff assistants.

### Added (Phase 3: identity)
- API keys can be limited to particular agents and environments (`agents`, `environments` when creating a key; migration 0033). A limited key reaches only routes that name one of its agents in their path, plus `/v1/me` and its own agent list; everything else is refused. A sweep generated from the route table proves it on every route.
- SCIM 2.0 provisioning (`NORTHCX_SCIM_TOKEN`, `/scim/v2` Users and Groups with patch and filter; migration 0035): deactivating or deleting a person revokes their sessions in the same request and blocks sign-in; SCIM never sets roles. Tested against RFC-style messages and the string booleans Azure sends, not against a real identity provider.
- Two-person rule for releases (`NORTHCX_RELEASE_APPROVALS`, `/v1/release-requests`, migration 0036): in the listed environments a publish or promote waits for a different person with the release permission; the release gate is judged at approval; staged rollouts are unavailable there; rollback is never held up.
- Tenant isolation for all tenant data (migrations 0038 to 0041): knowledge and its meaning-search index, crawling, attachments, email, SMS, voice and verification, versions, releases, rollouts, scenarios, simulation runs, usage and budgets (counted per tenant), groups, SCIM people, idempotency, alerts, findings, exports, qualifications and release requests join the conversation tables. Inbound channel messages are routed by binding (SMS number, WhatsApp number id, Telegram bot, email domain); unbound addresses are ignored once any binding exists. Background jobs run once per tenant. Gates: table coverage, conversation-route API sweep, two-tenant fuzz, migration round trip. Not built: per-tenant configuration and credentials, per-tenant rate limits, the platform API, the load gate.
- Tenant isolation for conversation data (migration 0038): sessions, messages, facts, memories, traces, approvals, hand-offs, outbox, feedback, tags, reviews, routes and the customer index carry a tenant and are protected by Postgres row-level security (raw SQL included); client-chosen ids are unique per tenant; background jobs run once per tenant; the server must run as an ordinary database role when more than one tenant exists (`NORTHCX_MIGRATION_DATABASE_URL` for migrations) and checks this at start. Other tables are not isolated yet.
- Tenancy, first slice (migration 0037, `08-governance-safety/NorthCX_Tenancy-ADR.md`): tenants and channel bindings, a request-scoped tenant from the key, keys and audit entries per tenant, suspension, and the decision between predicate and row-level security with measurements. **Isolation of every other table is not built**, so creating a second tenant needs `NORTHCX_TENANCY_PREVIEW=1`; a deployment with no tenants behaves as before.
- Groups (`/v1/groups`, migration 0034): roles bound to people, by hand-added email or by the identity provider's group name. With `NORTHCX_SSO_USE_GROUPS=1` a sign-in session's permissions are the union of the role map and every group the person is in.

### Added (Phase 2: model foundations)
- OpenAI-compatible provider (any chat-completions server: hosted, vLLM, Ollama, llama.cpp), providers file (`NORTHCX_PROVIDERS_FILE`) with tiers, capabilities and per-model prices; the Anthropic key becomes optional when a providers file is given. Tested against a fake server only.
- Daily spending limit in currency (`NORTHCX_DAILY_BUDGET`, `NORTHCX_BUDGET_CURRENCY`), shared across processes with the postgres limits backend (migration 0031). The server refuses to start with a budget when a provider's default model has no price in that currency.
- Hybrid model selection (`NORTHCX_ROUTING_RULES_FILE`): sensitivity marking, a data policy that keeps sensitive conversations off forbidden tiers (including on fallback), ordered routing rules, and a `model_choice` trace event; agents can be marked `sensitive`.

- Per-agent model qualification (`qualification: {required: true}`): a model serves an agent's customers only after a recorded live run passed all required scenarios and 90 percent of the rest, for the agent's current definition (`model` on simulation runs; `/v1/agents/{id}/qualifications`; migration 0032).
- Review fixes: sensitivity now sticks after personal data has been masked in the history; topic words match at the start of a word only; a sensitive conversation whose default model is forbidden finds an allowed one before going to a person.

### Added (Phase 1: screens on existing APIs)
- Both web apps now use the approved design and final names: glass tokens with one accent (blue, teal, violet or graphite), six left items with sub-tabs, a collapsed icon rail (Ctrl B), full window mode (Ctrl .), a command bar (Ctrl K), original line icons on the left items only, and preferences for theme, accent, density, text size, contrast, motion and solid surfaces.
- Workspace routes renamed to the final tabs (Inbox, Approvals, Customers, Pilot, Assistants, Search, Library, Outputs, Spaces, Automations, Quality, Performance); tabs without a backend say so. Admin has the six items Overview, Operate, Build, Govern, Platform and Personal; pages not built yet show an honest not-available page.
- A contrast test checks every text pair on the design tokens against WCAG AA in light, dark, each accent and high contrast; it found and fixed four dark-theme values.
- A Workspace container image and compose service (port 3002, `NORTHCX_WORKSPACE_PORT`); CI smoke-tests it.
- Review fixes: each group remembers its last sub-tab; one heading per page; the collapse button is hidden on narrow screens where the rail is always icons; the Admin browser smoke test now seeds the version and simulation run it needs, so it passes on a fresh stack.

### Added (model providers, first part)
- `northcx/providers/`: provider types, a registry that routes `provider:model` names (bare names keep going to the default provider), capability checks, and Claude as an adapter with two clients: the official SDK and an optional direct HTTPS client (`NORTHCX_ANTHROPIC_CLIENT=http`). The SDK's `citations: null` fields are no longer carried into conversation history.

### Added (resolution rate)
- Provisional resolution rate beside containment in insights, Studio and plain-language analytics: completed, no hand-off, quiet for the window (`NORTHCX_RESOLUTION_WINDOW_DAYS`, default 3 days); conversations inside the window are pending. PRD scope wording updated for after 1.0.

### Added (webhook tester)
- `POST /v1/events/test` sends a signed sample event to the configured events webhook and reports whether the receiver accepted it (marked as a test, not stored or retried, audited, six a minute per key).

### Added (API reference)
- Generated API reference: `docs/api/openapi.json` and `docs/api/index.html`, built from the application's own schema with the permission each route needs; tests keep it in step with the code.

### Added (masked PDF text)
- Agent spec `attachments: [pdf_text]`: a PDF is read as text, personal data is masked, the text passes the input checks, and the file never reaches the model; scanned PDFs are refused with a reason. Accepting `pdf` (the file as it is) now needs `acknowledge_unmasked_files: true`; choosing both is refused. Specs that use neither keep their digests.

### Added (multi-replica)
- `NORTHCX_ROLE=all|api|worker`: run API replicas and background workers as separate processes. Background jobs take a database lease for each pass so workers never repeat each other's work; firing alerts, alert events and crawl progress now live in the database (migration 0030), so any process shows and continues them. Topology in the Deployment Guide.

### Added (shared limits)
- `NORTHCX_LIMITS_BACKEND=postgres` shares rate limits, the abuse burst check and the daily token budget between server processes through two small tables (`rate_counters`, `usage_ledger`, migration 0029). If the database is unreachable each process falls back to its own counters and logs a warning. Default unchanged (per process).

### Changed (supply chain)
- Backend dependencies are now hash-pinned (`requirements.lock`, `requirements-dev.lock`, regenerated by `scripts/lock.sh`); the container image and CI install from them with hashes required, a test fails when a lock is older than `pyproject.toml`, and CI runs `pip-audit` on both. Design tokens moved into the shared `@northcx/ui` package (compiled output unchanged).

### Added
- Monitoring page in Studio: active alerts, rules, recent alert events with delivery status, a test-alert button, and the conversations flagged by the always-on checks.

### Added (abuse detection)
- Optional `abuse_detection` input check: threats go to a person, repeated abuse and repetition are handed off after a limit, bursts get a polite slow-down; the agent is told to stay calm. New `conversation.abuse` status event.

### Added (identity verification)
- One-time-code identity checks (`NORTHCX_VERIFY=1`): two tools send a code only to the email or phone the company reported and check it; success sets a platform-only, time-limited fact that tool scopes can require.

### Added (status events)
- Signed status-event webhook and a pollable feed (`/v1/events`) for hand-offs, approvals, alerts, ratings, releases, key changes, knowledge changes and erasures. Events never contain message text.

### Added (messaging)
- Telegram channel; WhatsApp now supports several numbers (an agent each), incoming pictures and documents through the attachment checks, and approved templates sent only to people who wrote in first or opted in.

### Added (agent building)
- Automatic test scenarios, refinement of a draft by instruction, and audio transcription (operator-configured service) when building an agent.

### Added (insights, filters and charts)
- Analytics questions can filter by language, channel, hand-off, queue and rating, find individual conversations (masked, permission-checked) and draw charts. Turns now record their channel.

### Added (knowledge, scale and freshness)
- Scheduled re-crawls, an automatic approximate (HNSW) index for large knowledge bases, and an optional embedding model per source.

### Added (knowledge, Office files)
- Import Word (.docx), PowerPoint (.pptx) and Excel (.xlsx) files into the knowledge base (read with the standard library; hidden sheets and speaker notes are not read; zip bombs and XML entities are refused).

### Added (residency)
- Data residency policy (`NORTHCX_RESIDENCY_FILE`): every destination data can be sent to is checked against allowed regions at start-up (strict mode refuses to start), with a data-flow report at `/v1/residency` and in Studio.

### Added (building)
- Draft an agent from procedures and conversation transcripts (`POST /v1/builder/draft`, Studio: Agents → Build an agent from your material): personal details masked, only safe fields taken from the model, names checked against the registry, nothing saved.

### Added (insights)
- Ask performance questions in plain words (`POST /v1/insights/ask`, “Ask a question” on the Insights page). The model only picks the figure, period, agent and comparison; the numbers and the answer are computed from the recorded figures and the reading is shown.

### Added (channels)
- WhatsApp channel (Meta Cloud API webhook, signed requests, one-time verification) on the same engine as SMS; refused replies are recorded as undeliverable instead of retried.

### Added (knowledge)
- Optional meaning-based knowledge search: configure any embeddings service (`NORTHCX_EMBEDDINGS_URL`/`_MODEL`); passages are embedded in the background into pgvector, results merge keyword and meaning rankings, and search falls back to keywords if the service fails. The shipped compose file now uses a Postgres image with pgvector.
- Import PDF, HTML, Markdown and text files into the knowledge base; crawl listed websites (robots.txt, sitemap, limits, pruning) from the API or Studio.

### Changed
- Connectors can read paged lists (cursor, page number, offset, Link header) and sign in with OAuth 2 (client credentials, refresh token).
- Alert webhook deliveries are retried (three attempts) and each event records whether it was delivered.

## [1.0.0-rc.1] - 2026-11-03

First release candidate: the planned feature set (phases 1 to 6, minus the items listed under "Not in this release") is built and tested. Before 1.0.0: an independent penetration test and a run against a real model.

### Added
- **Runtime and safety**: typed tools; reply, tool, input and output guardrails; personal-data masking and takeover-phrase checks; fail-closed supervision; human approval with exactly-once execution and expiry; always-to-a-person topics; token budgets; model fallback and retries; conversation summarising; customer facts, company context and long-term memory; skills with enforced step order; brand voice; per-customer tool scopes.
- **Agents as data**: YAML specs with immutable versions, diffs, environments (dev, staging, production), a release gate tied to the exact version, publish checklist, staged rollouts, one-step rollback; journeys (goal, steps, rules, hand-off conditions, progress metrics, generated tests, drafts from plain language); languages with automatic detection; specialist agents and in-turn transfers; attachments (pictures, PDFs, text) enabled per agent.
- **Proof**: scenario simulations with personas and attack suites, regression scenarios drafted from real conversations, release gating in CI, load testing and token-cost estimates with a CI baseline.
- **Channels**: web chat with streaming and a browser SDK with a drop-in `<northcx-chat>` widget; email; SMS; phone calls through a provider-neutral WebSocket bridge with disclosure, consent, barge-in, keypad and language switching.
- **People**: hand-off queues with hours and after-hours routing, hand-off package, suggested replies, person replies and hand-back to the agent, helpdesk and webhook inbox delivery, conversation review with failure tagging and quality metrics.
- **Studio**: a web console for editing and testing agents, scenarios, knowledge, versions, rollouts, reviews, hand-offs, approvals, insights, conversations, access and audit.
- **Insight and operations**: metrics with numerators and denominators, alerts, search and tags, trace export, privacy export/erasure/retention, hash-chained audit log, roles and hashed API keys, single sign-on (OpenID Connect), rate limits, request size caps, safe response headers.
- **Docs**: product, architecture, security (threat model, review report), deployment, performance and cost, SDK and voice guides.

### Security
- Review findings fixed before this release: request size caps, voice stream flood limits, default security headers, a crash on malformed identity tokens, explicit no-redirect HTTP clients. See `docs/08-governance-safety/NorthCX_Security-Review.md`.

### Not in this release
Native iOS and Android SDKs; outbound calls; agent-assisted building (A8); natural-language analytics (O8); data residency options (P6); messaging apps beyond SMS; knowledge crawling and meaning-based search; per-agent scoping of roles; multi-tenancy and metering.

### Known limits
Rate limits and daily budgets are per process unless the Postgres limits backend is turned on; pictures and PDFs reach the model unmasked; real-model and long-run (soak) results are unmeasured. The full list is in the threat model.
