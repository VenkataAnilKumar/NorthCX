"""Edit a customer message and run the conversation again from there, in a sandbox: nothing is saved, sent or executed for real."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.agent import Agent, Tool
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.rerun import customer_turns, original_reply
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10


class Amount(BaseModel):
    order_id: str
    amount: float


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def setup(script, agent=None):
    llm = ScriptedLLM(script)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": agent or support_agent()}, access=ac)), ac, rt, llm


def H(t=KEY):
    return {"authorization": f"Bearer {t}"}


def chat(c, msg, session="s1"):
    return c.post("/v1/agents/support/chat", json={"sessionId": session, "message": msg}, headers=H()).json()


def rerun(c, turn, message, session="s1", headers=None):
    return c.post(f"/v1/sessions/{session}/rerun", json={"turn": turn, "message": message}, headers=H() if headers is None else headers)


# ---- the message arithmetic ----
def test_customer_turns_skip_tool_results_and_system_notes_and_the_reply_is_the_last_thing_said_before_the_next_customer_message():
    msgs = [{"role": "user", "content": "one"}, {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "x", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "{}"}]}, {"role": "assistant", "content": [{"type": "text", "text": "answer one"}]},
            {"role": "user", "content": "[system] A teammate approved it."}, {"role": "assistant", "content": "told them"},
            {"role": "user", "content": "two"}, {"role": "assistant", "content": "answer two"}]
    assert customer_turns(msgs) == [0, 6]
    assert original_reply(msgs, 0) == "told them" and original_reply(msgs, 6) == "answer two"
    assert original_reply([{"role": "user", "content": "unanswered"}], 0) is None


# ---- the sandbox ----
def test_the_edited_message_is_answered_with_the_history_before_it_and_nothing_is_saved():
    c, _, rt, llm = setup([text("It is on its way."), text("Original answer."), text("Rerun answer.")])
    chat(c, "where is my order?")
    chat(c, "can you cancel it?")
    saved_messages = run(rt.store.load_messages("s1"))
    traces_before = len(run(rt.traces.summaries("s1", 50)))
    r = rerun(c, 2, "can you change the address?")
    assert r.status_code == 200
    out = r.json()
    assert out["turn"] == 2 and out["original"] == {"message": "can you cancel it?", "reply": "Original answer."}
    assert out["rerun"]["message"] == "can you change the address?" and out["rerun"]["reply"] == "Rerun answer." and out["rerun"]["status"] == "completed" and out["sandbox"] is True
    sent = json.dumps(llm.requests[-1].messages)
    assert "where is my order?" in sent and "It is on its way." in sent and "can you change the address?" in sent and "can you cancel it?" not in sent and "Original answer." not in sent
    assert run(rt.store.load_messages("s1")) == saved_messages                           # the conversation is untouched
    assert len(run(rt.traces.summaries("s1", 50))) == traces_before and run(rt.outbox.list("s1")) == []
    assert run(rt.approvals.list()) == [] and run(rt.handoffs.list(None, None, 10)) == []
    assert any(e["type"] == "reply" for e in out["rerun"]["events"])


def test_the_first_turn_can_be_rerun_with_no_history():
    c, _, rt, llm = setup([text("Original."), text("Again.")])
    chat(c, "hello")
    out = rerun(c, 1, "hello there").json()
    assert out["rerun"]["reply"] == "Again." and llm.requests[-1].messages == [{"role": "user", "content": "hello there"}]


def test_a_write_in_the_rerun_is_simulated_and_never_executed():
    calls = []
    agent = Agent(id="support", instructions="help", tools=[Tool("issue_refund", "refund", Amount, lambda d, ctx: calls.append(d.amount) or {"ok": True}, effect="write")])
    c, _, rt, _ = setup([text("hi"), tool_call("issue_refund", {"order_id": "1", "amount": 20}, "t1"), text("Refunded."), tool_call("issue_refund", {"order_id": "1", "amount": 20}, "t2"), text("Refunded in the rerun.")], agent)
    chat(c, "hello")
    chat(c, "refund order 1 for 20")
    assert calls == [20.0]                                                               # the live turn ran it
    out = rerun(c, 2, "refund order 1 for 20 please").json()
    assert calls == [20.0]                                                               # the rerun did not run it again
    results = [e for e in out["rerun"]["events"] if e["type"] == "tool_result"]
    assert results and results[0]["data"].get("dry_run") is True


# ---- who, and what is refused ----
def test_only_people_who_may_run_simulations_can_rerun_and_a_customer_token_cannot():
    c, ac, _, _ = setup([text("a"), text("b"), text("c")] * 2)
    loop = asyncio.new_event_loop()
    mk = lambda n, role: loop.run_until_complete(ac.issue(n, role, "root"))[1]            # noqa: E731
    viewer, reviewer, dev, chan = mk("v", "viewer"), mk("r", "reviewer"), mk("d", "developer"), mk("c", "channel")
    chat(c, "hi")
    token = c.post("/v1/chat-tokens", json={"sessionId": "s1", "customerId": "c1"}, headers=H(chan)).json()["token"]
    for h in ({}, H(viewer), H(reviewer), H(token)):
        assert rerun(c, 1, "x", headers=h).status_code in (401, 403)
    assert rerun(c, 1, "hello again", headers=H(dev)).status_code == 200


def test_unknown_conversations_turns_and_staff_agents_are_refused_with_a_reason():
    c, _, rt, _ = setup([text("a")] * 3)
    assert rerun(c, 1, "x", session="nope").status_code == 404
    chat(c, "hi")
    r = rerun(c, 5, "x")
    assert r.status_code == 400 and "1 customer message" in r.json()["error"]["message"]
    assert rerun(c, 0, "x").status_code == 400 and rerun(c, 1, "").status_code == 400 and rerun(c, 1, "x" * 9000).status_code == 400


def test_a_rerun_is_audited_with_lengths_not_text():
    c, _, _, _ = setup([text("a"), text("b")])
    chat(c, "hi")
    rerun(c, 1, "a secret question")
    entries = c.get("/v1/audit", headers=H()).json()["entries"]
    hit = [e for e in entries if e["action"] == "session.rerun"]
    assert len(hit) == 1 and "secret question" not in json.dumps(entries)


def test_a_conversation_with_a_staff_agent_is_not_rerun_here():
    from northcx.access import Identity
    staff = Agent(id="support", instructions="help staff", audience="staff")
    c, _, rt, _ = setup([text("ok")], staff)
    run(rt.run(staff, "ss", "hello", None, actor=Identity("ann", "viewer", "t")))
    r = rerun(c, 1, "hello again", session="ss")
    assert r.status_code == 400 and "staff" in r.json()["error"]["message"]


def test_a_rerun_counts_against_the_daily_budget_and_stops_when_it_is_spent():
    from northcx.reliability import UsageLedger
    c, _, rt, _ = setup([text("a"), text("b")])
    chat(c, "hi")
    rt.ledger = UsageLedger(daily_limit=10)
    rt.ledger.add("support", 50)                                                         # today's budget is already used up
    out = rerun(c, 1, "hi again").json()
    assert out["rerun"]["status"] == "escalated" and any(e["type"] == "budget" for e in out["rerun"]["events"])


def test_the_turns_route_lists_each_customer_message_with_the_reply_it_got_using_the_numbers_rerun_takes():
    c, ac, _, _ = setup([text("first answer"), text("second answer"), text("rerun answer")])
    assert c.get("/v1/sessions/nope/turns", headers=H()).status_code == 404
    chat(c, "one")
    chat(c, "two")
    got = c.get("/v1/sessions/s1/turns", headers=H()).json()
    assert got["turns"] == [{"turn": 1, "message": "one", "reply": "first answer"}, {"turn": 2, "message": "two", "reply": "second answer"}]
    assert rerun(c, got["turns"][1]["turn"], "two, differently").json()["original"] == {"message": "two", "reply": "second answer"}
    viewer = asyncio.new_event_loop().run_until_complete(ac.issue("v", "viewer", "root"))[1]
    assert c.get("/v1/sessions/s1/turns", headers=H(viewer)).status_code == 200            # reading is for anyone who may read traces
    assert c.get("/v1/sessions/s1/turns", headers={}).status_code == 401
