"""Multi-agent routing (R8): transfers to specialists, stickiness, limits, erasure, validation, simulations."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import SPEC_PATH, support_agent
from northcx.agent import Agent
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.spec import AgentSpec, load_spec
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.transfers import (MAX_TRANSFERS_PER_TURN, TRANSFER, InMemorySessionRoutes, RouteSpec, check_routes, handover_note, transfer_spec)


def tool_results(llm):
    """Every tool result the model was shown (the request objects share the live message list, so look at the fullest one)."""
    return " ".join(str(b.get("content")) for m in llm.requests[-1].messages if isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_result")


def route(agent="billing", when="questions about refunds and charges"):
    return RouteSpec(agent=agent, when=when)


def triage(*routes):
    return Agent(id="triage", instructions="You are the front desk. Send refund questions to billing.", routes=list(routes or [route()]))


def billing():
    return dataclasses.replace(support_agent(), id="billing", instructions="You are the billing specialist.")


def world(script, *extra):
    llm = ScriptedLLM(list(script))
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    known = {"triage": triage(), "billing": billing(), **{a.id: a for a in extra}}

    async def resolver(agent_id, environment, session_id):
        return known.get(agent_id)
    rt.agent_resolver = resolver
    return llm, rt, known


def test_routes_are_validated_and_described_to_the_model():
    spec = transfer_spec([route(), route("shipping", "where is my parcel")])
    assert spec["name"] == TRANSFER and spec["input_schema"]["properties"]["agent"]["enum"] == ["billing", "shipping"]
    assert "refunds and charges" in spec["description"] and "where is my parcel" in spec["description"]
    assert check_routes("triage", [route(), route()]) == ["The same specialist is listed more than once. Remove the repeats so each specialist appears once."] and check_routes("billing", [route()]) == ["An agent cannot hand a conversation to itself. Remove this agent from its own list of specialists."]
    for bad in ({"agent": "bad agent!", "when": "x"}, {"agent": "billing", "when": ""}, {"agent": "billing", "when": "x" * 301}, {"agent": "b", "when": "x", "extra": 1}):
        with pytest.raises(ValueError):
            RouteSpec.model_validate(bad)
    assert "'triage' agent" in handover_note("triage", "refund")


def test_specs_with_routes_have_new_digests_but_old_digests_are_unchanged():
    base = load_spec(SPEC_PATH)
    assert "routes" not in base.canonical()
    data = base.model_dump(mode="json")
    data["routes"] = [{"agent": "billing", "when": "refunds"}]
    assert AgentSpec.model_validate(data).digest() != base.digest()
    data["routes"] = [{"agent": base.id, "when": "myself"}]
    from examples.support_agent import registry
    assert any("cannot hand a conversation to itself" in p for p in registry().validate(AgentSpec.model_validate(data)))


async def test_the_conversation_moves_to_the_specialist_in_the_same_turn():
    llm, rt, known = world([tool_call(TRANSFER, {"agent": "billing", "reason": "wants a refund"}, "t"), text("I can help with that refund.")])
    r = await rt.run(known["triage"], "s1", "I was charged twice")
    assert (r.reply, r.status) == ("I can help with that refund.", "completed")
    first, second = llm.requests
    assert "front desk" in first.system and any(t["name"] == TRANSFER for t in first.tools)
    assert "billing specialist" in second.system and "front desk" not in second.system and "passed to you from the 'triage' agent" in second.system and "wants a refund" in second.system
    assert not any(t["name"] == TRANSFER for t in second.tools) and any(t["name"] == "lookup_order" for t in second.tools)  # the specialist's own tools
    ev = [e for e in r.trace.events if e.type == "transfer"]
    assert len(ev) == 1 and ev[0].data == {"from": "triage", "to": "billing", "reason": "wants a refund"} and r.trace.agent_id == "billing"
    assert await rt.routes.get("s1") == "billing"
    assert (await rt.active_agent(known["triage"], "s1")).id == "billing"      # later messages go to the specialist
    assert (await rt.active_agent(known["triage"], "other")).id == "triage"     # other conversations are untouched


async def test_a_transfer_the_agent_may_not_make_is_refused_and_the_conversation_stays_put():
    llm, rt, known = world([tool_call(TRANSFER, {"agent": "ghost", "reason": "x"}, "t"), text("Let me handle it myself.")])
    r = await rt.run(known["triage"], "s1", "hi")
    assert r.reply == "Let me handle it myself." and r.trace.agent_id == "triage" and not [e for e in r.trace.events if e.type == "transfer"]
    assert "not available" in tool_results(llm) and await rt.routes.get("s1") is None


async def test_an_unavailable_specialist_is_reported_to_the_model():
    llm, rt, known = world([tool_call(TRANSFER, {"agent": "billing", "reason": "x"}, "t"), text("Sorry, I'll help directly.")])
    async def none(*a):
        return None
    rt.agent_resolver = none
    r = await rt.run(known["triage"], "s1", "hi")
    assert r.status == "completed" and "not available" in tool_results(llm) and await rt.routes.get("s1") is None
    rt.agent_resolver = None
    llm2 = ScriptedLLM([tool_call(TRANSFER, {"agent": "billing", "reason": "x"}, "t"), text("ok")])
    rt.llm = llm2
    assert (await rt.run(known["triage"], "s2", "hi")).status == "completed"


async def test_agents_cannot_hand_a_conversation_back_and_forth_forever():
    a = dataclasses.replace(triage(route("billing")), id="a")
    b = dataclasses.replace(billing(), id="b", routes=[route("a", "anything")])
    a.routes = [route("b", "anything")]
    script = [tool_call(TRANSFER, {"agent": "b" if i % 2 == 0 else "a", "reason": "pass it on"}, f"t{i}") for i in range(MAX_TRANSFERS_PER_TURN + 1)] + [text("Done.")]
    llm, rt, known = world(script, a, b)
    r = await rt.run(a, "s1", "hi")
    assert r.reply == "Done." and len([e for e in r.trace.events if e.type == "transfer"]) == MAX_TRANSFERS_PER_TURN
    assert "cannot be passed on again" in tool_results(llm)


async def test_the_specialists_own_checks_apply_after_a_transfer():
    llm, rt, known = world([tool_call(TRANSFER, {"agent": "billing", "reason": "refund"}, "t"), text("Your card is 4111 1111 1111 1111."), text("Your refund is on its way.")])
    r = await rt.run(known["triage"], "s1", "refund please")
    assert r.reply == "Your refund is on its way." and any(e.type == "guardrail" and e.data["guardrail"] == "no-card-numbers" for e in r.trace.events)


@pytest.fixture(params=["memory", "postgres"])
def session_routes(request):
    if request.param == "memory":
        return InMemorySessionRoutes()
    from northcx.db import PgSessionRoutes
    return PgSessionRoutes(request.getfixturevalue("engine"))


async def test_session_route_repository_contract(session_routes):
    assert await session_routes.get("s1") is None
    await session_routes.set("s1", "billing")
    await session_routes.set("s1", "shipping")
    await session_routes.set("s2", "billing")
    assert await session_routes.get("s1") == "shipping" and await session_routes.get("s2") == "billing"
    assert await session_routes.erase_session("s1") == 1 and await session_routes.erase_session("s1") == 0 and await session_routes.get("s1") is None


KEY = "boot" * 10


def test_through_the_api_later_messages_reach_the_specialist_and_erasure_clears_the_route():
    llm = ScriptedLLM([tool_call(TRANSFER, {"agent": "billing", "reason": "refund"}, "t"), text("Billing here."), text("Still billing.")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"triage": triage(), "billing": billing()}))
    post = lambda msg: c.post("/v1/agents/triage/chat", json={"sessionId": "w1", "message": msg, "customerId": "cu"}).json()  # noqa: E731
    assert post("I was charged twice")["reply"] == "Billing here."
    assert post("and again?")["reply"] == "Still billing." and "billing specialist" in llm.requests[-1].system and "front desk" not in llm.requests[-1].system
    traces = c.get("/v1/traces").json()["traces"]
    assert {t["agentId"] for t in traces} == {"billing"}
    c.delete("/v1/privacy/customers/cu")
    assert rt.routes.items == {}


async def test_the_publish_check_rejects_a_route_to_an_agent_that_does_not_exist():
    from northcx.versions import InMemoryReleases, InMemoryVersions
    from tests.test_versions import Env
    env = Env(InMemoryVersions(), InMemoryReleases())
    data = load_spec(SPEC_PATH).model_dump(mode="json")
    data["routes"] = [{"agent": "ghost", "when": "anything"}]
    out = await env.svc.preview("support", data)
    assert out["valid"] is False and any("specialist called 'ghost'" in p for p in out["problems"])
    data["routes"] = []
    assert (await env.svc.preview("support", data))["valid"] is True


async def test_simulations_can_test_a_transfer():
    from northcx.simulation.runner import SimConfig, SimulationRunner
    from northcx.simulation.scenario import Scenario
    known = {"triage": triage(), "billing": billing()}
    sc = Scenario.model_validate({
        "name": "refund-goes-to-billing", "agent": "triage",
        "model": [{"tool_call": {"name": TRANSFER, "input": {"agent": "billing", "reason": "refund"}}}, {"text": "Billing here, I can refund that."},
                  {"text": "Anything else on billing?"}],
        "turns": [{"say": "I was charged twice", "expect": {"reply_includes": ["Billing here"]}}, {"say": "thanks", "expect": {"reply_includes": ["billing"]}}]})
    suite = await SimulationRunner(lambda aid, llm: known[aid], SimConfig("scripted")).run_suite([sc])
    assert suite.passed, suite.results[0].trials[0].failures
