"""Live and candidate side by side: the same tests on both, and what differs."""
import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.plain import compare_verdict
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios
from northcx.spec import AgentSpec, BuildContext, load_specs
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}
KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def setup():
    r = registry()
    sim = SimulationService(load_scenarios(ROOT / "examples" / "scenarios"), lambda a, l: r.build(SPECS[a], BuildContext(llm=l)), InMemorySimRuns(), {},
                            spec_builder=lambda spec, llm: r.build(spec, BuildContext(llm=llm)))
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, SPECS, sim)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), releases=svc, simulations=sim))
    return c, svc


def base():
    return json.loads(SPECS["support"].canonical())


def new_version(svc, **changes):
    return asyncio.new_event_loop().run_until_complete(svc.create_version("support", AgentSpec.model_validate({**base(), **changes}), "dev"))


def test_the_verdict_says_in_plain_words_what_got_better_and_worse():
    rows = [{"name": "a", "live": True, "candidate": True, "change": "same"}, {"name": "b", "live": True, "candidate": False, "change": "regressed"},
            {"name": "c", "live": False, "candidate": True, "change": "fixed"}]
    assert compare_verdict(rows) == "The candidate fails 1 test that the live version passes: b. It passes 1 test that the live version fails: c."
    assert compare_verdict([{"name": "a", "live": True, "candidate": True, "change": "same"}]) == "The candidate gives the same results as the live version on 1 test."
    assert compare_verdict([]) == "There are no tests to compare."


def test_the_same_tests_run_on_the_live_version_and_the_candidate_and_the_differences_are_listed():
    c, svc = setup()
    same = new_version(svc, instructions=base()["instructions"] + "\nAlways greet the customer by name.")
    out = c.post("/v1/agents/support/compare", json={"candidate": same.number}, headers=H)
    assert out.status_code == 200
    body = out.json()
    assert body["live"]["number"] is None and body["candidate"]["number"] == same.number          # nothing is released yet: live is the file the agent was started from
    assert body["scenarios"] and all(r["live"] is not None and r["candidate"] is not None for r in body["scenarios"])
    assert "Always greet the customer by name." in (body["differences"]["instructions"] or "")
    assert body["counts"]["live"]["total"] == body["counts"]["candidate"]["total"] == len(body["scenarios"])


def test_a_candidate_that_breaks_a_test_is_shown_as_regressed_and_the_verdict_names_it():
    c, svc = setup()
    bad = new_version(svc, forced_handoff=[*base().get("forced_handoff", []), {"name": "orders", "patterns": ["order"]}])    # every order question now goes to a person
    body = c.post("/v1/agents/support/compare", json={"candidate": bad.number}, headers=H).json()
    regressed = [r["name"] for r in body["scenarios"] if r["change"] == "regressed"]
    assert regressed and body["verdict"].startswith("The candidate fails") and regressed[0] in body["verdict"]
    assert "orders" in json.dumps(body["differences"]["forced_handoff"]["added"])


def test_unknown_candidates_and_permissions_are_refused_with_what_to_do():
    c, svc = setup()
    r = c.post("/v1/agents/support/compare", json={"candidate": 99}, headers=H)
    assert r.status_code == 404 and "no version 99" in r.json()["error"]["message"]
    assert c.post("/v1/agents/support/compare", json={"candidate": 1}).status_code == 401
    assert c.post("/v1/agents/support/compare", json={}, headers=H).status_code == 400
