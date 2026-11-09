"""Tenant isolation for conversation data (WP2.3 batch b, WP2.4). Everything here runs as an ordinary database role, so row-level security applies;
the stores are used exactly as the server uses them, with only the current tenant changing."""
from contextlib import contextmanager

import pytest
from sqlalchemy import text

from northcx.approvals import Approval  # noqa: F401
from northcx.db import PgApprovalStore, PgHandoffs, PgMemories, PgMemoryStore, PgOutbox, PgPrivacy, PgSessionRoutes, PgTraceStore
from northcx.handoffs import Handoff
from northcx.tenancy import DEFAULT_TENANT, TENANT, for_each_tenant
from northcx.trace import Trace


@contextmanager
def as_tenant(t):
    token = TENANT.set(t)
    try:
        yield
    finally:
        TENANT.reset(token)


async def raw(eng, sql, **p):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async with async_sessionmaker(eng)() as s:  # a normal session: sets the tenant like every store does
        return (await s.execute(text(sql), p)).all()


async def test_the_same_session_id_in_two_tenants_holds_two_separate_conversations(app_engine):
    store = PgMemoryStore(app_engine)
    with as_tenant("acme"):
        await store.save_messages("s1", [{"role": "user", "content": "acme secret"}])
        await store.set_fact("c1", "plan", "gold")
    with as_tenant("globex"):
        await store.save_messages("s1", [{"role": "user", "content": "globex hello"}, {"role": "assistant", "content": "hi"}])
        await store.set_fact("c1", "plan", "silver")
    with as_tenant("acme"):
        assert [m["content"] for m in await store.load_messages("s1")] == ["acme secret"] and await store.get_facts("c1") == {"plan": "gold"}
    with as_tenant("globex"):
        assert len(await store.load_messages("s1")) == 2 and await store.get_facts("c1") == {"plan": "silver"}
    with as_tenant("nobody"):
        assert await store.load_messages("s1") == [] and await store.get_facts("c1") == {}


async def test_raw_sql_with_no_tenant_condition_still_sees_only_its_own_rows(app_engine):
    """The WP2.4 test: take the predicate away and another tenant's rows are still not returned."""
    store = PgMemoryStore(app_engine)
    with as_tenant("acme"):
        await store.save_messages("s1", [{"role": "user", "content": "a"}])
    with as_tenant("globex"):
        assert await raw(app_engine, "select * from messages") == []
        assert await raw(app_engine, "select * from sessions") == []
        assert (await raw(app_engine, "select count(*) from messages"))[0][0] == 0
    with as_tenant("acme"):
        assert (await raw(app_engine, "select count(*) from messages"))[0][0] == 1


async def test_a_write_cannot_name_another_tenant(app_engine):
    store = PgMemoryStore(app_engine)
    with as_tenant("acme"):
        await store.save_messages("s1", [{"role": "user", "content": "a"}])
    with as_tenant("globex"):
        with pytest.raises(Exception, match="row-level security|violates"):
            await raw(app_engine, "insert into sessions (tenant_id, id) values ('acme', 'planted')")
        # an update or delete aimed at acme's row finds nothing
        from sqlalchemy.ext.asyncio import async_sessionmaker
        async with async_sessionmaker(app_engine)() as s:
            assert (await s.execute(text("update sessions set updated_at = now() where id = 's1'"))).rowcount == 0
            assert (await s.execute(text("delete from messages where session_id = 's1'"))).rowcount == 0
            await s.commit()
    with as_tenant("acme"):
        assert len(await PgMemoryStore(app_engine).load_messages("s1")) == 1


async def test_traces_approvals_handoffs_outbox_and_routes_are_per_tenant(app_engine):
    traces, approvals, handoffs, outbox, routes = PgTraceStore(app_engine), PgApprovalStore(app_engine), PgHandoffs(app_engine), PgOutbox(app_engine), PgSessionRoutes(app_engine)
    with as_tenant("acme"):
        t = Trace("support", "s1")
        t.add("llm", tokens=5)
        await traces.save(t)
        a = await approvals.add(trace_id=t.id, session_id="s1", tool="refund", input={"amount": 400}, reason="big", agent_id="support", customer_id="c1")
        h = await handoffs.add(Handoff("s1", t.id, "support", "customer_asked", "wants a person", {}, customer_id="c1"))
        await outbox.add("s1", "reply", {"text": "hello"})
        await routes.set("s1", "billing")
    with as_tenant("globex"):
        assert await traces.get(t.id) is None and await traces.summaries() == [] and await traces.summaries("s1") == []
        assert await approvals.get(a.id) is None and await approvals.list() == [] and await approvals.list("pending") == []
        with pytest.raises(Exception):
            await approvals.decide(a.id, True, "mallory")
        assert await handoffs.get(h.id) is None and await handoffs.list() == [] and await handoffs.list("open", "s1") == []
        with pytest.raises(Exception):
            await handoffs.resolve(h.id, "mallory", "taken")
        assert await outbox.list("s1") == [] and await outbox.undelivered() == [] and await routes.get("s1") is None
    with as_tenant("acme"):
        assert (await traces.get(t.id)) is not None and (await approvals.get(a.id)).state == "pending" and (await handoffs.get(h.id)).state == "open"
        assert len(await outbox.list("s1")) == 1 and await routes.get("s1") == "billing"


async def test_erasing_a_session_or_a_customer_touches_only_the_callers_tenant(app_engine):
    store, priv, mem = PgMemoryStore(app_engine), PgPrivacy(app_engine), PgMemories(app_engine)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await store.save_messages("s1", [{"role": "user", "content": f"{tenant} data"}])
            await store.set_fact("c1", "k", tenant)
            await priv.link("s1", "c1")
            await mem.remember("c1", f"{tenant} likes tea", "s1")
    with as_tenant("acme"):
        assert await priv.sessions_for_customer("c1") == ["s1"]
        out = await priv.erase_session("s1")
        assert out["messages"] == 1
        await priv.erase_facts("c1")
        await priv.erase_memories("c1")
    with as_tenant("globex"):
        assert [m["content"] for m in await store.load_messages("s1")] == ["globex data"]
        assert await store.get_facts("c1") == {"k": "globex"} and len(await mem.list("c1")) == 1
        assert (await priv.export_session("s1"))["messages"][0]["content"] == "globex data"
        assert await priv.sessions_idle_since(1e12) == ["s1"]
    with as_tenant("acme"):
        assert await store.load_messages("s1") == [] and await store.get_facts("c1") == {} and await mem.list("c1") == []


async def test_memories_recall_and_per_tenant_uniqueness(app_engine):
    mem = PgMemories(app_engine)
    with as_tenant("acme"):
        await mem.remember("c1", "prefers email over phone", "s1")
    with as_tenant("globex"):
        assert await mem.recall("c1", "email") == []
        m, new = await mem.remember("c1", "prefers email over phone", "s9")  # the same note in another tenant is a different memory
        assert new
    with as_tenant("acme"):
        assert len(await mem.recall("c1", "email")) == 1


async def test_background_jobs_run_once_per_tenant_as_that_tenant(app_engine):
    from northcx.tenancy import TenantService
    svc = TenantService(preview=True)
    await svc.create("acme", "Acme")
    await svc.create("globex", "Globex")
    await svc.set_status("globex", "suspended")
    seen = []

    async def job():
        from northcx.tenancy import current_tenant
        seen.append(current_tenant())
    await for_each_tenant(svc, job)
    assert sorted(seen) == ["acme", "default"]  # a suspended tenant gets no pass
    seen.clear()
    await for_each_tenant(None, job)
    assert seen == [DEFAULT_TENANT]
    with pytest.raises(RuntimeError):  # a single-tenant deployment still sees a failing pass, as before
        async def boom():
            raise RuntimeError("x")
        await for_each_tenant(None, boom)


async def test_the_default_tenant_and_a_connection_with_no_tenant_still_work(engine):
    """The owner/superuser connection (today's deployments, migrations, one-off tools) bypasses the policies and writes the default tenant."""
    store = PgMemoryStore(engine)
    await store.save_messages("s1", [{"role": "user", "content": "x"}])
    assert (await raw(engine, "select tenant_id from messages"))[0][0] == DEFAULT_TENANT


async def test_the_server_can_tell_whether_its_database_role_is_protected_by_row_level_security(engine, app_engine):
    from northcx.db.tenant_sql import isolation_problem
    assert await isolation_problem(app_engine) is None
    assert "owns the tables" in (await isolation_problem(engine) or "") or "superuser" in (await isolation_problem(engine) or "")
