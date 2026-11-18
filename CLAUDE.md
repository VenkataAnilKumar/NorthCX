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

Work in the order given in the design's phasing table, one small step at a time. Models are hybrid (decision 198): local and cloud models side by side, each qualified per agent; Claude is one cloud option. No real-model pass has been run yet; the first is a local-model pass (`docs/09-models/NorthCX_Local-Models-Guide.md`). Mark anything that depends on real model behaviour as unverified.

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

## Rules to keep
- **The core safety model is not negotiable:** risky actions wait for a person, fail closed, every action audited. New tool sources (MCP, connectors) go through the gateway so approvals, scopes, dry-run, secrets and audit apply equally. Routines never write to customers.
- **No third-party code is copied** (`NOTICE`, `THIRD_PARTY.md`). Reference projects are for reading; the rules for any exception are in `docs/08-governance-safety/NorthCX_Code-Reuse-Policy.md`. Reference material lives in a separate folder outside this repository (for example `northcx-sources/`); never commit it. The list of what to study is `docs/00-reference/NorthCX_Reference-Sources.md`.
- **Every change ships complete:** tests (a bug fix comes with a test that failed before), the affected docs, `CHANGELOG.md`, a decision-log entry for non-obvious decisions, and settings added to `.env.example`. New endpoints need a route-permission entry (a test fails otherwise). Outbound calls must not follow redirects; SQL values are always bound.
- **Sign commits** with `git commit -s` (see `CONTRIBUTING.md`).
- **Next.js here is not the version you know.** Each app has an `AGENTS.md`; read the docs in `node_modules/next/dist/docs/` before writing Next.js code.
- **Be honest about status.** The README's status table and the docs' status lines must match what was actually verified. Items that need an outside party (an API key, a penetration test, vendor sandbox accounts, tags) are listed in `docs/10-releases/NorthCX_Release-Checklist.md`; do not tick them without evidence.
- Do not commit secrets. Do not open a pull request or merge unless asked.
