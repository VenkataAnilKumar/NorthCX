# Penetration test brief

Status: **Ready to hand to a tester.** Updated: 2026-11-10. Purpose: what to test before a second tenant is allowed on a real deployment (`NORTHCX_TENANCY_PREVIEW`), and before 1.0.0 is tagged. Read first: the [tenant isolation threat model](NorthCX_Tenant-Isolation-Threat-Model.md) and the [threat model](NorthCX_Threat-Model.md).

## Goal

Find any way for a user of one tenant to read, change, count, infer or spend another tenant's data or allowance; any way to escalate a role; and any way for a customer-facing chat to be made to act beyond its agent's tools.

## Scope

In scope: the backend API (`/v1/...`) and the platform API (`/platform/v1/...`, separate listener), the Admin and Workspace web apps, the chat token flow, the channel webhooks (SMS, WhatsApp, Telegram, email), the SCIM and single sign-on endpoints, file and PDF handling (attachments, Spaces), and the routine webhook (`/v1/automations/{id}/hook`).

Out of scope: the underlying cloud, DNS and TLS terminator; denial of service by volume (rate limits are tested separately); social engineering; the model providers themselves.

## Set-up the tester receives

Run the stack with two tenants (see the Deployment Guide, "Tenants and the database role"):

```bash
export NORTHCX_TENANCY_PREVIEW=1
export NORTHCX_PLATFORM_KEY=<32+ random characters>
export NORTHCX_MASTER_KEY=<32+ random characters>
docker compose up -d
```

Create the tenants and an administrator key in each through the platform API (listener on `127.0.0.1:3100` by default), then give the tester **tenant A's administrator key, tenant B's administrator key, a viewer key in each, a chat token minted by each tenant's key, and the platform key only for the platform API part of the test**. Seed some data in each tenant: a conversation, a customer note, an output, a space with a file, a library item, a routine, an organization policy and template.

## What to try (starting points)

1. **Cross-tenant by id.** With B's keys, request, change and delete every object type of A's using A's real ids (the repository's own sweep does this; try to beat it with encodings, unusual methods, path tricks, batch routes, exports, search and streaming endpoints).
2. **Cross-tenant by listing, search and aggregates.** Counts, "latest", usage and performance figures, insights, the audit log and its integrity check, the unified search, order-number search, suggestions.
3. **Tenant switching.** Headers, cookies, query parameters, request bodies, SSO claims, SCIM bodies, chat-token fields, and the `Host` header, trying to change the tenant a request runs as.
4. **Chat tokens.** Use a token minted in A against B's routes and conversations; reuse after the minting key is revoked; forge or alter one.
5. **Roles.** Each role against each route: the route table is `src/backend/northcx/server.py` (`ROUTE_PERMISSIONS`) and is generated into the API reference. Look for a route that checks less than its table entry says, and for the two-person rules (releases, policies, templates, routines) being satisfied by one person with two keys or one key used twice.
6. **Injection into the model.** From a customer chat, from uploaded files and PDFs, from knowledge pages, and from routine webhook bodies, try to make an agent call a tool it should not, reveal another customer's data, or follow instructions in data.
7. **The platform API.** Reach it from a tenant key; find any route that returns tenant content; try to use it to change another tenant's settings through a tenant's own audit log.
8. **Secrets.** Any response, log or audit entry that contains a secret value, a webhook secret, an API key or a master-key-derived value.
9. **Files.** Oversized, malformed and hostile PDFs, text files with control characters, filenames with path or header tricks, exports with script content.
10. **Webhooks and outbound calls.** Routine destinations, the events webhook, provider addresses: any way to make the server call an internal address.

## Rules

Use only the test deployment and the keys provided. Do not use real customer data. Stop and report at once if you find a cross-tenant read or write.

## What to deliver

A report with, for each finding: where, how to reproduce it (the exact request), what was reached, severity, and a suggested fix. A statement of what was tested and what was not. A retest of each fix.

## When the test is done

For each finding, add a case to `tests/test_tenant_sweep.py` (or the matching test file) that fails before the fix and passes after. Only when no cross-tenant finding remains open should the owner remove the need for `NORTHCX_TENANCY_PREVIEW=1` (a small change in `northcx/tenancy.py` and the start-up check in `northcx/bootstrap/storage.py`, with the decision recorded in the decision log).
