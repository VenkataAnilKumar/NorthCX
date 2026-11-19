# NorthCX Agent Platform Plan

Status: **Plan**. Updated: 2026-11-18. Master for: the phases, work packages and exit checks for building the Agent Platform (`../00-platform/NorthCX_Agent-Platform-Design.md`), and the seven-stage process every phase follows. Progress is recorded in the table at the end and in `NorthCX_Project-Status.md`.

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
| 1.1 | The Agent API contract (sessions, runs, events, approvals, versions), documented and versioned from the existing routes | The contract is published; screens use only it |
| 1.2 | A `ToolSource` interface; the YAML connectors become the first source | Existing connector tests pass unchanged |
| 1.3 | The gateway applies approvals, scopes, dry-run, secrets, audit and output screening for every source | The existing suite passes unchanged |
| 1.4 | A conformance suite every source must pass (reads run; writes held or dry-run; no secret in results; disallowed hosts and redirects refused) | Green for the YAML source |
| 1.5 | The acting identity carried on every tool call (a staff tool acts with that person's rights) | A staff tool runs only with the permission |

### Phase 2: Integrations (L)
| WP | Work | Exit check | Needs |
|---|---|---|---|
| 2.1 | An MCP client on the official SDK, against the 2026-07-28 specification (read first) | Passes the conformance suite against a fake MCP server | |
| 2.2 | Trust rules: tools default to write unless the server is trusted; tool lists pinned and hashed, re-approval on change; output screened as untrusted | Injection and changed-tool-list scenarios pass | |
| 2.3 | Tenant-scoped connections; an operator screen for allowed hosts, servers and secrets | An operator adds a connection without editing files | |
| 2.4 | One catalogue of tools and triggers, read by Studio and Automations | Catalogue API with tests | |
| 2.5 | Connectors for the target market: helpdesk first, then commerce, then payments (vendor MCP servers where documented, otherwise YAML); writes need approval | Sandbox demonstration: ticket lookup, order lookup, a refund held for approval | Vendor sandbox accounts |
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
| 0.2, 0.4, 0.5, 0.6 | Not started | 0.2 needs a machine that can run a local model; 0.4 needs cloud keys; 0.5 needs the owner and a tester |
| Phases 1 to 7 | Not started | |
