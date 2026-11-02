"""Retries, fallback models, circuit breaking and token budgets."""
import asyncio

import pytest

from examples.support_agent import support_agent
from northcx.agent import Agent
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.reliability import ModelUnavailable, ReliableLLM, UsageLedger, is_transient
from northcx.runtime import Runtime
from northcx.spec import AgentSpec, default_registry
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.types import LLMRequest, LLMResponse


class HttpError(Exception):
    def __init__(self, status):
        super().__init__(f"http {status}")
        self.status_code = status


class Flaky:
    """Fails per model according to a plan: {model: [exception or None, ...]}."""

    def __init__(self, plan):
        self.plan, self.calls = plan, []

    async def complete(self, req):
        self.calls.append(req.model)
        steps = self.plan.get(req.model, [None])
        step = steps.pop(0) if len(steps) > 1 else steps[0]
        if step is not None:
            raise step
        return text(f"from {req.model}")


def rel(inner, models=None, **kw):
    delays = []

    async def sleep(d):
        delays.append(d)

    r = ReliableLLM(inner, models, sleep=sleep, jitter=lambda: 1.0, **kw)
    r.delays = delays
    return r


REQ = LLMRequest(system="s", messages=[{"role": "user", "content": "hi"}])


@pytest.mark.parametrize("e,expected", [
    (HttpError(429), True), (HttpError(500), True), (HttpError(529), True), (HttpError(408), True), (HttpError(400), False),
    (HttpError(401), False), (HttpError(404), False), (asyncio.TimeoutError(), True), (ConnectionResetError(), True),
    (ValueError("x"), False), (type("RateLimitError", (Exception,), {})(), True),
])
def test_which_errors_are_worth_retrying(e, expected):
    assert is_transient(e) is expected


async def test_a_transient_failure_is_retried_with_growing_delays():
    inner = Flaky({None: [HttpError(529), HttpError(529), None]})
    r = rel(inner, retries=2, base_delay=1, max_delay=10)
    assert (await r.complete(REQ)).content[0]["text"] == "from None" and len(inner.calls) == 3
    assert r.delays == [1.0, 2.0]


async def test_delays_are_capped_and_jittered():
    inner = Flaky({None: [HttpError(500)] * 5 + [None]})
    r = ReliableLLM(inner, retries=5, base_delay=4, max_delay=6, breaker_failures=99, sleep=lambda d: asyncio.sleep(0), jitter=lambda: 0.0)
    seen = []
    orig = r._sleep

    async def spy(d):
        seen.append(d)
        await orig(d)

    r._sleep = spy
    await r.complete(REQ)
    assert seen == [2.0, 3.0, 3.0, 3.0, 3.0]  # min(cap, base*2^n) * 0.5 with zero jitter


async def test_bad_requests_are_not_retried_and_not_hidden():
    inner = Flaky({"a": [HttpError(400)]})
    r = rel(inner, ["a", "b"])
    with pytest.raises(HttpError):
        await r.complete(REQ)
    assert inner.calls == ["a"]


async def test_fallback_model_answers_when_the_primary_is_down():
    inner = Flaky({"primary": [HttpError(529)], "backup": [None]})
    r = rel(inner, ["primary", "backup"], retries=1)
    res = await r.complete(REQ)
    assert res.content[0]["text"] == "from backup" and res.fallback and res.model == "backup"
    assert inner.calls == ["primary", "primary", "backup"]


async def test_a_requested_model_is_tried_first_and_everything_failing_is_reported():
    inner = Flaky({"x": [None], "a": [HttpError(500)], "b": [HttpError(500)]})
    r = rel(inner, ["a", "b"], retries=0, breaker_failures=99)
    assert (await r.complete(LLMRequest("s", [], model="x"))).model == "x" and inner.calls == ["x"]
    with pytest.raises(ModelUnavailable, match="HttpError"):
        await r.complete(REQ)


async def test_the_breaker_skips_a_failing_model_then_recovers():
    inner = Flaky({"a": [HttpError(500)], "b": [None]})
    now = [0.0]
    r = ReliableLLM(inner, ["a", "b"], retries=5, breaker_failures=2, breaker_cooldown=30, sleep=lambda d: asyncio.sleep(0), clock=lambda: now[0], jitter=lambda: 1.0)
    await r.complete(REQ)
    assert inner.calls == ["a", "a", "b"]  # two failures open the circuit; no more retries on a
    inner.calls.clear()
    await r.complete(REQ)
    assert inner.calls == ["b"]  # skipped while open
    now[0] = 31
    inner.plan["a"] = [None]
    inner.calls.clear()
    assert (await r.complete(REQ)).model == "a" and inner.calls == ["a"]


async def test_the_last_model_is_always_tried_even_if_its_circuit_is_open():
    inner = Flaky({"a": [HttpError(500)], "b": [HttpError(500), None]})
    r = rel(inner, ["a", "b"], retries=0, breaker_failures=1)
    with pytest.raises(ModelUnavailable):
        await r.complete(REQ)
    assert (await r.complete(REQ)).model == "b"  # b's circuit is open but it is the only one left


async def test_a_hung_call_times_out_and_falls_back():
    class Slow:
        async def complete(self, req):
            if req.model == "a":
                await asyncio.sleep(5)
            return text(f"from {req.model}")

    r = rel(Slow(), ["a", "b"], retries=0, timeout=0.05)
    assert (await r.complete(REQ)).model == "b"


async def test_no_chain_behaves_like_the_plain_model_with_retries():
    inner = Flaky({None: [HttpError(503), None]})
    assert (await rel(inner).complete(REQ)).content[0]["text"] == "from None"


# ---- budgets ----
def usage(resp, n_in, n_out):
    resp.usage = {"input_tokens": n_in, "output_tokens": n_out}
    return resp


async def test_usage_is_recorded_in_the_trace_and_ledger():
    rt = Runtime(ScriptedLLM([usage(text("hi"), 100, 20)]), InMemoryStore(), TraceStore())
    r = await rt.run(support_agent(), "s", "hello")
    assert [e.data["tokens"] for e in r.trace.events if e.type == "llm"] == [120]
    assert rt.ledger.used_today("support") == 120 and rt.ledger.used_today("other") == 0


async def test_a_run_over_its_budget_hands_off_instead_of_continuing():
    a = support_agent()
    a.max_run_tokens = 1000
    script = [usage(tool_call("lookup_order", {"order_id": "1"}, "t1"), 900, 200), text("never reached")]
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    r = await rt.run(a, "s", "where is it")
    assert r.status == "escalated" and r.handoff_id and len(rt.llm.requests) == 1
    assert [e.data["scope"] for e in r.trace.events if e.type == "budget"] == ["run"]
    history = await rt.store.load_messages("s")
    assert history[-1]["role"] == "assistant" and all(isinstance(m["content"], (str, list)) for m in history)


async def test_the_daily_budget_stops_model_calls_for_everyone():
    rt = Runtime(ScriptedLLM([usage(text("one"), 600, 500)]), InMemoryStore(), TraceStore(), ledger=UsageLedger(1000))
    assert (await rt.run(support_agent(), "s1", "hi")).status == "completed"
    r = await rt.run(support_agent(), "s2", "hi again")
    assert r.status == "escalated" and len(rt.llm.requests) == 1
    assert next(e for e in r.trace.events if e.type == "budget").data["scope"] == "daily"


def test_ledger_days_and_pruning():
    L = UsageLedger(100)
    L.add("a", 60, at=0)
    assert L.used_today("a", at=0) == 60
    L.add("a", 50, at=86400 * 10)
    assert L.used_today(None, at=86400 * 10) == 50 and L.used_today("a", at=0) == 0  # three-day-old usage is dropped
    assert L.exhausted(at=0) is False and UsageLedger(None).exhausted() is False
    L.add("a", 60, at=86400 * 10)
    assert L.exhausted(at=86400 * 10) and len(L._days) == 1  # the old day was dropped


def test_spec_budget_field_validates_and_keeps_old_digests():
    base = {"spec_version": 1, "id": "a", "instructions": "i"}
    old = AgentSpec.model_validate(base)
    assert "max_run_tokens" not in old.canonical()
    new = AgentSpec.model_validate({**base, "max_run_tokens": 20000})
    assert new.digest() != old.digest() and default_registry().build(new).max_run_tokens == 20000
    for bad in (10, 10**9, "many"):
        with pytest.raises(Exception):
            AgentSpec.model_validate({**base, "max_run_tokens": bad})
