# Tenant isolation: threat model

Status: **Built and tested here, not yet independently tested.** Updated: 2026-11-10. Master for: how one tenant is kept from another, what is checked, and what is not. Work package WP2.10. Companion to the general [threat model](NorthCX_Threat-Model.md) and the [tenancy decision record](NorthCX_Tenancy-ADR.md). The external penetration test is described in the [test brief](NorthCX_Penetration-Test-Brief.md).

A deployment with no second tenant is the single tenant `default` and nothing here changes it. A second tenant still needs `NORTHCX_TENANCY_PREVIEW=1` until the owner lifts that after the penetration test.

## What is protected

Everything a tenant stores: conversations, customer records and notes, memories, knowledge, outputs, spaces, library items, routines and their runs, agents and releases, keys, the audit log, budgets and settings, and the secrets in the vault. The test of success is simple: **a request made as one tenant never reads, changes, counts or reveals the existence of another tenant's data**, and never spends its allowance.

## How isolation works (the layers)

| Layer | What it does | Where it is checked |
|---|---|---|
| 1. The tenant comes from the key | A key, a session and a chat token each carry the tenant of the key that made them. The request's tenant is set once, in the request guard, from the authenticated identity and nothing the caller sends. A chat token carries the tenant of the key that minted it. | `tests/test_tenant_sweep.py` (the token case), `tests/test_access.py` |
| 2. Every query is scoped | Every tenant table has a `tenant_id` column that defaults from the session's tenant, is part of every primary key, and is added to ORM statements by one base class. | `tests/test_tenant_isolation.py` |
| 3. The database enforces it | Row-level security policies on every tenant table, run as an ordinary database role (never the table owner), so a missing predicate in application code still returns nothing for another tenant. | the raw-SQL test, the table-coverage gate (`test_every_table_is_isolated_unless_it_is_platform_data`) |
| 4. Background work runs as a tenant | Each periodic job runs once per active tenant with that tenant set; a failure in one does not stop the others. | `test_background_jobs_run_once_per_tenant_as_that_tenant` |
| 5. Secrets are sealed per tenant | Vault values are encrypted with a key derived from the master key and the tenant id, with the tenant and name authenticated, so a copied value cannot be opened elsewhere. | `tests/test_vault.py` |
| 6. Limits are per tenant | A request ceiling, an Outputs cap and a retention period are set by the operator, never raised by a tenant. | `tests/test_platform_api.py` |
| 7. The platform API is separate | Its own listener (internal by default), its own key, metadata only; every change is also written to the affected tenant's audit log. | `tests/test_platform_api.py` |

## Gates that run on every build

- **Table coverage:** a new table without a tenant column and a policy fails the build.
- **Whole-route-table sweep** (`tests/test_tenant_sweep.py`): the real server over a database with two tenants. Tenant A creates data on every feature that stores any and leaves a marker in it. Tenant B's administrator then calls **every route the server has**, with A's real ids filled in. No answer may contain a marker or an id of A's, no route may fail, and afterwards A's data must be exactly as it was. A route added later is covered because the sweep reads the routes from the app; a second test fails if any route is missing from the permission table; a third checks that every route refuses a caller with no key.
- **Interleaving fuzz:** random interleavings of two tenants never mix data.
- **Migration round trip:** going back and forward through the tenant migrations keeps the default tenant's data.
- **Load gate:** reads under row-level security stay within 15 percent of the baseline (measured about 0 to 2 percent), enforced with `NORTHCX_LOAD_GATE=1`.

The sweep has already found two real defects, both fixed and covered: a chat token minted by a tenant's key opened its conversation in the `default` tenant, and the retention job used an import that would have failed at run time.

## Threats considered

| # | Threat | Control | Residual |
|---|---|---|---|
| T1 | Tenant B reads or changes A's object by guessing or knowing its id | Scoped queries, row-level security, the route sweep; an id of another tenant answers as missing (404), the same as an unknown id | A route returning *different* errors for "exists elsewhere" and "does not exist" would leak existence; the sweep checks answers for A's markers and ids, not the exact wording of every error |
| T2 | B lists collections and sees A's items | Every list is a scoped query; the sweep reads every list route as B | none known |
| T3 | A request carries a tenant in a header, body or URL to switch tenant | The tenant is taken only from the authenticated key; nothing in a request can set it | none known |
| T4 | A chat token (customer) acts in another tenant | Token carries the minting key's tenant; verified on every request, and revoking the key ends the token | tokens last up to 24 hours unless the key is revoked |
| T5 | A background job writes into the wrong tenant | Jobs run once per tenant with that tenant set | a new job that forgets to use the per-tenant runner would run once as `default`; reviewers should check any new `_every(...)` job |
| T6 | Data leaks through shared caches | Caches are keyed by tenant (settings, limits, templates, library, rubric, switches) | a new cache keyed only by object id would be a defect; the sweep would catch a leak through any route |
| T7 | A tenant exhausts shared capacity | Per-key and per-tenant request ceilings, per-tenant budgets, an Outputs cap, per-routine and per-tenant concurrency | no per-tenant cap on knowledge size, attachments or database storage yet |
| T8 | A tenant reaches the platform's network (SSRF) through a provider or destination it configures | Only the operator sets a tenant's provider or a routine destination; providers must be public https addresses; destinations are listed by the administrator; routine webhooks never follow redirects | the operator is trusted to enter correct addresses; there is no DNS-rebinding defence on a configured address |
| T9 | The platform operator reads tenant data | The platform API has no route to conversations, people or documents; its actions are written to the tenant's own audit log | an operator with database or host access can read anything (see below) |
| T10 | A stored secret is read from a database dump | Values are sealed; the master key is not in the database | the master key lives in the server's environment; anyone who has both the dump and the environment can open the secrets |
| T11 | Cross-tenant timing or error-message side channels | Not addressed beyond uniform 404s | A determined attacker could measure response time differences |
| T12 | A suspended tenant keeps access | Keys of a suspended tenant are refused on the next request | chat tokens minted by the tenant's keys are refused too (`test_a_suspended_tenants_chat_tokens_stop_working_at_once`). Until 2026-11-19 they were not: the key stayed active, so its tokens kept working until they expired, although this row said otherwise |
| T13 | A migration or restore mixes tenants | Migration round-trip test; restores are whole-database | a partial restore by hand could; use whole-database restores |
| T14 | Model providers see other tenants' data | A tenant with its own provider never falls back to the platform's; the platform's model sees only the requests made by tenants without their own | prompts to a shared provider are not separated by tenant at the provider |

## Assumptions

1. The server runs as an **ordinary database role** with `NORTHCX_MIGRATION_DATABASE_URL` pointing at the table owner. If it runs as the owner or a superuser, row-level security does not apply and only layer 2 protects tenants. The server checks this and says so at start.
2. The operator, the database administrator and anyone with the server's environment are trusted. Isolation is between tenants, not against the operator.
3. TLS ends at a gateway the operator controls, and `NORTHCX_PLATFORM_KEY` is held by the operator alone.
4. The master key (`NORTHCX_MASTER_KEY`) is long, random and not stored with database backups.

## Known gaps

- The external penetration test has not been done.
- No per-tenant storage caps beyond Outputs; no per-tenant connector, SSO or channel credentials (they are platform-wide).
- The exact wording of an error for an object that exists in another tenant is not compared with the wording for one that does not exist.
- There is no automated check that a new background job uses the per-tenant runner.
