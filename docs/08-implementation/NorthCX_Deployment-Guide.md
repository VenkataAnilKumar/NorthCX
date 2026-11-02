# NorthCX Deployment Guide

Status: Draft (target; not yet runnable end to end)

## Environments
| Env | Setup |
|---|---|
| Local | Target: one compose file starts Postgres, the backend and the web platform; model API key from the environment. The TypeScript prototype (in `src/prototype`) still runs with `npm install && ANTHROPIC_API_KEY=... npm run dev` (in-memory, state lost on restart) |
| Staging/production | Container image for the server, Postgres, optional queue |

## Storage
Set `NORTHCX_DATABASE_URL` (for example `postgresql://northcx:northcx@localhost:5432/northcx`) to use Postgres; pending migrations are applied at startup. Without it the backend uses in-memory storage and logs a warning. `docker-compose.yml` starts a development Postgres. Migrations live in `src/backend/northcx/db/migrations` and are checked against the models in tests.

## Approvals and notifications
`NORTHCX_APPROVAL_TTL_SECONDS` expires approvals that wait too long (escalating the conversation); unset, approvals wait indefinitely. `NORTHCX_WEBHOOK_URL` with `NORTHCX_WEBHOOK_SECRET` pushes approval results to your system, signed with HMAC-SHA256; the receiver should verify the signature and the five-minute timestamp window.

## Releasing agent changes
Spec files provide the baseline agent. To change what customers get, save a new version, run its scenarios, publish it, and roll back if needed (see Release Management). Releases are stored in the database, so every server process serves the same version immediately; without a database they last only until restart. Back up the `agent_versions` and `releases` tables with the rest of the database.

## Agents and scenarios
The server loads agent specs from `NORTHCX_AGENTS_DIR` and scenarios from `NORTHCX_SCENARIOS_DIR` (both default to the bundled examples) and exposes the simulation API and release gate. In CI, run `python -m northcx.simulation ... --record --source ci --meta commit=$SHA` with `NORTHCX_DATABASE_URL` set so each build records its result.

## Configuration
Environment variables: model API key, server port, API keys for clients, database URL, trace export endpoint, retention settings. Secrets via a secrets manager.

## Environments
dev, staging and production are separate deployments or namespaces with separate secrets, databases and API keys. Promotion of agent versions follows the Release Management spec.

## Release steps
1. Typecheck and unit tests pass.
2. Required simulations pass.
3. Build and tag the image.
4. Deploy to staging; smoke test chat and a handoff.
5. Promote; watch error rate, escalation rate and guardrail blocks.

## Rollback
Redeploy the previous image; agent definitions are versioned so a prior version can be republished.

## Operations
Health endpoint, structured logs, alerts on error rate and model latency, regular backup and retention jobs.
