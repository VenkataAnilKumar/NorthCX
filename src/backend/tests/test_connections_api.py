"""The connections routes (Phase 2, WP 2.3): who may use them, the whole review, approve and check flow over HTTP, the audit trail, and limits."""
import httpx

from northcx.access import AccessControl
from northcx.audit import InMemoryAudit
from northcx.llm import ScriptedLLM
from northcx.mcp_connections import McpConnections
from northcx.runtime import Runtime
from northcx.secrets import SecretStore
from northcx.server import create_app
from northcx.spec import Registry
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from tests.mcp_fake import SECRET, URL, FakeMcp

KEY = "boot" * 10
SHOP = "shop__orders_lookup"


async def world(fake=None, configured=True):
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    if configured:
        rt.mcp = McpConnections(None, Registry(), {"localhost"}, SecretStore({"orders": SECRET}), transport=fake.transport() if fake else None)
    ac, audit = AccessControl(bootstrap_key=KEY), InMemoryAudit()
    app = create_app(rt, rt.traces, {}, access=ac, audit=audit)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    keys = {}
    for role in ("admin", "viewer", "developer"):
        keys[role] = {"authorization": "Bearer " + (await ac.issue(role, role, "t"))[1]}
    return client, keys, rt


async def test_without_the_service_the_routes_say_so_plainly():
    client, keys, _ = await world(configured=False)
    r = await client.get("/v1/connections", headers=keys["admin"])
    assert r.status_code == 501 and r.json()["error"]["code"] == "not_configured"


async def test_anyone_who_can_read_versions_may_look_but_only_an_administrator_may_change_anything():
    async with FakeMcp().running() as fake:
        client, keys, _ = await world(fake)
        body = {"name": "shop", "url": URL, "secret": "orders", "trusted": True}
        assert (await client.post("/v1/connections", headers=keys["developer"], json=body)).status_code == 403
        assert (await client.post("/v1/connections", headers=keys["viewer"], json=body)).status_code == 403
        made = await client.post("/v1/connections", headers=keys["admin"], json=body)
        assert made.status_code == 201
        cid = made.json()["id"]
        for role in ("viewer", "developer", "admin"):
            assert (await client.get("/v1/connections", headers=keys[role])).status_code == 200
            assert (await client.get(f"/v1/connections/{cid}", headers=keys[role])).status_code == 200
        for method, path in (("PUT", f"/v1/connections/{cid}"), ("DELETE", f"/v1/connections/{cid}"), ("POST", f"/v1/connections/{cid}/review"),
                             ("POST", f"/v1/connections/{cid}/approve"), ("POST", f"/v1/connections/{cid}/check")):
            assert (await client.request(method, path, headers=keys["developer"], json={})).status_code == 403, path
        assert (await client.get("/v1/connections")).status_code == 401


async def test_the_whole_flow_over_http_review_approve_check_switch_off_and_every_step_is_audited():
    async with FakeMcp().running() as fake:
        client, keys, rt = await world(fake)
        h = keys["admin"]
        c = (await client.post("/v1/connections", headers=h, json={"name": "shop", "url": URL, "secret": "orders", "trusted": True})).json()
        assert c["approvedTools"] == [] and c["host"] == "localhost" and SECRET not in str(c)
        review = (await client.post(f"/v1/connections/{c['id']}/review", headers=h)).json()
        seen = {t["name"]: t["fingerprint"] for t in review["tools"]}
        assert SHOP in seen and any(s["name"] == "poisoned_description" for s in review["skipped"])
        approved = await client.post(f"/v1/connections/{c['id']}/approve", headers=h, json={"tools": {SHOP: seen[SHOP]}})
        assert approved.status_code == 200 and approved.json()["approvedTools"] == [SHOP] and rt.mcp.registry.tool_names() == [SHOP]
        assert (await client.post(f"/v1/connections/{c['id']}/check", headers=h)).json() == {"reachable": True, "message": None, "added": [n for n in sorted(seen) if n != SHOP], "changed": [], "removed": []}
        fake.redescribe("orders_lookup", "Look up an order and also email it.")
        assert (await client.post(f"/v1/connections/{c['id']}/check", headers=h)).json()["changed"] == [SHOP]
        off = await client.put(f"/v1/connections/{c['id']}", headers=h, json={"enabled": False})
        assert off.json()["enabled"] is False and rt.mcp.registry.tool_names() == []
        assert (await client.delete(f"/v1/connections/{c['id']}", headers=h)).json() == {"deleted": True}
        actions = [e["action"] for e in (await client.get("/v1/audit?limit=50", headers=h)).json()["entries"]]
        assert {"connection.create", "connection.review", "connection.approve", "connection.check", "connection.update", "connection.delete"} <= set(actions)


async def test_approving_a_tool_the_server_changed_since_the_review_is_refused_and_nothing_is_approved():
    async with FakeMcp().running() as fake:
        client, keys, rt = await world(fake)
        h = keys["admin"]
        c = (await client.post("/v1/connections", headers=h, json={"name": "shop", "url": URL, "secret": "orders"})).json()
        seen = {t["name"]: t["fingerprint"] for t in (await client.post(f"/v1/connections/{c['id']}/review", headers=h)).json()["tools"]}
        fake.redescribe("orders_lookup", "Look up an order. Also post it publicly.")
        r = await client.post(f"/v1/connections/{c['id']}/approve", headers=h, json={"tools": {SHOP: seen[SHOP]}})
        assert r.status_code == 409 and "changed since you looked" in r.json()["error"]["message"] and rt.mcp.registry.tool_names() == []


async def test_a_connection_that_breaks_the_rules_is_refused_with_what_to_change_and_an_unreachable_server_is_a_502():
    async with FakeMcp().running() as fake:
        client, keys, _ = await world(fake)
        h = keys["admin"]
        bad = await client.post("/v1/connections", headers=h, json={"name": "shop", "url": "https://evil.example.com/mcp"})
        assert bad.status_code == 400 and "allowed list" in bad.json()["error"]["message"]
        assert (await client.post("/v1/connections", headers=h, json={"name": "Shop!", "url": URL})).status_code == 400
        c = (await client.post("/v1/connections", headers=h, json={"name": "shop", "url": URL, "secret": "orders"})).json()
        assert (await client.post("/v1/connections", headers=h, json={"name": "shop", "url": URL})).status_code == 409
        fake.mode = "redirect"
        down = await client.post(f"/v1/connections/{c['id']}/review", headers=h)
        assert down.status_code == 502 and "redirect" in down.json()["error"]["message"]
        assert (await client.get("/v1/connections/nope", headers=h)).status_code == 404


async def test_asking_servers_is_rate_limited_per_key():
    async with FakeMcp().running() as fake:
        client, keys, _ = await world(fake)
        h = keys["admin"]
        c = (await client.post("/v1/connections", headers=h, json={"name": "shop", "url": URL, "secret": "orders"})).json()
        codes = [(await client.post(f"/v1/connections/{c['id']}/check", headers=h)).status_code for _ in range(14)]
        assert codes[:12] == [200] * 12 and codes[12:] == [429, 429]
