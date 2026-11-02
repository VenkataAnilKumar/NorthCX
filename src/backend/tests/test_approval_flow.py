"""Approval resume: exactly-once execution, outcomes reach the agent and customer, expiry escalates."""
import asyncio
import json

import pytest
from pydantic import BaseModel

from northcx.agent import Agent, Tool
from northcx.approval_flow import ApprovalFlow
from northcx.guardrails import Guardrail, Verdict
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.outbox import Outbox
from northcx.runtime import Runtime
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from tests.test_runtime import valid_history


class Amount(BaseModel):
    amount: float


class Calls:
    def __init__(self):
        self.keys: list = []
        self.fail = False


@pytest.fixture(params=["memory", "postgres"])
def env(request):
    """A runtime wired to memory or Postgres stores, a tool-call recorder, and a way to script the model."""
    kind = request.param
    if kind == "memory":
        from northcx.approvals import ApprovalStore

        stores = dict(store=InMemoryStore(), traces=TraceStore(), approvals=ApprovalStore(), outbox=Outbox())
    else:
        from northcx.db import PgApprovalStore, PgMemoryStore, PgOutbox, PgTraceStore

        eng = request.getfixturevalue("engine")
        stores = dict(store=PgMemoryStore(eng), traces=PgTraceStore(eng), approvals=PgApprovalStore(eng), outbox=Outbox(PgOutbox(eng)))
    calls = Calls()

    def refund(d: Amount, ctx):
        calls.keys.append(ctx.idempotency_key)
        if calls.fail:
            raise RuntimeError("payment provider down")
        return {"refunded": d.amount}

    tool = Tool("refund", "refund", Amount, refund, requires_approval=lambda d: "over limit" if d.amount > 100 else None)

    def make(script, guardrails=None):
        llm = ScriptedLLM(script)
        rt = Runtime(llm, stores["store"], stores["traces"], stores["approvals"], stores["outbox"])
        agent = Agent(id="a", instructions="help", tools=[tool], guardrails=guardrails or [])
        return llm, rt, agent, ApprovalFlow(rt), {"a": agent}

    return make, calls, stores


async def held(env_, extra=None, guardrails=None):
    make, calls, stores = env_
    llm, rt, agent, flow, agents = make([tool_call("refund", {"amount": 500}, "t1")] + (extra or [text("Your refund went through.")]), guardrails)
    r = await rt.run(agent, "s", "refund 500", "cust")
    assert r.status == "needs_approval"
    return llm, rt, agent, flow, agents, r.pending_approvals[0]["id"], calls


async def test_approval_executes_once_and_the_customer_is_told(env):
    llm, rt, agent, flow, agents, aid, calls = await held(env)
    res = await flow.resolve(agents, aid, True, "rae", "looks fine")
    assert res.error is None and res.run.status == "completed" and res.run.reply == "Your refund went through."
    assert calls.keys == [aid]  # executed once, with the approval id as idempotency key
    a = await rt.approvals.get(aid)
    assert (a.state, a.decided_by, a.note, a.result) == ("executed", "rae", "looks fine", {"result": {"refunded": 500.0}})
    assert valid_history(await rt.store.load_messages("s"))
    assert (await rt.store.load_messages("s"))[-1]["role"] == "assistant"
    assert "Outcome" in str(llm.requests[1].messages) and "500" in str(llm.requests[1].messages)
    msgs = await rt.outbox.list("s")
    assert [m.kind for m in msgs] == ["approval_result"]
    assert msgs[0].payload["reply"] == "Your refund went through." and msgs[0].payload["approved"] is True
    assert any(e.type == "system" for e in res.run.trace.events)


async def test_second_decision_never_executes_again(env):
    _, rt, _, flow, agents, aid, calls = await held(env)
    await flow.resolve(agents, aid, True, "rae")
    with pytest.raises(ValueError):
        await flow.resolve(agents, aid, True, "someone-else")
    with pytest.raises(ValueError):
        await flow.resolve(agents, aid, False, "someone-else")
    assert len(calls.keys) == 1
    with pytest.raises(KeyError):
        await flow.resolve(agents, "missing", True, "rae")


async def test_concurrent_decisions_execute_exactly_once(env):
    _, _, _, flow, agents, aid, calls = await held(env, extra=[text("ok")] * 6)
    results = await asyncio.gather(*[flow.resolve(agents, aid, i % 2 == 0, f"u{i}") for i in range(6)], return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert len(calls.keys) <= 1


async def test_rejection_does_not_execute_and_the_agent_explains(env):
    llm, rt, _, flow, agents, aid, calls = await held(env, extra=[text("A teammate declined; can I help another way?")])
    res = await flow.resolve(agents, aid, False, "rae", "amount too high")
    assert calls.keys == [] and res.run.reply.startswith("A teammate declined")
    assert (await rt.approvals.get(aid)).state == "rejected"
    sent = str(llm.requests[1].messages)
    assert "declined" in sent and "amount too high" in sent
    assert (await rt.outbox.list("s"))[0].payload["approved"] is False
    assert valid_history(await rt.store.load_messages("s"))


async def test_a_failing_tool_is_recorded_and_reported_to_the_agent(env):
    make, calls, stores = env
    calls.fail = True
    llm, rt, _, flow, agents, aid, _ = await held(env, extra=[text("Sorry, the refund failed; a teammate will follow up.")])
    res = await flow.resolve(agents, aid, True, "rae")
    a = await rt.approvals.get(aid)
    assert a.state == "failed" and "payment provider down" in json.dumps(a.result)
    assert "payment provider down" in str(llm.requests[1].messages)
    assert res.run.status == "completed"


async def test_supervisors_are_rechecked_at_execution_time(env):
    class Blocking(Guardrail):
        name = "freeze"
        frozen = False

        async def check_tool_call(self, name, input, ctx):
            return Verdict.deny("refunds are frozen") if self.frozen else Verdict.ok()

    g = Blocking()
    llm, rt, _, flow, agents, aid, calls = await held(env, extra=[text("Refunds are paused right now.")], guardrails=[g])
    g.frozen = True  # policy changed while the approval was waiting
    await flow.resolve(agents, aid, True, "rae")
    a = await rt.approvals.get(aid)
    assert a.state == "failed" and "frozen" in json.dumps(a.result) and calls.keys == []


async def test_input_that_is_no_longer_valid_is_not_executed(env):
    _, rt, _, flow, agents, aid, calls = await held(env, extra=[text("I couldn't process that.")])
    agents["a"].tools[0].input_model = type("Strict", (BaseModel,), {"__annotations__": {"amount": float, "reason": str}})
    await flow.resolve(agents, aid, True, "rae")
    assert (await rt.approvals.get(aid)).state == "failed" and calls.keys == []


async def test_missing_agent_is_reported_without_executing(env):
    _, rt, _, flow, _, aid, calls = await held(env)
    res = await flow.resolve({}, aid, True, "rae")
    assert res.run is None and "not available" in res.error and calls.keys == []
    assert (await rt.approvals.get(aid)).state == "failed"


async def test_a_follow_up_can_need_another_approval(env):
    _, rt, _, flow, agents, aid, _ = await held(env, extra=[tool_call("refund", {"amount": 700}, "t2")])
    res = await flow.resolve(agents, aid, True, "rae")
    assert res.run.status == "needs_approval" and len(await rt.approvals.list("pending")) == 1
    assert (await rt.outbox.list("s"))[0].payload["status"] == "needs_approval"


async def test_model_failure_after_the_action_still_records_the_outcome(env):
    def boom(req):
        raise RuntimeError("model down")

    _, rt, _, flow, agents, aid, calls = await held(env, extra=[boom])
    res = await flow.resolve(agents, aid, True, "rae")
    assert (await rt.approvals.get(aid)).state == "executed" and len(calls.keys) == 1
    assert res.run.status == "escalated"  # the run itself degrades to a handoff instead of crashing


async def test_stale_approvals_expire_and_escalate(env):
    _, rt, _, flow, agents, aid, calls = await held(env)
    created = (await rt.approvals.get(aid)).created_at
    assert await flow.expire_stale(agents, 3600, now=created + 60) == []  # not stale yet
    done = await flow.expire_stale(agents, 3600, now=created + 3601)
    assert [a.id for a in done] == [aid]
    assert (await rt.approvals.get(aid)).state == "expired"
    hist = await rt.store.load_messages("s")
    assert valid_history(hist) and hist[-1]["role"] == "assistant" and "connecting you with a person" in hist[-1]["content"]
    msg = (await rt.outbox.list("s"))[0]
    assert (msg.kind, msg.payload["status"]) == ("approval_expired", "escalated")
    trace = await rt.traces.get(msg.payload["traceId"])
    assert any(e.type == "handoff" for e in trace.events)
    assert await flow.expire_stale(agents, 3600, now=created + 9999) == []  # idempotent
    with pytest.raises(ValueError):
        await flow.resolve(agents, aid, True, "rae")  # too late
    assert calls.keys == []


async def test_an_approval_decided_just_before_expiry_is_not_expired(env):
    _, rt, _, flow, agents, aid, _ = await held(env)
    created = (await rt.approvals.get(aid)).created_at
    await flow.resolve(agents, aid, True, "rae")
    assert await flow.expire_stale(agents, 1, now=created + 1000) == []
    assert (await rt.approvals.get(aid)).state == "executed"
