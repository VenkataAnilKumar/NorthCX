"""WP2.2 and the first batch of WP2.3: tenants, keys and the audit log. A tenant sees only its own; the default tenant behaves as before."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from northcx.access import AccessControl
from northcx.audit import AuditEntry, InMemoryAudit, entry_hash, verify_entries
from northcx.tenancy import DEFAULT_TENANT, TENANT, TenantError, TenantService
from route_snapshot import build_app

BOOT = {"authorization": "Bearer " + "boot" * 10}


def stack():
    app = build_app()
    c = TestClient(app)
    ac = app.state.access if hasattr(app.state, "access") else None
    return app, c, ac


async def setup(access):
    access.tenants = TenantService(preview=True)
    await access.tenants.create("acme", "Acme")
    await access.tenants.create("globex", "Globex")
    _, acme = await access.issue("acme-admin", "admin", "t", tenant_id="acme")
    _, globex = await access.issue("globex-admin", "admin", "t", tenant_id="globex")
    return {"authorization": f"Bearer {acme}"}, {"authorization": f"Bearer {globex}"}


def test_a_tenant_sees_and_changes_only_its_own_keys_and_audit_entries():
    from northcx.server import create_app
    from examples.support_agent import support_agent
    from northcx.llm import ScriptedLLM
    from northcx.runtime import Runtime
    from northcx.store import InMemoryStore
    from northcx.trace import TraceStore
    ac = AccessControl(bootstrap_key="boot" * 10)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    acme, globex = asyncio.run(setup(ac))
    assert c.get("/v1/me", headers=acme).json()["tenant"] == "acme" and c.get("/v1/me", headers=BOOT).json()["tenant"] == DEFAULT_TENANT
    k = c.post("/v1/keys", headers=acme, json={"name": "ci", "role": "developer"}).json()
    assert [x["name"] for x in c.get("/v1/keys", headers=acme).json()["keys"]] == ["ci", "acme-admin"]
    assert [x["name"] for x in c.get("/v1/keys", headers=globex).json()["keys"]] == ["globex-admin"]
    assert [x["name"] for x in c.get("/v1/keys", headers=BOOT).json()["keys"]] == []  # the default tenant has none of its own here
    # the same key name may exist in two tenants; another tenant's key id is simply unknown
    assert c.post("/v1/keys", headers=globex, json={"name": "ci", "role": "developer"}).status_code == 201
    assert c.post(f"/v1/keys/{k['id']}/revoke", headers=globex).status_code == 404
    assert c.post(f"/v1/keys/{k['id']}/revoke", headers=BOOT).status_code == 404
    assert c.post(f"/v1/keys/{k['id']}/revoke", headers=acme).status_code == 200
    mine = c.get("/v1/audit?limit=50", headers=acme).json()["entries"]
    assert mine and all("acme" in str(e["detail"]) or e["action"].startswith("key.") for e in mine)
    theirs = c.get("/v1/audit?limit=50", headers=globex).json()["entries"]
    assert not {e["id"] for e in mine} & {e["id"] for e in theirs}
    assert {e["action"] for e in mine} >= {"key.create", "key.revoke"}
    assert c.get("/v1/audit/verify", headers=acme).json() == {"ok": True}  # a tenant learns only whether the chain holds


def test_a_suspended_tenants_keys_stop_working_at_once():
    from northcx.server import create_app
    from examples.support_agent import support_agent
    from northcx.llm import ScriptedLLM
    from northcx.runtime import Runtime
    from northcx.store import InMemoryStore
    from northcx.trace import TraceStore
    ac = AccessControl(bootstrap_key="boot" * 10)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    acme, globex = asyncio.run(setup(ac))
    assert c.get("/v1/me", headers=acme).status_code == 200
    asyncio.run(ac.tenants.set_status("acme", "suspended"))
    assert c.get("/v1/me", headers=acme).status_code == 401 and c.get("/v1/me", headers=globex).status_code == 200
    asyncio.run(ac.tenants.set_status("acme", "active"))
    assert c.get("/v1/me", headers=acme).status_code == 200


async def test_tenant_rules():
    s = TenantService()
    with pytest.raises(TenantError, match="NORTHCX_TENANCY_PREVIEW"):
        await s.create("acme", "Acme")
    s = TenantService(preview=True)
    for bad, why in [("default", "not 'default'"), ("A", "3 to 40"), ("has space", "3 to 40"), ("-x-", "3 to 40")]:
        with pytest.raises(TenantError, match=why):
            await s.create(bad, "n")
    await s.create("acme", "Acme")
    with pytest.raises(TenantError, match="already exists"):
        await s.create("acme", "Again")
    with pytest.raises(TenantError, match="cannot be suspended"):
        await s.set_status(DEFAULT_TENANT, "suspended")
    assert await s.is_active(DEFAULT_TENANT) and await s.is_active("acme") and not await s.is_active("ghost")


async def test_an_address_belongs_to_one_tenant_and_an_unbound_one_resolves_to_nothing():
    s = TenantService(preview=True)
    await s.create("acme", "Acme")
    await s.create("globex", "Globex")
    await s.bind("acme", "sms", "+15550100")
    with pytest.raises(TenantError, match="already belongs"):
        await s.bind("globex", "sms", "+15550100")
    await s.bind("globex", "whatsapp", "+15550100")  # the same digits on another channel kind are a different address
    assert await s.resolve("sms", "+15550100") == "acme" and await s.resolve("whatsapp", "+15550100") == "globex"
    assert await s.resolve("sms", "+15559999") is None  # unbound: ignore it, never guess
    with pytest.raises(TenantError):
        await s.bind("acme", "carrier-pigeon", "x")
    with pytest.raises(KeyError):
        await s.bind("nobody", "sms", "+1")


def test_the_default_tenants_audit_hash_is_unchanged_and_other_tenants_are_covered_by_it():
    e = AuditEntry(actor="a", role="admin", action="x", id=1, at=1.0, prev_hash="0" * 64, tenant_id=DEFAULT_TENANT)
    legacy = {"id": 1, "at": 1.0, "actor": "a", "role": "admin", "key_id": None, "action": "x", "target": "", "outcome": "success", "detail": {}}
    import hashlib, json
    assert entry_hash(e) == hashlib.sha256(("0" * 64 + json.dumps(legacy, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()
    other = AuditEntry(actor="a", role="admin", action="x", id=1, at=1.0, prev_hash="0" * 64, tenant_id="acme")
    assert entry_hash(other) != entry_hash(e)  # moving an entry to another tenant breaks the chain


async def test_the_audit_entry_takes_the_requests_tenant_by_default():
    token = TENANT.set("acme")
    try:
        assert AuditEntry(actor="a", role="r", action="x").tenant_id == "acme"
    finally:
        TENANT.reset(token)
    assert AuditEntry(actor="a", role="r", action="x").tenant_id == DEFAULT_TENANT
    a = InMemoryAudit()
    for t in ("acme", "globex", "acme"):
        await a.append(AuditEntry(actor="a", role="r", action="x", tenant_id=t))
    assert len(await a.list(tenant_id="acme")) == 2 and len(await a.list(tenant_id="globex")) == 1 and len(await a.list()) == 3
    assert verify_entries(list(a._items)).ok


async def test_tenants_keys_and_audit_in_the_database(engine):
    from northcx.db import PgAudit, PgKeys, PgTenants
    import uuid
    tid = "t-" + uuid.uuid4().hex[:8]  # tenants are not truncated between tests: the default one must stay
    ts = TenantService(PgTenants(engine), preview=True)
    assert DEFAULT_TENANT in [t.id for t in await ts.repo.list()]  # the migration seeds the default tenant
    await ts.create(tid, "Acme")
    await ts.bind(tid, "email_domain", "Acme.com")
    assert await TenantService(PgTenants(engine)).resolve("email_domain", "acme.com") == tid
    with pytest.raises(TenantError):
        await ts.bind(DEFAULT_TENANT, "email_domain", "acme.com")
    ac = AccessControl(keys=PgKeys(engine))
    ac.tenants = ts
    _, secret = await ac.issue("k", "developer", "t", tenant_id=tid)
    assert (await ac.authenticate(secret)).tenant == tid
    await ts.set_status(tid, "suspended")
    assert await ac.authenticate(secret) is None
    audit = PgAudit(engine)
    await audit.append(AuditEntry(actor="a", role="r", action="x", tenant_id=tid))
    await audit.append(AuditEntry(actor="a", role="r", action="x"))
    await audit.append(AuditEntry(actor="a", role="r", action="y", tenant_id=tid))
    assert [e.action for e in await audit.list(tenant_id=tid)] == ["y", "x"] and len(await audit.list(tenant_id=DEFAULT_TENANT)) == 1
    assert (await audit.verify()).ok
