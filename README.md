# NorthCX

Open-source platform for deploying supervised AI agents that resolve customer issues end to end, built on the Claude API.

> **Status: release candidate (1.0.0-rc.1).** The feature set is complete and tested; an independent penetration test has not been done and the real-model path has been exercised only with scripted and offline models. Read [`docs/06-security/NorthCX_Security-Review.md`](docs/06-security/NorthCX_Security-Review.md) before putting it on the public internet.

## What it does
- **Agents** defined in YAML (instructions, tools, checks, skills, journeys, languages, specialist agents, attachments) and edited in a web **Studio** without code.
- **Supervision** of every reply and tool call, input checks (personal-data masking, takeover phrasing), human **approval** for sensitive actions, always-to-a-person topics, token budgets, fail-closed.
- **Channels**: web chat and a drop-in widget/SDK, email, SMS, phone calls (through your telephony bridge), with attachments.
- **People in the loop**: hand-off queues with hours, a package with the transcript and actions, suggested replies, person replies, hand-back to the agent, conversation review with failure tagging.
- **Proof before release**: scenario simulations (including attack suites), immutable versions, a publish checklist, release gate tied to the exact version, staged rollout, environments, one-step rollback.
- **Insight and operations**: metrics with numerators and denominators, alerts, search, trace export (OpenTelemetry, Langfuse), privacy export/erasure/retention, hash-chained audit log, single sign-on, load and cost tools.

## Layout
| Path | Contents |
|---|---|
| `src/backend/` | Python backend (FastAPI): runtime, guardrails, stores, server, channels, tools (`loadtest`, `cost`, `simulation`, `voice_sim`), example agent, tests |
| `src/web/` | Studio web console (Next.js) |
| `src/sdk/` | Browser SDK and `<northcx-chat>` widget (TypeScript, no runtime dependencies) |
| `src/prototype/` | TypeScript reference implementation of the runtime semantics |
| `docs/` | Documentation; start at [`docs/README.md`](docs/README.md) |

## Quick start: try it in five minutes (offline demo model, no API key)
```bash
cp .env.example .env
# edit .env: set NORTHCX_DB_PASSWORD (letters and digits) and NORTHCX_API_KEY (a long random value), and set NORTHCX_DEMO=1
docker compose up -d --build --wait
# Studio: http://localhost:3001  (Settings > paste the API key)     API: http://localhost:3000
```
The demo model is a handful of keyword rules, not an AI: try "where is order 1042?", "refund 500 for order 1042" (over the limit, so it waits for approval) and "I want a person". For real conversations set `ANTHROPIC_API_KEY` instead of `NORTHCX_DEMO=1`.

## Run from source
```bash
# backend
cd src/backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest                                   # Postgres-backed tests are skipped without a database (NORTHCX_REQUIRE_DB=1 makes them fail instead)
NORTHCX_DEMO=1 NORTHCX_API_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(32))") python -m northcx     # http://localhost:3000
# Postgres storage: add NORTHCX_DATABASE_URL=postgresql://northcx:northcx@localhost:5432/northcx (migrations run at start)

# Studio
cd src/web && npm ci && npm test && NORTHCX_API_URL=http://localhost:3000 npm run dev      # http://localhost:3001

# browser SDK and widget
cd src/sdk && npm ci && npm test && npm run build
```

## Where to go next
| You want to | Read |
|---|---|
| Deploy it | [`docs/08-implementation/NorthCX_Deployment-Guide.md`](docs/08-implementation/NorthCX_Deployment-Guide.md) (every setting), [Performance](docs/08-implementation/NorthCX_Performance.md) |
| Put chat on your website | [`docs/05-technical/NorthCX_Client-SDK.md`](docs/05-technical/NorthCX_Client-SDK.md) |
| Take phone calls | [`docs/05-technical/NorthCX_Voice.md`](docs/05-technical/NorthCX_Voice.md) |
| Write and test agents | [`docs/04-ai-architecture/`](docs/04-ai-architecture/), [`docs/07-design/NorthCX_Studio.md`](docs/07-design/NorthCX_Studio.md) |
| Judge the security | [`docs/06-security/NorthCX_Threat-Model.md`](docs/06-security/NorthCX_Threat-Model.md), [`SECURITY.md`](SECURITY.md) |
| Contribute | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| See what changed | [`CHANGELOG.md`](CHANGELOG.md) |

## Licence
Apache-2.0. See `LICENSE`; copied code keeps its own notices (`NOTICE`, `THIRD_PARTY.md`).
