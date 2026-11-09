"""WP1.11 and the Phase 2 review fixes: qualification gates which models may serve an agent; sensitivity sticks; mixed providers fall back safely."""
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text
from northcx.providers import Capabilities, ProviderRegistry
from northcx.providers.openai_compat import OpenAICompatibleLLM
from northcx.providers.qualification import Qualifications, evaluate
from northcx.providers.selection import parse_routing
from northcx.reliability import ModelUnavailable, ReliableLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation.store import SimRun
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.types import LLMRequest, LLMResponse

KEY = "boot" * 10
M = "loc:small"


def result(name, required, passed, agent="support", notes=()):
    return {"name": name, "required": required, "passed": passed, "agent": agent, "notes": list(notes)}


def run(results, mode="live", model=M, digest="d1", **kw):
    return SimRun(mode=mode, passed=True, counts={}, agent_digests={"support": "dX"}, results=results, meta={"model": model, "agent_digest": digest, **kw})


def test_thresholds_100_percent_of_required_and_90_percent_of_the_rest():
    ok = [result(f"r{i}", True, True) for i in range(3)] + [result(f"o{i}", False, i != 0) for i in range(10)]  # 9 of 10 others
    q = evaluate(run(ok), "support", M)
    assert q.qualified and (q.required_passed, q.required_total, q.other_passed, q.other_total) == (3, 3, 9, 10) and q.agent_digest == "d1"
    bad_req = evaluate(run([result("r1", True, False), result("r2", True, True)]), "support", M)
    assert not bad_req.qualified and "1 of 2" in bad_req.reasons[0]
    bad_other = evaluate(run([result("r", True, True)] + [result(f"o{i}", False, i < 8) for i in range(10)]), "support", M)
    assert not bad_other.qualified and "other scenarios" in bad_other.reasons[0]


@pytest.mark.parametrize("r,why", [
    (run([result("r", True, True)], mode="scripted"), "only a live run"),
    (run([result("r", True, True)], model="other:x"), "not made against this model"),
    (run([result("r", True, True, agent="other")]), "no scenarios for this agent"),
    (run([result("o", False, True)]), "no required scenarios"),
    (run([result("r", True, True, notes=["judge skipped"])]), "skipped"),
])
def test_evidence_that_does_not_count(r, why):
    q = evaluate(r, "support", M)
    assert not q.qualified and any(why in x for x in q.reasons)


async def test_a_qualification_belongs_to_one_definition_and_the_newest_result_wins():
    svc = Qualifications()
    await svc.record(run([result("r", True, True)]), "support", M)
    assert await svc.is_qualified("support", M, "d1") and await svc.is_qualified("support", M, None)
    assert not await svc.is_qualified("support", M, "d2")  # the prompt or tools changed: qualify again
    assert not await svc.is_qualified("support", "loc:other", "d1")
    await svc.record(run([result("r", True, False)]), "support", M)
    assert not await svc.is_qualified("support", M, "d1")  # a later failing run withdraws it


class Fake:
    def __init__(self, name, model):
        self.name, self.default_model, self.capabilities, self.prices, self.calls = name, model, Capabilities(), {}, []

    async def complete(self, req):
        self.calls.append(req.model)
        return LLMResponse(content=[{"type": "text", "text": f"from {self.name}"}], model=req.model)


def stack(exempt=""):
    reg = ProviderRegistry()
    f = {"pub": Fake("pub", "big"), "loc": Fake("loc", "small")}
    reg.register(f["pub"], default=True)
    reg.register(f["loc"])
    sel = parse_routing(f"qualification: {{required: true{exempt}}}", reg, {"pub": "public-cloud", "loc": "local"})
    sel.qualifier = Qualifications()
    rel = ReliableLLM(reg, ["pub:big"], retries=0, timeout=None)
    rel.selector = sel
    return rel, f, sel


REQ = lambda **c: LLMRequest(system="", messages=[{"role": "user", "content": "x"}], model="loc:small", context={"agent": "support", "sensitive": False, **c})  # noqa: E731


async def test_an_unqualified_model_never_serves_a_customer():
    rel, f, sel = stack()
    with pytest.raises(ModelUnavailable, match="not qualified"):
        await rel.complete(REQ())  # nothing is qualified or exempt: the conversation goes to a person
    assert f["loc"].calls == [] and f["pub"].calls == []


async def test_qualification_gates_in_order_and_exempt_models_are_trusted():
    rel, f, sel = stack(exempt=', exempt: ["pub:big"]')
    r = await rel.complete(REQ())
    assert r.content[0]["text"] == "from pub" and r.decision["skipped"][0]["model"] == "loc:small" and "not qualified" in r.decision["skipped"][0]["reason"]
    await sel.qualifier.record(run([result("r", True, True)]), "support", "loc:small")
    r = await rel.complete(REQ(agent_digest="d1"))
    assert r.content[0]["text"] == "from loc"
    r = await rel.complete(REQ(agent_digest="d2"))  # definition changed
    assert r.content[0]["text"] == "from pub"
    r = await rel.complete(REQ(evaluation=True, agent_digest="d2"))  # an evaluation run is how a model earns it
    assert r.content[0]["text"] == "from loc"
    r = await rel.complete(LLMRequest(system="", messages=[], model="loc:small", context={"sensitive": False}))  # internal call with no agent: not an agent's customers
    assert r.content[0]["text"] == "from loc"


# ---------- API ----------
def client(sim_runs):
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    rt.qualifications = Qualifications()
    sims = SimpleNamespace(runs=SimpleNamespace(get=lambda rid: _get(sim_runs, rid)), modes=["scripted"], scenarios=[])
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), simulations=sims)), rt


async def _get(runs, rid):
    return runs.get(rid)


def test_the_api_records_a_qualification_from_a_stored_run_and_lists_it():
    stored = {"r1": run([result("r", True, True)])}
    stored["r1"].id = "r1"
    c, rt = client(stored)
    h = {"authorization": f"Bearer {KEY}"}
    assert c.post("/v1/agents/support/qualifications", headers=h, json={"model": M, "runId": "nope"}).status_code == 404
    out = c.post("/v1/agents/support/qualifications", headers=h, json={"model": M, "runId": "r1"})
    assert out.status_code == 201 and out.json()["qualified"] is True and out.json()["runId"] == "r1"
    assert [q["model"] for q in c.get("/v1/agents/support/qualifications", headers=h).json()["qualifications"]] == [M]
    assert c.post("/v1/agents/support/qualifications", json={"model": M, "runId": "r1"}).status_code == 401


# ---------- review fixes ----------
async def test_sensitivity_sticks_after_personal_data_has_been_masked():
    from northcx.runtime import _flat
    assert _flat([{"type": "text", "text": "a"}, {"type": "tool_result"}]) == "a"
    reg = ProviderRegistry()
    pub, loc = Fake("pub", "big"), Fake("loc", "small")
    reg.register(pub, default=True)
    reg.register(loc)
    rel = ReliableLLM(reg, ["pub:big"], retries=0, timeout=None)
    rel.selector = parse_routing("policy: {sensitive: [local]}", reg, {"pub": "public-cloud", "loc": "local"})
    rt = Runtime(rel, InMemoryStore(), TraceStore())
    agent = support_agent()
    await rt.run(agent, "s", "hello")
    assert pub.calls == ["big"]
    await rt.run(agent, "s", "my number is 123-45-6789")   # masked before it reaches the model; the conversation is now sensitive
    assert loc.calls and pub.calls == ["big"]
    loc.calls.clear()
    await rt.run(agent, "s", "thanks, that is all")        # the personal data is only asterisks in the history now, and still counts
    assert loc.calls and pub.calls == ["big"]


def test_topic_words_match_the_start_of_a_word_not_the_middle():
    sel = parse_routing("", ProviderRegistry(), {})
    assert sel.is_sensitive_text("I can't access my Account") and sel.is_sensitive_text("my accounts are locked")
    assert not sel.is_sensitive_text("the discard pile and a scorecard") and not sel.is_sensitive_text("embankment")


# ---------- mixed providers, with the real adapter (WP1.6) ----------
async def test_a_chain_across_providers_falls_back_and_never_crosses_the_tier_line():
    def down(req):
        return httpx.Response(503, json={"error": {"message": "overloaded"}})

    def up(req):
        return httpx.Response(200, json={"model": "m2", "choices": [{"message": {"role": "assistant", "content": "ok from the second"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    def provider(name, handler):
        return OpenAICompatibleLLM(name, "https://x.example.com/v1", "m", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    reg = ProviderRegistry()
    reg.register(provider("first", down), default=True)
    reg.register(provider("second", up))
    reg.register(provider("cloud", up))
    rel = ReliableLLM(reg, ["second:m", "cloud:m"], retries=0, timeout=None)
    r = await rel.complete(LLMRequest(system="", messages=[{"role": "user", "content": "x"}], model="first:m"))
    assert r.fallback and r.content[0]["text"] == "ok from the second" and r.provider == "second"
    rel.selector = parse_routing("policy: {sensitive: [local]}", reg, {"first": "local", "second": "local", "cloud": "public-cloud"})
    r = await rel.complete(LLMRequest(system="", messages=[{"role": "user", "content": "x"}], model="first:m", context={"sensitive": True}))
    assert r.provider == "second" and all(s["model"] != "second:m" for s in r.decision["skipped"]) and r.decision["skipped"][0]["model"] == "cloud:m"


async def test_qualifications_are_kept_in_the_database(engine):
    from northcx.db import PgQualifications
    svc = Qualifications(PgQualifications(engine))
    await svc.record(run([result("r", True, True)]), "support", M)
    other = Qualifications(PgQualifications(engine))  # another server process sees the same answer
    assert await other.is_qualified("support", M, "d1") and not await other.is_qualified("support", M, "d2")
    await svc.record(run([result("r", True, False)]), "support", M)
    assert not await other.is_qualified("support", M, "d1")
    assert [q.qualified for q in await other.list("support")] == [False, True]
