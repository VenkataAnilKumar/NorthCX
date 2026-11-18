# NorthCX Operations: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** Running NorthCX on your own infrastructure: deployment, settings, runbooks, the database and performance.

## Built
- A Docker Compose stack with Postgres 16 and pgvector, migrations at start, readiness checks
- Several processes with job leases and shared limits; every setting documented (checked by a test)
- Owner runbooks; measured performance; seven CI jobs including a compose stack smoke test (all green on `main` again since the image build fix of 2026-11-18; the stack job had failed since 2026-11-09)

## Gaps and next steps
- Operator experience for self-hosted customers: a one-command install with a setup wizard, tested upgrades, backup and restore commands, a health page (design section 13)

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Deployment-Guide.md`](NorthCX_Deployment-Guide.md) | Deployment and every setting (master) |
| [`NorthCX_Owner-Runbooks.md`](NorthCX_Owner-Runbooks.md) | Owner runbooks |
| [`NorthCX_Performance.md`](NorthCX_Performance.md) | Measured performance |
| [`NorthCX_Database-Schema.md`](NorthCX_Database-Schema.md) | Database tables (checked by a test) |
| [`NorthCX_Repo-Structure.md`](NorthCX_Repo-Structure.md) | Repository layout |
