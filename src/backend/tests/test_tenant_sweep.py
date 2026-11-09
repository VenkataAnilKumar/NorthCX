"""WP2.9: the isolation sweep over the whole route table.

The real server is assembled the way `python -m northcx` assembles it (database, row-level security, every router), with two tenants.
Tenant A's administrator creates something on every feature that stores data and leaves a marker in it. Then tenant B's administrator calls
EVERY route the server has, with A's real ids filled in wherever a route takes one. No route may crash, nothing of A's may appear in any answer, and afterwards
A's own data must be exactly as it was. A route added later is covered automatically, because the sweep reads the routes from the app.
"""
import json
import os
import re
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

MARK = "ACMEMARKER"
CUSTOMER = "amy.acme@example.com"          # the customer of tenant A; the identifier alone must not reveal anything to tenant B (an answer may repeat what the caller typed)


@pytest.fixture
def sweep_app(engine, db_url, app_engine, monkeypatch):
    """The whole server over a database, running as an ordinary role, with two tenants."""
    from northcx import bootstrap
    from northcx.bootstrap import app as appmod
    host = urlsplit(db_url).netloc.rsplit("@", 1)[-1]
    app_url = urlunsplit(("postgresql", f"northcx_app_test:app-test-pw@{host}", urlsplit(db_url).path, "", ""))
    for k in [k for k in os.environ if k.startswith("NORTHCX_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("NORTHCX_DEMO", "1")
    monkeypatch.setenv("NORTHCX_API_KEY", "k" * 32)
    monkeypatch.setenv("NORTHCX_DATABASE_URL", app_url)
    monkeypatch.setenv("NORTHCX_MIGRATION_DATABASE_URL", db_url.replace("+asyncpg", ""))
    monkeypatch.setenv("NORTHCX_TENANCY_PREVIEW", "1")
    monkeypatch.setenv("NORTHCX_RATE_LIMITS", "off")            # the sweep makes hundreds of calls; a throttled answer would hide what the route does
    monkeypatch.setenv("NORTHCX_ROLE", "api")                  # no background jobs: the sweep is about requests
    c = SimpleNamespace()
    for step in bootstrap.STEPS:
        step(c)
    web = appmod.build_app(c)
    with TestClient(web) as client:                           # one event loop for the server and for the setup below, as in a real process
        call = client.portal.call
        for tid, name in (("acme", "Acme"), ("globex", "Globex")):
            try:
                call(c.access.tenants.create, tid, name)
            except Exception:  # noqa: BLE001 - left over from an earlier test in the same database: the tables were emptied, the tenant list is not
                pass
        admin = lambda tenant: {"authorization": "Bearer " + call(lambda: c.access.issue(f"{tenant}-admin", "admin", "t", tenant_id=tenant))[1]}  # noqa: E731
        yield SimpleNamespace(web=web, client=client, A=admin("acme"), B=admin("globex"), c=c)


def seed(w) -> dict[str, str]:
    """Tenant A creates data on every feature that keeps any. Returns the ids a route might take."""
    c, A = w.client, w.A
    ids: dict[str, str] = {}

    def ok(r, what):
        assert r.status_code in (200, 201, 202), f"seeding {what}: {r.status_code} {r.text[:200]}"
        return r.json()
    # a conversation, a hand-off, a rating, a customer
    tok = ok(c.post("/v1/chat-tokens", headers=A, json={"sessionId": "web-a", "customerId": CUSTOMER}), "token")["token"]
    chat = ok(c.post("/v1/agents/support/chat", headers={"authorization": f"Bearer {tok}"}, json={"sessionId": "web-a", "message": f"I want a person please {MARK} order ORD-77123"}), "chat")
    ids["session_id"], ids["trace_id"] = "web-a", chat["traceId"]
    ids["handoff_id"] = chat.get("handoffId") or ""
    c.post("/v1/sessions/web-a/feedback", headers={"authorization": f"Bearer {tok}"}, json={"rating": 5, "comment": MARK})
    # outputs, spaces
    ids["space_id"] = ok(c.post("/v1/workspace/spaces", headers=A, json={"name": f"{MARK} space", "instructions": MARK, "visibility": "shared"}), "space")["id"]
    ok(c.post(f"/v1/workspace/spaces/{ids['space_id']}/files", headers=A, json={"name": "acme-notes.txt", "text": MARK + " file text"}), "space file")
    ids["output_id"] = ok(c.post("/v1/workspace/outputs", headers=A, json={"title": f"{MARK} output", "body": MARK + " body", "visibility": "shared", "spaceId": ids["space_id"]}), "output")["id"]
    ids["item_id"] = ok(c.post("/v1/workspace/library-items", headers=A, json={"title": f"{MARK} macro", "body": MARK + " reply text", "kind": "macro", "visibility": "shared"}), "library item")["id"]
    # customers
    ok(c.post("/v1/customers/notes", headers=A, json={"customerId": CUSTOMER, "note": f"{MARK} staff note about the customer"}), "customer note")
    # policies, templates, automations, quality
    pol = {"name": f"{MARK} limit", "policy": "tool_limit", "config": {"tool": "issue_refund", "field": "amount", "max": 50},
           "cases": [{"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 40}}, "expected": "allowed"}, {"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 60}}, "expected": "blocked"}]}
    ids["policy_id"] = ok(c.post("/v1/org-policies", headers=A, json=pol), "policy")["id"]
    tpl = {"id": "acme-only", "title": f"{MARK} template", "description": "d", "intent": "i", "spec": {"instructions": MARK, "tools": []},
           "scenarios": [{"name": "{{agent_id}}-x", "model": [{"text": "hi"}], "turns": [{"say": "hi", "expect": {"status": "completed"}}]}]}
    ids["template_id"] = ok(c.post("/v1/org-templates", headers=A, json={"template": tpl}), "template")["id"]
    ids["automation_id"] = ok(c.post("/v1/automations", headers=A, json={"definition": {"id": "acme-routine", "name": f"{MARK} routine", "trigger": {"type": "manual"},
                              "steps": [{"id": "r", "kind": "report", "report": "performance", "days": 1}]}}), "automation")["id"]
    ids["note_id"] = ok(c.post("/v1/quality/coaching", headers=A, json={"sessionId": "web-a", "about": "rae", "note": f"{MARK} coaching note here"}), "coaching")["id"]
    ok(c.put("/v1/quality/rubric", headers=A, json={"criteria": [{"id": "e", "label": f"{MARK} no error", "weight": 1, "check": "no_errors"}], "passMark": 80, "sample": 0.5}), "rubric")
    # a key and a group
    made = ok(c.post("/v1/keys", headers=A, json={"name": f"{MARK}-key", "role": "viewer"}), "key")
    ids["key_id"] = made["key"]["id"] if isinstance(made.get("key"), dict) else made.get("id", "")
    ok(c.put("/v1/budgets", headers=A, json={"dailyTokenLimit": 123456}), "budget")
    return ids


def routes(web):
    for r in web.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path and methods and path.startswith("/v1/"):
            for m in sorted(methods - {"HEAD", "OPTIONS"}):
                yield m, path


def fill(path: str, ids: dict[str, str]) -> str:
    def one(m: re.Match) -> str:
        name = m.group(1).split(":")[0]
        if name in ids and ids[name]:
            return ids[name]
        if name.endswith("customer_id"):
            return CUSTOMER
        return {"agent_id": "support", "policy_id": ids["policy_id"], "template_id": ids["template_id"], "automation_id": ids["automation_id"], "space_id": ids["space_id"],
                "output_id": ids["output_id"], "item_id": ids["item_id"], "session_id": ids["session_id"], "note_id": ids["note_id"], "run_id": "run-x"}.get(name, "x")
    return re.sub(r"\{([^}]+)\}", one, path)


def snapshot_a(w, ids) -> dict[str, str]:
    """What A sees, route by route, for the reads that matter."""
    c, A = w.client, w.A
    paths = ["/v1/workspace/outputs", f"/v1/workspace/outputs/{ids['output_id']}", "/v1/workspace/library-items", f"/v1/workspace/library-items/{ids['item_id']}", "/v1/workspace/spaces", f"/v1/workspace/spaces/{ids['space_id']}", "/v1/org-policies", "/v1/org-templates",
             "/v1/automations", f"/v1/automations/{ids['automation_id']}", "/v1/quality/coaching", "/v1/quality/rubric", f"/v1/traces/{ids['trace_id']}", "/v1/sessions/web-a/transcript",
             f"/v1/privacy/customers/{MARK}@example.com/export"]
    out = {}
    for p in paths:
        r = c.get(p, headers=A)
        assert r.status_code == 200, f"A cannot read its own {p}: {r.status_code}"
        out[p] = json.dumps(r.json(), sort_keys=True)
    out["lookup"] = json.dumps(c.post("/v1/customers/lookup", headers=A, json={"customerId": CUSTOMER}).json()["notes"], sort_keys=True)
    out["budget"] = json.dumps(c.get("/v1/models/overview", headers=A).json().get("budget"), sort_keys=True) if c.get("/v1/models/overview", headers=A).status_code == 200 else ""
    return out


def volatile(text: str) -> str:
    return re.sub(r'"(updatedAt|nextRun|lastRun|ranAt|checkedAt|generatedAt|expiresAt)": [0-9.]+', r'"\1": 0', text)


def test_tenant_b_cannot_reach_tenant_a_through_any_route(sweep_app):
    w = sweep_app
    ids = seed(w)
    before = {k: volatile(v) for k, v in snapshot_a(w, ids).items()}
    leaks, crashes, count = [], [], 0
    needles = [MARK.lower(), ids["item_id"], ids["output_id"], ids["space_id"], ids["policy_id"], ids["trace_id"], ids["automation_id"]]
    for method, path in routes(w.web):
        url = fill(path, ids)
        count += 1
        kwargs: dict = {"headers": w.B}
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            kwargs["json"] = {}
        try:
            r = w.client.request(method, url, **kwargs)
        except Exception as e:  # noqa: BLE001
            crashes.append((method, path, repr(e)[:150]))
            continue
        if r.status_code >= 500 and r.status_code != 501:          # 501 is "not set up on this server", an honest answer
            crashes.append((method, path, r.status_code))
        body = r.text.lower()
        for n in needles:
            if n and n.lower() in body:
                leaks.append((method, path, r.status_code, n))
    assert count > 150, "the sweep read too few routes"
    assert not crashes, crashes
    assert not leaks, leaks
    after = {k: volatile(v) for k, v in snapshot_a(w, ids).items()}
    assert after == before, [k for k in before if before[k] != after[k]]
    # and A, with its own key, can still do the same things
    assert w.client.get(f"/v1/workspace/outputs/{ids['output_id']}", headers=w.A).status_code == 200


def test_every_route_refuses_a_caller_with_no_key(sweep_app):
    w = sweep_app
    ids = seed(w)
    open_routes = []
    for method, path in routes(w.web):
        kwargs: dict = {}
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            kwargs["json"] = {}
        r = w.client.request(method, fill(path, ids), **kwargs)
        if r.status_code not in (401, 403, 404, 405) and (method, path) not in OPEN_BY_DESIGN:
            open_routes.append((method, path, r.status_code))
    assert not open_routes, open_routes


# Routes that answer without a key on purpose: they carry their own check (a signature, a one-time code) or are public.
OPEN_BY_DESIGN: set[tuple[str, str]] = set()


def test_every_route_the_server_has_is_in_the_permission_table(sweep_app):
    """A route missing from the table is refused with 404 for everyone, so the sweep above could pass without ever reaching its code. This keeps that from hiding a route."""
    from northcx.server import permission_for
    ids = {k: "x" for k in ("session_id", "trace_id", "handoff_id", "space_id", "output_id", "policy_id", "template_id", "automation_id", "note_id", "key_id", "item_id")}
    missing = [(m, p) for m, p in routes(sweep_app.web) if permission_for(m, fill(p, ids)) is None]
    assert not missing, missing


async def test_a_chat_token_belongs_to_the_tenant_of_the_key_that_minted_it():
    """Found by the sweep: a token minted by a tenant's key used to open its conversation in the default tenant."""
    from northcx.access import AccessControl
    from northcx.tokens import TokenSigner
    ac = AccessControl(bootstrap_key="boot" * 10, signer=TokenSigner(b"s" * 32))
    key, _ = await ac.issue("acme-channel", "channel", "t", tenant_id="acme")
    token, _ = ac.signer.mint(sid="web-1", kid=key.key_id, cid="c1")
    who = await ac.authenticate(token)
    assert who is not None and who.role == "customer_session" and who.tenant == "acme"
    boot, _ = ac.signer.mint(sid="web-2", kid="bootstrap", cid="c1")
    assert (await ac.authenticate(boot)).tenant == "default"
