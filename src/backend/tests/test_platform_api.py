"""WP2.5, WP2.7, WP2.8: the platform API, and the per-tenant limits and configuration it sets."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl, LimitConfig
from northcx.audit import InMemoryAudit
from northcx.budget_settings import InMemorySettings
from northcx.llm import ScriptedLLM, text
from northcx.platform_api import create_platform_app
from northcx.runtime import Runtime
from northcx.secrets import ConfigError
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.tenancy import TenantService
from northcx.tenant_limits import LimitError, TenantLimits, validate
from northcx.trace import TraceStore

PKEY = "p" * 40
P = {"authorization": f"Bearer {PKEY}"}


def world(limits_config=None, defaults=None):
    loop = asyncio.new_event_loop()
    run = loop.run_until_complete
    rt = Runtime(ScriptedLLM([text("ok")] * 50), InMemoryStore(), TraceStore())
    settings = InMemorySettings()
    rt.tenant_limits = TenantLimits(settings, defaults)
    ac = AccessControl(bootstrap_key="boot" * 10, limits=limits_config)
    ac.tenants = TenantService(preview=True)
    audit = InMemoryAudit()
    web = create_app(rt, rt.traces, {"support": support_agent()}, access=ac, audit=audit)
    plat = create_platform_app(PKEY, ac.tenants, rt.tenant_limits, settings, audit, ac)
    key = lambda tenant, role="admin", name=None: {"authorization": "Bearer " + run(ac.issue(name or f"{tenant}-{role}", role, "t", tenant_id=tenant))[1]}  # noqa: E731
    return TestClient(web), TestClient(plat), key, ac, rt, run


def test_the_platform_api_needs_its_own_key_and_a_tenants_key_does_not_work_on_it():
    web, plat, key, ac, rt, run = world()
    assert plat.get("/platform/v1/tenants").status_code == 401
    assert plat.get("/platform/v1/tenants", headers={"authorization": "Bearer wrong"}).status_code == 401
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    assert plat.get("/platform/v1/tenants", headers=key("acme")).status_code == 401                    # a tenant's administrator is not the operator
    assert plat.get("/v1/me", headers=P).status_code == 404 and web.get("/platform/v1/tenants", headers=P).status_code in (401, 404)
    assert plat.get("/platform/health").json() == {"ok": True}
    with pytest.raises(ConfigError):
        create_platform_app("short", None, None, None, None)


def test_the_platform_api_has_no_route_to_a_tenants_data():
    web, plat, key, ac, rt, run = world()
    paths = {r.path for r in plat.app.routes if getattr(r, "path", "").startswith("/platform")}
    assert all(p.startswith("/platform/v1/tenants") or p in ("/platform/health", "/platform/v1/vault/reseal") for p in paths)
    assert not any(w in p for p in paths for w in ("session", "conversation", "customer", "message", "document", "trace", "output", "note"))


def test_tenants_are_created_suspended_resumed_planned_and_bound_by_the_operator():
    web, plat, key, ac, rt, run = world()
    r = plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme", "plan": "Team"})
    assert r.status_code == 201 and r.json()["plan"] == "team" and r.json()["status"] == "active"
    assert plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Again"}).status_code == 409
    assert plat.post("/platform/v1/tenants", headers=P, json={"id": "default", "name": "No"}).status_code == 400
    admin = key("acme")
    assert web.get("/v1/me", headers=admin).status_code == 200
    assert plat.post("/platform/v1/tenants/acme/suspend", headers=P).json()["status"] == "suspended"
    assert web.get("/v1/me", headers=admin).status_code == 401                                          # a suspended tenant's keys stop working at once
    assert plat.post("/platform/v1/tenants/acme/resume", headers=P).json()["status"] == "active" and web.get("/v1/me", headers=admin).status_code == 200
    assert plat.post("/platform/v1/tenants/default/suspend", headers=P).status_code == 400
    assert plat.post("/platform/v1/tenants/nope/suspend", headers=P).status_code == 404
    assert plat.put("/platform/v1/tenants/acme/plan", headers=P, json={"plan": "Business"}).json()["plan"] == "business"
    assert plat.put("/platform/v1/tenants/acme/plan", headers=P, json={"plan": "bad/plan!"}).status_code == 400
    b = plat.post("/platform/v1/tenants/acme/bindings", headers=P, json={"kind": "sms", "address": "+15550001111"})
    assert b.status_code == 201
    plat.post("/platform/v1/tenants", headers=P, json={"id": "globex", "name": "Globex"})
    assert plat.post("/platform/v1/tenants/globex/bindings", headers=P, json={"kind": "sms", "address": "+15550001111"}).status_code == 409      # one address, one tenant
    assert plat.delete("/platform/v1/tenants/globex/bindings/sms/+15550001111", headers=P).status_code == 404
    assert plat.delete("/platform/v1/tenants/acme/bindings/sms/+15550001111", headers=P).json() == {"removed": True}
    listed = {t["id"]: t for t in plat.get("/platform/v1/tenants", headers=P).json()["tenants"]}
    assert set(listed) == {"default", "acme", "globex"} and listed["acme"]["activeKeys"] == 1 and listed["acme"]["plan"] == "business"


def test_what_the_operator_does_is_written_to_that_tenants_own_audit_log_only():
    web, plat, key, ac, rt, run = world()
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    plat.post("/platform/v1/tenants", headers=P, json={"id": "globex", "name": "Globex"})
    plat.post("/platform/v1/tenants/acme/suspend", headers=P)
    plat.post("/platform/v1/tenants/acme/resume", headers=P)
    acme = web.get("/v1/audit?limit=50", headers=key("acme")).json()["entries"]
    globex = web.get("/v1/audit?limit=50", headers=key("globex")).json()["entries"]
    assert {"platform.tenant_suspended", "platform.tenant_resumed"} <= {e["action"] for e in acme} and all(e["actor"] == "platform" for e in acme if e["action"].startswith("platform."))
    assert not any(e["action"] in ("platform.tenant_suspended", "platform.tenant_resumed") for e in globex)


def test_limits_are_validated_and_a_tenant_can_read_but_not_change_its_own():
    for bad in ({"requestsPerMinute": 0}, {"requestsPerMinute": "many"}, {"maxOutputs": -1}, {"retentionDays": 5000}, {"colour": 1}, []):
        with pytest.raises(LimitError):
            validate(bad)
    assert validate({"requestsPerMinute": 30, "maxOutputs": None, "retentionDays": 30.5}) == {"requestsPerMinute": 30, "retentionDays": 30.5}
    web, plat, key, ac, rt, run = world(defaults={"requestsPerMinute": 1000})
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    admin = key("acme")
    assert web.get("/v1/tenant/limits", headers=admin).json()["limits"]["requestsPerMinute"] == {"value": 1000, "source": "platform"}
    assert plat.put("/platform/v1/tenants/acme/limits", headers=P, json={"requestsPerMinute": 5, "maxOutputs": 2}).json()["limits"]["requestsPerMinute"] == {"value": 5, "source": "tenant"}
    assert plat.put("/platform/v1/tenants/acme/limits", headers=P, json={"requestsPerMinute": 0}).status_code == 400
    rt.tenant_limits._cache.clear()
    got = web.get("/v1/tenant/limits", headers=admin).json()["limits"]
    assert got["requestsPerMinute"]["value"] == 5 and got["maxOutputs"] == {"value": 2, "source": "tenant"} and got["retentionDays"] == {"value": None, "source": "none"}
    assert web.put("/v1/tenant/limits", headers=admin, json={"requestsPerMinute": 999999}).status_code in (404, 405)            # no way to raise it from inside
    plat.delete("/platform/v1/tenants/acme/limits", headers=P)
    rt.tenant_limits._cache.clear()
    assert web.get("/v1/tenant/limits", headers=admin).json()["limits"]["requestsPerMinute"]["source"] == "platform"            # back to the platform default


def test_a_tenant_ceiling_stops_that_tenant_without_touching_another():
    web, plat, key, ac, rt, run = world(limits_config=LimitConfig())
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    plat.post("/platform/v1/tenants", headers=P, json={"id": "globex", "name": "Globex"})
    plat.put("/platform/v1/tenants/acme/limits", headers=P, json={"requestsPerMinute": 4})
    rt.tenant_limits._cache.clear()
    a1, a2, g = key("acme", name="acme-one"), key("acme", name="acme-two"), key("globex")
    codes = [web.get("/v1/me", headers=h).status_code for h in (a1, a2, a1, a2, a1, a2)]
    assert codes[:4] == [200] * 4 and codes[4:] == [429, 429]                                              # two keys of one tenant share the ceiling
    assert [web.get("/v1/me", headers=g).status_code for _ in range(8)] == [200] * 8


def test_a_tenant_cannot_keep_more_outputs_than_its_limit_allows():
    web, plat, key, ac, rt, run = world()
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    plat.put("/platform/v1/tenants/acme/limits", headers=P, json={"maxOutputs": 2})
    rt.tenant_limits._cache.clear()
    admin = key("acme")
    codes = [web.post("/v1/workspace/outputs", headers=admin, json={"title": f"Note {i}", "body": "text"}).status_code for i in range(3)]
    assert codes == [201, 201, 429]
    other = key("globex")
    plat.post("/platform/v1/tenants", headers=P, json={"id": "globex", "name": "Globex"})
    assert web.post("/v1/workspace/outputs", headers=other, json={"title": "Note", "body": "text"}).status_code == 201


async def test_limits_survive_the_database_and_stay_in_their_tenant(app_engine):
    from northcx.db import PgSettings
    tl = TenantLimits(PgSettings(app_engine), {"requestsPerMinute": 100})
    await tl.put("acme", {"retentionDays": 30}, "platform")
    assert (await tl.effective("acme"))["retentionDays"] == {"value": 30, "source": "tenant"}
    assert (await tl.effective("globex"))["retentionDays"] == {"value": None, "source": "none"} and (await tl.effective("globex"))["requestsPerMinute"]["source"] == "platform"
    await tl.clear("acme")
    tl._cache.clear()
    assert (await tl.effective("acme"))["retentionDays"]["value"] is None


async def test_the_retention_job_uses_the_tenants_own_period_and_the_platform_default():
    """The job runs once per tenant; this runs its body for one tenant to be sure the import and the lookup work."""
    from northcx.api.background import start_background
    from northcx.tenancy import TENANT
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    rt.tenant_limits = TenantLimits(InMemorySettings(), {})
    await rt.tenant_limits.put("acme", {"retentionDays": 7}, "platform")
    purged: list[float] = []

    class Privacy:
        async def purge_idle(self, days):
            purged.append(days)
            return {"sessions": 0, "removed": {}}
    ran = []

    def fake_every(seconds, name, job, *a, **k):
        ran.append((name, job))

        class T:
            def cancel(self): ...
        return T()
    import northcx.api.background as bg
    original = bg._every
    bg._every = fake_every
    try:
        stop = start_background("all", None, runtime=rt, traces=rt.traces, flow=None, agents=None, approval_ttl_seconds=None, alerts=None, privacy=Privacy(), audit=InMemoryAudit(),
                                retention_days=None, kb=None, crawl_scheduler=None)
        job = dict(ran)["retention"]
        token = TENANT.set("acme")
        try:
            await job()
        finally:
            TENANT.reset(token)
        token = TENANT.set("globex")
        try:
            await job()                                  # no period for this tenant and no platform default: nothing is erased
        finally:
            TENANT.reset(token)
        await stop()
    finally:
        bg._every = original
    assert purged == [7]


def test_channel_status_lists_what_is_on_and_no_credentials():
    web, plat, key, ac, rt, run = world()
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    got = web.get("/v1/channels", headers=key("acme"))
    assert got.status_code == 200
    rows = {c["id"]: c for c in got.json()["channels"]}
    assert rows["web"]["configured"] is True and {"email", "sms", "whatsapp", "telegram", "voice"} <= set(rows)
    assert all(set(c) <= {"id", "label", "configured", "inbound", "note"} for c in rows.values())    # nothing else, so no secret can leak
    assert web.get("/v1/channels").status_code in (401, 403)


def test_a_suspended_tenants_chat_tokens_stop_working_at_once():
    # Chat tokens are minted by a tenant's key; suspending the tenant must end them as it ends the keys, not when they expire.
    web, plat, key, ac, rt, run = world()
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    k, _ = run(ac.issue("acme-web", "admin", "t", tenant_id="acme"))
    token, _ = ac.signer.mint(sid="web-1", kid=k.key_id, agent="support", ttl=600)
    assert run(ac.authenticate(token)) is not None
    plat.post("/platform/v1/tenants/acme/suspend", headers=P)
    assert run(ac.authenticate(token)) is None
    plat.post("/platform/v1/tenants/acme/resume", headers=P)
    assert run(ac.authenticate(token)) is not None
