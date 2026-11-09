"""WP1.9 and WP1.10: tiers, the data policy, routing rules, a fallback that never crosses the line, and the decision in the trace."""
import pytest

from examples.support_agent import support_agent
from northcx.llm import ScriptedLLM, text
from northcx.providers import Capabilities, ProviderRegistry
from northcx.providers.selection import NoEligibleModel, parse_routing
from northcx.reliability import ModelUnavailable, ReliableLLM
from northcx.runtime import Runtime
from northcx.secrets import ConfigError
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.types import MODEL_CONTEXT, LLMRequest, LLMResponse

TIERS = {"loc": "local", "priv": "private-cloud", "pub": "public-cloud"}


class Fake:
    def __init__(self, name, model, tools=True, fail=False):
        self.name, self.default_model, self.capabilities, self.prices, self.fail, self.calls = name, model, Capabilities(tools=tools), {}, fail, []

    async def complete(self, req):
        self.calls.append(req.model)
        if self.fail:
            raise ConnectionError("down")
        return LLMResponse(content=[{"type": "text", "text": f"from {self.name}"}], model=req.model)


def stack(rules="", policy="", fail_local=False, topics=""):
    reg = ProviderRegistry()
    fakes = {"pub": Fake("pub", "big"), "loc": Fake("loc", "small", fail=fail_local), "priv": Fake("priv", "mid")}
    for n in ("pub", "loc", "priv"):
        reg.register(fakes[n], default=n == "pub")
    sel = parse_routing(f"{policy}\n{topics}\n{rules}", reg, TIERS)
    rel = ReliableLLM(reg, ["pub:big", "priv:mid"], retries=0, timeout=None)
    rel.selector = sel
    return rel, fakes, sel


REQ = lambda ctx=None, model=None: LLMRequest(system="", messages=[{"role": "user", "content": "x"}], model=model, context=ctx)  # noqa: E731


async def test_a_sensitive_conversation_never_reaches_public_cloud_even_on_fallback():
    rel, f, _ = stack(fail_local=True)
    r = await rel.complete(REQ({"sensitive": True}, "loc:small"))
    assert r.content[0]["text"] == "from priv" and r.fallback  # local failed; the fallback stayed inside the allowed tiers
    assert f["pub"].calls == [] and f["loc"].calls == ["small"] and f["priv"].calls == ["mid"]
    assert r.decision["skipped"] == [{"model": "pub:big", "reason": "public-cloud is not allowed for a sensitive conversation"}]


async def test_an_empty_eligible_set_means_a_person_never_a_forbidden_tier():
    rel, f, _ = stack(policy="policy: {sensitive: [local]}")
    f["loc"].fail = True
    with pytest.raises(ModelUnavailable):  # the only allowed model failed: the runtime hands off; no other tier is tried
        await rel.complete(REQ({"sensitive": True}, "loc:small"))
    assert f["pub"].calls == [] and f["priv"].calls == []
    only_public = ProviderRegistry()
    only_public.register(Fake("pub", "big"), default=True)
    r2 = ReliableLLM(only_public, [], retries=0, timeout=None)
    r2.selector = parse_routing("", only_public, {"pub": "public-cloud"})
    with pytest.raises(ModelUnavailable, match="no model is allowed"):
        await r2.complete(REQ({"sensitive": True}))


async def test_unknown_context_is_treated_as_sensitive():
    rel, f, _ = stack()
    r = await rel.complete(REQ(None))
    assert f["pub"].calls == [] and r.decision["sensitive"] is True


async def test_an_ordinary_conversation_may_use_any_tier_and_rules_pick_the_first_match():
    rules = """rules:
  - name: simple reads stay local
    when: {sensitive: false, effect: read}
    use: {tier: local}
  - name: writes need the strong model
    when: {sensitive: false, effect: write}
    use: {model: "pub:big"}
"""
    rel, f, _ = stack(rules=rules)
    r = await rel.complete(REQ({"sensitive": False, "effect": "read"}))
    assert f["loc"].calls == ["small"] and r.decision["rule"] == "simple reads stay local" and r.decision["tier"] == "local"
    r = await rel.complete(REQ({"sensitive": False, "effect": "write"}))
    assert f["pub"].calls == ["big"] and r.decision["rule"] == "writes need the strong model"
    r = await rel.complete(REQ({"sensitive": False, "effect": "none"}))
    assert r.decision["rule"] is None  # no rule matched: the requested or default model


async def test_a_named_agent_may_be_allowed_public_cloud_explicitly():
    rel, f, _ = stack(policy="policy: {publicCloudAllowedAgents: [billing]}")
    await rel.complete(REQ({"sensitive": True, "agent": "billing"}, "pub:big"))
    assert f["pub"].calls == ["big"]
    # another agent is still refused public cloud
    r = await rel.complete(REQ({"sensitive": True, "agent": "other"}, "pub:big"))
    assert r.decision["skipped"][0]["model"] == "pub:big"


async def test_tools_need_a_model_that_can_call_them():
    reg = ProviderRegistry()
    reg.register(Fake("loc", "small", tools=False), default=True)
    reg.register(Fake("priv", "mid"))
    rel = ReliableLLM(reg, ["priv:mid"], retries=0, timeout=None)
    rel.selector = parse_routing("", reg, {"loc": "local", "priv": "private-cloud"})
    r = await rel.complete(REQ({"sensitive": True, "needs_tools": True}))
    assert r.decision["model"] == "priv:mid" and r.decision["skipped"] == [{"model": "loc:small", "reason": "cannot call tools"}]


@pytest.mark.parametrize("bad,msg", [
    ("policy: {sensitive: [moon]}", "policy.sensitive"),
    ("sensitiveTopics: [1]", "list of words"),
    ("colour: red", "unknown setting"),
    ("rules: [{name: a, use: {tier: local, model: 'loc:x'}}]", "exactly one"),
    ("rules: [{name: a, when: {mood: sad}, use: {tier: local}}]", "unknown condition"),
    ("rules: [{use: {tier: local}}]", "needs a name"),
])
def test_the_rules_file_refuses_mistakes_with_a_reason(bad, msg):
    reg = ProviderRegistry()
    reg.register(Fake("loc", "small"), default=True)
    with pytest.raises(ConfigError, match=msg):
        parse_routing(bad, reg, {"loc": "local"})


# ---------- in the runtime ----------
def runtime(rel, sensitive_agent=False):
    rt = Runtime(rel, InMemoryStore(), TraceStore())
    a = support_agent()
    a.sensitive = sensitive_agent
    return rt, a


async def test_the_runtime_marks_personal_data_and_topics_sensitive_and_records_the_choice():
    rel, f, _ = stack()
    rt, agent = runtime(rel)
    r = await rt.run(agent, "s1", "hello there")
    assert f["pub"].calls  # nothing sensitive: public allowed, and it is the default
    r = await rt.run(agent, "s2", "my card was charged twice, my email is a.b@example.com")
    choice = next(e for e in r.trace.events if e.type == "model_choice").data
    assert choice["sensitive"] is True and choice["tier"] in ("local", "private-cloud") and any(s["model"] == "pub:big" for s in choice["skipped"])
    f["pub"].calls.clear()
    r = await rt.run(agent, "s2", "thanks")  # once sensitive, the conversation stays sensitive
    assert f["pub"].calls == []


async def test_an_agent_marked_sensitive_and_the_context_does_not_leak_out_of_the_turn():
    rel, f, _ = stack()
    rt, agent = runtime(rel, sensitive_agent=True)
    await rt.run(agent, "s", "hello there")
    assert f["pub"].calls == [] and MODEL_CONTEXT.get() is None


def test_the_sensitive_flag_keeps_old_digests():
    from northcx.spec import AgentSpec
    base = {"spec_version": 1, "id": "a", "instructions": "i"}
    assert AgentSpec.model_validate(base).digest() == AgentSpec.model_validate({**base, "sensitive": False}).digest()
    assert AgentSpec.model_validate({**base, "sensitive": True}).digest() != AgentSpec.model_validate(base).digest()
