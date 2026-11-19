# NorthCX: guide for Claude Code

NorthCX is an open-source, self-hosted platform for supervised customer-experience AI agents (Apache-2.0, release candidate 1.0.0-rc.1). Read `README.md` first for what it is and `CONTRIBUTING.md` for how changes are made. This file only adds what a new session needs to start.

## Layout
- `src/backend/northcx/`: Python 3.12+ backend (runtime, guardrails, approvals, connectors, automations, channels, API routers under `api/routers/`). Tests in `src/backend/tests/`; example agent, tools and scenarios in `src/backend/examples/`.
- `src/apps/studio/` (port 3001) and `src/apps/workspace/` (port 3002): Next.js apps. Shared code in `src/packages/ui` and `src/packages/api-client`.
- `src/sdk/`: dependency-free browser SDK and `<northcx-chat>` widget (the built bundle is committed and a test checks it).
- `docs/`: numbered sections (product, specs, AI architecture, technical, security, design, implementation). The index is `docs/README.md`; every document must be listed there.

## Run and test
Copied from `CONTRIBUTING.md`; check it for the current commands.
```bash
cd src/backend && python -m venv .venv && . .venv/bin/activate && pip install --require-hashes -r requirements-dev.lock && pip install --no-deps -e .
python -m pytest                              # Postgres tests are skipped without a database; NORTHCX_REQUIRE_DB=1 makes them fail instead
cd src && npm ci && npm run typecheck && npm test
cd src/sdk && npm ci && npm test              # npm run build if you changed src/sdk/src
```
Offline demo (no API key): set `NORTHCX_DEMO=1` plus a database password and an API key in `.env`, then `docker compose up -d --build --wait`. The demo model is keyword rules, not an AI.

## Current direction (decided 2026-11-18)
Read `docs/00-platform/NorthCX_Agent-Platform-Design.md`. In short: re-platform in place (keep the safety core and its tests), add a unified Agent API and a tool gateway, and rebuild Chat, Agent Studio, Integrations and Automations on top, one module at a time. Self-hosted first. Studio is a product for non-engineers (YAML is an advanced view). The Workspace and packaged CX agents are later products. Nothing in the design is built yet.

Work in the order of `docs/12-project/NorthCX_Agent-Platform-Plan.md`, one work package at a time, and run every phase and work package through its seven stages: research, requirements, design, architecture, implementation (tests with or before the code), review, test. Stages 1 to 4 change only documents. The owner decided that stages run without waiting for approval and that each work package merges into `main` when CI is green; record anything blocked by an outside party (a key, a sandbox account, a tester) and carry on elsewhere. Update the plan's progress table as work packages finish. Models are hybrid (decision 198): local and cloud models side by side, each qualified per agent; Claude is one cloud option. No real-model pass has been run yet; the first is a local-model pass (`docs/09-models/NorthCX_Local-Models-Guide.md`). Mark anything that depends on real model behaviour as unverified.

## Reference sources (read-only)
Open-source projects, specifications and product pages studied for the four modules. The full list with links and the clone script is `docs/00-reference/NorthCX_Reference-Sources.md`; the conclusions are in sections 2 to 2b of the design, and the named research (which projects and products taught what) is `docs/00-reference/NorthCX_Agent-Platform-Research.md`. A developer may keep clones in a folder outside this repository, laid out as `northcx-sources/{integrations,chat,studio,automations,benchmarks}/`. If that folder is available, read it; if not, work from the design and the links, and do not guess at what a project does.

| Module | Read first | Study for |
|---|---|---|
| Integrations | `integrations/mcp-python-sdk`, `mcp-servers`, the MCP 2026-07-28 spec; `activepieces` | Stateless transport and authorization; how an integration defines actions, triggers and one auth |
| Chat | `chat/ag-ui`, `chat/assistant-ui`; `librechat`, `copilotkit` | Typed run events; approval as an interrupt then a resume; tool cards; branching and edit-and-rerun |
| Studio | `studio/sim`, `studio/xyflow`; `langflow`, `agenta` | Graph editor and node inspector; tools and triggers in one catalogue; side-by-side version comparison |
| Automations | `automations/hermes-agent`, `opengeni`; Temporal's approval docs | One gateway for many channels; scheduled jobs; replayable sessions; signal-with-timeout approvals |
| Product benchmark | `benchmarks/` (Sierra, Decagon, Intercom Fin pages) | Plain-language procedures, simulations, always-on quality checks |

How to use them:
- Read for ideas and patterns. Do not paste or port code. Record what you adopt as a decision-log entry, not as copied files. Anything copied needs provenance under the Code Reuse Policy, and `NOTICE` and `THIRD_PARTY.md` change with it.
- Licences were not reviewed. Several are unclear or restrictive (for example LobeHub, Open WebUI, and any `ee` or enterprise directory), so check a LICENSE file before depending on anything, and never use `ee` code.
- Competitor and project facts came from search summaries and vendor pages and are directional. Treat marketing claims as unverified. Specific points still to confirm before building: the AG-UI interrupt and resume shape, assistant-ui's AG-UI runtime, MCP tool annotations and the 2026-07-28 authorization changes, and Activepieces embedding.
- Do not use OpenCode as an agent backend (decided): it is a coding agent with shell and file access, not a supervised customer agent.

## Quality bar: a real product, no AI slop (owner's instruction)
Everything shipped must be real, specific and checkable. Each review stage applies these rules; a change that breaks one is not done.
- **No vague requirements.** Every requirement names who it is for, what they can do, and an acceptance check that passes or fails. Words like "intuitive", "fast", "robust", "seamless" or "scalable" need a number or an observable test, or they are cut.
- **No dead requirements.** A requirement nobody will build in the plan, or that no longer matches the direction, is removed or moved to the archive, not left in place.
- **No dead code.** No unused functions, settings, flags, routes or files; no stubs, placeholders or `TODO`s left in shipped paths; code replaced by a change is deleted in the same change. Do not add an abstraction until a second real use exists or is the next work package in the plan.
- **No fake behaviour.** No mocked or hard-coded data in product paths; demo data only in demo mode, labelled as such. A screen or route that is not built is not shown as if it were (no "soon" pages without a plan entry). A feature counts as built only when it works end to end through the real API and storage, with tests.
- **No invented facts.** Figures in docs, UI and changelogs come from a measurement or the code; anything not verified is marked unverified. No made-up customers, results, benchmarks or quotes.
- **No filler.** Docs, UI text and commit messages are short, plain and specific: what it does, for whom, how to check. No marketing superlatives, no repeating the same point, no sections that say nothing.
- **Review generated code like anyone else's.** Read every line before committing: no copy-paste duplication, no speculative options, no error handling that hides failures, and tests that check behaviour rather than mirror the code.
- **Say what was verified.** Every pull request lists what was tested, how, and what was not.

## Engineering rules
- **One work package per pull request.** No unrelated changes, no drive-by refactors; keep `main` green.
- **Do not break what exists.** API changes are additive or versioned; database changes are migrations that run on an existing install; a change that alters behaviour says so in the changelog. Upgrades from the previous release must keep working.
- **Hybrid by default.** No feature may assume one model provider. Test with the scripted model, and with a local model where behaviour depends on the model; never hard-code a model name outside configuration.
- **Privacy in every path.** Customer personal data is masked before storage and in logs; test fixtures use invented data; a new store is covered by export, erasure and retention; a new outbound destination appears in the residency report.
- **Every action is observable.** New features write trace events for what the agent did and audit entries for what a person did; errors are visible, never swallowed.
- **Measure, do not guess.** A change on a hot path (a conversation turn, the widget, a list endpoint) checks it does not slow down or grow: the widget's size budget, the load and cost tools.
- **New dependencies need a reason.** Prefer the standard library and what is already used; a new package is pinned, maintained, licence-checked and named with its reason in the pull request.
- **Built for the people who use it.** Screens for non-engineers use plain words and meet the accessibility checks already in the apps (contrast, keyboard use); every error tells the reader what to do next.
- **Stop and record, never fake.** When work needs an outside party (a key, a sandbox account, a tester, a customer) or an owner's decision (D1, pricing, licences), record what is blocked and why in the plan's progress table, and carry on with other work.

## Rules to keep
- **The core safety model is not negotiable:** risky actions wait for a person, fail closed, every action audited. New tool sources (MCP, connectors) go through the gateway so approvals, scopes, dry-run, secrets and audit apply equally. Routines never write to customers.
- **No third-party code is copied** (`NOTICE`, `THIRD_PARTY.md`). Reference projects are for reading; the rules for any exception are in `docs/08-governance-safety/NorthCX_Code-Reuse-Policy.md`. Reference material lives in a separate folder outside this repository (for example `northcx-sources/`); never commit it. The list of what to study is `docs/00-reference/NorthCX_Reference-Sources.md`.
- **Every change ships complete:** tests (a bug fix comes with a test that failed before), the affected docs, `CHANGELOG.md`, a decision-log entry for non-obvious decisions, and settings added to `.env.example`. New endpoints need a route-permission entry (a test fails otherwise). Outbound calls must not follow redirects; SQL values are always bound.
- **Sign commits** with `git commit -s` (see `CONTRIBUTING.md`).
- **Next.js here is not the version you know.** Each app has an `AGENTS.md`; read the docs in `node_modules/next/dist/docs/` before writing Next.js code.
- **Be honest about status.** The README's status table and the docs' status lines must match what was actually verified. Items that need an outside party (an API key, a penetration test, vendor sandbox accounts, tags) are listed in `docs/10-releases/NorthCX_Release-Checklist.md`; do not tick them without evidence.
- Do not commit secrets. Open a pull request per work package and merge it into `main` only when every CI check is green (owner's standing instruction).
