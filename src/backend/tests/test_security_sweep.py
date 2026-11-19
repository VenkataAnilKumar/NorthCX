"""A sweep over every route the app has: no route may be reachable by someone who should not reach it."""
import asyncio
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl, ROLES
from northcx.knowledge import InMemoryKnowledge
from northcx.llm import ScriptedLLM
from northcx.regression import RegressionRunner
from northcx.runtime import Runtime
from northcx.server import PUBLIC_ROUTES, ROUTE_PERMISSIONS, create_app
from northcx.simulation import InMemorySimRuns, SimulationService
from northcx.store import InMemoryStore
from northcx.templates import LIBRARY, load_templates
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

KEY = "boot" * 10
# The only /v1 routes a customer's chat token may use (/v1/me just describes the caller's own identity).
TOKEN_ROUTES = {("GET", "/v1/me"), ("POST", "/v1/me/logout"), ("PUT", "/v1/sessions/x/attachments"), ("POST", "/v1/sessions/x/feedback"), ("POST", "/v1/agents/x/chat"), ("POST", "/v1/agents/x/chat/stream"), ("POST", "/v1/agents/x/agui"), ("GET", "/v1/sessions/x/outbox")}
OUTSIDE_V1_PUBLIC = {("POST", "/channels/sms/twilio"), ("POST", "/channels/whatsapp/meta"), ("GET", "/channels/whatsapp/meta"), ("POST", "/channels/telegram/webhook"), ("GET", "/auth/sso/config"), ("GET", "/auth/sso/login"), ("GET", "/auth/sso/callback"), ("GET", "/sdk/northcx-widget.js"), ("GET", "/sdk/northcx-client.js")}  # authenticated by the provider's signature instead


def build():
    r = registry()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    sim = SimulationService([], lambda a, l: None, InMemorySimRuns(), {})
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, {}, sim)
    ac = AccessControl(bootstrap_key=KEY)
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc, simulations=sim, knowledge=InMemoryKnowledge(),
                     regression=RegressionRunner(sim, rt.monitor.repo), skills=r.skill_info(), templates=load_templates(LIBRARY))
    return TestClient(app, raise_server_exceptions=False), ac, app


def routes(app):
    out = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            path = re.sub(r"\{[^}]+\}", "x", r.path)
            for m in r.methods - {"HEAD", "OPTIONS"}:
                out.append((m, path))
    return sorted(set(out))


def test_the_sweep_sees_every_route():
    c, ac, app = build()
    rs = routes(app)
    assert len(rs) > 60 and ("POST", "/v1/agents/x/chat") in rs and ("GET", "/v1/privacy/customers/x/export") in rs


def test_nothing_under_v1_works_without_credentials():
    c, ac, app = build()
    leaks = []
    for m, path in routes(app):
        if (m, path) in PUBLIC_ROUTES or (m, path) in OUTSIDE_V1_PUBLIC or not path.startswith("/v1/"):
            continue
        r = c.request(m, path, json={} if m != "GET" else None)
        if r.status_code not in (401, 404):
            leaks.append((m, path, r.status_code))
    assert leaks == []


def test_every_v1_route_has_a_permission_and_no_unlisted_route_is_served():
    c, ac, app = build()
    from northcx.server import permission_for
    missing = [(m, p) for m, p in routes(app) if p.startswith("/v1/") and permission_for(m, p) is None]
    assert missing == []
    r = c.get("/v1/definitely/not/a/route", headers={"authorization": f"Bearer {KEY}"})
    assert r.status_code == 404


def test_a_customers_chat_token_reaches_only_its_own_conversation_routes():
    c, ac, app = build()
    token = c.post("/v1/chat-tokens", json={"sessionId": "w1", "customerId": "c1"}, headers={"authorization": f"Bearer {KEY}"}).json()["token"]
    h = {"authorization": f"Bearer {token}"}
    reached = []
    for m, path in routes(app):
        if not path.startswith("/v1/") or (m, path) in PUBLIC_ROUTES:
            continue
        r = c.request(m, path, json={} if m != "GET" else None, headers=h)
        if r.status_code != 403:
            reached.append((m, path))
    assert set(reached) <= TOKEN_ROUTES, sorted(set(reached) - TOKEN_ROUTES)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_each_role_reaches_exactly_the_routes_its_permissions_allow(role):
    c, ac, app = build()
    key = asyncio.new_event_loop().run_until_complete(ac.issue(role, role, "root"))[1]
    from northcx.server import permission_for
    wrong = []
    for m, path in routes(app):
        if not path.startswith("/v1/") or (m, path) in PUBLIC_ROUTES:
            continue
        perm = permission_for(m, path)
        r = c.request(m, path, json={} if m != "GET" else None, headers={"authorization": f"Bearer {key}"})
        allowed = perm == "authenticated" or perm in ROLES[role]
        # A route that needs a stricter permission inside its handler (production releases) may still say 403 for an allowed role.
        if allowed and r.status_code == 403 and not (m == "POST" and re.search(r"/(releases|rollback|promote)$", path)):
            wrong.append((m, path, "denied but allowed"))
        if not allowed and r.status_code != 403:
            wrong.append((m, path, f"reached with {r.status_code}"))
    assert wrong == [], wrong


def test_the_demo_page_and_health_checks_are_the_only_public_pages():
    assert PUBLIC_ROUTES == {("GET", "/"), ("GET", "/health"), ("GET", "/ready")}
    c, ac, app = build()
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404
