"""Contract tests: the in-memory and Postgres repositories must behave identically."""
import asyncio
import datetime
import decimal

import pytest

from northcx.approvals import ApprovalStore
from northcx.store import InMemoryStore
from northcx.trace import Trace, TraceStore

KINDS = ["memory", "postgres"]


@pytest.fixture(params=KINDS)
def kind(request):
    return request.param


@pytest.fixture
def memory_store(kind, request):
    if kind == "memory":
        return InMemoryStore()
    from northcx.db import PgMemoryStore

    return PgMemoryStore(request.getfixturevalue("engine"))


@pytest.fixture
def trace_store(kind, request):
    if kind == "memory":
        return TraceStore()
    from northcx.db import PgTraceStore

    return PgTraceStore(request.getfixturevalue("engine"))


@pytest.fixture
def approval_store(kind, request):
    if kind == "memory":
        return ApprovalStore()
    from northcx.db import PgApprovalStore

    return PgApprovalStore(request.getfixturevalue("engine"))


# ---- memory ----
async def test_missing_session_is_empty(memory_store):
    assert await memory_store.load_messages("nope") == []
    assert await memory_store.get_facts("nobody") == {}


async def test_messages_round_trip_including_tool_blocks(memory_store):
    msgs = [
        {"role": "user", "content": "refund order 1"},
        {"role": "assistant", "content": [{"type": "text", "text": "ok"},
                                          {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"id": "1", "n": [1, 2]}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{\"total\": 5}"}]},
        {"role": "assistant", "content": "Done ✓ — 日本語"},
    ]
    await memory_store.save_messages("s1", msgs)
    assert await memory_store.load_messages("s1") == msgs


async def test_save_replaces_history_and_sessions_are_isolated(memory_store):
    await memory_store.save_messages("a", [{"role": "user", "content": "1"}, {"role": "assistant", "content": "2"}])
    await memory_store.save_messages("b", [{"role": "user", "content": "other"}])
    await memory_store.save_messages("a", [{"role": "user", "content": "only"}])
    assert await memory_store.load_messages("a") == [{"role": "user", "content": "only"}]
    assert len(await memory_store.load_messages("b")) == 1
    await memory_store.save_messages("a", [])
    assert await memory_store.load_messages("a") == []


async def test_loaded_messages_are_copies(memory_store):
    await memory_store.save_messages("s", [{"role": "user", "content": "x"}])
    got = await memory_store.load_messages("s")
    got[0]["content"] = "mutated"
    assert (await memory_store.load_messages("s"))[0]["content"] == "x"


async def test_facts_upsert_and_isolation(memory_store):
    await memory_store.set_fact("c1", "tier", "gold")
    await memory_store.set_fact("c1", "tier", "platinum")
    await memory_store.set_fact("c1", "lang", "fr")
    await memory_store.set_fact("c2", "tier", "basic")
    assert await memory_store.get_facts("c1") == {"tier": "platinum", "lang": "fr"}
    assert await memory_store.get_facts("c2") == {"tier": "basic"}


async def test_concurrent_saves_to_one_session_stay_consistent(memory_store):
    a = [{"role": "user", "content": str(i)} for i in range(5)]
    b = [{"role": "user", "content": f"b{i}"} for i in range(3)]
    await asyncio.gather(*[memory_store.save_messages("s", a if i % 2 else b) for i in range(10)])
    assert await memory_store.load_messages("s") in (a, b)


# ---- traces ----
def make_trace(session="s", agent="a", status="completed", tools=("lookup",)):
    t = Trace(agent_id=agent, session_id=session)
    t.add("user", message="hi")
    for name in tools:
        t.add("tool_call", name=name, input={"x": 1})
    t.add("reply", reply="ok", status=status)
    return t


async def test_trace_round_trip_keeps_order_and_data(trace_store):
    t = make_trace()
    await trace_store.save(t)
    got = await trace_store.get(t.id)
    assert [e.type for e in got.events] == ["user", "tool_call", "reply"]
    assert got.events[1].data == {"name": "lookup", "input": {"x": 1}}
    assert (got.agent_id, got.session_id) == ("a", "s")
    assert await trace_store.get("missing") is None


async def test_resaving_a_trace_replaces_it(trace_store):
    t = make_trace()
    await trace_store.save(t)
    t.add("error", error="late")
    await trace_store.save(t)
    assert len((await trace_store.get(t.id)).events) == 4
    assert len(await trace_store.summaries()) == 1


async def test_summaries_are_newest_first_filterable_and_limited(trace_store):
    first, second, third = make_trace("s1"), make_trace("s2", status="escalated", tools=()), make_trace("s1")
    for i, t in enumerate((first, second, third)):
        for e in t.events:
            e.t = 1000.0 + i  # deterministic ordering
        await trace_store.save(t)
    allv = await trace_store.summaries()
    assert [s.id for s in allv] == [third.id, second.id, first.id]
    assert {s.status for s in allv} == {"completed", "escalated"}
    esc = next(s for s in allv if s.id == second.id)
    assert esc.tools == [] and esc.events == 2
    assert [s.id for s in await trace_store.summaries("s1")] == [third.id, first.id]
    assert len(await trace_store.summaries(limit=1)) == 1
    assert next(s for s in allv if s.id == first.id).tools == ["lookup"]


async def test_traces_with_unserialisable_tool_output_can_be_saved(trace_store):
    t = Trace(agent_id="a", session_id="s")
    t.add("tool_result", name="x", output={"when": datetime.datetime(2026, 1, 1), "amount": decimal.Decimal("1.50")})
    t.add("reply", reply="ok", status="completed")
    await trace_store.save(t)
    got = await trace_store.get(t.id)
    assert got is not None and len(got.events) == 2


# ---- approvals ----
async def test_approval_lifecycle(approval_store):
    a = await approval_store.add(trace_id="t1", session_id="s", tool="refund", input={"amount": 500}, reason="over limit")
    b = await approval_store.add(trace_id="t2", session_id="s", tool="refund", input={"amount": 900}, reason="over limit")
    assert [x.id for x in await approval_store.list("pending")] == [a.id, b.id]
    done = await approval_store.decide(a.id, True, "rae")
    assert (done.state, done.decided_by) == ("approved", "rae") and done.decided_at
    assert [x.id for x in await approval_store.list("pending")] == [b.id]
    assert [x.state for x in await approval_store.list()] == ["approved", "pending"]
    got = await approval_store.get(a.id)
    assert got.state == "approved" and got.input == {"amount": 500}
    assert await approval_store.get("missing") is None


async def test_approval_cannot_be_decided_twice_or_when_unknown(approval_store):
    a = await approval_store.add(trace_id="t", session_id="s", tool="x", input={}, reason="r")
    await approval_store.decide(a.id, False, "rae")
    with pytest.raises(ValueError):
        await approval_store.decide(a.id, True, "someone")
    assert (await approval_store.get(a.id)).state == "rejected"
    with pytest.raises(KeyError):
        await approval_store.decide("missing", True, "rae")


async def test_concurrent_decisions_have_exactly_one_winner(approval_store):
    a = await approval_store.add(trace_id="t", session_id="s", tool="x", input={}, reason="r")
    results = await asyncio.gather(*[approval_store.decide(a.id, i % 2 == 0, f"u{i}") for i in range(6)], return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert all(isinstance(r, ValueError) for r in results if isinstance(r, Exception))


# ---- approval state machine ----
async def test_approval_state_machine(approval_store):
    a = await approval_store.add(trace_id="t", session_id="s", agent_id="ag", customer_id="c", tool="x", input={"n": 1}, reason="r")
    assert (a.agent_id, a.customer_id) == ("ag", "c")
    with pytest.raises(ValueError):
        await approval_store.claim_execution(a.id)  # not approved yet
    with pytest.raises(ValueError):
        await approval_store.complete(a.id, True, {})
    d = await approval_store.decide(a.id, True, "rae", "fine")
    assert (d.state, d.note) == ("approved", "fine")
    c = await approval_store.claim_execution(a.id)
    assert c.state == "executing"
    with pytest.raises(ValueError):
        await approval_store.claim_execution(a.id)  # a second claim must lose
    assert await approval_store.expire(a.id) is None  # only pending approvals expire
    done = await approval_store.complete(a.id, True, {"result": {"ok": 1}})
    assert (done.state, done.result) == ("executed", {"result": {"ok": 1}})
    got = await approval_store.get(a.id)
    assert (got.state, got.result, got.agent_id, got.customer_id, got.note) == ("executed", {"result": {"ok": 1}}, "ag", "c", "fine")


async def test_failed_and_expired_paths(approval_store):
    a = await approval_store.add(trace_id="t", session_id="s", tool="x", input={}, reason="r")
    await approval_store.decide(a.id, True, "rae")
    await approval_store.claim_execution(a.id)
    assert (await approval_store.complete(a.id, False, {"error": "boom"})).state == "failed"
    b = await approval_store.add(trace_id="t", session_id="s", tool="x", input={}, reason="r")
    assert (await approval_store.expire(b.id)).state == "expired"
    assert await approval_store.expire(b.id) is None
    with pytest.raises(ValueError):
        await approval_store.decide(b.id, True, "late")
    with pytest.raises(KeyError):
        await approval_store.expire("missing")
    with pytest.raises(KeyError):
        await approval_store.claim_execution("missing")


async def test_only_one_concurrent_claim_wins(approval_store):
    a = await approval_store.add(trace_id="t", session_id="s", tool="x", input={}, reason="r")
    await approval_store.decide(a.id, True, "rae")
    res = await asyncio.gather(*[approval_store.claim_execution(a.id) for _ in range(6)], return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in res) == 1


# ---- outbox ----
@pytest.fixture
def outbox_repo(kind, request):
    from northcx.outbox import InMemoryOutbox

    if kind == "memory":
        return InMemoryOutbox()
    from northcx.db import PgOutbox

    return PgOutbox(request.getfixturevalue("engine"))


async def test_outbox_orders_filters_and_paginates(outbox_repo):
    a = await outbox_repo.add("s1", "approval_result", {"reply": "one"})
    b = await outbox_repo.add("s2", "approval_result", {"reply": "other"})
    c = await outbox_repo.add("s1", "approval_expired", {"reply": "two"})
    assert a.id < b.id < c.id
    assert [m.payload["reply"] for m in await outbox_repo.list("s1")] == ["one", "two"]
    assert [m.payload["reply"] for m in await outbox_repo.list("s1", after_id=a.id)] == ["two"]
    assert await outbox_repo.list("s1", after_id=c.id) == []
    assert len(await outbox_repo.list("s1", limit=1)) == 1


async def test_outbox_tracks_delivery_attempts(outbox_repo):
    m = await outbox_repo.add("s", "approval_result", {})
    assert [x.id for x in await outbox_repo.undelivered()] == [m.id]
    await outbox_repo.record_attempt(m.id, False)
    assert (await outbox_repo.undelivered())[0].attempts == 1
    await outbox_repo.record_attempt(m.id, True)
    assert await outbox_repo.undelivered() == []
    assert (await outbox_repo.list("s"))[0].attempts == 2


# ---- handoffs ----
@pytest.fixture
def handoff_repo(kind, request):
    from northcx.handoffs import InMemoryHandoffs

    if kind == "memory":
        return InMemoryHandoffs()
    from northcx.db import PgHandoffs

    return PgHandoffs(request.getfixturevalue("engine"))


def make_handoff(session="s", created=1000.0, trigger="agent_handoff"):
    from northcx.handoffs import Handoff

    return Handoff(session_id=session, trace_id="t", agent_id="a", customer_id="c", trigger=trigger, reason="because",
                   topics=["legal"], package={"summary": "S", "transcript": [{"from": "customer", "text": "héllo 日本"}]}, created_at=created)


async def test_handoff_round_trip_listing_and_filters(handoff_repo):
    a, b, c = make_handoff("s1", 1.0), make_handoff("s2", 2.0, "forced_topic"), make_handoff("s1", 3.0)
    for h in (a, b, c):
        await handoff_repo.add(h)
    got = await handoff_repo.get(b.id)
    assert (got.trigger, got.topics, got.customer_id, got.state) == ("forced_topic", ["legal"], "c", "open")
    assert got.package == b.package
    assert [h.id for h in await handoff_repo.list()] == [c.id, b.id, a.id]  # newest first
    assert [h.id for h in await handoff_repo.list(session_id="s1")] == [c.id, a.id]
    assert len(await handoff_repo.list(limit=1)) == 1
    await handoff_repo.resolve(a.id, "jo", "done")
    assert [h.id for h in await handoff_repo.list("open")] == [c.id, b.id]
    assert [h.id for h in await handoff_repo.list("resolved")] == [a.id]
    assert await handoff_repo.get("missing") is None


async def test_handoff_resolves_exactly_once_even_concurrently(handoff_repo):
    h = await handoff_repo.add(make_handoff())
    res = await asyncio.gather(*[handoff_repo.resolve(h.id, f"u{i}") for i in range(6)], return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in res) == 1
    assert all(isinstance(r, ValueError) for r in res if isinstance(r, Exception))
    assert (await handoff_repo.get(h.id)).state == "resolved"
    with pytest.raises(KeyError):
        await handoff_repo.resolve("missing", "jo")
