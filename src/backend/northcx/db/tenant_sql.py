"""How the database knows which tenant a statement is for (WP2.3, WP2.4; see docs/05-technical/NorthCX_Tenancy-ADR.md).

Every database session sets two settings right after it begins: `app.tenant` (the request's tenant) and `app.system` (on only inside
`system_scope()`, for background jobs that must see every tenant). Row-level security policies on each tenant table compare `tenant_id` with
`app.tenant`, and the column default fills `tenant_id` from it, so even raw SQL that forgets the tenant sees and writes only its own rows.
The ORM additionally adds an explicit `tenant_id` predicate to every ORM select, update and delete (defence in depth, and it uses the index)."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from sqlalchemy import event, text
from sqlalchemy.orm import Session, with_loader_criteria

from northcx.tenancy import current_tenant

SYSTEM: ContextVar[bool] = ContextVar("northcx_system_scope", default=False)

# The column default: the session's tenant, or 'default' on a connection that never set one (a migration, a one-off script).
TENANT_DEFAULT_SQL = "coalesce(nullif(current_setting('app.tenant', true), ''), 'default')"
POLICY_SQL = "tenant_id = current_setting('app.tenant', true) OR current_setting('app.system', true) = 'on'"


@contextmanager
def system_scope() -> Iterator[None]:
    """Background work that must reach every tenant's rows (expiry, delivery, retention). Never used for anything a request triggers."""
    token = SYSTEM.set(True)
    try:
        yield
    finally:
        SYSTEM.reset(token)


def enable_rls_sql(table: str) -> list[str]:
    return [f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
            f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY_SQL}) WITH CHECK ({POLICY_SQL})"]


async def isolation_problem(engine: Any) -> str | None:
    """Why row-level security would NOT protect tenants on this connection (None: it will). It does not apply to a superuser, to a role that
    bypasses it, or to the owner of the tenant tables, which is what a single-company deployment usually connects as."""
    async with engine.connect() as c:
        row = (await c.execute(text(
            "select r.rolsuper or r.rolbypassrls as bypass, "
            "exists (select 1 from pg_tables t where t.schemaname = 'public' and t.tablename = 'sessions' and t.tableowner = current_user) as owner "
            "from pg_roles r where r.rolname = current_user"))).one()
    if row.bypass:
        return "the database role is a superuser or can bypass row-level security"
    if row.owner:
        return "the database role owns the tables (the table owner is not subject to row-level security)"
    return None


_installed = False


def install_session_hooks() -> None:
    """Once per process: set the tenant on every session's connection, and add the ORM predicate."""
    global _installed
    if _installed:
        return
    _installed = True

    @event.listens_for(Session, "after_begin")
    def _set_tenant(session: Any, transaction: Any, connection: Any) -> None:
        # Session-level (not local) so it also holds on the autocommit connections the read path uses, and it is remembered on the pooled connection so
        # only a change of tenant costs a statement. Behind a transaction-mode connection pooler (PgBouncer) session settings do not hold: use session pooling.
        want = (current_tenant(), "on" if SYSTEM.get() else "off")
        if connection.info.get("northcx_tenant") == want:  # this pooled connection already carries these settings: no round trip (the common case)
            return
        connection.execute(text("select set_config('app.tenant', :t, false), set_config('app.system', :s, false)"), {"t": want[0], "s": want[1]})
        connection.info["northcx_tenant"] = want

    @event.listens_for(Session, "do_orm_execute")
    def _scope_orm(state: Any) -> None:
        from northcx.db.models import TenantScoped
        if SYSTEM.get() or not (state.is_select or state.is_update or state.is_delete):
            return
        tenant = current_tenant()  # read here, not inside the lambda: the lambda's cached form keeps the variable and takes its value on each run
        state.statement = state.statement.options(with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tenant, include_aliases=True))
