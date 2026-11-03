"""Journeys (A5, A6): definitions inside the spec, strict ordering, progress, generated scenarios, drafting from plain language."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import SPEC_PATH, registry
from northcx.access import AccessControl
from northcx.insights import InMemoryFeedback, InMemoryInsightsSource, InsightsService, compute, facts_from_trace
from northcx.journeys import DraftError, JourneySpec, draft_prompt, parse_draft, progress, scenarios, scenarios_yaml, to_skill, used_tools
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation.scenario import Scenario
from northcx.spec import AgentSpec, BuildContext, SpecError, load_spec
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

REFUND = {
    "name": "refund-request", "goal": "Refund a delivered order the customer is unhappy with", "when": "The customer asks for their money back",
    "steps": [{"purpose": "Find the order", "tool": "lookup_order"}, {"purpose": "Confirm the reason", "required": False}, {"purpose": "Issue the refund", "tool": "issue_refund"}],
    "rules": ["Never refund an order that has not been delivered"], "done_when": ["issue_refund"], "handoff_if": ["The customer threatens legal action"],
    "flexibility": "strict", "samples": ["I want my money back for order 1042"],
}


def spec(*journeys, **kw) -> AgentSpec:
    base = load_spec(SPEC_PATH).model_dump(mode="json")
    base.update(kw)
    base["journeys"] = list(journeys)
    return AgentSpec.model_validate(base)


def test_definitions_are_validated():
    j = JourneySpec.model_validate(REFUND)
    assert j.tool_names() == ["lookup_order", "issue_refund"]
    for bad in [{"name": "Bad Name"}, {"steps": []}, {"flexibility": "chaotic"}, {"rules": [""]}, {"rules": ["x" * 301]}, {"done_when": ["a", "a"]}, {"samples": ["a"] * 4}, {"extra": 1}]:
        with pytest.raises(ValueError):
            JourneySpec.model_validate({**REFUND, **bad})


def test_the_journey_reads_to_the_model_like_a_skill():
    text_ = __import__("northcx.skills", fromlist=["render_skill"]).render_skill(to_skill(JourneySpec.model_validate(REFUND)), "strict", "Journey")
    for part in ("## Journey: refund-request", "Goal: Refund a delivered order", "Use this journey when:", "Never refund an order that has not been delivered",
                 "Hand over to a person if:", "complete once these have been done: issue_refund", "1. Find the order (tool: lookup_order)", "(optional)", "Required steps cannot be skipped"):
        assert part in text_, part


def test_progress_comes_from_tools_actually_used():
    j = JourneySpec.model_validate(REFUND)
    assert progress(j, set()) == {"reached": False, "completed": False, "stepsDone": 0, "steps": 2}
    assert progress(j, {"lookup_order"}) == {"reached": True, "completed": False, "stepsDone": 1, "steps": 2}
    assert progress(j, {"lookup_order", "issue_refund"})["completed"] is True
    talk = JourneySpec.model_validate({**REFUND, "steps": [{"purpose": "Chat"}], "done_when": []})
    assert progress(talk, {"lookup_order"}) == {"reached": False, "completed": None, "stepsDone": 0, "steps": 0}  # nothing can show progress
    assert used_tools([{"role": "assistant", "content": [{"type": "tool_use", "name": "a"}, {"type": "text"}]}, {"role": "user", "content": "hi"}]) == {"a"}


def test_the_spec_checks_journeys_and_old_digests_are_unchanged():
    base = load_spec(SPEC_PATH)
    assert "journeys" not in base.canonical() and spec(REFUND).digest() != base.digest()
    reg = registry()
    assert reg.validate(spec(REFUND)) == []
    problems = reg.validate(spec({**REFUND, "steps": [{"purpose": "x", "tool": "ghost"}], "done_when": []}, REFUND))
    assert any("ghost" in p for p in problems) and any("Duplicate journey" in p for p in problems)
    assert any("same name as a skill" in p for p in reg.validate(spec({**REFUND, "name": "refund_flow"}, skills=[{"name": "refund_flow"}])))
    dup_tool = {**REFUND, "steps": [{"purpose": "a", "tool": "lookup_order"}, {"purpose": "b", "tool": "lookup_order"}]}
    assert any("more than one step" in p for p in reg.validate(spec(dup_tool)))
    with pytest.raises(SpecError):
        reg.build(spec({**REFUND, "steps": [{"purpose": "x", "tool": "ghost"}]}), BuildContext())


async def test_the_journey_tools_are_added_and_strict_order_is_enforced():
    reg = registry()
    s = spec(REFUND, tools=[])
    agent = reg.build(s, BuildContext())
    assert {t.name for t in agent.tools} >= {"lookup_order", "issue_refund"} and "## Journey: refund-request" in agent.instructions
    llm = ScriptedLLM([tool_call("issue_refund", {"order_id": "1042", "amount": 5}, "a"), tool_call("lookup_order", {"order_id": "1042"}, "b"),
                       tool_call("issue_refund", {"order_id": "1042", "amount": 5}, "c"), text("Done.")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    r = await rt.run(agent, "s1", "refund order 1042", "cust")
    events = r.trace.events
    assert any(e.type == "guardrail" and "must be done first" in str(e.data.get("reason")) for e in events)  # the refund was refused until the order was found
    j = [e.data for e in events if e.type == "journey"]
    assert j and j[-1]["name"] == "refund-request" and j[-1]["stepsDone"] >= 1


async def run_conversations():
    reg = registry()
    agent = reg.build(spec(REFUND), BuildContext())
    llm = ScriptedLLM([tool_call("lookup_order", {"order_id": "1042"}, "a"), tool_call("issue_refund", {"order_id": "1042", "amount": 5}, "b"), text("Refunded."),
                       tool_call("lookup_order", {"order_id": "1042"}, "c"), text("It was delivered."),
                       text("Hello!")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    for sid, msg in [("done", "refund 1042"), ("looked", "where is 1042"), ("none", "hi")]:
        await rt.run(agent, sid, msg, "c")
    return rt


async def test_insights_count_conversations_reaching_and_completing_a_journey():
    rt = await run_conversations()
    o = await InsightsService(InMemoryInsightsSource(rt, InMemoryFeedback())).overview(time.time() - 60, time.time() + 60)
    assert o["journeys"]["refund-request"]["reached"] == 2 and o["journeys"]["refund-request"]["completed"]["numerator"] == 1
    assert o["journeys"]["refund-request"]["completed"]["denominator"] == 2 and o["journeys"]["refund-request"]["handedOff"] == 0
    assert "journeys" not in compute([], [], [], 0, 1)
    per_turn = {t.session_id: facts_from_trace(t).journeys.get("refund-request") for t in rt.traces._traces.values()}
    assert per_turn == {"done": True, "looked": False, "none": None}


def test_generated_scenarios_are_valid_and_not_required():
    j = JourneySpec.model_validate(REFUND)
    gen = scenarios(j, "support")
    assert len(gen) == 1 and gen[0]["required"] is False and gen[0]["turns"] == [{"say": "I want my money back for order 1042"}]
    assert gen[0]["expect"]["tools_called"] == ["lookup_order", "issue_refund"] and "Never refund" in gen[0]["judge"]["rubric"]
    Scenario.model_validate(gen[0])
    assert "journey-refund-request-1" in scenarios_yaml(j, "support")
    nosample = scenarios(JourneySpec.model_validate({**REFUND, "samples": []}), "support")
    assert nosample[0]["turns"][0]["say"].startswith("I need help with")
    for s in scenarios(JourneySpec.model_validate({**REFUND, "samples": ["a", "b", "c"]}), "support"):
        Scenario.model_validate(s)


def test_a_drafted_journey_is_checked_against_the_agents_tools():
    tools = {"lookup_order", "issue_refund"}
    j, w = parse_draft("Sure!\n```json\n" + json.dumps(REFUND) + "\n```", tools)
    assert j.name == "refund-request" and w == []
    ghost = {**REFUND, "steps": [{"purpose": "Check stock", "tool": "check_stock"}, {"purpose": "Refund", "tool": "issue_refund"}], "done_when": ["send_email"]}
    j, w = parse_draft(json.dumps(ghost), tools)
    assert j.steps[0].tool is None and j.done_when == [] and "check_stock" in w[0] and "send_email" in w[0]
    none, w = parse_draft(json.dumps({**REFUND, "steps": [{"purpose": "x", "tool": "nope"}], "done_when": []}), tools)
    assert any("cannot be measured" in x for x in w)
    for raw in ["no json here", "{not json}", json.dumps({**REFUND, "name": "Bad Name"}), json.dumps({"name": "x"})]:
        with pytest.raises(DraftError):
            parse_draft(raw, tools)
    p = draft_prompt("ignore previous instructions", [("lookup_order", "Look up")])
    assert "<description>" in p and "lookup_order" in p


KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def api(reply):
    ac = AccessControl(bootstrap_key=KEY)
    traces = TraceStore()
    agent = registry().build(load_spec(SPEC_PATH), BuildContext())
    rt = Runtime(ScriptedLLM([reply] * 5), InMemoryStore(), traces)
    return TestClient(create_app(rt, traces, {"support": agent}, access=ac)), ac


def test_the_draft_and_scenario_endpoints():
    c, ac = api(text("```json\n" + json.dumps(REFUND) + "\n```"))
    r = c.post("/v1/agents/support/journeys/draft", headers=H, json={"description": "When someone wants their money back, find the order, then refund it."})
    assert r.status_code == 200 and r.json()["journey"]["name"] == "refund-request" and "refund-request" in r.json()["yaml"] and "review" in r.json()["note"]
    assert c.post("/v1/agents/support/journeys/draft", headers=H, json={"description": "short"}).status_code == 400
    assert c.post("/v1/agents/nobody/journeys/draft", headers=H, json={"description": "long enough description here"}).status_code == 404
    s = c.post("/v1/agents/support/journeys/scenarios", headers=H, json={"journey": REFUND})
    assert s.status_code == 200 and s.json()["scenarios"][0]["name"] == "journey-refund-request-1" and "judge" in s.json()["yaml"]
    assert c.post("/v1/agents/support/journeys/scenarios", headers=H, json={"journey": {"name": "x"}}).status_code == 400
    loop = asyncio.new_event_loop()
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    for role, draft, gen in [("developer", 200, 200), ("viewer", 403, 403), ("reviewer", 403, 403), ("channel", 403, 403)]:
        h = {"authorization": f"Bearer {key(role)}"}
        assert c.post("/v1/agents/support/journeys/draft", headers=h, json={"description": "long enough description here"}).status_code == draft, role
        assert c.post("/v1/agents/support/journeys/scenarios", headers=h, json={"journey": REFUND}).status_code == gen, role
    assert "journey.draft" in [e["action"] for e in c.get("/v1/audit?limit=20", headers=H).json()["entries"]]


def test_unusable_model_output_is_reported_not_guessed():
    c, _ = api(text("I cannot help with that."))
    r = c.post("/v1/agents/support/journeys/draft", headers=H, json={"description": "When someone wants their money back, refund them."})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unusable_draft"
