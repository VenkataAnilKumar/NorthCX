"""Skills, workflow flexibility, brand voice and tool scopes."""
import json

import pytest
import yaml

from examples.support_agent import registry
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.skills import SkillError, load_skills, parse_skill, render_skill
from northcx.spec import AgentSpec, BuildContext, SpecError
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

BASE = {"spec_version": 1, "id": "a", "instructions": "You help customers.\n", "tools": ["lookup_order"]}


def spec(**kw):
    return AgentSpec.model_validate({**BASE, **kw})


def build(**kw):
    return registry().build(spec(**kw), BuildContext())


# ---- skill files ----
def test_skill_files_are_parsed_strictly():
    s = parse_skill({"name": "triage", "instructions": "Sort the request.", "steps": ["Ask what happened", {"purpose": "Look it up", "tool": "lookup_order", "required": False}]})
    assert [x.purpose for x in s.steps] == ["Ask what happened", "Look it up"] and s.steps[1].required is False and s.tool_names() == ["lookup_order"]
    for bad in [{"name": "X", "instructions": "i"}, {"name": "ok", "instructions": ""}, {"name": "ok", "instructions": "i", "colour": 1}, {"name": "ok", "instructions": "i", "steps": [{"tool": "t"}]},
                {"name": "ok", "instructions": "i", "steps": [{"purpose": "p", "extra": 1}]}, {"name": "ok", "instructions": "i", "tools": "lookup_order"}, "not a map"]:
        with pytest.raises(SkillError):
            parse_skill(bad)


def test_shipped_skills_load_and_names_must_be_unique(tmp_path):
    assert {s.name for s in load_skills("examples/skills")} == {"order_status", "refund_flow"}
    (tmp_path / "a.yaml").write_text("name: dup\ninstructions: x\n")
    (tmp_path / "b.yaml").write_text("name: dup\ninstructions: y\n")
    with pytest.raises(SkillError, match="unique"):
        load_skills(tmp_path)
    (tmp_path / "b.yaml").write_text(": : bad\n\t")
    with pytest.raises(SkillError, match="not valid"):
        load_skills(tmp_path)


# ---- composition ----
def test_skills_voice_and_scopes_do_not_change_old_digests_and_compose_the_prompt():
    plain = spec()
    assert all(k not in plain.canonical() for k in ("skills", "voice", "tool_scopes"))
    rich = spec(skills=[{"name": "refund_flow", "flexibility": "strict"}], voice={"tone": "warm and brief", "guidelines": ["Use the customer's name"], "avoid_phrases": ["unfortunately"], "sign_off": "Take care!"})
    assert rich.digest() != plain.digest()
    a = registry().build(rich, BuildContext())
    assert a.instructions.startswith("You help customers.") and "## Brand voice" in a.instructions and "Tone: warm and brief" in a.instructions
    assert 'Never use these words or phrases: "unfortunately"' in a.instructions and 'End conversations with: "Take care!"' in a.instructions
    assert "## Skill: refund_flow" in a.instructions and "Required steps cannot be skipped" in a.instructions and "1. Look up the order" in a.instructions
    assert [t.name for t in a.tools] == ["lookup_order", "issue_refund"]  # the skill brought the refund tool; nothing is listed twice
    assert "refund_flow" not in plain.instructions and build().instructions == BASE["instructions"]


def test_skill_flexibility_changes_the_wording_and_only_strict_adds_a_rule():
    sk = parse_skill({"name": "sk", "instructions": "i", "steps": [{"purpose": "one", "tool": "lookup_order"}]})
    assert "Required steps cannot be skipped" in render_skill(sk, "strict") and "unless the customer's situation" in render_skill(sk, "guided") and "suggestions" in render_skill(sk, "free")
    for flex, enforced in [("strict", True), ("guided", False), ("free", False)]:
        a = build(skills=[{"name": "refund_flow", "flexibility": flex}])
        assert any(g.name.startswith("skill-order") for g in a.guardrails) is enforced, flex


def test_bad_skill_references_are_reported_together():
    reg = registry()
    problems = reg.validate(spec(skills=[{"name": "ghost"}, {"name": "refund_flow"}, {"name": "refund_flow"}], tool_scopes={"nope": {"requires_customer": True}}))
    text_ = "; ".join(problems)
    assert "Unknown skill 'ghost'" in text_ and "Duplicate skill references" in text_ and "unknown tool 'nope'" in text_
    with pytest.raises(Exception):
        spec(skills=[{"name": "refund_flow", "flexibility": "rigid"}])
    from northcx.skills import Skill, SkillStep
    r2 = registry()
    r2.skill(Skill("needs_crm", "d", "i", (SkillStep("look up", "crm_lookup"),)))
    assert any("needs the tool 'crm_lookup'" in p for p in r2.validate(spec(skills=[{"name": "needs_crm"}])))
    with pytest.raises(SpecError, match="already registered"):
        r2.skill(Skill("needs_crm", "d", "i"))


# ---- enforcement through the runtime ----
async def run(agent, script, messages, customer=None, channel=None):
    llm = ScriptedLLM(script)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    out = [await rt.run(agent, "s", m, customer, channel=channel) for m in messages]
    return out, rt, llm


async def test_a_strict_skill_makes_the_agent_look_before_it_refunds():
    a = build(tools=[], skills=[{"name": "refund_flow", "flexibility": "strict"}])
    script = [tool_call("issue_refund", {"order_id": "1042", "amount": 10}, "t1"), tool_call("lookup_order", {"order_id": "1042"}, "t2"),
              tool_call("issue_refund", {"order_id": "1042", "amount": 10}, "t3"), text("Done.")]
    (r,), rt, llm = await run(a, script, ["refund order 1042 for 10"])
    guard = [e for e in r.trace.events if e.type == "guardrail"]
    assert len(guard) == 1 and "must be done first (use lookup_order)" in guard[0].data["reason"]
    assert r.trace.tools_called() == ["issue_refund", "lookup_order", "issue_refund"] and r.reply == "Done."
    refused = json.dumps(llm.requests[1].messages)
    assert "Blocked by policy" in refused and "lookup_order" in refused


async def test_a_guided_skill_is_advice_only():
    a = build(tools=[], skills=[{"name": "refund_flow", "flexibility": "guided"}])
    (r,), _, _ = await run(a, [tool_call("issue_refund", {"order_id": "1042", "amount": 10}, "t1"), text("Done.")], ["refund 1042 for 10"])
    assert not [e for e in r.trace.events if e.type == "guardrail"] and r.trace.tools_called() == ["issue_refund"]


async def test_optional_steps_do_not_block_and_earlier_turns_count():
    from northcx.skills import Skill, SkillStep
    reg = registry()
    reg.skill(Skill("flex", "d", "i", (SkillStep("look", "lookup_order", required=False), SkillStep("refund", "issue_refund"))))
    a = reg.build(spec(tools=[], skills=[{"name": "flex", "flexibility": "strict"}]), BuildContext())
    (r,), _, _ = await run(a, [tool_call("issue_refund", {"order_id": "1042", "amount": 10}, "t1"), text("ok")], ["refund"])
    assert not [e for e in r.trace.events if e.type == "guardrail"]  # the optional step was skipped, which is allowed
    a2 = build(tools=[], skills=[{"name": "refund_flow", "flexibility": "strict"}])
    results, _, _ = await run(a2, [tool_call("lookup_order", {"order_id": "1042"}, "t1"), text("It is delivered."), tool_call("issue_refund", {"order_id": "1042", "amount": 10}, "t2"), text("Refunded.")],
                              ["where is 1042", "ok please refund 10"])
    assert not [e for e in results[1].trace.events if e.type == "guardrail"]  # the lookup in the earlier turn satisfies the step


async def test_brand_voice_forbidden_words_are_enforced_not_just_requested():
    a = build(voice={"tone": "warm", "avoid_phrases": ["unfortunately"]})
    (r,), _, _ = await run(a, [text("Unfortunately your order is late."), text("Sorry, your order is late.")], ["where is it"])
    assert r.reply == "Sorry, your order is late." and any("brand voice" in e.data["reason"] for e in r.trace.events if e.type == "guardrail")


async def test_tool_scopes_depend_on_the_customer_their_facts_and_the_channel():
    scopes = {"issue_refund": {"requires_customer": True, "facts": {"tier": ["gold", "platinum"]}, "channels": ["web", "email"]}}
    a = build(tools=["lookup_order", "issue_refund"], tool_scopes=scopes)
    call = [tool_call("issue_refund", {"order_id": "1042", "amount": 10}, "t1"), text("answered")]
    anon, _, _ = await run(a, call, ["refund"], customer=None, channel="web")
    assert "only available to identified customers" in [e.data["reason"] for e in anon[0].trace.events if e.type == "guardrail"][0]
    rt = Runtime(ScriptedLLM(list(call)), InMemoryStore(), TraceStore())
    plain = await rt.run(a, "s1", "refund", "jane", channel="web")
    assert "not available for this customer" in [e.data["reason"] for e in plain.trace.events if e.type == "guardrail"][0]
    await rt.store.set_fact("jane", "tier", "Gold")
    rt.llm.script = list(call)
    ok = await rt.run(a, "s2", "refund", "jane", channel="web")
    assert not [e for e in ok.trace.events if e.type == "guardrail"] and ok.status == "completed"
    rt.llm.script = list(call)
    sms = await rt.run(a, "s3", "refund", "jane", channel="sms")
    assert "not available on this channel" in [e.data["reason"] for e in sms.trace.events if e.type == "guardrail"][0]


async def test_company_context_counts_as_customer_facts_for_scopes():
    from northcx.context import CachedContext

    class Crm:
        async def fetch(self, customer_id, session_id):
            return {"tier": "platinum"}

    a = build(tools=["lookup_order", "issue_refund"], tool_scopes={"issue_refund": {"facts": {"tier": ["platinum"]}}})
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "1042", "amount": 10}, "t1"), text("ok")]), InMemoryStore(), TraceStore(), context=CachedContext(Crm()))
    r = await rt.run(a, "s", "refund", "jane")
    assert not [e for e in r.trace.events if e.type == "guardrail"]


async def test_scopes_are_checked_again_when_an_approved_action_runs():
    from northcx.approval_flow import ApprovalFlow
    a = build(tools=["lookup_order", "issue_refund"], tool_scopes={"issue_refund": {"facts": {"tier": ["gold"]}}})
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1"), text("done")]), InMemoryStore(), TraceStore())
    await rt.store.set_fact("jane", "tier", "gold")
    held = await rt.run(a, "s", "refund 240 on 2077", "jane")
    assert held.status == "needs_approval"
    await rt.store.set_fact("jane", "tier", "bronze")  # her status changed while the approval waited
    res = await ApprovalFlow(rt).resolve({"a": a}, (await rt.approvals.list("pending"))[0].id, True, "rae")
    assert "blocked by policy" in json.dumps(res.error or (await rt.approvals.list())[0].result)


def test_api_lists_skills_for_viewers():
    import asyncio
    from fastapi.testclient import TestClient
    from examples.support_agent import support_agent
    from northcx.access import AccessControl
    from northcx.server import create_app
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key="boot" * 10)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, skills=registry().skill_info()))
    H = {"authorization": "Bearer " + "boot" * 10}
    body = c.get("/v1/skills", headers=H).json()
    assert [s["name"] for s in body["skills"]] == ["order_status", "refund_flow"] and body["flexibility"] == ["strict", "guided", "free"]
    assert body["skills"][1]["steps"][0] == {"purpose": "Look up the order and confirm its status and total", "tool": "lookup_order", "required": True}
    chan = asyncio.new_event_loop().run_until_complete(ac.issue("c", "channel", "root"))[1]
    assert c.get("/v1/skills", headers={"authorization": f"Bearer {chan}"}).status_code == 403
