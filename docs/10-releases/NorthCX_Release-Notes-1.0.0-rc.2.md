# NorthCX 1.0.0-rc.2 release notes

Date: 2026-11-23. A release candidate, **not 1.0.0**: the items under "Before 1.0.0" are not done, and this document says so. The full list of changes is `CHANGELOG.md`; the design behind them is `docs/12-project/NorthCX_Agent-Platform-Plan.md`.

## What changed since rc.1
- **Agent API:** 66 stable operations with typed responses and a checked contract (changes are additions only inside `/v1`). Tools from any source (your registry, YAML connectors, MCP servers) pass through one gateway with the same approvals, scopes, dry-run, secrets and audit. MCP connections are managed in Studio with a pinned tool list and re-approval when it changes.
- **Studio for people who are not engineers:** guided setup, "try it" on an unsaved draft, save a conversation as a test, live-and-candidate comparison, release requests, a model picker that shows qualification results, a graph view of journeys, and plain-language messages for every check. Approvals are on by default for anything that changes something.
- **Chat:** a test console that shows each step, shadow mode (a person sends, edits or rejects every draft), replay and edit-and-run-again, buttons for offered choices on the chat widget, WhatsApp, Telegram, SMS and email, and an AG-UI endpoint.
- **Automations:** routines can call a tool, branch on a condition, go through a list, check a live agent's scenarios, raise an alert, and judge recent conversations; webhooks start a routine once per event id; anything that changes something needs a person's approval first on every path.
- **Running it:** `scripts/setup.py` writes a working `.env`; `python -m northcx backup` and `restore` handle the whole database in one file; a System health page; upgrades are tested from seven earlier schema revisions; the compose stack refuses to start without sign-in; a resolution figure that counts a returning customer against it.
- **Local models:** the first pass ran (see below). Three problems it found are fixed.

## Known limits (state these when you share this release)
- **Never run with a real cloud model.** Every scenario and judge check ran against scripted or offline models, except one pass with a small local model.
- **One small local model has run the shipped scenarios:** Qwen2.5 3B (Q4_K_M) on llama-cpp-python passed 8 of 18 and is **not qualified**. It often wrote tool calls as text, which then reached the customer. No model has qualified yet; do not serve customers with an unqualified model. No 7B or larger model, no Ollama, vLLM or llama.cpp-server run.
- **The judge is not calibrated against people's labels,** so judge-based results (including the routine `criteria` step) are marked unverified.
- **No independent penetration test.** The brief is ready; the test is not done.
- **Nobody who is not an engineer has used Studio or the setup script.** The usability test script is written and has not been run; no time to a first agent is measured.
- **No pilot has run.** No resolution rate, saving or satisfaction figure from real customers exists, and none is claimed.
- **The resolution figure that counts returns can only check conversations whose customer is known;** the page shows how many that is.
- **Not verified:** the AG-UI wire shape against the specification (the site was unreachable); WhatsApp and Telegram buttons against the real services (mock servers only); the compose commands outside CI; upgrading from rc.1 by name (its schema revision cannot be read from the source tree; seven earlier revisions are tested); backups of a database whose owner is not a superuser.
- **One region and one company per deployment.** Multi-tenant operation is for evaluation only. No metering or billing.
- **Not built:** sending media on messaging channels; vendor connectors (no vendor sandbox accounts); SAML; connector-registered event triggers (signed webhooks with event ids instead); a drag-and-drop graph editor; Office files in the website crawler; analytics forecasts.
- **Backups hold personal data and are not encrypted.** The meaning-search index is not saved and is rebuilt from the knowledge sources.

## Upgrading from rc.1
1. Take a backup first. With rc.1 use `pg_dump` or copy the Postgres volume; with rc.2 use `python -m northcx backup` (see the deployment guide).
2. Pull or build the new images and run `docker compose up -d --build --wait`. Migrations newer than your database's apply on start (up to 0058) and only move forward. The upgrade tests check that no row is lost when a database from an earlier revision is upgraded; rc.1's own revision could not be read here, so test the upgrade on a copy of your data first.
3. The compose backend now mounts `./config` (read-only) and knows `host.docker.internal`; nothing to do if you do not use a providers file.
4. Check **System health** (Platform) in Studio.

Behaviour changes to know about:
- The wording of definition checks, release-gate reasons and field errors is now plain language. Code that matched the old wording needs updating.
- Providers using the OpenAI-compatible type now send `tool_choice: "auto"` with tools and an empty string (not null) as the content of a tool-calling assistant turn.
- The Models page shows each provider's declared tier even when there is no routing rules file.
- In shadow mode a chat reply may be empty while a draft waits for review; the chat widget handles it, other clients should too.

## Before 1.0.0
Tracked in `docs/10-releases/NorthCX_Release-Checklist.md`: a pass with a model that qualifies (cloud or a larger local one) and a stronger judge; the usability test with real CX leads; the penetration test; the pilot (`NorthCX_Pilot-Plan.md`); the open-versus-commercial decision; the rc tags published from a machine with access.

## Verification behind these notes
Backend 2,159 tests passed (7 skipped) on Postgres 16 with 32 more in CI that need pgvector; 128 Studio and 217 Workspace unit tests; browser smokes of Studio, Workspace and the widget, a backup and restore drill, and the setup script run on the real compose stack in CI on every change; all CI checks green on every change merged since rc.1.
