"""WP 5.1: a routine calls a tool through the same runtime path an agent uses; a change needs a person first."""
import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.automations import AutomationError, AutomationService, Hooks, validate_definition
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios
from northcx.spec import load_specs
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

ROOT = Path(__file__).resolve().parents[1]
KEY = "boot" * 10
ADM = {"authorization": f"Bearer {KEY}"}


def world():
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), registry(), {s.id: s for s in load_specs(ROOT / "examples")},
                         SimulationService(load_scenarios(ROOT / "examples" / "scenarios"), lambda a, l: None, InMemorySimRuns(), {}))
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc)
    key = lambda n, r: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    return app, key, loop


def routine(rid, steps, trigger=None):
    return {"id": rid, "name": rid.replace("-", " ").title(), "trigger": trigger or {"type": "manual"}, "steps": steps}


LOOKUP = {"id": "find", "kind": "tool", "tool": "lookup_order", "args": {"order_id": "{{input.order}}"}}
SAVE = {"id": "save", "kind": "output", "title": "Order {date}"}
ASK = {"id": "ask", "kind": "person", "ask": "Refund the order shown above?"}


def finished(c, run_id, headers):
    for _ in range(100):
        got = c.get(f"/v1/automation-runs/{run_id}", headers=headers).json()
        if got["status"] not in ("running", "waiting"):
            return got
        time.sleep(0.05)
    raise AssertionError("the run did not finish")


def publish(c, ann, ben, d):
    assert c.post("/v1/automations", headers=ann, json={"definition": d}).status_code == 201
    assert c.post(f"/v1/automations/{d['id']}/propose", headers=ann).status_code == 200
    assert c.post(f"/v1/automations/{d['id']}/approve", headers=ben, json={}).status_code == 200


def test_a_read_tool_runs_and_its_result_reaches_the_next_step_and_the_record():
    app, key, loop = world()
    c, ann, ben = TestClient(app), key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("look-up", [LOOKUP, SAVE]))
    run = loop.run_until_complete(app.state.automations.run("look-up", "manual", "ann", json.dumps({"order": "1042"})))
    assert run.status == "succeeded", run.error
    step = run.steps[0]
    assert step["tool"] == "lookup_order" and step["effect"] == "read" and step["args"] == {"order_id": "1042"}
    assert json.loads(step["output"])["id"] == "1042"
    assert run.steps[1]["outputId"]


def test_a_change_waits_for_a_person_and_runs_once_after_the_answer():
    app, key, loop = world()
    c, ann, ben = TestClient(app), key("ann", "release_manager"), key("ben", "release_manager")
    rev = key("rev", "reviewer")
    refund = {"id": "refund", "kind": "tool", "tool": "issue_refund", "args": {"order_id": "{{input.order}}", "amount": 20}}
    publish(c, ann, ben, routine("refund-one", [LOOKUP, ASK, refund]))
    svc = app.state.automations
    run = loop.run_until_complete(svc.run("refund-one", "manual", "ann", json.dumps({"order": "1042"})))
    assert run.status == "waiting" and [s["id"] for s in run.steps] == ["find", "ask"]
    r = c.post(f"/v1/automation-runs/{run.id}/decision", headers=rev, json={"approve": True})
    assert r.status_code == 200
    done = finished(c, run.id, ann)
    assert done['status'] == "succeeded", done['error']
    assert json.loads(done['steps'][-1]["output"]) == {"order_id": "1042", "refunded": 20}
    assert c.post(f"/v1/automation-runs/{run.id}/decision", headers=rev, json={"approve": True}).status_code == 409        # a second answer cannot repeat the change


def test_a_change_with_no_person_step_before_it_cannot_be_saved():
    app, key, loop = world()
    c, ann = TestClient(app), key("ann", "release_manager")
    refund = {"id": "refund", "kind": "tool", "tool": "issue_refund", "args": {"order_id": "1042", "amount": 20}}
    r = c.post("/v1/automations", headers=ann, json={"definition": routine("no-person", [refund])})
    assert r.status_code == 400 and "'person' step must come before" in r.json()["error"]["message"]
    assert c.post("/v1/automations", headers=ann, json={"definition": routine("person-last", [ASK, refund][::-1])}).status_code == 400


def test_a_tool_that_asks_for_approval_needs_a_person_step_that_names_who_may_approve():
    app, key, loop = world()
    c, ann, ben = TestClient(app), key("ann", "release_manager"), key("ben", "release_manager")
    rev = key("rev", "reviewer")
    big = {"id": "refund", "kind": "tool", "tool": "issue_refund", "args": {"order_id": "2077", "amount": 240}}
    publish(c, ann, ben, routine("big-open", [ASK, big]))
    named = {**ASK, "approver": {"role": "reviewer"}}
    publish(c, ann, ben, routine("big-named", [named, big]))
    svc = app.state.automations
    for rid, ok in (("big-open", False), ("big-named", True)):
        run = loop.run_until_complete(svc.run(rid, "manual", "ann"))
        assert c.post(f"/v1/automation-runs/{run.id}/decision", headers=rev, json={"approve": True}).status_code == 200
        done = finished(c, run.id, ann)
        assert (done['status'] == "succeeded") is ok, done['error']
        if not ok:
            assert "must name an approver role or team" in done['error']


@pytest.mark.parametrize("step,why", [
    ({"id": "a", "kind": "tool", "tool": "no_such_tool"}, "tool must be one of"),
    ({"id": "a", "kind": "tool", "tool": "lookup_order", "args": {"order": "1"}}, "not valid"),
    ({"id": "a", "kind": "tool", "tool": "lookup_order", "args": [1]}, "args must be a mapping"),
    ({"id": "a", "kind": "tool", "tool": "lookup_order", "args": {"order_id": "{{item.id}}"}}, "only inside a foreach"),
])
def test_a_bad_tool_step_is_refused_with_the_reason(step, why):
    tools = {"lookup_order": {"effect": "read", "allowed": True, "model": registry().get("lookup_order").input_model}}
    with pytest.raises(AutomationError, match=why):
        validate_definition(routine("bad-tool", [step]), set(), tools=tools)


def test_a_tool_the_service_identity_may_not_use_is_refused():
    with pytest.raises(AutomationError, match="cannot use 'audit_log'"):
        validate_definition(routine("no-perm", [{"id": "a", "kind": "tool", "tool": "audit_log", "args": {}}]), set(),
                            tools={"audit_log": {"effect": "read", "allowed": False, "why": "it needs the audit:read permission"}})


def test_a_result_too_large_to_pass_on_fails_the_step_instead_of_being_cut():
    svc = AutomationService()
    big = lambda name, args, key: asyncio.sleep(0, "x" * 4001)  # noqa: E731
    async def go():
        async def noop(*a): return ("", "completed", None)
        svc.hooks = Hooks(noop, noop, tools=lambda: {"t": {"effect": "read", "allowed": True}}, call_tool=big)
        d = routine("big-result", [{"id": "a", "kind": "tool", "tool": "t", "args": {}}])
        a = await svc.create(d, "ann")
        await svc.propose(a.id, "ann")
        await svc.decide(a.id, True, "ben", None)
        return await svc.run(a.id, "manual", "ann")
    run = asyncio.run(go())
    assert run.status == "stopped" and "4001 characters" in run.error


def test_the_key_of_a_tool_call_is_the_same_whenever_the_step_is_run_again():
    seen = []
    svc = AutomationService()
    async def go():
        async def noop(*a): return ("", "completed", None)
        async def call(name, args, key):
            seen.append(key)
            return {}
        svc.hooks = Hooks(noop, noop, tools=lambda: {"t": {"effect": "read", "allowed": True}}, call_tool=call)
        a = await svc.create(routine("keyed", [{"id": "a", "kind": "tool", "tool": "t", "args": {}}]), "ann")
        await svc.propose(a.id, "ann")
        await svc.decide(a.id, True, "ben", None)
        run = await svc.run(a.id, "manual", "ann")
        return run, await svc.repo.versions(a.id)
    run, versions = asyncio.run(go())
    assert seen == [f"auto:{run.id}:a"]


def test_a_change_made_by_a_routine_is_in_the_audit_log_with_its_run_and_key_and_a_read_is_not():
    app, key, loop = world()
    c, ann, ben, rev = TestClient(app), key("ann", "release_manager"), key("ben", "release_manager"), key("rev", "reviewer")
    refund = {"id": "refund", "kind": "tool", "tool": "issue_refund", "args": {"order_id": "1042", "amount": 20}}
    publish(c, ann, ben, routine("audited", [LOOKUP, ASK, refund]))
    run = loop.run_until_complete(app.state.automations.run("audited", "manual", "ann", json.dumps({"order": "1042"})))
    assert c.post(f"/v1/automation-runs/{run.id}/decision", headers=rev, json={"approve": True}).status_code == 200
    finished(c, run.id, ann)
    entries = [e for e in c.get("/v1/audit?limit=60", headers=ADM).json()["entries"] if e["action"] == "automation.tool"]
    assert len(entries) == 1 and entries[0]["actor"] == "automation" and entries[0]["target"] == "audited:issue_refund"
    assert entries[0]["detail"] == {"run": run.id, "step": "refund", "tool": "issue_refund", "effect": "write", "key": f"auto:{run.id}:refund"}
