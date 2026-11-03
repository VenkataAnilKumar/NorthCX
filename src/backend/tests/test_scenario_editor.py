"""Scenarios saved in the database: storage, validation, permissions, the release gate, and templates."""
import asyncio
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios, parse_scenario
from northcx.simulation.managed import InMemoryScenarios, ManagedScenario, as_scenario, parse_definition
from northcx.simulation.scenario import ScenarioError
from northcx.spec import AgentSpec, BuildContext, load_specs
from northcx.store import InMemoryStore
from northcx.templates import LIBRARY, load_templates
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}
FILES = load_scenarios(ROOT / "examples" / "scenarios")

GOOD = """
name: greets-by-name
agent: support
description: Says hello.
model:
  - text: Hello there!
turns:
  - say: hi
    expect: {status: completed, reply_includes: [Hello]}
"""


def definition(**kw):
    d = yaml.safe_load(GOOD)
    d.update(kw)
    return d


@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        return InMemoryScenarios()
    from northcx.db import PgScenarios
    return PgScenarios(request.getfixturevalue("engine"))


# ---- parsing ----
def test_definitions_are_validated_like_files():
    d, sc = parse_definition(GOOD)
    assert sc.name == "greets-by-name" and d["turns"][0]["say"] == "hi" and parse_definition(d)[1].digest() == sc.digest()
    assert "source" not in parse_definition({**d, "source": "x.yaml"})[0]
    for bad in ["name: x\nturns: []", ": : :\n\t", "- a list", "name: bad name\nagent: a\nturns: [{say: hi}]", "x" * 100_001,
                "name: n\nagent: a\nturns: [{say: hi}]\ncolour: red", "name: n\nagent: a\nturns: [{say: hi, expect: {reply_matches: '('}}]"]:
        with pytest.raises(ScenarioError):
            parse_definition(bad)


# ---- storage ----
async def test_repository_contract(repo):
    d, sc = parse_definition(GOOD)
    m, created = await repo.put(sc, d, "rae", now=1000.0)
    assert created and (m.name, m.agent, m.required, m.revision, m.created_by) == ("greets-by-name", "support", True, 1, "rae")
    d2, sc2 = parse_definition({**d, "required": False, "description": "changed"})
    m2, created2 = await repo.put(sc2, d2, "jo", now=2000.0)
    assert not created2 and (m2.revision, m2.required, m2.created_by, m2.updated_by, m2.created_at, m2.updated_at) == (2, False, "rae", "jo", 1000.0, 2000.0)
    got = await repo.get("greets-by-name")
    assert got.definition["description"] == "changed" and as_scenario(got).required is False and as_scenario(got).source == "managed:greets-by-name"
    assert [x.name for x in await repo.list()] == ["greets-by-name"] and await repo.get("nope") is None
    assert await repo.delete("greets-by-name") is True and await repo.delete("greets-by-name") is False and await repo.list() == []


# ---- the simulation service and the gate ----
def service(managed=None):
    r = registry()
    return SimulationService(list(FILES), lambda a, l: r.build(SPECS[a], BuildContext(llm=l)), InMemorySimRuns(), {i: s.digest() for i, s in SPECS.items()},
                             spec_builder=lambda spec, l: r.build(spec, BuildContext(llm=l)), managed=managed)


async def test_saved_scenarios_run_with_the_files_and_file_names_win():
    repo = InMemoryScenarios()
    d, sc = parse_definition(GOOD)
    await repo.put(sc, d, "rae")
    clash = dict(d, name=FILES[0].name)
    await repo.put(parse_definition(clash)[1], clash, "rae")
    svc = service(repo)
    names = [s.name for s in await svc.all_scenarios()]
    assert len(names) == len(FILES) + 1 and "greets-by-name" in names and names.count(FILES[0].name) == 1
    run = await svc.run("scripted", only="greets-by-name", skip_judge=True)
    assert run.counts["total"] == 1 and run.passed
    assert next(s for s in await svc.all_scenarios() if s.name == FILES[0].name).source != "managed:" + FILES[0].name


async def test_a_saved_required_scenario_counts_toward_the_gate_and_editing_it_voids_the_proof():
    repo = InMemoryScenarios()
    svc = service(repo)
    base = await svc.gate("support")
    d, sc = parse_definition(GOOD)
    await repo.put(sc, d, "rae")
    after = await svc.gate("support")
    assert after.required == base.required + 1 and not after.satisfied
    await svc.run("scripted", skip_judge=True, source="ci")
    assert (await svc.gate("support")).satisfied
    edited = dict(d, description="edited")
    await repo.put(parse_definition(edited)[1], edited, "rae")
    g = await svc.gate("support")
    assert not g.satisfied and any("greets-by-name" in r for r in g.reasons)  # the scenario changed, so the earlier pass no longer counts
    await svc.run("scripted", skip_judge=True, source="ci")
    assert (await svc.gate("support")).satisfied
    await repo.delete("greets-by-name")
    assert (await svc.gate("support")).required == base.required


async def test_a_broken_saved_scenario_is_left_out_not_fatal():
    repo = InMemoryScenarios()
    repo.items["broken"] = ManagedScenario("broken", "support", True, {"name": "broken"}, "x", "x")
    assert len(await service(repo).all_scenarios()) == len(FILES)


# ---- API ----
KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def api():
    from northcx.knowledge import InMemoryKnowledge, knowledge_tool
    r = registry()
    r.tool(knowledge_tool(InMemoryKnowledge()))
    sim = service(InMemoryScenarios())
    rel = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, SPECS, sim)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=rel, simulations=sim, templates=load_templates(LIBRARY))
    return TestClient(app), ac, sim, rel


def key(ac, role):
    return {"authorization": "Bearer " + asyncio.new_event_loop().run_until_complete(ac.issue(role, role, "root"))[1]}


def test_api_validate_create_read_update_delete_with_audit():
    c, ac, sim, rel = api()
    v = c.post("/v1/simulations/scenarios/validate", json={"yaml": GOOD}, headers=H).json()
    assert v["valid"] and v["name"] == "greets-by-name" and v["steps"] == 1 and len(v["digest"]) == 64
    bad = c.post("/v1/simulations/scenarios/validate", json={"yaml": "name: x"}, headers=H).json()
    assert bad["valid"] is False and bad["problems"]
    assert c.get("/v1/simulations/scenarios/greets-by-name", headers=H).status_code == 404
    r = c.post("/v1/simulations/scenarios", json={"yaml": GOOD}, headers=H)
    assert r.status_code == 201 and r.json()["revision"] == 1
    assert c.post("/v1/simulations/scenarios", json={"yaml": GOOD}, headers=H).status_code == 409
    listed = {s["name"]: s for s in c.get("/v1/simulations/scenarios", headers=H).json()["scenarios"]}
    assert listed["greets-by-name"]["source"] == "managed" and listed["greets-by-name"]["editable"] and listed[FILES[0].name]["source"] == "file" and not listed[FILES[0].name]["editable"]
    got = c.get("/v1/simulations/scenarios/greets-by-name", headers=H).json()
    assert got["editable"] and yaml.safe_load(got["yaml"])["turns"][0]["say"] == "hi" and got["revision"] == 1
    upd = c.put("/v1/simulations/scenarios/greets-by-name", json={"scenario": dict(got["definition"], description="v2")}, headers=H)
    assert upd.json()["revision"] == 2
    assert c.put("/v1/simulations/scenarios/greets-by-name", json={"scenario": dict(got["definition"], name="other")}, headers=H).status_code == 400  # no renaming
    assert c.put("/v1/simulations/scenarios/never", json={"yaml": GOOD}, headers=H).status_code == 404
    assert c.post("/v1/simulations/scenarios", json={}, headers=H).status_code == 400 and c.post("/v1/simulations/scenarios", json={"yaml": GOOD, "scenario": {}}, headers=H).status_code == 400
    assert c.delete("/v1/simulations/scenarios/greets-by-name", headers=H).json() == {"deleted": True} and c.delete("/v1/simulations/scenarios/greets-by-name", headers=H).status_code == 404
    actions = [e["action"] for e in c.get("/v1/audit?limit=50", headers=H).json()["entries"]]
    assert {"scenario.create", "scenario.update", "scenario.delete"} <= set(actions)


def test_file_scenarios_are_read_only_through_the_api():
    c, ac, sim, rel = api()
    name = FILES[0].name
    detail = c.get(f"/v1/simulations/scenarios/{name}", headers=H).json()
    assert detail["source"] == "file" and detail["editable"] is False and detail["definition"]["name"] == name and yaml.safe_load(detail["yaml"])["name"] == name
    assert c.put(f"/v1/simulations/scenarios/{name}", json={"yaml": GOOD.replace("greets-by-name", name)}, headers=H).status_code == 409
    assert c.delete(f"/v1/simulations/scenarios/{name}", headers=H).status_code == 409
    assert c.post("/v1/simulations/scenarios", json={"yaml": GOOD.replace("greets-by-name", name)}, headers=H).status_code == 409


def test_who_may_write_and_who_may_touch_required_scenarios():
    c, ac, sim, rel = api()
    dev, rm, viewer, reviewer = key(ac, "developer"), key(ac, "release_manager"), key(ac, "viewer"), key(ac, "reviewer")
    optional = GOOD.replace("agent: support", "agent: support\nrequired: false")
    assert c.post("/v1/simulations/scenarios", json={"yaml": optional}, headers=dev).status_code == 201  # developers write ordinary scenarios
    assert c.post("/v1/simulations/scenarios", json={"yaml": GOOD.replace("greets-by-name", "needs-gate")}, headers=dev).status_code == 403  # but not required ones
    assert "scenarios:require" in c.post("/v1/simulations/scenarios", json={"yaml": GOOD.replace("greets-by-name", "needs-gate")}, headers=dev).json()["error"]["message"]
    assert c.put("/v1/simulations/scenarios/greets-by-name", json={"yaml": optional.replace("required: false", "required: true")}, headers=dev).status_code == 403  # cannot make it required
    assert c.post("/v1/simulations/scenarios", json={"yaml": GOOD.replace("greets-by-name", "gate-me")}, headers=rm).status_code == 201
    assert c.put("/v1/simulations/scenarios/gate-me", json={"yaml": GOOD.replace("greets-by-name", "gate-me").replace("agent: support", "agent: support\nrequired: false")}, headers=dev).status_code == 403  # cannot relax one either
    assert c.delete("/v1/simulations/scenarios/gate-me", headers=dev).status_code == 403
    assert c.delete("/v1/simulations/scenarios/gate-me", headers=rm).status_code == 200
    assert c.delete("/v1/simulations/scenarios/greets-by-name", headers=dev).status_code == 200
    for who in (viewer, reviewer):
        assert c.post("/v1/simulations/scenarios", json={"yaml": optional}, headers=who).status_code == 403
        assert c.get("/v1/simulations/scenarios", headers=who).status_code == 200
    assert c.post("/v1/simulations/scenarios/validate", json={"yaml": GOOD}, headers=viewer).status_code == 403
    denied = [e for e in c.get("/v1/audit?limit=100", headers=H).json()["entries"] if e["action"] == "auth.denied"]
    assert any(e["detail"].get("permission") == "scenarios:require" for e in denied)


def test_an_agent_made_from_a_template_gets_its_tests_without_a_restart_and_they_gate_its_release():
    c, ac, sim, rel = api()
    dev = key(ac, "developer")
    r = c.post("/v1/templates/knowledge-faq/create-version", json={"agentId": "faq-bot", "saveScenarios": True}, headers=dev)
    assert r.status_code == 201 and r.json()["scenariosSaved"] == ["faq-bot-searches-then-cites"] and r.json()["scenariosRequired"] is False
    s = {x["name"]: x for x in c.get("/v1/simulations/scenarios", headers=H).json()["scenarios"]}["faq-bot-searches-then-cites"]
    assert s["required"] is False and "template" in s["tags"]  # a developer's copy does not decide the gate
    again = c.post("/v1/templates/knowledge-faq/create-version", json={"agentId": "faq-bot", "saveScenarios": True, "params": {"company_name": "Acme"}}, headers=dev).json()
    assert again["scenariosSaved"] == [] and again["scenariosSkipped"] == ["faq-bot-searches-then-cites"]
    r2 = c.post("/v1/templates/human-triage/create-version", json={"agentId": "tri-bot", "saveScenarios": True}, headers=key(ac, "release_manager"))
    assert r2.json()["scenariosRequired"] is True
    v = asyncio.new_event_loop().run_until_complete(rel.versions.get_number("tri-bot", 1))
    g = asyncio.new_event_loop().run_until_complete(sim.gate_for("tri-bot", v.digest))
    assert g.required == 1 and not g.satisfied and "tri-bot-hands-off-when-asked" in " ".join(g.reasons)  # its release is blocked until its test has passed
    asyncio.new_event_loop().run_until_complete(sim.run("scripted", skip_judge=True, spec=AgentSpec.model_validate(v.spec)))
    assert asyncio.new_event_loop().run_until_complete(sim.gate_for("tri-bot", v.digest)).satisfied
    faq = asyncio.new_event_loop().run_until_complete(rel.versions.get_number("faq-bot", 1))
    assert asyncio.new_event_loop().run_until_complete(sim.gate_for("faq-bot", faq.digest)).required == 0  # the developer's copy is optional, so it does not gate
    no_save = c.post("/v1/templates/order-status/create-version", json={"agentId": "ord-bot"}, headers=dev).json()
    assert "scenariosSaved" in no_save and no_save["scenariosSaved"] == []
