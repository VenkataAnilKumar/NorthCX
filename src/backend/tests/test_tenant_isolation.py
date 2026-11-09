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


# ---------- batch c: knowledge, crawl schedules, attachments ----------
async def test_knowledge_sources_documents_and_search_are_per_tenant(app_engine):
    from northcx.db import PgKnowledge
    from northcx.knowledge import Source
    kb = PgKnowledge(app_engine)
    for tenant, text_ in (("acme", "Acme refunds take five days to arrive."), ("globex", "Globex refunds are instant.")):
        with as_tenant(tenant):
            await kb.create_source(Source("faq", "FAQ"))  # the same source id in both tenants
            await kb.upsert("faq", "doc1", "Refunds", None, text_, None)
    with as_tenant("acme"):
        hits = await kb.search("refunds")
        assert [h.text for h in hits] and all("Acme" in h.text for h in hits) and len(await kb.list_sources()) == 1
        assert await kb.get_document("faq", "doc1") is not None
    with as_tenant("globex"):
        assert all("Globex" in h.text for h in await kb.search("refunds"))
        assert await kb.delete("faq", "doc1") is True            # deletes only its own copy
    with as_tenant("acme"):
        assert len(await kb.search("refunds")) >= 1 and len(await kb.documents()) == 1
        with pytest.raises(Exception):
            await kb.create_source(Source("faq", "again"))          # a duplicate inside one tenant is still refused
    with as_tenant("nobody"):
        assert await kb.search("refunds") == [] and await kb.list_sources() == [] and await kb.documents() == []
        assert await kb.delete_source("faq") == 0


async def test_deleting_a_source_removes_only_that_tenants_documents(app_engine):
    from northcx.db import PgKnowledge
    from northcx.knowledge import Source
    kb = PgKnowledge(app_engine)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await kb.create_source(Source("faq", "FAQ"))
            await kb.upsert("faq", "d", "T", None, f"{tenant} policy text about warranty", None)
    with as_tenant("acme"):
        await kb.delete_source("faq")
        assert await kb.list_sources() == [] and await kb.search("warranty") == []
    with as_tenant("globex"):
        assert len(await kb.list_sources()) == 1 and len(await kb.search("warranty")) == 1


async def test_crawl_schedules_and_attachments_are_per_tenant(app_engine):
    import time
    from northcx.attachments import Attachment
    from northcx.crawl_schedule import Schedule
    from northcx.db import PgAttachments, PgKnowledge, PgSchedules
    from northcx.knowledge import Source
    kb, sched, att = PgKnowledge(app_engine), PgSchedules(app_engine), PgAttachments(app_engine)
    with as_tenant("acme"):
        await kb.create_source(Source("site", "Site"))
        s = Schedule("site", {"start_url": "https://example.com"}, 24, time.time() - 10, "rae")
        await sched.add(s)
        a = Attachment("s1", "a.txt", "text", "text/plain", 3, "x" * 64, b"abc", "rae")
        await att.add(a)
    with as_tenant("globex"):
        assert await sched.list() == [] and await sched.claim_due(time.time()) == [] and not await sched.delete(s.id)
        assert await att.get(a.id) is None and await att.for_session("s1") == [] and await att.usage("s1") == (0, 0)
        assert await att.erase_session("s1") == 0
    with as_tenant("acme"):
        assert len(await sched.list()) == 1 and (await att.get(a.id)).data == b"abc"
        assert len(await sched.claim_due(time.time())) == 1


async def test_meaning_search_embeddings_are_per_tenant(app_engine, engine):
    from northcx.db import PgKnowledge
    from northcx.knowledge import KnowledgeError, Source
    owner = PgKnowledge(engine)
    try:
        await owner.ensure_semantic()
    except KnowledgeError:
        pytest.skip("pgvector is not installed in this database")
    from sqlalchemy import text as sql
    async with engine.begin() as c:
        await c.execute(sql("grant all on knowledge_embeddings to northcx_app_test"))
    kb = PgKnowledge(app_engine)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await kb.create_source(Source("faq", "FAQ"))
            await kb.upsert("faq", "d", "T", None, f"{tenant} warranty covers two years", None)
            todo = await kb.pending_chunks("m", 10)
            await kb.save_embeddings("m", [(c, [1.0, 0.0, 0.0]) for c, *_ in todo] if todo and isinstance(todo[0], tuple) else [])
    with as_tenant("acme"):
        counts = await kb.embedding_counts("m")
        assert counts[1] == 1  # one passage in this tenant, not two
        assert await kb.clear_embeddings() <= 1
    with as_tenant("globex"):
        assert (await kb.embedding_counts("m"))[1] == 1


# ---------- batch d: channels ----------
async def test_email_sms_voice_and_verification_state_is_per_tenant(app_engine):
    from northcx.channels.email import EmailSession
    from northcx.channels.sms import SmsSession
    from northcx.db import PgCalls, PgEmailRepo, PgSmsRepo, PgVerify
    from northcx.verification import VerifyRecord
    email, sms, calls, verify = PgEmailRepo(app_engine), PgSmsRepo(app_engine), PgCalls(app_engine), PgVerify(app_engine)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await email.save_session(EmailSession("e1", f"{tenant}@x.com", "Hi", "<m1>"))
            assert await email.record_message("<m1>", "e1", "in", "ok", "p")          # the same Message-ID is new in each tenant
            await sms.save_session(SmsSession("s1", "+15550001", "+15559999", 1.0, 1.0))
            assert await sms.record_message("SM1", "s1", "in", "ok", "p")
            await sms.set_opt_out("+15550001", True)
            await verify.save(VerifyRecord("v1", "c1", "sms", "d", None, 9e9, 0, [], None))
    with as_tenant("acme"):
        assert (await email.get_session("e1")).sender == "acme@x.com" and await email.has_message("<m1>") and not await email.record_message("<m1>", "e1", "in", "ok", "p")
        assert await sms.is_opted_out("+15550001")
        await sms.set_opt_out("+15550001", False)
        assert not await sms.is_opted_out("+15550001")
        assert await verify.erase_session("v1") == 1
    with as_tenant("globex"):
        assert (await email.get_session("e1")).sender == "globex@x.com" and await sms.is_opted_out("+15550001")  # acme's opt-in change did not touch globex
        assert await verify.get("v1") is not None
    with as_tenant("nobody"):
        assert await email.get_session("e1") is None and await sms.get_session("s1") is None and not await sms.has_message("SM1") and await verify.get("v1") is None


async def test_an_inbound_address_is_routed_by_its_binding_and_unbound_ones_are_ignored():
    from northcx.tenancy import TenantService
    s = TenantService(preview=True)
    await s.create("acme", "Acme")
    await s.create("globex", "Globex")
    assert await s.inbound_tenant("sms", "+15550100") == DEFAULT_TENANT            # no bindings anywhere: a single-tenant deployment as before
    await s.bind("acme", "sms", "+15550100")
    assert await s.inbound_tenant("sms", "+15550100") == "acme"
    assert await s.inbound_tenant("sms", "+15550100", key_tenant="acme") == "acme"
    assert await s.inbound_tenant("sms", "+15550100", key_tenant="globex") is None  # another tenant's key cannot deliver to acme's number
    assert await s.inbound_tenant("sms", "+15559999") is None                       # bindings exist and this number has none: ignored, never guessed
    await s.set_status("acme", "suspended")
    assert await s.inbound_tenant("sms", "+15550100") is None                       # a suspended tenant's number is ignored


def test_the_email_route_delivers_only_to_the_tenant_that_owns_the_recipient_domain():
    import asyncio
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from examples.support_agent import support_agent
    from northcx.access import AccessControl
    from northcx.llm import ScriptedLLM
    from northcx.runtime import Runtime
    from northcx.server import create_app
    from northcx.store import InMemoryStore
    from northcx.tenancy import TenantService, current_tenant
    from northcx.trace import TraceStore
    seen = []

    class FakeEmail:
        repo = None

        async def receive(self, raw):
            seen.append(current_tenant())
            return SimpleNamespace(status="replied", session_id="s", reason=None, trace_id=None, handoff_id=None)
    ac = AccessControl(bootstrap_key="boot" * 10)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, email=FakeEmail()))
    loop = asyncio.new_event_loop()
    ac.tenants = TenantService(preview=True)
    for t in ("acme", "globex"):
        loop.run_until_complete(ac.tenants.create(t, t))
    loop.run_until_complete(ac.tenants.bind("acme", "email_domain", "acme.com"))
    acme = {"authorization": "Bearer " + loop.run_until_complete(ac.issue("acme-ch", "channel", "t", tenant_id="acme"))[1], "content-type": "message/rfc822"}
    globex = {"authorization": "Bearer " + loop.run_until_complete(ac.issue("globex-ch", "channel", "t", tenant_id="globex"))[1], "content-type": "message/rfc822"}
    msg = b"From: x@y.com\r\nTo: help@acme.com\r\nSubject: hi\r\n\r\nbody"
    assert c.post("/v1/channels/email/inbound", headers=acme, content=msg).json()["status"] == "replied" and seen == ["acme"]
    assert c.post("/v1/channels/email/inbound", headers=globex, content=msg).json()["status"] == "ignored"   # globex's key cannot deliver to acme's domain
    assert c.post("/v1/channels/email/inbound", headers=acme, content=b"From: x@y.com\r\nTo: help@other.com\r\nSubject: hi\r\n\r\nbody").json()["status"] == "ignored"  # unbound


# ---------- batches e and f: versions, releases, rollouts, scenarios, usage, groups, SCIM, idempotency ----------
async def test_versions_releases_and_rollouts_are_per_tenant_and_agent_ids_may_repeat(app_engine):
    from northcx.db import PgReleases, PgRollouts, PgVersions
    from northcx.rollout import Rollout
    from northcx.versions import Release
    versions, releases, rollouts = PgVersions(app_engine), PgReleases(app_engine), PgRollouts(app_engine)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            v = await versions.create("support", {"instructions": tenant}, f"digest-{tenant}", tenant, None)   # both tenants have a "support" agent, each at version 1
            assert v.number == 1
            await releases.add(Release("support", "publish", "rae", v.id, v.number))
            await rollouts.add(Rollout("support", "production", 1, None, 10, "rae"))       # one active rollout per agent and environment, per tenant
    with as_tenant("acme"):
        assert (await versions.get_number("support", 1)).author == "acme" and len(await versions.list("support")) == 1
        assert (await rollouts.active("support", "production")) is not None
    with as_tenant("nobody"):
        assert await versions.get_number("support", 1) is None and await versions.list("support") == [] and await rollouts.active("support", "production") is None


async def test_scenarios_runs_usage_and_idempotency_are_per_tenant(app_engine):
    from northcx.db import PgIdempotency, PgScenarios, PgSimRuns, PgUsageLedger
    from northcx.simulation.store import SimRun
    scen, runs, ledger, idem = PgScenarios(app_engine), PgSimRuns(app_engine), PgUsageLedger(app_engine, 100), PgIdempotency(app_engine)
    from types import SimpleNamespace
    sc = SimpleNamespace(name="refund", agent="support", required=True)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await scen.put(sc, {"name": "refund"}, tenant)                      # the same scenario name in both tenants
            run = await runs.add(SimRun("scripted", True, {}, {}, [], meta={"t": tenant}))
            await ledger.charge("support", 60 if tenant == "acme" else 10)
            await idem.begin("scope-1", "hash-1")
    with as_tenant("acme"):
        assert len(await scen.list()) == 1 and (await scen.get("refund")).created_by == "acme" and len(await runs.list()) == 1
        assert await ledger.spent() == 60 and not await ledger.over_budget()
        await ledger.charge("support", 50)
        ledger._cache.clear()
        assert await ledger.over_budget()                                      # acme used up its own budget...
    with as_tenant("globex"):
        assert await ledger.spent() == 10 and not await ledger.over_budget()   # ...and globex's is untouched, even in the same process
        assert [r.meta for r in await runs.list()] == [{"t": "globex"}]
        assert await scen.delete("refund") is True
    with as_tenant("acme"):
        assert await scen.get("refund") is not None


async def test_groups_and_scim_people_are_per_tenant(app_engine):
    from northcx.db import PgGroups, PgScimUsers
    from northcx.groups import GroupService
    from northcx.scim import ScimService
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            g = GroupService(PgGroups(app_engine))
            grp = await g.create("Support", ["reviewer"], "t", external_name="idp-support")        # the same group name and provider name in each tenant
            await g.add_member(grp.id, "rae@corp.com")
            sc = ScimService(PgScimUsers(app_engine), g, None)
            await sc.create_user({"userName": "rae@corp.com"}, "scim")                           # the same person in two tenants
    with as_tenant("acme"):
        g = GroupService(PgGroups(app_engine))
        assert len(await g.repo.list()) == 1 and (await g.effective_roles(["rae@corp.com"], []))[0] == ["reviewer"]
        sc = ScimService(PgScimUsers(app_engine), g, None)
        u = await sc.users.by_name("rae@corp.com")
        await sc.patch_user(u.id, {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"], "Operations": [{"op": "replace", "path": "active", "value": False}]})
        assert not await sc.may_sign_in("rae@corp.com")
    with as_tenant("globex"):
        sc = ScimService(PgScimUsers(app_engine), GroupService(PgGroups(app_engine)), None)
        assert await sc.may_sign_in("rae@corp.com")                              # deactivating her in acme does not touch globex


async def test_qualifications_release_requests_and_alert_state_are_per_tenant(app_engine):
    from northcx.db import PgAlertState, PgQualifications, PgReleaseRequests
    from northcx.providers.qualification import Qualification
    from northcx.release_requests import ApprovalError, ReleaseApprovals
    qual, appr, alerts = PgQualifications(app_engine), ReleaseApprovals({"production"}, PgReleaseRequests(app_engine)), PgAlertState(app_engine)
    ids = {}
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await qual.save(Qualification("support", "m:x", "d", tenant == "acme", 1, 1, 0, 0, "r"))
            ids[tenant] = (await appr.request("support", "publish", "production", 1, "key:1", None)).id   # the same request in both tenants is not a duplicate
            await alerts.set_active("high-handoffs", {"n": 1 if tenant == "acme" else 2})
    with as_tenant("acme"):
        assert (await qual.latest("support", "m:x")).qualified and [r.id for r in await appr.repo.list(None, None, 10)] == [ids["acme"]]
        with pytest.raises(ApprovalError, match="Unknown"):
            await appr.claim(ids["globex"], "key:2", True, None)           # another tenant's request does not exist here
        active, _ = await alerts.load()
        assert active["high-handoffs"]["n"] == 1
    with as_tenant("globex"):
        assert not (await qual.latest("support", "m:x")).qualified
        assert (await appr.claim(ids["globex"], "key:2", True, None)).status == "approved"
        await alerts.clear_active("high-handoffs")
    with as_tenant("acme"):
        assert "high-handoffs" in (await alerts.load())[0]                 # clearing globex's alert did not clear acme's
        assert (await appr.repo.get(ids["acme"])).status == "pending"


# ---------- gates (WP2.9) ----------
PLATFORM_TABLES = {"api_keys", "audit_log", "tenants", "channel_bindings", "job_leases", "rate_counters", "alembic_version"}


async def test_every_table_is_isolated_unless_it_is_platform_data(engine):
    """A table added later without a tenant column and a policy fails here, so a new table cannot quietly skip isolation."""
    rows = await raw(engine, "select c.relname, c.relrowsecurity, "
                             "exists (select 1 from information_schema.columns k where k.table_name = c.relname and k.column_name = 'tenant_id' and k.table_schema = 'public') as has_col, "
                             "exists (select 1 from pg_policies p where p.tablename = c.relname and p.policyname = 'tenant_isolation') as has_policy "
                             "from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r' order by 1")
    problems = [r.relname for r in rows if r.relname not in PLATFORM_TABLES and not (r.relrowsecurity and r.has_col and r.has_policy)]
    assert problems == [], f"tables without a tenant column, row-level security and a policy: {problems}"
    assert {r.relname for r in rows} >= {"messages", "knowledge_chunks", "groups", "usage_ledger"}
    for name in ("api_keys", "audit_log"):  # these carry a tenant but are read before the tenant is known, or across tenants; the API filters them
        assert any(r.relname == name for r in rows)


async def test_random_interleavings_of_two_tenants_never_mix_their_data(app_engine):
    """Isolation fuzz: many concurrent operations from two tenants against the same session and customer ids; each tenant ends with exactly its own."""
    import asyncio
    import random
    store, mem = PgMemoryStore(app_engine), PgMemories(app_engine)
    rnd = random.Random(7)
    expected = {"acme": {}, "globex": {}}

    async def work(tenant, i):
        with as_tenant(tenant):
            sid = f"s{rnd.randrange(4)}"                    # few ids, so the two tenants keep colliding on them
            msgs = [{"role": "user", "content": f"{tenant}-{i}-{k}"} for k in range(rnd.randrange(1, 4))]
            await asyncio.sleep(rnd.random() * 0.01)
            await store.save_messages(sid, msgs)
            await store.set_fact(f"c{sid}", "last", f"{tenant}-{i}")
            await mem.remember(f"c{sid}", f"{tenant} note {i % 3}", sid)
            return sid, msgs
    jobs = [(rnd.choice(("acme", "globex")), i) for i in range(60)]
    # operations on one (tenant, session) are applied one after another, as the server serialises a conversation; the two tenants run in parallel
    by_key: dict = {}
    for tenant, i in jobs:
        by_key.setdefault(tenant, []).append(i)

    async def run_tenant(tenant):
        for i in by_key.get(tenant, []):
            sid, msgs = await work(tenant, i)
            expected[tenant][sid] = ([m["content"] for m in msgs], f"{tenant}-{i}")
    await asyncio.gather(run_tenant("acme"), run_tenant("globex"))
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            for sid, (contents, fact) in expected[tenant].items():
                assert [m["content"] for m in await store.load_messages(sid)] == contents, (tenant, sid)
                assert (await store.get_facts(f"c{sid}"))["last"] == fact
                assert all(m.text.startswith(tenant) for m in await mem.list(f"c{sid}"))
    with as_tenant("acme"):
        for sid in expected["acme"]:
            assert not any(m["content"].startswith("globex") for m in await store.load_messages(sid))


def test_going_back_and_forward_through_the_tenant_migrations_keeps_the_default_tenants_data(db_url):
    """Backfill and downgrade gate: default-tenant rows survive both directions; the other tenants' rows are removed on the way back."""
    import asyncio

    from sqlalchemy import text as sql
    from sqlalchemy.pool import NullPool

    from northcx.db import create_engine, migrate
    from northcx.db.engine import downgrade

    async def run(statement, **p):
        eng = create_engine(db_url, poolclass=NullPool)
        try:
            async with eng.begin() as c:
                res = await c.execute(sql(statement), p)
                return res.all() if res.returns_rows else []
        finally:
            await eng.dispose()
    asyncio.run(run("insert into sessions (tenant_id, id) values ('default', 'keep'), ('acme', 'drop'), ('acme', 'keep')"))
    asyncio.run(run("insert into knowledge_sources (tenant_id, id, name, created_at) values ('default', 'faq', 'n', 1), ('acme', 'faq', 'n', 1)"))
    downgrade(db_url, "0036")
    assert [r[0] for r in asyncio.run(run("select id from sessions order by id"))] == ["keep"]          # only the default tenant's row is left, with the old key
    assert [r[0] for r in asyncio.run(run("select id from knowledge_sources"))] == ["faq"]
    migrate(db_url)
    rows = asyncio.run(run("select tenant_id, id from sessions"))
    assert [tuple(r) for r in rows] == [("default", "keep")]                                          # backfilled as the default tenant
    asyncio.run(run("insert into sessions (id) values ('new')"))
    assert {tuple(r) for r in asyncio.run(run("select tenant_id, id from sessions"))} == {("default", "keep"), ("default", "new")}


def test_api_sweep_one_tenants_key_cannot_reach_anothers_conversations(app_engine):
    """The route-level gate: tenant B's administrator against tenant A's real ids on every route that takes one. Nothing is returned, changed or erased."""
    import asyncio

    from fastapi.testclient import TestClient

    from examples.support_agent import support_agent
    from northcx.access import AccessControl
    from northcx.db import PgAudit, PgKeys
    from northcx.llm import ScriptedLLM
    from northcx.outbox import Outbox
    from northcx.runtime import Runtime
    from northcx.server import create_app
    from northcx.tenancy import TenantService
    eng = app_engine
    store, traces, appr, handoffs, outbox = PgMemoryStore(eng), PgTraceStore(eng), PgApprovalStore(eng), PgHandoffs(eng), PgOutbox(eng)
    rt = Runtime(ScriptedLLM([]), store, traces, appr, Outbox(outbox), handoffs, privacy=PgPrivacy(eng))
    ac = AccessControl(keys=PgKeys(eng), bootstrap_key="boot" * 10)
    ac.tenants = TenantService(preview=True)
    app = create_app(rt, traces, {"support": support_agent()}, access=ac, audit=PgAudit(eng))
    c = TestClient(app)
    loop = asyncio.new_event_loop()
    run = loop.run_until_complete

    async def seed():
        await ac.tenants.create("acme", "Acme")
        await ac.tenants.create("globex", "Globex")
        out = {}
        for tenant in ("acme", "globex"):
            with as_tenant(tenant):
                await store.save_messages("s1", [{"role": "user", "content": f"{tenant} private"}])
                await store.set_fact("c1", "k", tenant)
                await PgPrivacy(eng).link("s1", "c1")
                t = Trace("support", "s1")
                t.add("llm", tokens=1)
                await traces.save(t)
                a = await appr.add(trace_id=t.id, session_id="s1", tool="refund", input={}, reason="r", agent_id="support", customer_id="c1")
                h = await handoffs.add(Handoff("s1", t.id, "support", "customer_asked", "why", {}, customer_id="c1"))
                out[tenant] = (t.id, a.id, h.id)
        return out
    ids = run(seed())
    _, acme_h = None, None
    admin = lambda tenant: {"authorization": "Bearer " + run(ac.issue(f"{tenant}-admin", "admin", "t", tenant_id=tenant))[1]}  # noqa: E731
    A, B = admin("acme"), admin("globex")
    t_a, ap_a, h_a = ids["acme"]
    # B asks about A's ids: not found, or an empty list
    assert c.get(f"/v1/traces/{t_a}", headers=B).status_code == 404
    assert c.get(f"/v1/handoffs/{h_a}", headers=B).status_code == 404
    assert c.post(f"/v1/handoffs/{h_a}/resolve", headers=B, json={"note": "mine now"}).status_code == 404
    assert c.post(f"/v1/approvals/{ap_a}/decision", headers=B, json={"approved": True}).status_code == 404
    seen = c.get("/v1/approvals", headers=B).json()["approvals"]
    assert [x["id"] for x in seen] == [ids["globex"][1]]                                  # B sees only its own
    assert [x["id"] for x in c.get("/v1/handoffs", headers=B).json()["handoffs"]] == [ids["globex"][2]]
    tr = c.get("/v1/traces", headers=B).json()
    assert t_a not in str(tr)
    transcript = c.get("/v1/sessions/s1/transcript", headers=B)
    assert "acme private" not in transcript.text and "globex private" in transcript.text   # the same session id shows B's own conversation
    assert "acme" not in c.get("/v1/privacy/customers/c1/export", headers=B).text
    # B erasing "its" session s1 or customer c1 leaves A's untouched
    c.delete("/v1/privacy/sessions/s1", headers=B)
    c.delete("/v1/privacy/customers/c1", headers=B)
    with as_tenant("acme"):
        assert [m["content"] for m in run(store.load_messages("s1"))] == ["acme private"] and run(store.get_facts("c1")) == {"k": "acme"}
        assert run(appr.get(ap_a)).state == "pending" and run(handoffs.get(h_a)).state == "open" and run(traces.get(t_a)) is not None
    with as_tenant("globex"):
        assert run(store.load_messages("s1")) == [] and run(store.get_facts("c1")) == {}
    # A's own administrator still sees everything, and the audit log of each tenant holds only that tenant's entries
    assert c.get(f"/v1/handoffs/{h_a}", headers=A).status_code == 200
    assert c.post("/v1/keys", headers=A, json={"name": "ci", "role": "developer"}).status_code == 201   # an audited action of A's own
    a_audit = c.get("/v1/audit?limit=100", headers=A).json()["entries"]
    b_audit = c.get("/v1/audit?limit=100", headers=B).json()["entries"]
    assert a_audit and b_audit and not {e["id"] for e in a_audit} & {e["id"] for e in b_audit}
