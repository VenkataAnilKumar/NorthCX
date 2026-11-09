# NorthCX Tenancy: decision record

Status: **Partly built**. Updated: 2026-11-09. Master for: how tenants are isolated (WP2.1 decision, WP2.2 and the first batch of WP2.3 built). Implementation plan: epic E2 in `08-implementation/NorthCX_Implementation-Plan.md`.

## 1. What is built, and what is not
**Built:** `tenants` and `channel_bindings` tables (migration 0037; the default tenant is seeded); a request-scoped current tenant (`northcx/tenancy.py`) set from the key; keys and audit entries carry a tenant; the key and audit APIs show and change only the caller's tenant (another tenant's key id is "unknown", never "forbidden"); a suspended tenant's keys stop working at once; an inbound address belongs to exactly one tenant and an unbound one resolves to nothing; `python -m northcx.tenants` and `python -m northcx.keys --tenant`.

**Not built, and why it matters:** every other table (sessions, messages, facts, memories, traces, approvals, hand-offs, knowledge, channels, versions, releases and the rest: WP2.3 batches b to f), row-level security (WP2.4), per-tenant configuration (WP2.5), channel routing by binding in the channels (WP2.6), limits (WP2.7), the platform API (WP2.8) and the isolation gates (WP2.9). **Until those are done there is no tenant isolation.** A second tenant would share conversations, knowledge and agents with the first. For that reason creating a tenant other than `default` is refused unless `NORTHCX_TENANCY_PREVIEW=1`, and the setting is for evaluation only. A deployment with no tenants configured is the single tenant `default` and behaves exactly as before.

## 2. The decision (WP2.1)
**Primary mechanism: an explicit tenant predicate added in one place (the store base class), on every read and write, with the tenant taken from the request-scoped context. Second layer: row-level security (RLS) policies on the same tables, enabled in WP2.4, so a missing predicate returns nothing instead of another tenant's rows.**

Why not RLS alone: the read path deliberately avoids a transaction per statement (autocommit), and RLS with a per-transaction setting needs one. Why not predicate alone: one forgotten predicate would leak; the RLS layer turns that into an empty result, and a test removes the predicate and checks it still returns nothing (WP2.4).

### Measurements (this container, local Postgres, 400,000 rows, 50 tenants, 3,000 point reads each, single connection pool of 4)
| Path | p50 | p95 | p99 |
|---|---|---|---|
| Explicit predicate, autocommit (today's read path) | 0.44 ms | 1.47 ms | 2.24 ms |
| Explicit predicate, inside a transaction | 0.57 ms | 1.05 ms | 1.50 ms |
| RLS, tenant set per transaction (`set_config(..., true)`) | 0.79 ms | 1.41 ms | 2.32 ms |
| RLS plus explicit predicate | 0.75 ms | 1.57 ms | 2.69 ms |

With no tenant set, RLS returned 0 rows. RLS with a per-transaction setting costs about 0.35 ms more at the median than today's path (one extra statement and a transaction), and the tail is similar. A conversation turn makes dozens of store calls, so the RLS layer is expected to add roughly ten milliseconds per turn; WP2.9 re-measures this on the load tool and holds it to the documented figure within 10 percent, and if it does not, the setting moves to the connection checkout (one statement per checkout, not per call). These are numbers from one machine, not a production benchmark.

## 2a. Revision while building batch b: row-level security is the enforcement, the predicate is the helper
The first draft above made the explicit predicate primary. Building batch b showed why that is the wrong way round here: the stores contain about 145 hand-written SQL statements, and a predicate that must be remembered in each one is exactly the thing that gets forgotten. So the enforcement is now in the database, and it covers raw SQL too:
- every session sets `app.tenant` (and `app.system`, used by nothing in a request) as its first statement (`northcx/db/tenant_sql.py`); one extra statement per session, the cost measured above;
- each tenant table has a policy `tenant_id = current_setting('app.tenant')` for reading and writing, and its `tenant_id` column defaults from the same setting, so an insert that names no tenant gets the caller's and one that names another tenant is refused;
- the ORM also adds the predicate to every ORM select, update and delete (defence in depth, and it uses the index);
- ids chosen by clients or outside systems (session, customer, source ids and so on) are unique per tenant, so two tenants may use the same id; a write cannot overwrite another tenant's row because the conflict target includes the tenant;
- background jobs run once per active tenant, as that tenant, instead of seeing every tenant at once;
- the policies do not apply to a superuser, a role with BYPASSRLS or the table owner, so a deployment with more than one tenant must run the server as an ordinary role (`NORTHCX_MIGRATION_DATABASE_URL` keeps migrations on the owner); the server checks this at start and refuses otherwise.
Tests run as an ordinary role: the same session id in two tenants stays separate; a raw `select * from messages` with no tenant condition returns only the caller's rows; a write naming another tenant is refused; another tenant's approval cannot be decided; erasing a session or a customer touches only the caller's tenant.

**Built so far (2026-11-09):** conversation data (batch b). **Still to do:** knowledge (c), channels (d), releases and versions (e), the rest (f), per-tenant configuration, channel routing by binding, limits, the platform API, and the full gates.

## 3. Rules the rest of the work follows
1. The tenant comes only from the authenticated key, a chat token's minting key or an inbound channel binding. It is never read from a request body, header or query.
2. A resource of another tenant is "not found" (404), never "forbidden".
3. An unbound inbound message is ignored, not routed to a default.
4. Each batch of WP2.3 adds `tenant_id` (default `default`, backfilled in batches), its predicate, a reversible migration and its own isolation tests before the next batch starts.
5. The audit chain stays one chain across tenants, with the tenant inside each entry's hash for tenants other than `default` (so default-tenant entries hash exactly as before and an existing chain still verifies). A tenant can only learn whether the chain holds. Per-tenant chains are the intended shape in batch (f) so that a tenant can verify its own entries; recorded here as an open design point, not decided.
6. Platform operators (WP2.8) see tenant metadata, never conversation content.

## 4. Risks
Partial tenancy is more dangerous than none because it looks like isolation. The preview switch, the "not built" list above and the Feature Catalog state exist to prevent a second tenant being created by accident.
