"""Environments (dev, staging, production), promotion, per-environment serving and who may use them."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.inbox import InboxDispatcher, InMemoryInbox
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.trace_export import convert, Redactor
from northcx.versions import (Conflict, GateBlocked, InMemoryReleases, InMemoryVersions, NotFound, check_environment)
from tests.test_versions import Env, SPECS, build_agent


@pytest.fixture(params=["memory", "postgres"])
def env(request):
    if request.param == "memory":
        return Env(InMemoryVersions(), InMemoryReleases())
    from northcx.db import PgReleases, PgSimRuns, PgVersions
    eng = request.getfixturevalue("engine")
    return Env(PgVersions(eng), PgReleases(eng), PgSimRuns(eng))


async def proven(env, **changes):
    v = await env.new_version(**changes)
    await env.prove(v)
    return v


def test_environment_names():
    assert check_environment("staging") == "staging"
    for bad in ["prod", "", "Production", "qa"]:
        with pytest.raises(ValueError):
            check_environment(bad)


async def test_dev_needs_no_proof_but_staging_and_production_do(env):
    v = await env.new_version(max_steps=9)  # never simulated
    r = await env.svc.publish("support", v.number, "dev-user", environment="dev")
    assert r.environment == "dev" and r.gate["satisfied"] is None
    for target in ("staging", "production"):
        with pytest.raises(GateBlocked):
            await env.svc.publish("support", v.number, "dev-user", environment=target)
    await env.prove(v)
    assert (await env.svc.publish("support", v.number, "rm", environment="staging")).environment == "staging"
    assert (await env.svc.publish("support", v.number, "rm")).environment == "production"


async def test_each_environment_has_its_own_history_and_rollback(env):
    a, b = await proven(env), await proven(env, max_steps=9)
    for number in (a.number, b.number):
        await env.svc.publish("support", number, "x", environment="staging")
    await env.svc.publish("support", a.number, "x")
    assert (await env.svc.live("support", "staging"))[0].number == b.number and (await env.svc.live("support"))[0].number == a.number
    assert (await env.svc.live("support", "dev"))[1] is None
    rb = await env.svc.rollback("support", "x", environment="staging")
    assert rb.environment == "staging" and rb.number == a.number and (await env.svc.live("support"))[0].number == a.number
    assert [r.environment for r in await env.svc.releases.list("support", "staging")] == ["staging"] * 3
    with pytest.raises(Conflict, match="Nothing has been released"):
        await env.svc.rollback("support", "x", environment="dev")
    with pytest.raises(Conflict, match="already live in staging"):
        await env.svc.publish("support", a.number, "x", environment="staging")


async def test_promotion_moves_the_version_from_the_previous_environment(env):
    v = await proven(env)
    with pytest.raises(Conflict, match="Nothing is released in dev"):
        await env.svc.promote("support", "staging", "x")
    await env.svc.publish("support", v.number, "x", environment="dev")
    r = await env.svc.promote("support", "staging", "x")
    assert r.environment == "staging" and r.number == v.number and r.note == "promoted from dev"
    r2 = await env.svc.promote("support", "production", "x", "go")
    assert r2.environment == "production" and r2.note == "go" and r2.previous_number is None
    with pytest.raises(Conflict, match="Nothing is promoted into dev"):
        await env.svc.promote("support", "dev", "x")
    with pytest.raises(Conflict, match="already live in production"):
        await env.svc.promote("support", "production", "x")
    unproven = await env.new_version(max_steps=7)
    await env.svc.publish("support", unproven.number, "x", environment="dev")
    with pytest.raises(GateBlocked):
        await env.svc.promote("support", "staging", "x")  # promotion is gated like any release


async def test_promoting_the_baseline_is_refused_with_advice(env):
    from northcx.versions import Release
    await env.svc.releases.add(Release("support", "rollback", "x", None, None, {}, None, None, "dev"))
    with pytest.raises(Conflict, match="baseline spec file"):
        await env.svc.promote("support", "staging", "x")


async def test_strict_promotion_requires_staging_first(env):
    env.svc.strict_promotion = True
    v = await proven(env)
    with pytest.raises(GateBlocked, match="not been live in staging"):
        await env.svc.publish("support", v.number, "x")
    await env.svc.publish("support", v.number, "x", environment="staging")
    assert (await env.svc.publish("support", v.number, "x")).environment == "production"
    v2 = await proven(env, max_steps=9)
    await env.svc.publish("support", v2.number, "x", environment="staging")
    await env.svc.publish("support", v.number, "x", environment="staging")  # staging moved on; v2 was still staged once
    assert (await env.svc.publish("support", v2.number, "x")).number == v2.number


async def test_an_environment_without_a_release_serves_the_next_one_up(env):
    v = await proven(env)
    assert (await env.svc.resolve("support", "dev"))[2:] == ("production",) and (await env.svc.resolve("support", "dev"))[1] is None  # baseline everywhere
    assert (await env.live.get("support", "staging")).version is None
    await env.svc.publish("support", v.number, "x", environment="staging")
    assert (await env.live.get("support", "dev")).version == v.number  # dev -> staging
    assert (await env.live.get("support")).version is None  # production is untouched: still the baseline
    w = await proven(env, max_steps=9)
    await env.svc.publish("support", w.number, "x", environment="dev")
    assert (await env.live.get("support", "dev")).version == w.number and (await env.live.get("support", "staging")).version == v.number
    _, _, served = await env.svc.resolve("support", "staging")
    assert served == "staging"
    with pytest.raises(ValueError):
        await env.live.get("support", "qa")


# ---- through the API ----
KEY = "boot" * 10


def H(k=KEY):
    return {"authorization": f"Bearer {k}"}


@pytest.fixture
def api():
    e = Env(InMemoryVersions(), InMemoryReleases())
    llm = ScriptedLLM([text("from whichever agent")] * 10)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    app = create_app(rt, rt.traces, e.live, access=ac, releases=e.svc, simulations=e.sim)
    return TestClient(app), ac, e, rt


def key(ac, role):
    return asyncio.new_event_loop().run_until_complete(ac.issue(role, role, "root"))[1]


def test_who_may_release_where(api):
    c, ac, e, rt = api
    loop = asyncio.new_event_loop()
    v = loop.run_until_complete(e.new_version())
    dev, rm, viewer = key(ac, "developer"), key(ac, "release_manager"), key(ac, "viewer")
    ok = c.post("/v1/agents/support/releases", json={"version": v.number, "environment": "dev"}, headers=H(dev))
    assert ok.status_code == 200 and ok.json()["environment"] == "dev"
    r = c.post("/v1/agents/support/releases", json={"version": v.number}, headers=H(dev))
    assert r.status_code == 403 and "releases:publish" in r.json()["error"]["message"]
    r = c.post("/v1/agents/support/promote", json={"to": "production"}, headers=H(dev))
    assert r.status_code == 403 and "releases:publish" in r.json()["error"]["message"]
    r = c.post("/v1/agents/support/rollback", json={}, headers=H(dev))
    assert r.status_code == 403 and "releases:rollback" in r.json()["error"]["message"]
    assert c.post("/v1/agents/support/releases", json={"version": v.number, "environment": "dev"}, headers=H(viewer)).status_code == 403
    assert c.post("/v1/agents/support/releases", json={"version": v.number, "environment": "qa"}, headers=H(rm)).status_code == 400
    assert c.post("/v1/agents/support/promote", json={"to": "qa"}, headers=H(rm)).status_code == 400
    blocked = c.post("/v1/agents/support/promote", json={"to": "staging"}, headers=H(dev))
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "gate_not_satisfied"
    loop.run_until_complete(e.prove(v))
    assert c.post("/v1/agents/support/promote", json={"to": "staging", "note": "ok"}, headers=H(dev)).json()["environment"] == "staging"
    assert c.post("/v1/agents/support/promote", json={"to": "production"}, headers=H(rm)).json()["environment"] == "production"
    entries = c.get("/v1/audit?limit=50", headers=H()).json()["entries"]
    assert {"release.publish", "release.promote", "auth.denied"} <= {x["action"] for x in entries}
    assert any(x["action"] == "release.promote" and x["detail"].get("environment") == "production" for x in entries)


def test_environments_endpoint_history_and_live(api):
    c, ac, e, rt = api
    loop = asyncio.new_event_loop()
    v = loop.run_until_complete(e.new_version())
    loop.run_until_complete(e.prove(v))
    c.post("/v1/agents/support/releases", json={"version": v.number, "environment": "staging"}, headers=H())
    d = c.get("/v1/agents/support/environments", headers=H()).json()
    envs = d["environments"]
    assert d["strictPromotion"] is False and envs["staging"]["version"] == v.number and envs["production"]["version"] is None
    assert envs["dev"]["servedFrom"] == "staging" and envs["dev"]["servedVersion"] == v.number and envs["production"]["servedFrom"] == "production"
    assert [r["environment"] for r in c.get("/v1/agents/support/releases?environment=staging", headers=H()).json()["releases"]] == ["staging"]
    assert c.get("/v1/agents/support/releases", headers=H()).json()["releases"] == []
    assert c.get("/v1/agents/support/releases?environment=qa", headers=H()).status_code == 400
    live = c.get("/v1/agents/support/live?environment=dev", headers=H()).json()
    assert live["version"] == v.number and live["servedFrom"] == "staging" and live["environment"] == "dev"
    assert c.get("/v1/agents/support/live", headers=H()).json()["source"] == "baseline"
    assert c.get("/v1/agents/nope/environments", headers=H()).status_code == 404


def test_chat_in_another_environment_is_for_developers_and_is_recorded(api):
    c, ac, e, rt = api
    loop = asyncio.new_event_loop()
    v = loop.run_until_complete(e.new_version(max_steps=9))
    c.post("/v1/agents/support/releases", json={"version": v.number, "environment": "dev"}, headers=H())
    dev, chan, viewer = key(ac, "developer"), key(ac, "channel"), key(ac, "viewer")
    token = c.post("/v1/chat-tokens", json={"sessionId": "web-1"}, headers=H()).json()["token"]
    body = {"sessionId": "s1", "message": "hi", "environment": "dev"}
    r = c.post("/v1/agents/support/chat", json=body, headers=H(dev))
    assert r.status_code == 200 and r.json()["agentVersion"] == v.number
    trace = c.get(f"/v1/traces/{r.json()['traceId']}", headers=H()).json()
    assert trace["environment"] == "dev"
    prod = c.post("/v1/agents/support/chat", json={"sessionId": "s2", "message": "hi"}, headers=H(dev)).json()
    assert prod["agentVersion"] is None and c.get(f"/v1/traces/{prod['traceId']}", headers=H()).json()["environment"] == "production"
    for who in (chan, token, viewer):
        assert c.post("/v1/agents/support/chat", json={**body, "sessionId": "web-1"}, headers=H(who)).status_code == 403
        assert c.post("/v1/agents/support/chat/stream", json={**body, "sessionId": "web-1"}, headers=H(who)).status_code == 403
    assert c.post("/v1/agents/support/chat", json={**body, "environment": "production"}, headers=H(chan)).status_code == 200
    assert c.post("/v1/agents/support/chat", json={**body, "environment": "qa"}, headers=H(dev)).status_code == 400
    s = c.post("/v1/agents/support/chat/stream", json={"sessionId": "s3", "message": "hi", "environment": "dev"}, headers=H(dev))
    assert s.status_code == 200 and f'"agentVersion": {v.number}' in s.text
    listing = c.get("/v1/traces", headers=H()).json()["traces"]
    assert {t["environment"] for t in listing} == {"dev", "production"}


def test_idempotency_keys_do_not_mix_environments(api):
    c, ac, e, rt = api
    h = {**H(), "idempotency-key": "k1"}
    a = c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "hi"}, headers=h)
    b = c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "hi", "environment": "dev"}, headers=h)
    assert a.status_code == 200 and b.status_code == 422 and b.json()["error"]["code"] == "idempotency_key_reused"


async def test_non_production_conversations_do_not_reach_the_helpdesk_and_exports_are_labelled():
    repo = InMemoryInbox()

    class Fake:
        name = "f"

        async def created(self, h):
            return "r"

        async def resolved(self, h, ref):
            return None

    rt = Runtime(ScriptedLLM([tool_call("handoff_to_human", {"reason": "x"}, "t1")] * 2), InMemoryStore(), TraceStore(), inbox=InboxDispatcher(repo, [Fake()]))
    a = await rt.run(support_agent(), "s1", "person", environment="staging")
    b = await rt.run(support_agent(), "s2", "person")
    assert await repo.for_handoff(a.handoff_id) == [] and len(await repo.for_handoff(b.handoff_id)) == 1
    assert convert(a.trace, Redactor()).environment == "staging" and convert(b.trace, Redactor(), "prod-eu").environment == "prod-eu"


async def test_trace_environment_round_trips_in_postgres(engine):
    from northcx import db
    store = db.PgTraceStore(engine)
    from northcx.trace import Trace
    t = Trace("support", "s1", environment="staging")
    t.add("user", message="hi")
    await store.save(t)
    assert (await store.get(t.id)).environment == "staging" and (await store.summaries("s1"))[0].environment == "staging"
