"""WP3.1: keys limited to agents and environments. The sweep is generated from the route table, so a new route cannot forget the rule."""
import re

import pytest
from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute

from northcx.access import AccessControl
from route_snapshot import build_app, example_path

BOOT = {"authorization": "Bearer " + "boot" * 10}


@pytest.fixture(scope="module")
def stack():
    app = build_app()
    c = TestClient(app)
    def mint(**body):
        r = c.post("/v1/keys", headers=BOOT, json={"role": "developer", **body})
        assert r.status_code == 201, r.text
        return {"authorization": "Bearer " + r.json()["key"]}
    return app, c, mint


def test_keys_can_be_limited_and_the_limits_are_listed(stack):
    app, c, mint = stack
    h = mint(name="support-only", agents=["support"], environments=["dev", "staging"])
    me = c.get("/v1/me", headers=h).json()
    assert me["agents"] == ["support"] and me["environments"] == ["dev", "staging"]
    listed = [k for k in c.get("/v1/keys", headers=BOOT).json()["keys"] if k["name"] == "support-only"][0]
    assert listed["agents"] == ["support"] and listed["environments"] == ["dev", "staging"]
    assert c.get("/v1/me", headers=BOOT).json()["agents"] is None  # an ordinary key has no limit


@pytest.mark.parametrize("body,why", [
    ({"agents": []}, "1 to 50"), ({"agents": ["a", "a"]}, "different"), ({"agents": ["bad name!"]}, "agent ids"),
    ({"environments": ["moon"]}, "environments must be from"), ({"environments": []}, "1 to 50"),
    ({"role": "admin", "agents": ["support"]}, "cannot be limited"), ({"role": "channel", "environments": ["dev"]}, "cannot be limited"),
])
def test_bad_limits_are_refused_with_a_reason(stack, body, why):
    _, c, _ = stack
    r = c.post("/v1/keys", headers=BOOT, json={"name": "x" + str(abs(hash(str(body)))), "role": "developer", **body})
    assert r.status_code == 400 and why in r.json()["error"]["message"], r.text


def test_the_sweep_every_route_refuses_a_key_limited_to_another_agent(stack):
    app, c, mint = stack
    h = mint(name="sweep-support", agents=["support"])
    checked_other = checked_agentless = checked_own = 0
    for r in app.router.routes:
        if isinstance(r, WebSocketRoute) or not r.path.startswith("/v1/"):
            continue
        for method in sorted(r.methods - {"HEAD", "OPTIONS"}):
            if (method, r.path) in {("GET", "/v1/me"), ("GET", "/v1/agents"), ("POST", "/v1/me/logout")}:
                continue
            in_path = "/v1/agents/{agent_id}" in r.path
            # a different agent in the path, or no agent in the path at all: both must be refused for being out of scope
            path = example_path(r.path.replace("{agent_id}", "other"))
            res = c.request(method, path, headers=h, json={})
            msg = res.text
            assert res.status_code == 403 and "This key is limited" in msg, f"{method} {r.path} was not refused for scope: {res.status_code} {msg[:120]}"
            checked_other += in_path
            checked_agentless += not in_path
            if in_path:  # its own agent is never refused for scope (it may fail for other reasons)
                own = c.request(method, example_path(r.path.replace("{agent_id}", "support")), headers=h, json={})
                assert "This key is limited" not in own.text, f"{method} {r.path} refused the key's own agent"
                checked_own += 1
    assert checked_other > 20 and checked_agentless > 60 and checked_own == checked_other


def test_the_agent_list_shows_only_what_the_key_may_reach(stack):
    app, c, mint = stack
    assert [a["id"] for a in c.get("/v1/agents", headers=mint(name="list-support", agents=["support"])).json()["agents"]] == ["support"]
    assert c.get("/v1/agents", headers=mint(name="list-none", agents=["nobody"])).json()["agents"] == []
    assert [a["id"] for a in c.get("/v1/agents", headers=BOOT).json()["agents"]] == ["support"]


def test_environment_limits_apply_to_queries_and_chat(stack):
    app, c, mint = stack
    h = mint(name="staging-only", environments=["staging"])
    r = c.get("/v1/insights/overview?environment=production", headers=h)
    assert r.status_code == 403 and "limited to the staging" in r.text
    assert "limited" not in c.get("/v1/insights/overview?environment=staging", headers=h).text
    r = c.post("/v1/agents/support/chat", headers=h, json={"sessionId": "s1", "message": "hi"})  # defaults to production
    assert r.status_code == 403 and "limited to the staging" in r.text
    h2 = mint(name="both", agents=["support"], environments=["dev"])
    assert c.post("/v1/agents/other/chat", headers=h2, json={"sessionId": "s", "message": "hi", "environment": "dev"}).status_code == 403


async def test_scope_survives_the_database(engine):
    from northcx.db import PgKeys
    ac = AccessControl(keys=PgKeys(engine))
    key, secret = await ac.issue("scoped", "developer", "t", agents=["support"], environments=["dev"])
    who = await AccessControl(keys=PgKeys(engine)).authenticate(secret)
    assert who.scope_agents == ("support",) and who.scope_envs == ("dev",) and who.allows_agent("support") and not who.allows_agent("x") and not who.allows_env("production")
    _, plain = await ac.issue("plain", "developer", "t")
    assert (await ac.authenticate(plain)).scope_agents is None
