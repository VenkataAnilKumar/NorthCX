"""Retried writes never act twice: API idempotency keys, in-turn duplicate calls, per-call keys, read retries."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from examples.support_agent import support_agent
from northcx.agent import Agent, Tool
from northcx.idempotency import STALE_AFTER, TTL_SECONDS, InMemoryIdempotency, request_hash, scope_hash, valid_key
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        return InMemoryIdempotency()
    from northcx.db import PgIdempotency
    return PgIdempotency(request.getfixturevalue("engine"))


async def test_store_contract(store):
    assert (await store.begin("s", "h1", 1000)).state == "new"
    assert (await store.begin("s", "h1", 1001)).state == "in_progress"
    assert (await store.begin("s", "h2", 1001)).state == "conflict"
    await store.complete("s", {"reply": "ok", "n": 1})
    o = await store.begin("s", "h1", 1002)
    assert (o.state, o.response) == ("replay", {"reply": "ok", "n": 1})
    assert (await store.begin("s", "other", 1002)).state == "conflict"
    assert (await store.begin("t", "h1", 1002)).state == "new"  # scopes are independent
    await store.abandon("t")
    assert (await store.begin("t", "h9", 1003)).state == "new"  # abandoned: a retry may start over
    await store.abandon("s")  # a finished request cannot be abandoned
    assert (await store.begin("s", "h1", 1004)).state == "replay"


async def test_a_crashed_request_can_be_retried_after_a_while_and_old_keys_expire(store):
    assert (await store.begin("c", "h", 1000)).state == "new"
    assert (await store.begin("c", "h", 1000 + STALE_AFTER - 1)).state == "in_progress"
    assert (await store.begin("c", "h2", 1000 + STALE_AFTER + 1)).state == "new"  # never finished: taken over
    await store.complete("c", {"a": 1})
    assert (await store.begin("c", "h2", 1000 + TTL_SECONDS - 5)).state == "replay"
    assert (await store.begin("c", "zzz", 1000 + TTL_SECONDS + STALE_AFTER + 10)).state == "new"  # expired


async def test_only_one_of_many_simultaneous_requests_starts(store):
    outs = await asyncio.gather(*[store.begin("race", "h", 5000) for _ in range(12)])
    assert sorted(o.state for o in outs) == ["in_progress"] * 11 + ["new"]


def test_key_and_hash_helpers():
    assert valid_key("abc-123_X") and not valid_key("") and not valid_key("a b") and not valid_key("é") and not valid_key("x" * 201)
    assert scope_hash("a", "b") != scope_hash("ab", "") and request_hash({"a": 1, "b": 2}) == request_hash({"b": 2, "a": 1})


# ---- API ----
def client(script, key="boot" * 10):
    llm = ScriptedLLM(script)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, api_key=key)), llm, key


def chat(c, key, msg="hello", idem="k1", session="s1", **extra):
    h = {"authorization": f"Bearer {key}", **({"idempotency-key": idem} if idem else {})}
    return c.post("/v1/agents/support/chat", json={"sessionId": session, "message": msg}, headers=h)


def test_a_retried_chat_returns_the_first_answer_without_running_again():
    c, llm, key = client([text("first answer"), text("second answer")])
    a, b = chat(c, key), chat(c, key)
    assert a.status_code == b.status_code == 200 and a.json() == b.json() and a.json()["reply"] == "first answer"
    assert b.headers.get("Idempotent-Replay") == "true" and "Idempotent-Replay" not in a.headers and len(llm.requests) == 1
    assert chat(c, key, idem=None).json()["reply"] == "second answer"  # no key: runs normally


def test_reusing_a_key_for_a_different_request_is_refused_and_keys_are_scoped():
    c, llm, key = client([text("one"), text("two"), text("three")])
    chat(c, key)
    r = chat(c, key, msg="a different message")
    assert r.status_code == 422 and r.json()["error"]["code"] == "idempotency_key_reused" and len(llm.requests) == 1
    assert chat(c, key, session="other-session").json()["reply"] == "two"  # same key, another conversation
    assert chat(c, key, idem="k2").json()["reply"] == "three"


def test_bad_keys_are_rejected_and_failures_can_be_retried():
    c, llm, key = client([RuntimeError("x")])
    assert chat(c, key, idem="has space").status_code == 400
    llm.script = [text("recovered")]
    # a run that fails inside the model becomes a hand-off reply (completed request), but an unknown agent is not stored
    r = c.post("/v1/agents/nope/chat", json={"sessionId": "s", "message": "hi"}, headers={"authorization": f"Bearer {key}", "idempotency-key": "z"})
    assert r.status_code == 404
    assert c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "hi"}, headers={"authorization": f"Bearer {key}", "idempotency-key": "z"}).status_code == 200


def test_a_request_still_in_progress_is_not_run_a_second_time():
    from northcx.idempotency import Outcome

    class Busy(InMemoryIdempotency):
        async def begin(self, scope, req_hash, now=None):
            return Outcome("in_progress")

    llm = ScriptedLLM([text("never")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, api_key="boot" * 10, idempotency=Busy()))
    r = chat(c, "boot" * 10)
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_in_progress" and llm.requests == []


def test_a_conversation_that_ended_in_a_handoff_is_replayed_not_redone():
    c, llm, key = client([])  # the model fails, so the run hands off
    first = chat(c, key)
    assert first.status_code == 200 and first.json()["status"] == "escalated"
    again = chat(c, key)
    assert again.headers.get("Idempotent-Replay") == "true" and again.json() == first.json()


# ---- runtime ----
class Pay(BaseModel):
    amount: int


def paying_agent(log, fail_reads=0):
    async def pay(inp, ctx):
        log.append((inp.amount, ctx.idempotency_key))
        return {"paid": inp.amount}

    state = {"n": 0}

    async def peek(inp, ctx):
        state["n"] += 1
        if state["n"] <= fail_reads:
            raise RuntimeError("temporary")
        return {"seen": state["n"]}

    return Agent(id="a", instructions="i", tools=[Tool("pay", "d", Pay, pay), Tool("peek", "d", Pay, peek, effect="read")]), state


async def test_the_same_write_repeated_in_one_turn_runs_once():
    log = []
    a, _ = paying_agent(log)
    script = [tool_call("pay", {"amount": 5}, "t1"), tool_call("pay", {"amount": 5}, "t2"), tool_call("pay", {"amount": 6}, "t3"), text("done")]
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    r = await rt.run(a, "s", "pay")
    assert [x[0] for x in log] == [5, 6]
    assert [e.type for e in r.trace.events].count("duplicate_call") == 1
    results = [e.data["output"] for e in r.trace.events if e.type == "tool_result"]
    assert results == [{"paid": 5}, {"paid": 5}, {"paid": 6}]  # the repeat is answered with the first result


async def test_each_call_gets_a_stable_key_that_differs_between_calls_and_turns():
    log = []
    a, _ = paying_agent(log)
    rt = Runtime(ScriptedLLM([tool_call("pay", {"amount": 5}, "t1"), text("a"), tool_call("pay", {"amount": 5}, "t2"), text("b")]), InMemoryStore(), TraceStore())
    await rt.run(a, "s", "one")
    await rt.run(a, "s", "two")  # a new turn is a new, intentional action
    assert len(log) == 2 and log[0][1] and log[0][1] != log[1][1] and len(log[0][1]) == 32


async def test_reads_are_retried_once_and_writes_are_not():
    a, state = paying_agent([], fail_reads=1)
    rt = Runtime(ScriptedLLM([tool_call("peek", {"amount": 1}, "t1"), text("ok")]), InMemoryStore(), TraceStore())
    r = await rt.run(a, "s", "look")
    assert state["n"] == 2 and not [e for e in r.trace.events if e.type == "error"]
    a2, state2 = paying_agent([], fail_reads=5)
    r2 = await Runtime(ScriptedLLM([tool_call("peek", {"amount": 1}, "t1"), text("ok")]), InMemoryStore(), TraceStore()).run(a2, "s", "look")
    assert state2["n"] == 2 and [e for e in r2.trace.events if e.type == "error"]  # gave up after one retry

    calls = []

    async def flaky_write(inp, ctx):
        calls.append(1)
        raise RuntimeError("boom")

    w = Agent(id="w", instructions="i", tools=[Tool("pay", "d", Pay, flaky_write)])
    await Runtime(ScriptedLLM([tool_call("pay", {"amount": 1}, "t1"), text("sorry")]), InMemoryStore(), TraceStore()).run(w, "s", "pay")
    assert len(calls) == 1  # a failed write is never retried automatically
