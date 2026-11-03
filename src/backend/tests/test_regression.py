"""Scenario drafts from real conversations, and re-running simulations after knowledge changes."""
import asyncio
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.knowledge import Source
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.monitor import InMemoryMonitor
from northcx.regression import RegressionRunner, scenario_from_traces
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, run_scenarios, load_scenarios
from northcx.simulation.scenario import ScenarioError, parse_scenario
from northcx.store import InMemoryStore
from northcx.trace import Trace, TraceStore


async def record(script, messages, customer=None, session="web-abc12345"):
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    results = []
    for m in messages:
        results.append(await rt.run(support_agent(), session, m, customer))
    traces = [t for t in [await rt.traces.get(s.id) for s in await rt.traces.summaries(session, 50)] if t is not None]
    return traces, results, rt


async def replay(draft):
    sc = parse_scenario(draft.scenario, "draft")
    suite = await run_scenarios([sc], lambda aid, llm: support_agent())
    return suite


async def test_a_recorded_conversation_becomes_a_scenario_that_replays_and_passes():
    traces, _, _ = await record([tool_call("lookup_order", {"order_id": "1042"}, "t1"), text("Order 1042 was delivered."), text("Happy to help with anything else.")],
                                ["Where is order 1042?", "thanks!"])
    d = scenario_from_traces(traces, "web-abc12345")
    sc = d.scenario
    assert sc["name"] == "regression-abc12345" and sc["agent"] == "support" and sc["required"] is False and "regression" in sc["tags"]
    assert [t["say"] for t in sc["turns"]] == ["Where is order 1042?", "thanks!"]
    assert sc["turns"][0]["expect"] == {"status": "completed", "tools_called": ["lookup_order"]} and sc["turns"][1]["expect"] == {"status": "completed"}
    assert sc["model"] == [{"tool_call": {"name": "lookup_order", "input": {"order_id": "1042"}}}, {"text": "Order 1042 was delivered."}, {"text": "Happy to help with anything else."}]
    assert yaml.safe_load(d.yaml) == sc and d.warnings == []
    suite = await replay(d)
    assert suite.results[0].passed, suite.results[0].failures


async def test_drafts_catch_a_regression_when_the_agent_changes():
    traces, _, _ = await record([tool_call("lookup_order", {"order_id": "1042"}, "t1"), text("Delivered.")], ["Where is order 1042?"])
    d = scenario_from_traces(traces, "web-aaaa1111")
    from northcx.policies import ForbiddenPhrases
    agent = support_agent()
    agent.guardrails.append(ForbiddenPhrases(["delivered"]))  # someone added a policy that the recorded answer now violates
    suite = await run_scenarios([parse_scenario(d.scenario, "draft")], lambda aid, llm: agent)
    assert not suite.results[0].passed


async def test_personal_data_is_masked_in_drafts():
    traces, _, _ = await record([text("We have jane@example.com on file, call 415-555-0199.")], ["I'm jane@example.com, my number is 415-555-0199"])
    d = scenario_from_traces(traces, "web-pii00000")
    assert "jane@example.com" not in d.yaml and "415-555-0199" not in d.yaml


async def test_hand_offs_guardrails_and_held_approvals_are_described_and_flagged():
    traces, results, _ = await record([tool_call("handoff_to_human", {"reason": "wants a person"}, "t1")], ["let me talk to a person"])
    d = scenario_from_traces(traces, "web-handoff1")
    assert d.scenario["turns"][0]["expect"] == {"status": "escalated", "handoff": {}} and d.scenario["model"] == [{"tool_call": {"name": "handoff_to_human", "input": {"reason": "wants a person"}}}]
    traces, _, _ = await record([tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1")], ["refund 240 on order 2077"])
    d = scenario_from_traces(traces, "web-approval")
    assert d.scenario["turns"][0]["expect"]["status"] == "needs_approval" and any("decide" in w for w in d.warnings)
    assert (await replay(d)).results[0].passed


async def test_rejected_drafts_and_empty_sessions_are_reported_honestly():
    traces, _, _ = await record([text("Your card 4111 1111 1111 1111 is fine."), text("Your order is fine.")], ["status?"])
    d = scenario_from_traces(traces, "web-reject01")
    assert any("rejected or rewritten" in w for w in d.warnings) and d.scenario["turns"][0]["expect"]["guardrail_hits"] == ["no-card-numbers"]
    with pytest.raises(ScenarioError, match="no recorded turns"):
        scenario_from_traces([], "x")
    t = Trace("support", "s")
    t.add("system", message="[system] approval done")
    with pytest.raises(ScenarioError, match="no customer messages"):
        scenario_from_traces([t], "s")


async def test_turns_by_other_agents_are_left_out():
    traces, _, _ = await record([text("a")], ["hello"])
    other = Trace("billing", "web-abc12345")
    other.add("user", message="hi")
    other.add("reply", reply="x", status="completed")
    d = scenario_from_traces(traces + [other], "web-abc12345")
    assert len(d.scenario["turns"]) == 1 and any("another agent" in w for w in d.warnings)


# ---- re-running after knowledge changes ----
SCEN = [parse_scenario({"name": "kb-answer", "agent": "support", "tags": ["knowledge"], "model": [{"text": "Refunds take 5 days."}],
                        "turns": [{"say": "how long do refunds take?", "expect": {"reply_includes": ["5 days"]}}]}, "t"),
        parse_scenario({"name": "other", "agent": "support", "model": [{"text": "hi"}], "turns": [{"say": "hello", "expect": {"status": "completed"}}]}, "t")]


def sim(scenarios=None, bad=False):
    sc = scenarios or SCEN
    if bad:
        sc = [parse_scenario({**s.model_dump(mode="json", exclude={"source"}), "model": [{"text": "I don't know."}]}, "t") if s.name == "kb-answer" else s for s in sc]
    return SimulationService(sc, lambda aid, llm: support_agent(), InMemorySimRuns(), {"support": "d"})


def test_tags_filter_scenarios_and_do_not_change_digests():
    a = SCEN[0]
    b = parse_scenario({**a.model_dump(mode="json", exclude={"source"}), "tags": ["knowledge", "extra"]}, "t")
    assert a.digest() == b.digest() and a.tags == ["knowledge"]


async def test_only_tagged_scenarios_run_and_a_pass_is_recorded():
    s, mon = sim(), InMemoryMonitor()
    rr = RegressionRunner(s, mon, "scripted", debounce=0.01)
    last = await rr.run_now(["document help/returns updated"])
    assert last["ok"] is True and last["scenarios"] == 1 and last["failed"] == [] and await mon.list() == []
    run = (await s.runs.list())[0]
    assert run.source == "regression" and run.meta["trigger"] == "knowledge" and [r["name"] for r in run.results] == ["kb-answer"]


async def test_a_failing_rerun_raises_a_critical_finding():
    s, mon = sim(bad=True), InMemoryMonitor()
    last = await RegressionRunner(s, mon, "scripted").run_now(["source help deleted"])
    assert last["ok"] is False and last["failed"] == ["kb-answer"]
    f = (await mon.list())[0]
    assert (f.rule, f.severity) == ("regression_failed", "critical") and "1 of 1" in f.detail and "source help deleted" in f.detail


async def test_nothing_tagged_or_a_busy_runner_is_reported_not_raised():
    untagged = sim([SCEN[1]])
    last = await RegressionRunner(untagged, InMemoryMonitor()).run_now(["x"])
    assert last["ok"] is None and "tagged" in last["note"]
    with pytest.raises(ValueError):
        RegressionRunner(sim(), InMemoryMonitor(), "demo")


async def test_changes_close_together_make_one_run_and_a_change_during_a_run_makes_one_more():
    s, mon = sim(), InMemoryMonitor()
    calls = []
    orig = s.run

    async def slow(*a, **k):
        calls.append(k["meta"]["reasons"])
        await asyncio.sleep(0.15)
        return await orig(*a, **k)

    s.run = slow
    rr = RegressionRunner(s, mon, "scripted", debounce=0.05)
    for i in range(5):
        rr.trigger(f"doc {i}")
    assert rr.status()["pending"] is True
    await asyncio.sleep(0.12)  # the run has started
    rr.trigger("late change")
    await asyncio.sleep(0.8)
    assert len(calls) == 2 and calls[0] == [f"doc {i}" for i in range(5)] and calls[1] == ["late change"]
    assert rr.status()["pending"] is False and rr.status()["last"]["ok"] is True


# ---- API ----
KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def test_api_draft_endpoint_and_permissions():
    rt = Runtime(ScriptedLLM([text("Hello jane@example.com")]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    c.post("/v1/agents/support/chat", json={"sessionId": "web-draft001", "message": "hi, I'm jane@example.com"}, headers=H)
    r = c.get("/v1/sessions/web-draft001/scenario-draft", headers=H)
    assert r.status_code == 200 and "jane@example.com" not in r.text and r.json()["scenario"]["turns"][0]["expect"]["status"] == "completed"
    assert yaml.safe_load(r.json()["yaml"])["agent"] == "support"
    assert c.get("/v1/sessions/nope/scenario-draft", headers=H).status_code == 404
    loop = asyncio.new_event_loop()
    for role, code in [("developer", 200), ("viewer", 403), ("reviewer", 403), ("channel", 403)]:
        k = loop.run_until_complete(ac.issue(role, role, "root"))[1]
        assert c.get("/v1/sessions/web-draft001/scenario-draft", headers={"authorization": f"Bearer {k}"}).status_code == code, role
    assert "scenario.draft" in {e["action"] for e in c.get("/v1/audit?limit=20", headers=H).json()["entries"]}


async def test_api_knowledge_changes_trigger_a_rerun_and_status_is_visible():
    s, mon = sim(), InMemoryMonitor()
    rr = RegressionRunner(s, mon, "scripted", debounce=0.01)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, api_key=KEY, regression=rr))
    assert c.get("/v1/regression", headers=H).json()["last"] is None
    c.post("/v1/knowledge/sources", json={"id": "help", "name": "Help"}, headers=H)
    c.put("/v1/knowledge/sources/help/documents/r", json={"title": "Returns", "text": "Refunds take 5 days"}, headers=H)
    c.put("/v1/knowledge/sources/help/documents/r", json={"title": "Returns", "text": "Refunds take 5 days"}, headers=H)  # unchanged: no trigger
    assert rr.reasons == {"document help/r created"}
    off = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {"support": support_agent()}))
    assert off.get("/v1/regression").json() == {"enabled": False}
