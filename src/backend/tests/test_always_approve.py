"""approvals.always: tools that always wait for a person, whatever the tool's own rule says."""
import asyncio

import pytest
from pydantic import BaseModel

from examples.support_agent import support_agent
from northcx.agent import Agent, Tool
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.spec import AgentSpec, Registry
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


class Amount(BaseModel):
    order_id: str
    amount: float


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def registry(calls):
    r = Registry()
    r.add_tools("registry", [Tool("issue_refund", "Refund an order", Amount, lambda d, c: calls.append(d.amount) or {"ok": True}, effect="write"),
                             Tool("lookup_order", "Look up an order", Amount, lambda d, c: {"status": "delivered"}, effect="read")])
    return r


def spec(**kw):
    return AgentSpec(id="a", instructions="help", tools=["lookup_order", "issue_refund"], **kw)


def test_the_field_defaults_to_nothing_and_does_not_change_old_digests():
    assert spec().approvals.always == []
    assert spec().digest() == spec(approvals={"always": []}).digest()
    assert spec().digest() != spec(approvals={"always": ["issue_refund"]}).digest()
    assert "approvals" not in spec().canonical()


def test_a_listed_tool_must_be_one_the_agent_has():
    r = registry([])
    assert r.validate(spec(approvals={"always": ["issue_refund"]})) == []
    problems = r.validate(spec(approvals={"always": ["delete_everything"]}))
    assert len(problems) == 1 and "delete_everything" in problems[0] and "OK" in problems[0]
    assert r.build(spec(approvals={"always": ["issue_refund"]})).always_approve == ["issue_refund"]


def test_a_listed_tool_waits_for_a_person_even_when_its_own_rule_would_let_it_run():
    calls = []
    agent = registry(calls).build(spec(approvals={"always": ["issue_refund"]}))
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "1", "amount": 5}, "t1")]), InMemoryStore(), TraceStore())
    r = run(rt.run(agent, "s", "refund 5", "c"))
    assert r.status == "needs_approval" and calls == []
    (a,) = run(rt.approvals.list("pending"))
    assert a.tool == "issue_refund" and "always need a person" in a.reason


def test_a_tool_that_is_not_listed_runs_as_before_and_a_read_is_never_held():
    calls = []
    agent = registry(calls).build(spec())
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "1", "amount": 5}, "t1"), text("Done.")]), InMemoryStore(), TraceStore())
    r = run(rt.run(agent, "s", "refund 5", "c"))
    assert r.status == "completed" and calls == [5.0]
    listed = registry([]).build(spec(approvals={"always": ["issue_refund"]}))
    rt2 = Runtime(ScriptedLLM([tool_call("lookup_order", {"order_id": "1", "amount": 0}, "t1"), text("Delivered.")]), InMemoryStore(), TraceStore())
    assert run(rt2.run(listed, "s", "where?", "c")).status == "completed"
