# NorthCX Integrations: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** How agents reach other systems, and how other systems reach NorthCX: connectors, webhooks and the HTTP API.

## Built
- Connectors defined as data: operator host allowlist, HTTPS only, no redirects, timeouts and size caps, secrets looked up by name, idempotent writes, pagination, OAuth 2
- Customer context from business systems; signed status events (webhook and pollable feed); hand-off delivery to a helpdesk
- The HTTP API with a generated reference (`../api/`) and a webhook tester

## Gaps and next steps
- A tool gateway that every tool source passes through, so approvals, scopes, dry-run, secrets and audit apply equally (design section 5)
- An MCP client and later an MCP server; tenant-scoped connections managed by the operator; one catalogue of tools and triggers
- First native connectors for the target market (helpdesk, commerce, payments), each needing a sandbox account to verify

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Integrations.md`](NorthCX_Integrations.md) | Connectors and integrations (master) |
| [`NorthCX_Tool-Gateway.md`](NorthCX_Tool-Gateway.md) | What the runtime guarantees for every tool; Phase 1 work packages |
| [`NorthCX_Integration-Catalogue.md`](NorthCX_Integration-Catalogue.md) | The catalogue of tools and routine triggers that Studio and Workspace read |
| [`NorthCX_MCP-Integration.md`](NorthCX_MCP-Integration.md) | MCP client, trust rules and Phase 2 work packages |
| [`NorthCX_API-Design.md`](NorthCX_API-Design.md) | HTTP API (route table generated from code) |
