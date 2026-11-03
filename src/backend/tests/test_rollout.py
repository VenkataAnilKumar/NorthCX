"""Staged rollouts (Q11): sticky arms, frozen releases while running, promote/abort, comparison, API, permissions, erasure."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from northcx.access import AccessControl
from northcx.insights import FeedbackFacts, HandoffFacts, TurnFacts
from northcx.llm import ScriptedLLM, text
from northcx.rollout import CANDIDATE, CONTROL, ENOUGH, InMemoryRollouts, Rollout, RolloutService, bucket, check_percent, compare
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import Conflict, GateBlocked, InMemoryReleases, InMemoryVersions, NotFound
from tests.test_versions import Env


def test_bucket_is_stable_and_spreads_evenly():
    assert bucket("r", "s1") == bucket("r", "s1") and bucket("r", "s1") != bucket("r2", "s1")
    share = sum(bucket("r", f"s{i}") < 20 for i in range(5000)) / 5000
    assert 0.17 < share < 0.23
    assert check_percent(1) == 1 and check_percent(99) == 99
    for bad in (0, 100, -5):
        with pytest.raises(ValueError):
            check_percent(bad)


@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        return InMemoryRollouts()
    from northcx.db import PgRollouts
    return PgRollouts(request.getfixturevalue("engine"))


async def test_repository_contract(repo):
    r = Rollout("support", "production", 2, 1, 10, "rae", "n")
    await repo.add(r)
    with pytest.raises(Conflict):
        await repo.add(Rollout("support", "production", 3, 1, 5, "jo"))
    await repo.add(Rollout("support", "staging", 3, None, 5, "jo"))  # another environment is independent
    got = await repo.active("support", "production")
    assert (got.id, got.candidate_number, got.control_number, got.percent, got.note) == (r.id, 2, 1, 10, "n") and await repo.active("other", "production") is None
    assert await repo.assign(r.id, "s1", CANDIDATE) == CANDIDATE and await repo.assign(r.id, "s1", CONTROL) == CANDIDATE  # the first arm sticks
    await repo.assign(r.id, "s2", CONTROL)
    assert await repo.arm_sessions(r.id) == {CONTROL: ["s2"], CANDIDATE: ["s1"]}
    r.percent, r.state, r.ended_by, r.ended_at = 25, "aborted", "rae", 5.0
    await repo.save(r)
    assert await repo.active("support", "production") is None and (await repo.get(r.id)).state == "aborted"
    await repo.add(Rollout("support", "production", 4, 1, 5, "x"))  # a new one may start once the old one ended
    assert len(await repo.history("support")) == 3 and await repo.get("nope") is None
    assert await repo.erase_session("s1") == 1 and await repo.erase_session("s1") == 0


@pytest.fixture
def world():
    e = Env(InMemoryVersions(), InMemoryReleases())
    e.rollouts = RolloutService(InMemoryRollouts(), e.svc)
    e.live.service = e.svc
    return e


async def test_a_rollout_needs_a_proven_candidate_and_freezes_releases(world):
    v1 = await world.new_version()
    with pytest.raises(GateBlocked) as err:
        await world.rollouts.start("support", 1, 10, "rae")
    assert "not run against this agent version" in err.value.reasons[0]
    await world.prove(v1)
    with pytest.raises(ValueError, match="between"):
        await world.rollouts.start("support", 1, 0, "rae")
    with pytest.raises(ValueError, match="staging or production"):
        await world.rollouts.start("support", 1, 10, "rae", "dev")
    with pytest.raises(NotFound):
        await world.rollouts.start("support", 9, 10, "rae")
    r = await world.rollouts.start("support", 1, 10, "rae")
    assert (r.control_number, r.candidate_number, r.state) == (None, 1, "active")  # the baseline is the control
    with pytest.raises(Conflict, match="already running"):
        await world.rollouts.start("support", 1, 20, "rae")
    with pytest.raises(Conflict, match="rollout is running"):
        await world.svc.publish("support", 1, "rel", None)
    cl = await world.svc.checklist("support", 1, "production")
    assert cl["ready"] is False and "no_rollout" in {c["key"] for c in cl["checks"] if c["status"] == "fail"}
    await world.svc.publish("support", 1, "rel", None, "staging")  # other environments are not frozen
    await world.rollouts.abort("support", r.id, "rae")
    with pytest.raises(Conflict, match="already ended"):
        await world.rollouts.abort("support", r.id, "rae")
    await world.svc.publish("support", 1, "rel", None)  # unfrozen


async def test_conversations_keep_their_arm_and_arms_get_different_versions(world):
    v1 = await world.new_version()
    await world.prove(v1)
    live = await world.svc.publish("support", 1, "rel", None)
    v2 = await world.new_version(max_steps=6)
    await world.prove(v2)
    r = await world.rollouts.start("support", 2, 50, "rae")
    assert r.control_number == 1
    seen = {}
    for i in range(60):
        a = await world.live.get("support", "production", f"s{i}")
        seen[f"s{i}"] = a.version
    assert set(seen.values()) == {1, 2} and 15 < sum(v == 2 for v in seen.values()) < 45
    await world.rollouts.set_percent("support", r.id, 95)  # raising the share never moves a conversation that already started
    for sid, version in seen.items():
        assert (await world.live.get("support", "production", sid)).version == version
    assert (await world.live.get("support", "production")).version == 1  # no conversation id: the live version
    assert (await world.live.get("support", "staging", "s1")).version == 1  # a rollout only applies to its own environment
    arms = await world.rollouts.repo.arm_sessions(r.id)
    assert len(arms[CONTROL]) + len(arms[CANDIDATE]) == 60
    done = await world.rollouts.promote("support", r.id, "rel")
    assert done.state == "promoted" and (await world.svc.live("support"))[0].number == 2
    assert (await world.live.get("support", "production", "s-new")).version == 2 and live.number == 1
    with pytest.raises(Conflict):
        await world.rollouts.promote("support", r.id, "rel")


async def test_promote_keeps_the_rollout_if_the_gate_no_longer_holds(world):
    v1 = await world.new_version()
    await world.prove(v1)
    r = await world.rollouts.start("support", 1, 10, "rae")
    world.svc.simulations = None  # the gate cannot be checked any more
    with pytest.raises(GateBlocked):
        await world.rollouts.promote("support", r.id, "rel")
    assert (await world.rollouts.repo.get(r.id)).state == "active"


def test_comparison_measures_each_arm_the_same_way():
    now = 1_800_000_000.0

    def t(i, sid, status="completed"):
        return TurnFacts(f"t{i}", sid, "support", "production", now + i, 1.0, status, 100, 1, 0, [], [], [])
    turns = [t(1, "c1"), t(2, "c2", "escalated"), t(3, "n1"), t(4, "n2"), t(5, "other")]
    hands = [HandoffFacts("c2", "t2", "agent_handoff", [], None, now)]
    fb = [FeedbackFacts("n1", 5, now), FeedbackFacts("other", 1, now)]
    out = compare({CONTROL: ["c1", "c2"], CANDIDATE: ["n1", "n2"]}, turns, hands, fb, {}, now - 10, now + 100)
    c, n = out["arms"][CONTROL], out["arms"][CANDIDATE]
    assert c["conversations"] == n["conversations"] == 2 and c["containmentRate"]["numerator"] == 1 and n["containmentRate"]["numerator"] == 2
    assert n["satisfaction"] == 5.0 and c["satisfaction"] is None and out["enoughData"] is False and "noise" in out["note"]  # 'other' belongs to neither arm
    assert ENOUGH == 30


KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def api():
    e = Env(InMemoryVersions(), InMemoryReleases())
    svc = RolloutService(InMemoryRollouts(), e.svc)
    ac = AccessControl(bootstrap_key=KEY)
    traces = TraceStore()
    rt = Runtime(ScriptedLLM([text("hello")] * 200), InMemoryStore(), traces)
    return TestClient(create_app(rt, traces, e.live, access=ac, simulations=e.sim, releases=e.svc, rollouts=svc)), ac, e


def test_rollout_through_the_api_with_permissions_audit_and_erasure():
    c, ac, e = api()
    loop = asyncio.new_event_loop()
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    c.post("/v1/agents/support/versions", headers=H, json={"fromBaseline": True, "by": "dev"})
    unproven = c.post("/v1/agents/support/rollouts", headers=H, json={"version": 1, "percent": 10})
    assert unproven.status_code == 409 and unproven.json()["error"]["reasons"]
    c.post("/v1/simulations/runs", headers=H, json={"agent": "support", "version": 1, "skipJudge": True})
    rm = {"authorization": f"Bearer {key('release_manager')}"}
    dev = {"authorization": f"Bearer {key('developer')}"}
    assert c.post("/v1/agents/support/rollouts", headers=dev, json={"version": 1, "percent": 10}).status_code == 403  # production needs the release permission
    assert c.post("/v1/agents/support/rollouts", headers=rm, json={"version": 1, "percent": 100}).status_code == 400
    assert c.post("/v1/agents/support/rollouts", headers=rm, json={"version": 1, "percent": 10, "environment": "mars"}).status_code == 400
    started = c.post("/v1/agents/support/rollouts", headers=rm, json={"version": 1, "percent": 50, "note": "try it"})
    assert started.status_code == 201
    rid = started.json()["id"]
    assert c.post("/v1/agents/support/rollouts", headers=rm, json={"version": 1, "percent": 5}).status_code == 409
    versions = {c.post("/v1/agents/support/chat", headers=H, json={"sessionId": f"s{i}", "message": "hi"}).json()["agentVersion"] for i in range(30)}
    assert versions == {None, 1}  # control is the baseline spec file, candidate is version 1
    assert c.post("/v1/agents/support/chat", headers=H, json={"sessionId": "s0", "message": "again"}).json()["agentVersion"] == c.post("/v1/agents/support/chat", headers=H, json={"sessionId": "s0", "message": "x"}).json()["agentVersion"]
    sessions = lambda: sum(len(v) for v in loop.run_until_complete(c.app.state.rollouts.repo.arm_sessions(rid)).values())  # noqa: E731
    c.post("/v1/agents/support/chat", headers=H, json={"sessionId": "gone", "message": "hi", "customerId": "cust-x"})
    before = sessions()
    c.delete("/v1/privacy/customers/cust-x", headers=H)
    assert sessions() == before - 1  # erasing a customer removes their conversation's arm assignment
    cmp_ = c.get(f"/v1/agents/support/rollouts/{rid}/comparison", headers=H).json()
    assert cmp_["versions"] == {"control": None, "candidate": 1} and cmp_["arms"]["candidate"]["conversations"] > 0 and cmp_["enoughData"] is False
    assert c.get(f"/v1/agents/support/rollouts/nope/comparison", headers=H).status_code == 404
    assert c.put(f"/v1/agents/support/rollouts/{rid}/percent", headers=dev, json={"percent": 5}).status_code == 403
    assert c.put(f"/v1/agents/support/rollouts/{rid}/percent", headers=rm, json={"percent": 0}).status_code == 400
    assert c.put(f"/v1/agents/support/rollouts/{rid}/percent", headers=rm, json={"percent": 20}).json()["percent"] == 20
    assert c.get("/v1/agents/support/rollouts", headers=H).json()["rollouts"][0]["state"] == "active"
    for role, code in [("viewer", 200), ("auditor", 200), ("channel", 403)]:
        assert c.get("/v1/agents/support/rollouts", headers={"authorization": f"Bearer {key(role)}"}).status_code == code, role
    assert c.post(f"/v1/agents/support/rollouts/{rid}/abort", headers=dev).status_code == 403
    assert c.post(f"/v1/agents/support/rollouts/{rid}/promote", headers=rm).json()["state"] == "promoted"
    assert c.post(f"/v1/agents/support/rollouts/{rid}/abort", headers=rm).status_code == 409
    assert c.get("/v1/agents/support/live", headers=H).json()["version"] == 1
    actions = [x["action"] for x in c.get("/v1/audit?limit=50", headers=H).json()["entries"]]
    assert {"rollout.start", "rollout.percent", "rollout.promote"} <= set(actions)


def test_endpoints_need_configuration():
    e = Env(InMemoryVersions(), InMemoryReleases())
    traces = TraceStore()
    c = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), traces), traces, e.live, KEY, simulations=e.sim, releases=e.svc))
    assert c.get("/v1/agents/support/rollouts", headers=H).status_code == 501
