# NorthCX Agent Platform Plan

Status: **Plan**. Updated: 2026-11-19. Master for: the phases, work packages and exit checks for building the Agent Platform (`../00-platform/NorthCX_Agent-Platform-Design.md`), and the seven-stage process every phase follows. Progress is recorded in the table at the end and in `NorthCX_Project-Status.md`.

## 1. How every phase is run
Every phase, and every work package inside it, goes through the same seven stages. Small changes (a bug fix) compress the first four stages into a paragraph in the pull request; large ones get a written result per stage. The owner decided (2026-11-18) that stages run without waiting for approval and that each work package merges into `main` when CI is green.

| Stage | What happens | What it produces | Done when |
|---|---|---|---|
| 1. Research | Read the relevant code; study the specification and reference projects; note what is unverified | Research notes (named products in `../00-reference/`, otherwise in the area folder) | The facts the work depends on are verified or marked unverified |
| 2. Requirements | What it must do, for whom, what it must never do (the safety rules), acceptance criteria, limits (cost, speed, self-hosted) | Requirements with IDs (PRD, user stories, or the work package's section here) | Every requirement has an acceptance check |
| 3. Design | Behaviour and experience: flows, screens, plain-language messages, edge cases, failure behaviour | The design section of the area's master document; mockups for screens | Edge cases and failure behaviour are written down |
| 4. Architecture | Components, interfaces, data model and migrations, API changes, security and tenancy impact, threat-model update, alternatives considered | A decision record in the area folder; decision-log entries; schema and threat-model updates | The safety rules (approval before risky actions, fail closed, audit) and the self-hosted constraint are shown to hold |
| 5. Implementation | Small work packages; tests written with or before the code; docs, changelog and `.env.example` in the same change | Code and tests, one pull request per work package | Targeted tests pass; the change is complete per `CONTRIBUTING.md` |
| 6. Review | Code review (correctness, simplicity), security review against the threat model, docs review, requirements check | Findings recorded on the pull request and fixed | No open blocking finding |
| 7. Test | Full suites in CI, scenario simulations, browser tests, a real-model check where model behaviour matters (local first, then cloud), a usability test where a person is the user | CI green; the exit check's evidence; the area overview updated | The exit check passes; the pull request is merged into `main` |

**Quality bar (owner's instruction): a real product, no AI slop.** The full rules are in `CLAUDE.md`. In short: every requirement has a named user and a pass-or-fail acceptance check (vague words get a number or are cut); requirements and code that will not be built or are no longer used are removed; no stubs, placeholders, fake data or "coming soon" screens in shipped paths; a feature counts as built only when it works end to end through the real API and storage with tests; figures come from measurement or the code, and anything unverified says so; text is short, plain and specific. Stage 6 (review) checks every change against these rules, and a change that breaks one goes back to stage 5. The engineering rules in `CLAUDE.md` (one work package per pull request, no breaking changes, hybrid models by default, privacy in every path, every action observable, measure hot paths, justified dependencies, plain accessible screens, record what is blocked) are checked the same way.

Rules: stages 1 to 4 change only documents; tests are written in stage 5, not saved for stage 7; anything that needs an outside party (a model key, a sandbox account, a tester, a pilot customer) is recorded as blocked with what is needed, and work continues elsewhere.

## 2. Phases
Sizes are rough: S days, M one to two weeks, L several weeks.

### Phase 0: prove what exists (M)
| WP | Work | Exit check | Needs |
|---|---|---|---|
| 0.1 | Fix the review findings: approval scope re-check; chat tokens of a suspended tenant; saving the trace of execution-time checks; staff tools that need approval; tool error text shown to the model | A regression test per finding that failed first | |
| 0.2 | Local-model pass: a local server (for example Ollama), providers file, the test console flows, shipped scenarios live through the server, a qualification | Results recorded; `../09-models/NorthCX_Local-Models-Guide.md` corrected | A machine that can run the model |
| 0.3 | Live mode for configured providers in the command-line simulation runner | The command line runs scenarios on any configured provider | |
| 0.4 | Cloud-model pass (Claude and one other), judge calibration on a strong model | Scenarios pass live; judge agreement measured | Cloud keys |
| 0.5 | Decide D1 (open versus commercial); book the independent penetration test | Decision logged; tester booked | The owner; a tester |
| 0.6 | Remove dead and placeholder surfaces: the Studio "soon" pages (Systems, Connectors, MCP servers, Notifications, Usage and limits, and any others) are either removed from navigation or replaced when their work package ships; requirements and documents that no longer match the direction are archived | No placeholder page reachable from navigation; no requirement without a plan entry or an archive note | |

### Phase 1: Agent API and tool gateway (M)
No behaviour change; the existing suite is the safety net.
| WP | Work | Exit check |
|---|---|---|
| 1.2 | `Tool.source`, one registration function that refuses duplicate names, a tool fingerprint, `source` in the catalogue and the `tool_call` trace event | New tests pass; existing suite unchanged |
| 1.4 | A conformance suite for the runtime's guarantees on any tool source (this absorbs the old WP 1.3: the runtime already applies them to every tool) | Green for the YAML connectors and a second in-test source |
| 1.1 | The Agent API contract: a stated set of routes, a checked-in snapshot and a stability rule (add fields only within `/v1`) | Test fails on a removed or retyped field in a contract route |
| 1.5 | Deferred: no staff tool needs approval today; returns with the Phase 5 `tool` step | Recorded below |
| 1.6a | Type the responses of the conversation-time routes (chat, approvals, hand-offs, traces, outbox, tags, transcript, event types) and add them to the snapshot | A test calls each typed route and checks the answer against its model; the snapshot test fails on a removed or retyped response field |
| 1.6b | Type agents, versions, releases, rollouts, simulations, scenario drafts, feedback and review | The same: 48 of 61 operations typed |
| 1.6c | Type the 12 that need a configured service or a model (managed scenarios, qualifications, event feed and test, assist, improve, journey drafts) and the file upload | The same: 60 of 61 typed; the streaming chat sends server-sent events and stays untyped |

Details and research: `../04-integrations/NorthCX_Tool-Gateway.md`. Order: 1.2, 1.4, 1.1, 1.6a, 1.6b, 1.6c. The `ToolSource` interface is designed with the MCP client (WP 2.1).

### Phase 2: Integrations (L)
Stages 1 to 4 are written in `../04-integrations/NorthCX_MCP-Integration.md` (requirements M1 to M12 and the design). WP 2.1 and 2.2 are library work; MCP connections count as built when WP 2.3 wires them through the API, storage and screen.
| WP | Work | Exit check | Needs |
|---|---|---|---|
| 2.1 | `ToolSource` interface; YAML connectors as its first source; an MCP client on the official SDK, against the 2026-07-28 specification and the earlier handshake revisions | The conformance suite passes for the MCP source against a fake server; existing connector tests unchanged | The owner's exception to decision 199 (granted 2026-11-19) |
| 2.2 | Trust rules: tools default to write unless the connection is trusted; a write needs approval; tool lists pinned by fingerprint, re-approval on change; output screened as untrusted | Injection and changed-tool-list scenarios pass | |
| 2.3 | Stored connections; an operator screen for allowed hosts, servers and secrets (2.3a the backend, 2.3b the screen) | An operator adds a connection and approves its tools without editing files | |
| 2.4 | One catalogue of tools and triggers, read by Studio and Automations | Catalogue API with tests | |
| 2.5 | Connectors for the target market: helpdesk first, then commerce, then payments (vendor MCP servers where documented, otherwise YAML); writes need approval | Sandbox demonstration: ticket lookup, order lookup, a refund held for approval | **Vendor sandbox accounts (none; owner, 2026-11-19)** |
| 2.6 | A network-needs page and residency entries for every connection | Every external host is listed | |

### Phase 3: Chat (M to L)
| WP | Work | Exit check |
|---|---|---|
| 3.1 | Check the AG-UI interrupt and resume shape against the specification | Differences from the design recorded |
| 3.2 | An AG-UI endpoint beside the existing streaming endpoint | The same run gives the same content over both |
| 3.3 | A richer chat interface in the Studio test console: tool cards, inline approve and reject, the trace in plain steps | Browser tests for approve, reject and expiry |
| 3.4 | Shadow mode: the agent drafts, a person approves or edits in the Workspace inbox; reads may run, nothing else does | Nothing reaches a customer or an external system without a person |
| 3.5 | Edit and rerun from a turn; session replay from stored traces (staff only) | Browser tests |
| 3.6 | The widget's AG-UI subset; media and buttons on messaging channels | The widget's size budget is kept |

### Phase 4: Agent Studio for non-engineers (L)
| WP | Work | Exit check | Needs |
|---|---|---|---|
| 4.1 | The guided path: template, connect from the catalogue, procedures in plain words, a plain summary of what the agent will do | Browser tests | |
| 4.2 | Checks in plain language; write tools need approval by default; a release blocked with a plain checklist | Every validation message reviewed | |
| 4.3 | Test in place with the trace in words; one click to make a conversation a test | Browser tests | |
| 4.4 | Two or three ready-made agents (order status, refunds, returns) with passing scenarios | Scenarios green on a qualified model | |
| 4.5 | Live and candidate versions side by side; an agent catalogue with publish approval | The release flow is otherwise unchanged | |
| 4.6 | Models per tier for non-engineers, with qualification results | Shows which models passed each agent | |
| 4.7 | A graph editor kept equivalent to the YAML | Round-trip property tests green | |
| 4.8 | The usability gate | A CX lead releases a template agent unaided, timed and observed | A real CX lead |

### Phase 5: Automations (M)
| WP | Work | Exit check |
|---|---|---|
| 5.1 | A `tool` step through the gateway (a write needs an earlier person step) | Validation tests |
| 5.2 | `branch` (a small, total expression language) and a bounded `foreach` | Limit tests |
| 5.3 | Triggers from connector events | An event starts a routine exactly once |
| 5.4 | A scheduled routine that runs the live agent's simulations and alerts | A deliberately broken agent raises an alert |
| 5.5 | Quality criteria in plain language, judged by a model, with the deterministic rubric as the baseline | Marked unverified until a judge is calibrated |
| 5.6 | The canvas on the graph editor once Studio's is proven | Round-trip tests |

### Phase 6: Operator experience (M)
Can start any time after Phase 1.
| WP | Work | Exit check |
|---|---|---|
| 6.1 | A one-command install with a setup wizard (passwords, keys, demo, local or cloud model, allowed hosts) | Clone to a running agent, timed |
| 6.2 | Upgrades tested from the previous release | A CI job upgrades the release candidate to the next version |
| 6.3 | Backup and restore commands (database and stored files) | A restore drill passes |
| 6.4 | A health page: database, migrations, models, channels, alert delivery | Browser test |
| 6.5 | Sign-in required by default in the production compose setup | The stack refuses to start open |
| 6.6 | A firm resolution figure (a customer's return counts against it) | Old and new figures shown with denominators |

### Phase 7: pilot and release
| WP | Work | Exit check | Needs |
|---|---|---|---|
| 7.1 | Penetration-test findings fixed; the release checklist completed | The tester's report closed | A tester |
| 7.2 | A design-partner pilot: shadow mode, then a staged rollout | Measured honestly over an agreed period | A pilot customer |
| 7.3 | Cut the release; a case study | Published with denominators | |

### Later (after D1)
A managed offering (dedicated instances first), NorthCX as an MCP server, more connectors, a voice partner setup, metering and billing, single sign-on through SAML or a documented OpenID Connect bridge, the Workspace and packaged CX agents as products.

## 3. Order and dependencies
```
Phase 0 ──> Phase 1 ──┬──> Phase 2 ──> Phase 4 ──┐
   │                  ├──> Phase 3 (beside 2)    ├──> Phase 7
   │                  ├──> Phase 5 (after 2.4)   │
   │                  └──> Phase 6 (any time) ───┘
   └──> penetration test (in parallel)
```

## 4. Progress
| WP | State | Evidence |
|---|---|---|
| 0.1 approval scope re-check | Done | Pull request #7: two regression tests failed before the fix; full backend suite 1,585 passed |
| 0.1 suspended tenant's chat tokens | Done | Regression test failed before the fix |
| 0.1 execution record on approvals | Done | Two regression tests failed before the fix; a test that the held turn's status and latency do not change |
| 0.1 staff tools that need approval | No change | No staff tool requires approval today (staff tools are read-only; the Pilot's Do uses its own proposals), so the gap is not reachable; covered by WP 1.5 |
| 0.1 tool error text | No change, documented | Connectors already return safe messages; other tools are the company's code. The rule is written in the Agent Runtime doc |
| 0.3 live mode for configured providers in the CLI | Done | Two tests failed first (one runs scenarios on a local OpenAI-compatible server); the server and the CLI share one provider setup |
| 0.6 placeholder pages and dead plans | Done | Six "soon" pages removed from Studio navigation with the `/soon` route, the Profile placeholder box, the unused `ComingSoon` component and the "soon" badge; the old Implementation Plan no longer claims to be the master plan. Studio and Workspace tests, type-check and the Studio production build pass |
| 0.2 local-model pass | Blocked here | This environment's network policy refuses registry.ollama.ai, ollama.com and huggingface.co, so no model weights can be fetched. Needs those hosts allowed, or a run in the owner's local environment (session prompt 1a) |
| 0.4 cloud-model pass | Blocked | Needs cloud model keys |
| 0.5 D1 and penetration test | Blocked | Needs the owner's decision and an outside tester |
| 1.x stages 1 to 4 (research to architecture) | Done | `NorthCX_Tool-Gateway.md`; WP 1.3 folded into 1.4, WP 1.5 deferred |
| 1.2 tool source, registration and fingerprint | Done | 14 new tests; full backend suite 1,605 passed, existing tests unedited |
| 1.4 conformance suite | Done | `tests/test_tool_conformance.py`: 9 guarantees on the YAML connector source and a Python source (18 tests); removing the secret redaction, dry-run or duplicate-write protection from the runtime makes 6 of them fail |
| 1.1 Agent API contract | Done | Snapshot of 61 operations, stability rule, 7 tests (a removed route, a removed or retyped or newly required request field or parameter, and a lost enum value each fail; additions pass). Responses: WP 1.6a and 1.6b. The original exit "screens use only it" is dropped: the Studio also uses admin routes (keys, routing, policies) that are not part of the Agent API |
| 1.5 acting identity | Deferred | No staff tool needs approval; returns with Phase 5 |
| 1.6a typed responses, conversation-time routes | Done | 19 of 61 operations typed; a test calls each and checks the real answer; mutation check: a model that promises a missing field fails it |
| 1.6b typed responses: agents, versions, releases, rollouts, simulations | Done | 48 of 61 operations typed; the same test calls each |
| 1.6c typed responses: the 12 that need a configured service or a model, and the upload | Done | 60 of 61 operations typed through the harnesses of the tests that already cover them; the streaming chat stays untyped (server-sent events) |
| Phase 1 review (stage 6) | Done | A separate review pass over the whole Phase 1 diff found 7 issues (permission changes and tighter request limits not caught by the stability check; a documented error message that differed; the catalogue building each schema twice; a duplicate lookup in the runtime; responses checked only on in-memory stores; a conformance test using private state). All fixed. The Postgres check is verified only in CI |
| Phase 1 exit check | Met, except WP 1.5 (deferred) | Existing backend suite unchanged and green: 1,636 passed, 201 skipped (Postgres, run in CI) |
| 2.x stages 1 to 4 (research to architecture) | Done | `NorthCX_MCP-Integration.md`. The official MCP site does not resolve from this environment, so the specification was read from its GitHub source through a summarising fetch; the MUST and SHOULD wording is to be confirmed before the code that depends on it |
| 2.5 vendor connectors | Blocked | No vendor sandbox accounts; connectors from documentation alone would be unverified |
| 2.1 MCP client, `ToolSource`, `McpSource` | Done | 62 new tests (client wrapper over HTTP in memory, source and trust rule, the conformance suite for MCP: 6 of 9 tests run, 3 skipped because an MCP write always waits for a person). Mutation check: removing the redirect hook or the size cap fails its tests. Library level: not a feature until WP 2.3. Not verified: any real MCP server |
| 2.2 trust rules for MCP tools | Done | Pinned tool list (added, changed or removed tools are not offered), instructions in descriptions never offered, results and error text always screened, including after an approval; 23 new tests; mutation checks (ignoring the pin, removing the default screen) fail them. Library level; the audit entries move to WP 2.3 |
| 2.3a stored MCP connections and routes | Done | Migration 0057; service, gate, 8 routes with permissions and audit; 38 new tests, including the Postgres store and its tenant isolation (run locally against Postgres 16 and in CI); gate check 1.6 ms measured locally. Works through the API; not a screen yet. Default tenant only; agent files cannot name MCP tools |
| 2.3b operator screen | In review | Studio Connections page (Build): 11 component tests (permissions, the add form with labelled fields, review and approve with the fingerprints shown, a tool changed in between, checks in plain words, switch off, two-step delete) plus an api-client test; a real-browser walkthrough (Chromium against the built Studio, the backend and a real MCP server over HTTP on localhost): add, review (a poisoned description was left out), approve 2 tools, check, switch off and on, no page errors. Not tested: a screen reader, other browsers, a narrow screen; the smoke test in CI only checks that the page loads |
| Phases 2 (2.4, 2.6) to 7 | Not started | |

## 5. Open issues carried from Phase 1
Recorded 2026-11-19 when Phase 1 closed. Each is a known limit, not a defect in what was built; none blocks Phase 2.

| Issue | What it means | Resumes in |
|---|---|---|
| Acting identity (WP 1.5) | Approvals do not store who a staff tool acts for, so a staff tool that needed approval would fail at execution. No staff tool needs approval today. | Phase 5, the `tool` step (WP 5.1) |
| `ToolSource` interface | Tools register through `Registry.add_tools` with a source label and a fingerprint, but there is no interface for discovering or refreshing a source's tools. One implementation does not justify one. | WP 2.1, with the MCP client |
| Streaming chat response | `POST /agents/{id}/chat/stream` sends server-sent events, so the stability rule does not cover its events. The 60 JSON operations are covered. | Not scheduled; needs a contract for the event stream |
| Stability check limits | It does not read constraints inside `anyOf` branches; it reports some harmless changes as breaking (a nullable field made non-nullable in a response, a request field widened to accept null, a renamed path parameter, a relaxed permission). It errs on the side of reporting. | When a false report costs more than it saves |
| Response models are descriptive | They document responses and do not filter or validate them in production; the drift test catches a mismatch only for the routes and data it exercises. | Not planned; validating in production would change failure behaviour |
| Review by a person | Stage 6 was done by a separate model review pass, not by a person; no security review beyond the threat-model check (no new input, store or network call). | Before 1.0 (the penetration test, WP 0.5 and 7.1) |


## 6. Open issues carried from Phase 0
Recorded 2026-11-19. Phase 0 is done except the three work packages that need an outside party, and what they leave unverified.

| Issue | What it means | Needs | Resumes |
|---|---|---|---|
| WP 0.2 local-model pass | No real local model has run NorthCX yet. This container's network refuses `registry.ollama.ai`, `ollama.com` and `huggingface.co`, so no weights can be fetched. `../09-models/NorthCX_Local-Models-Guide.md` is written from the code and not corrected by a run; any claim about how a local model behaves is unverified. | The three hosts allowed for this environment, or a run on the owner's machine (session prompt 1a in `NorthCX_Session-Prompts.md`) | When a machine and a model are available |
| WP 0.4 cloud-model pass | No cloud model (Claude or another) has run the shipped scenarios live; the judge is not calibrated, so judge-based checks (Phase 5.5) stay marked unverified. | Cloud model keys (session prompt 1b) | When keys exist |
| WP 0.5 D1 and penetration test | Open versus commercial is undecided (affects licences, pricing and the managed offering); no independent penetration test is booked. | The owner's decision; an outside tester | Before 1.0 (WP 7.1) |
| Staff tools that need approval (WP 0.1) | Not reachable today, so no fix was made; it is the same gap as acting identity (WP 1.5). | Phase 5 | WP 5.1 |
| Tool error text (WP 0.1) | Connectors return safe messages; a deployment's own tools can put internal detail in an error the model reads. The rule is written in the Agent Runtime document and not enforced in code. | Not planned | If a deployment reports a leak |
