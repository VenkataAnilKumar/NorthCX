# NorthCX Deployment Guide

Status: Draft (target; not yet runnable end to end)

## Environments
| Env | Setup |
|---|---|
| Local | `npm install`, `npm test`. The server (`npm run dev`) does not exist yet; it arrives in Phase 1 |
| Staging/production | Container image for the server, Postgres, optional queue |

## Configuration
Environment variables: model API key, server port, API keys for clients, database URL, trace export endpoint, retention settings. Secrets via a secrets manager.

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
