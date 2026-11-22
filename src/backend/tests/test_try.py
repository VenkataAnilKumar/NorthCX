"""Try an agent definition that has not been saved: one message, the answer and the steps, in a sandbox."""
import asyncio
import json

from fastapi.testclient import TestClient

from pathlib import Path

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios
from northcx.spec import load_specs
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}

KEY = "boot" * 10


def setup(script):
    llm = ScriptedLLM(script)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    versions = InMemoryVersions()
    svc = ReleaseService(versions, InMemoryReleases(), registry(), SPECS, SimulationService(load_scenarios(ROOT / "examples" / "scenarios"), lambda a, l: None, InMemorySimRuns(), {}))
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc))
    return c, ac, rt, llm, versions


def H(t=KEY):
    return {"authorization": f"Bearer {t}"}


SPEC = {"id": "support", "instructions": "You help customers with orders.", "tools": ["lookup_order", "issue_refund"]}


def try_(c, message="where is order 1042?", spec=None, history=None, headers=None):
    return c.post("/v1/agents/support/try", json={"spec": spec or SPEC, "message": message, **({"history": history} if history else {})}, headers=H() if headers is None else headers)


def test_an_unsaved_draft_answers_with_the_steps_and_nothing_is_saved():
    c, _, rt, llm, versions = setup([tool_call("lookup_order", {"order_id": "1042"}, "a"), text("Order 1042 was delivered.")])
    r = try_(c)
    assert r.status_code == 200
    out = r.json()
    assert out["reply"] == "Order 1042 was delivered." and out["status"] == "completed" and out["sandbox"] is True and out["toolsCalled"] == ["lookup_order"]
    assert any(e["type"] == "tool_result" for e in out["events"])
    assert "instructions" in llm.requests[0].system or "You help customers with orders." in llm.requests[0].system        # the draft's own words were used
    loop = asyncio.new_event_loop()
    assert loop.run_until_complete(rt.traces.summaries(None, 10)) == [] and loop.run_until_complete(versions.list("support")) == []


def test_the_conversation_so_far_is_part_of_the_try():
    c, _, _, llm, _ = setup([text("It is on its way."), text("Yes, you can cancel it today.")])
    first = try_(c, "where is my order?").json()
    second = try_(c, "can I cancel it?", history=[{"role": "user", "text": "where is my order?"}, {"role": "assistant", "text": first["reply"]}]).json()
    assert second["reply"] == "Yes, you can cancel it today."
    sent = json.dumps(llm.requests[-1].messages)
    assert "where is my order?" in sent and "It is on its way." in sent and "can I cancel it?" in sent


def test_a_write_in_the_try_is_simulated():
    c, _, _, _, _ = setup([tool_call("issue_refund", {"order_id": "1042", "amount": 20}, "a"), text("Refunded.")])
    out = try_(c, "refund 20 for 1042").json()
    results = [e for e in out["events"] if e["type"] == "tool_result"]
    assert results and results[0]["data"].get("dry_run") is True


def test_a_definition_with_problems_is_refused_in_plain_words_and_never_run():
    c, _, _, llm, _ = setup([text("unused")])
    r = try_(c, spec={**SPEC, "tools": ["nope"]})
    assert r.status_code == 400 and "does not exist here" in r.json()["error"]["message"] and llm.requests == []
    assert try_(c, spec={"id": "support"}).status_code == 400
    assert try_(c, spec={**SPEC, "id": "other"}).status_code == 400


def test_a_good_exchange_comes_with_a_test_that_can_be_saved():
    c, _, _, _, _ = setup([tool_call("lookup_order", {"order_id": "1042"}, "a"), text("Order 1042 was delivered.")])
    out = try_(c).json()
    assert out["testYaml"] and "where is order 1042?" in out["testYaml"] and "lookup_order" in out["testYaml"] and "agent: support" in out["testYaml"]
    check = c.post("/v1/simulations/scenarios/validate", json={"yaml": out["testYaml"]}, headers=H()).json()
    assert check["valid"] is True


def test_only_people_who_may_run_simulations_can_try_and_the_message_is_bounded():
    c, ac, _, _, _ = setup([text("a")] * 3)
    loop = asyncio.new_event_loop()
    viewer = loop.run_until_complete(ac.issue("v", "viewer", "root"))[1]
    dev = loop.run_until_complete(ac.issue("d", "developer", "root"))[1]
    assert try_(c, headers={}).status_code == 401 and try_(c, headers=H(viewer)).status_code == 403 and try_(c, headers=H(dev)).status_code == 200
    assert try_(c, message="").status_code == 400 and try_(c, message="x" * 9000).status_code == 400
    assert try_(c, history=[{"role": "assistant", "text": "x"}]).status_code == 400                # a conversation starts with the customer


def test_every_try_gets_its_own_test_name_so_two_can_be_saved():
    import yaml
    c, _, _, _, _ = setup([text("One."), text("Two.")])
    a, b = (yaml.safe_load(try_(c, m).json()["testYaml"])["name"] for m in ("hello", "hello again"))
    assert a != b and a.startswith("regression-")
