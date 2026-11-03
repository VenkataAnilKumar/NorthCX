"""Versions, releases, rollback and the live-agent provider, over memory and Postgres."""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import registry
from northcx.approval_flow import ApprovalFlow
from northcx.catalog import AgentUnavailable
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios
from northcx.spec import AgentSpec, BuildContext, load_specs, parse_spec
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import (Conflict, GateBlocked, InMemoryReleases, InMemoryVersions, InvalidSpec, LiveAgents, NotFound,
                              ReleaseService, diff_specs)

ROOT = Path(__file__).resolve().parents[1]
SCEN = load_scenarios(ROOT / "examples" / "scenarios")
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}
BASE = SPECS["support"]


def edited(**changes) -> AgentSpec:
    return BASE.model_copy(update=changes)


def build_agent(spec, llm=None):
    return registry().build(spec, BuildContext(llm=llm))


class Env:
    def __init__(self, versions, releases, runs=None, with_sim=True):
        self.reg = registry()
        self.sim = SimulationService(SCEN, lambda aid, llm: build_agent(SPECS[aid], llm), runs or InMemorySimRuns(),
                                     {i: s.digest() for i, s in SPECS.items()},
                                     spec_builder=lambda spec, llm: build_agent(spec, llm)) if with_sim else None
        self.svc = ReleaseService(versions, releases, self.reg, SPECS, self.sim)
        baseline = {i: build_agent(s) for i, s in SPECS.items()}
        self.live = LiveAgents(baseline, self.svc, build_agent)

    async def new_version(self, **changes):
        return await self.svc.create_version("support", edited(**changes) if changes else BASE, "dev", "change")

    async def prove(self, version):
        """Run the required scenarios against exactly this version."""
        return await self.sim.run("scripted", skip_judge=True, spec=AgentSpec.model_validate(version.spec), source="ci")

    async def ship(self, **changes):
        v = await self.new_version(**changes)
        await self.prove(v)
        return v, await self.svc.publish("support", v.number, "rel-mgr", "ship it")


@pytest.fixture(params=["memory", "postgres"])
def env(request):
    if request.param == "memory":
        return Env(InMemoryVersions(), InMemoryReleases())
    from northcx.db import PgReleases, PgSimRuns, PgVersions
    eng = request.getfixturevalue("engine")
    return Env(PgVersions(eng), PgReleases(eng), PgSimRuns(eng))


# ---------------- versions ----------------
async def test_versions_are_numbered_immutable_snapshots(env):
    v1 = await env.new_version()
    v2 = await env.new_version(max_steps=9)
    assert (v1.number, v2.number) == (1, 2) and v1.digest == BASE.digest() and v2.digest != v1.digest
    assert v1.spec == json.loads(BASE.canonical()) and v1.author == "dev"
    assert [v.number for v in await env.svc.versions.list("support")] == [2, 1]
    assert (await env.svc.versions.get_number("support", 1)).id == v1.id and (await env.svc.versions.get(v2.id)).number == 2
    assert await env.svc.versions.get_number("support", 3) is None and await env.svc.versions.get("missing") is None


async def test_invalid_or_unchanged_versions_are_refused(env):
    await env.new_version()
    with pytest.raises(Conflict, match="No changes since version 1"):
        await env.new_version()
    with pytest.raises(InvalidSpec, match="does not match"):
        await env.svc.create_version("other", BASE, "dev")
    with pytest.raises(InvalidSpec, match="Unknown tool"):
        await env.new_version(tools=["lookup_order", "wire_money"])
    bad_cfg = parse_spec("id: support\ninstructions: x\nguardrails:\n  - name: llm_policy\n    config: {policies: []}\n")
    with pytest.raises(InvalidSpec, match="configuration"):
        await env.svc.create_version("support", bad_cfg, "dev")
    good_cfg = parse_spec("id: support\ninstructions: x\nguardrails:\n  - name: llm_policy\n    config: {policies: [be kind]}\n")
    assert (await env.svc.create_version("support", good_cfg, "dev")).number == 2
    reverted = await env.svc.create_version("support", BASE, "dev", "revert")  # going back to earlier content is a new version
    assert reverted.number == 3 and reverted.digest == BASE.digest()


async def test_concurrent_version_creation_never_repeats_a_number(env):
    made = await asyncio.gather(*[env.new_version(max_steps=2 + i) for i in range(6)])
    assert sorted(v.number for v in made) == [1, 2, 3, 4, 5, 6]


def test_diff_reads_like_a_review():
    a = json.loads(BASE.canonical())
    b = json.loads(edited(instructions=BASE.instructions + "Always greet by name.\n", max_steps=5, tools=["lookup_order"],
                          guardrails=[], forced_handoff=[]).canonical())
    d = diff_specs(a, b)
    assert not d["identical"] and "+Always greet by name." in d["instructions"]
    assert d["tools"] == {"added": [], "removed": ["issue_refund"]}
    assert d["guardrails"]["removed"] == ["no_card_numbers"] and d["forced_handoff"]["removed"] == ["formal_complaint", "legal", "safety"]
    assert d["other"]["max_steps"] == {"from": 8, "to": 5}
    assert diff_specs(a, a) == {"identical": True, "instructions": None, "tools": {"added": [], "removed": []},
                                "guardrails": {"added": [], "removed": [], "changed": []},
                                "input_guardrails": {"added": [], "removed": [], "changed": []},
                                    "output_guardrails": {"added": [], "removed": [], "changed": []},
                                "forced_handoff": {"added": [], "removed": [], "changed": []}, "other": {}}
    changed = json.loads(AgentSpec.model_validate({**a, "forced_handoff": [{"name": "legal", "patterns": ["attorney"]}]}).canonical())
    assert diff_specs(a, changed)["forced_handoff"]["changed"] == ["legal"]


# ---------------- publishing and the gate ----------------
async def test_publishing_requires_the_gate_for_that_exact_version(env):
    v1 = await env.new_version()
    with pytest.raises(GateBlocked) as e:
        await env.svc.publish("support", 1, "rel", None)
    assert e.value.reasons and "not run against this agent version" in e.value.reasons[0]
    await env.prove(v1)
    rel = await env.svc.publish("support", 1, "rel-mgr", "first release")
    assert (rel.action, rel.number, rel.by, rel.previous_number) == ("publish", 1, "rel-mgr", None)
    assert rel.gate["satisfied"] and rel.gate["covered"] == rel.gate["required"] == 17 and rel.gate["runIds"]
    v2 = await env.new_version(max_steps=6)  # a different spec has not been proven by v1's run
    with pytest.raises(GateBlocked):
        await env.svc.publish("support", 2, "rel", None)
    assert (await env.svc.live("support"))[0].number == 1


async def test_a_failing_proof_blocks_the_release(env):
    v = await env.new_version(guardrails=[])  # removes the card-number guardrail the scenarios rely on
    run = await env.prove(v)
    assert not run.passed
    with pytest.raises(GateBlocked) as e:
        await env.svc.publish("support", v.number, "rel", None)
    assert any("failed in run" in r for r in e.value.reasons)


async def test_publish_edge_cases(env):
    await env.ship()
    with pytest.raises(Conflict, match="already live"):
        await env.svc.publish("support", 1, "rel", None)
    with pytest.raises(NotFound):
        await env.svc.publish("support", 9, "rel", None)
    no_sim = Env(InMemoryVersions(), InMemoryReleases(), with_sim=False)
    await no_sim.new_version()
    with pytest.raises(GateBlocked, match="not configured"):
        await no_sim.svc.publish("support", 1, "rel", None)


# ---------------- rollback ----------------
async def test_rollback_undoes_the_last_release_and_toggles(env):
    await env.ship()
    v2, _ = await env.ship(max_steps=6)
    assert (await env.svc.live("support"))[0].number == 2
    back = await env.svc.rollback("support", "oncall", "bad release")
    assert (back.action, back.number, back.previous_number, back.note) == ("rollback", 1, 2, "bad release")
    assert (await env.svc.live("support"))[0].number == 1
    forward = await env.svc.rollback("support", "oncall")  # the undo of the undo
    assert forward.number == 2
    history = await env.svc.releases.list("support")
    assert [(r.action, r.number) for r in history] == [("rollback", 2), ("rollback", 1), ("publish", 2), ("publish", 1)]


async def test_rollback_to_a_named_version_or_the_baseline(env):
    await env.ship()
    await env.ship(max_steps=6)
    await env.ship(max_steps=7)
    assert (await env.svc.rollback("support", "o", to_number=1)).number == 1
    with pytest.raises(Conflict, match="already live"):
        await env.svc.rollback("support", "o", to_number=1)
    unreleased = await env.new_version(max_steps=3)
    with pytest.raises(Conflict, match="never live"):
        await env.svc.rollback("support", "o", to_number=unreleased.number)
    with pytest.raises(NotFound):
        await env.svc.rollback("support", "o", to_number=99)


async def test_first_release_can_be_withdrawn_to_the_baseline(env):
    with pytest.raises(Conflict, match="Nothing has been released"):
        await env.svc.rollback("support", "o")
    await env.ship()
    r = await env.svc.rollback("support", "o", "withdraw")
    assert r.version_id is None and r.number is None
    assert (await env.svc.live("support"))[0] is None
    assert (await env.live.get("support")).version is None  # the spec file's agent serves again
    again = await env.svc.rollback("support", "o", "undo the withdrawal")  # rolling back a rollback goes forward again
    assert again.number == 1 and (await env.svc.live("support"))[0].number == 1


async def test_rollback_needs_no_gate_even_after_scenarios_change(env):
    await env.ship()
    await env.ship(max_steps=6)
    env.sim.scenarios = []  # nothing proves anything any more
    assert (await env.svc.rollback("support", "o")).number == 1


# ---------------- live agents ----------------
async def test_live_agent_follows_releases_and_rollbacks(env):
    assert (await env.live.get("support")).version is None  # no release: the spec file's agent
    assert await env.live.get("ghost") is None
    await env.ship()
    a1 = await env.live.get("support")
    assert (a1.version, a1.digest) == (1, BASE.digest()) and a1 is await env.live.get("support")  # cached
    await env.ship(max_steps=3)
    assert (await env.live.get("support")).max_steps == 3
    await env.svc.rollback("support", "o")
    assert (await env.live.get("support")).max_steps == 8
    assert [a.id for a in await env.live.all()] == ["support"]


async def test_an_unbuildable_live_version_is_reported_not_guessed(env):
    await env.ship()
    broken = LiveAgents({}, env.svc, lambda spec: (_ for _ in ()).throw(RuntimeError("tool 'issue_refund' was removed")))
    with pytest.raises(AgentUnavailable, match="cannot be loaded"):
        await broken.get("support")


async def test_conversations_record_which_version_answered(env):
    await env.ship()
    rt = Runtime(ScriptedLLM([text("hi")]), InMemoryStore(), TraceStore())
    r = await rt.run(await env.live.get("support"), "s", "hello")
    assert r.trace.agent_version == 1 and r.trace.to_dict()["agent_version"] == 1
    assert (await rt.traces.summaries())[0].agent_version == 1


async def test_approvals_resolve_against_the_live_agent(env):
    await env.ship()
    live = await env.live.get("support")
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1"), text("Refunded.")]),
                 InMemoryStore(), TraceStore())
    held = await rt.run(live, "s", "refund 240 for 2077")
    res = await ApprovalFlow(rt).resolve(env.live, held.pending_approvals[0]["id"], True, "rae")
    assert res.error is None and res.run.status == "completed"
    assert res.run.trace.agent_version == 1


# ---------------- simulation runs against a version ----------------
async def test_simulation_against_a_spec_runs_only_that_agents_scenarios_with_its_digest():
    sim = Env(InMemoryVersions(), InMemoryReleases()).sim
    spec = edited(max_steps=5)
    run = await sim.run("scripted", skip_judge=True, spec=spec)
    assert run.agent_digests == {"support": spec.digest()} and run.counts["total"] == 18 and run.meta == {"agent": "support"}
    assert (await sim.gate_for("support", spec.digest())).satisfied
    assert not (await sim.gate("support")).satisfied  # the spec file's own digest was not proven by this run
    no_builder = SimulationService(SCEN, lambda a, l: build_agent(BASE, l), InMemorySimRuns(), {"support": BASE.digest()})
    with pytest.raises(ValueError, match="not configured"):
        await no_builder.run("scripted", spec=spec)
    with pytest.raises(ValueError, match="no scenarios"):
        await sim.run("scripted", spec=parse_spec("id: nobody\ninstructions: x\n"))


# ---------------- Postgres: survives a restart ----------------
async def test_live_version_survives_a_restart(engine, db_url):
    from sqlalchemy.pool import NullPool
    from northcx.db import PgReleases, PgSimRuns, PgVersions, create_engine
    first = Env(PgVersions(engine), PgReleases(engine), PgSimRuns(engine))
    await first.ship(max_steps=4)
    eng2 = create_engine(db_url, poolclass=NullPool)
    try:
        again = Env(PgVersions(eng2), PgReleases(eng2), PgSimRuns(eng2))
        agent = await again.live.get("support")
        assert (agent.version, agent.max_steps) == (1, 4)
        assert [r.action for r in await again.svc.releases.list("support")] == ["publish"]
        assert await again.svc.releases.agents_with_releases() == ["support"]
    finally:
        await eng2.dispose()


# ---------------- API ----------------
def api(with_sim=True, api_key=None):
    e = Env(InMemoryVersions(), InMemoryReleases(), with_sim=with_sim)
    traces = TraceStore()
    rt = Runtime(ScriptedLLM([text("hello")] * 20), InMemoryStore(), traces)
    app = create_app(rt, traces, e.live, api_key, simulations=e.sim, releases=e.svc)
    return TestClient(app), e


def test_release_flow_through_the_api():
    c, _ = api()
    chat = lambda sid: c.post("/v1/agents/support/chat", json={"sessionId": sid, "message": "hi"}).json()
    assert chat("a")["agentVersion"] is None
    live0 = c.get("/v1/agents/support/live").json()
    assert (live0["source"], live0["version"], live0["release"]) == ("baseline", None, None) and "id: support" in live0["specYaml"]

    v1 = c.post("/v1/agents/support/versions", json={"fromBaseline": True, "by": "dev", "note": "snapshot"})
    assert v1.status_code == 201 and v1.json()["number"] == 1 and v1.json()["digest"] == BASE.digest()
    blocked = c.post("/v1/agents/support/releases", json={"version": 1, "by": "rel"})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "gate_not_satisfied" and blocked.json()["error"]["reasons"]
    assert c.get("/v1/simulations/gate?agent=support&version=1").json()["gates"][0]["satisfied"] is False
    run = c.post("/v1/simulations/runs", json={"agent": "support", "version": 1, "skipJudge": True}).json()
    assert run["passed"] and run["agentDigests"] == {"support": BASE.digest()} and run["meta"]["version"] == 1
    assert c.get("/v1/simulations/gate?agent=support&version=1").json()["gates"][0]["satisfied"] is True
    rel = c.post("/v1/agents/support/releases", json={"version": 1, "by": "rel", "note": "go"}).json()
    assert (rel["action"], rel["version"], rel["by"], rel["gate"]["satisfied"]) == ("publish", 1, "rel", True)
    assert chat("b")["agentVersion"] == 1
    assert c.get("/v1/agents").json()["agents"][0]["version"] == 1
    assert c.get("/v1/traces?sessionId=b").json()["traces"][0]["agentVersion"] == 1

    yaml_v2 = BASE.instructions + "Greet customers by name.\n"
    v2 = c.post("/v1/agents/support/versions", json={"spec": {**json.loads(BASE.canonical()), "instructions": yaml_v2}, "by": "dev"})
    assert v2.status_code == 201 and v2.json()["number"] == 2
    d = c.get("/v1/agents/support/versions/1/diff/2").json()
    assert "+Greet customers by name." in d["instructions"] and not d["identical"]
    assert c.post("/v1/agents/support/releases", json={"version": 2, "by": "rel"}).status_code == 409  # not proven yet
    c.post("/v1/simulations/runs", json={"agent": "support", "version": 2, "skipJudge": True})
    assert c.post("/v1/agents/support/releases", json={"version": 2, "by": "rel"}).status_code == 200
    assert chat("c")["agentVersion"] == 2
    versions = c.get("/v1/agents/support/versions").json()["versions"]
    assert [(v["number"], v["live"], v["everReleased"]) for v in versions] == [(2, True, True), (1, False, True)]

    back = c.post("/v1/agents/support/rollback", json={"by": "oncall", "note": "regression"}).json()
    assert (back["action"], back["version"], back["previousVersion"]) == ("rollback", 1, 2)
    assert chat("d")["agentVersion"] == 1
    hist = c.get("/v1/agents/support/releases").json()["releases"]
    assert [(r["action"], r["version"]) for r in hist] == [("rollback", 1), ("publish", 2), ("publish", 1)]
    withdrawn = c.post("/v1/agents/support/rollback", json={"by": "oncall", "toVersion": 2}).json()
    assert withdrawn["version"] == 2
    detail = c.get("/v1/agents/support/versions/2").json()
    assert detail["live"] and "Greet customers by name." in detail["specYaml"]


def test_release_api_errors():
    c, _ = api()
    post = lambda path, body: c.post(f"/v1/agents/support/{path}", json=body)
    assert post("versions", {"by": "d"}).status_code == 400
    assert post("versions", {"by": "d", "spec": {}, "specYaml": "id: x"}).status_code == 400
    assert post("versions", {"by": "d", "specYaml": "id: [broken"}).status_code == 400
    assert post("versions", {"by": "d", "spec": {"id": "support", "instructions": "x", "tools": ["nope"]}}).status_code == 400
    assert post("versions", {"by": "d", "spec": {"id": "other", "instructions": "x"}}).status_code == 400
    assert c.post("/v1/agents/ghost/versions", json={"by": "d", "fromBaseline": True}).status_code == 404
    assert post("versions", {"by": "d", "fromBaseline": True}).status_code == 201
    assert post("versions", {"by": "d", "fromBaseline": True}).status_code == 409  # no changes
    assert post("releases", {"version": 7, "by": "r"}).status_code == 404
    assert post("rollback", {"by": "o"}).status_code == 409
    assert post("rollback", {"by": "o", "toVersion": 7}).status_code == 409
    assert c.get("/v1/agents/support/versions/9").status_code == 404
    assert c.get("/v1/agents/support/versions/1/diff/9").status_code == 404
    assert c.get("/v1/agents/ghost/live").status_code == 404
    assert c.post("/v1/simulations/runs", json={"agent": "support", "version": 9}).status_code == 404
    assert c.post("/v1/simulations/runs", json={"version": 1}).status_code == 400
    assert c.get("/v1/simulations/gate?agent=support&version=9").status_code == 404


def test_endpoints_need_configuration_and_a_key():
    unconfigured = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {}))
    assert unconfigured.get("/v1/agents/support/versions").status_code == 501
    assert unconfigured.post("/v1/agents/support/releases", json={"version": 1, "by": "r"}).status_code == 501
    c, _ = api(api_key="k")
    assert c.get("/v1/agents/support/live").status_code == 401
    assert c.get("/v1/agents/support/live", headers={"authorization": "Bearer k"}).status_code == 200


def test_an_unloadable_live_version_returns_503_not_a_guess():
    c, e = api()
    c.post("/v1/agents/support/versions", json={"fromBaseline": True, "by": "d"})
    c.post("/v1/simulations/runs", json={"agent": "support", "version": 1, "skipJudge": True})
    c.post("/v1/agents/support/releases", json={"version": 1, "by": "r"})
    e.live.build = lambda spec: (_ for _ in ()).throw(RuntimeError("tool removed"))
    e.live._cache.clear()
    r = c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "hi"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "agent_unavailable"
    assert c.get("/v1/agents").status_code == 503
    assert c.post("/v1/agents/support/rollback", json={"by": "o"}).status_code == 200  # rollback is the way out
    assert c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "hi"}).status_code == 200


# ---------------- publish checklist (U7) ----------------
def by_key(cl):
    return {c["key"]: c for c in cl["checks"]}


async def test_checklist_lists_every_requirement_and_matches_what_publish_enforces(env):
    v1 = await env.new_version()
    cl = await env.svc.checklist("support", 1, "production")
    k = by_key(cl)
    assert cl["ready"] is False and k["scenarios"]["status"] == "fail" and "not run against this agent version" in k["scenarios"]["detail"]
    assert k["valid"]["status"] == k["permission"]["status"] == k["not_live"]["status"] == "pass" and k["staged"]["status"] == "warn"
    assert cl["changes"]["identical"] is True and cl["liveVersion"] is None  # the baseline is what is live, and this version is a snapshot of it
    await env.prove(v1)
    cl = await env.svc.checklist("support", 1, "production")
    assert cl["ready"] is True and by_key(cl)["scenarios"]["status"] == "pass" and "17 of 17" in by_key(cl)["scenarios"]["detail"]
    await env.svc.publish("support", 1, "rel", None)
    assert by_key(await env.svc.checklist("support", 1, "production"))["not_live"]["status"] == "fail"
    v2 = await env.new_version(max_steps=6)
    cl = await env.svc.checklist("support", 2, "production", permitted=False, active_alerts=["error-rate (critical)"])
    k = by_key(cl)
    assert k["permission"]["status"] == "fail" and k["alerts"]["status"] == "warn" and "error-rate" in k["alerts"]["detail"] and cl["ready"] is False
    assert cl["changes"]["identical"] is False and cl["changes"]["otherChanged"] == ["max_steps"] and cl["liveVersion"] == 1
    assert by_key(await env.svc.checklist("support", 2, "dev"))["scenarios"]["status"] == "info"
    assert (await env.svc.checklist("support", 2, "dev"))["ready"] is True
    with pytest.raises(NotFound):
        await env.svc.checklist("support", 99)
    with pytest.raises(ValueError):
        await env.svc.checklist("support", 2, "nowhere")
    env.svc.strict_promotion = True
    await env.prove(v2)
    k = by_key(await env.svc.checklist("support", 2, "production"))
    assert k["staged"]["status"] == "fail" and "production only accepts" in k["staged"]["detail"]
    await env.svc.publish("support", 2, "rel", None, "staging")
    assert by_key(await env.svc.checklist("support", 2, "production"))["staged"]["status"] == "pass"


async def test_checklist_without_simulations_cannot_pass_outside_dev():
    e = Env(InMemoryVersions(), InMemoryReleases(), with_sim=False)
    await e.new_version()
    cl = await e.svc.checklist("support", 1, "staging")
    assert cl["ready"] is False and "not configured" in by_key(cl)["scenarios"]["detail"]


def test_checklist_through_the_api_with_permissions():
    from northcx.access import AccessControl
    ac = AccessControl(bootstrap_key="boot" * 10)
    e = Env(InMemoryVersions(), InMemoryReleases())
    traces = TraceStore()
    rt = Runtime(ScriptedLLM([text("hi")] * 5), InMemoryStore(), traces)
    c = TestClient(create_app(rt, traces, e.live, access=ac, simulations=e.sim, releases=e.svc))
    H = {"authorization": "Bearer " + "boot" * 10}
    c.post("/v1/agents/support/versions", headers=H, json={"fromBaseline": True, "by": "dev"})
    r = c.get("/v1/agents/support/versions/1/checklist", headers=H).json()
    assert r["ready"] is False and {x["key"] for x in r["checks"]} >= {"permission", "valid", "scenarios", "staged", "alerts", "changes"}
    assert c.get("/v1/agents/support/versions/9/checklist", headers=H).status_code == 404
    assert c.get("/v1/agents/support/versions/1/checklist?environment=mars", headers=H).status_code == 400
    loop = asyncio.new_event_loop()
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    dev = {"authorization": f"Bearer {key('developer')}"}
    assert by_key(c.get("/v1/agents/support/versions/1/checklist", headers=dev).json())["permission"]["status"] == "fail"
    assert by_key(c.get("/v1/agents/support/versions/1/checklist?environment=dev", headers=dev).json())["permission"]["status"] == "pass"
    assert c.get("/v1/agents/support/versions/1/checklist", headers={"authorization": f"Bearer {key('channel')}"}).status_code == 403
