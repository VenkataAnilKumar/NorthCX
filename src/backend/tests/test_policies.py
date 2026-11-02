"""The policy library: every policy is proven by its shipped cases."""
import pytest

from northcx.guardrails import GuardrailContext
from northcx.policies import BAD_CONFIGS, CASES, DESCRIPTIONS, FACTORIES
from northcx.spec import AgentSpec, SpecError, default_registry
from examples.support_agent import support_agent
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


@pytest.mark.parametrize("policy,cfg,kind,subject,allow", CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
async def test_policy_case(policy, cfg, kind, subject, allow):
    g = FACTORIES[policy](cfg, None)
    ctx = GuardrailContext("s", [])
    v = await (g.check_tool_call(*subject, ctx) if kind == "tool" else g.check_reply(subject, ctx))
    assert v.allow is allow
    assert allow or v.reason


def test_every_policy_is_documented_and_has_allow_and_block_cases():
    assert set(FACTORIES) == set(DESCRIPTIONS)
    for name in FACTORIES:
        outcomes = {c[4] for c in CASES if c[0] == name}
        assert outcomes == {True, False}, f"{name} needs both allowing and blocking cases"


@pytest.mark.parametrize("name,cfg", BAD_CONFIGS)
def test_bad_configuration_is_refused_at_build_time(name, cfg):
    spec = AgentSpec.model_validate({"spec_version": 1, "id": "a", "instructions": "i", "guardrails": [{"name": name, "config": cfg}]})
    with pytest.raises(SpecError):
        default_registry().build(spec)


def test_policies_are_available_to_specs():
    spec = AgentSpec.model_validate({"spec_version": 1, "id": "a", "instructions": "i",
                                     "guardrails": [{"name": "tool_limit", "config": {"tool": "issue_refund", "field": "amount", "max": 100}}, "max_reply_length"][:1]})
    assert [g.name for g in default_registry().build(spec).guardrails] == ["tool-limit"]


async def test_a_blocked_tool_call_reaches_the_model_as_a_policy_denial_and_runs_nothing():
    a = support_agent()
    a.guardrails.append(FACTORIES["tool_limit"]({"tool": "issue_refund", "field": "amount", "max": 100}, None))
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1"), text("I can't do that.")]), InMemoryStore(), TraceStore())
    r = await rt.run(a, "s", "refund 240")
    assert r.status == "completed" and not r.pending_approvals
    assert any(e.type == "guardrail" and "limit of 100" in e.data["reason"] for e in r.trace.events)
    assert not any(e.type == "approval" or e.type == "tool_result" for e in r.trace.events)
