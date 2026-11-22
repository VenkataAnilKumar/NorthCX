import json

import pytest
from pydantic import BaseModel

from examples.support_agent import SPEC_PATH, registry, support_agent
from northcx.agent import Tool
from northcx.llm import ScriptedLLM, text
from northcx.spec import AgentSpec, BuildContext, SpecError, default_registry, dump_spec, load_spec, load_specs, parse_spec

MINIMAL = "id: a\ninstructions: help people\n"


class In(BaseModel):
    x: str


def test_minimal_spec_gets_defaults():
    s = parse_spec(MINIMAL)
    assert s.max_steps == 8 and s.tools == [] and s.guardrails == [] and s.spec_version == 1


def test_json_is_accepted_and_round_trips():
    s = load_spec(SPEC_PATH)
    again = parse_spec(dump_spec(s))
    assert again == s and again.digest() == s.digest()


def test_digest_is_stable_and_sensitive():
    a, b = parse_spec(MINIMAL), parse_spec(MINIMAL)
    assert a.digest() == b.digest()
    assert parse_spec(MINIMAL + "max_steps: 9\n").digest() != a.digest()
    reordered = parse_spec("instructions: help people\nid: a\n")
    assert reordered.digest() == a.digest()


def test_bare_guardrail_names_equal_explicit_form():
    a = parse_spec(MINIMAL + "guardrails: [no_card_numbers]\n")
    b = parse_spec(MINIMAL + "guardrails:\n  - name: no_card_numbers\n")
    assert a == b


@pytest.mark.parametrize("bad,fragment", [
    ("id: a\n", "Instructions are required"),
    ("id: 'bad id'\ninstructions: x\n", "Agent id can only use"),
    (MINIMAL + "max_steps: 0\n", "Most steps per message must be at least 1"),
    (MINIMAL + "surprise: 1\n", "'surprise' is not something"),
    (MINIMAL + "spec_version: 99\n", "spec_version"),
    ("- not\n- a mapping\n", "mapping"),
    ("id: [unclosed\n", "YAML"),
])
def test_invalid_specs_are_rejected_with_a_useful_message(bad, fragment):
    with pytest.raises(SpecError) as e:
        parse_spec(bad)
    assert fragment in str(e.value)


def test_unknown_references_are_all_reported_together():
    s = parse_spec(MINIMAL + "tools: [nope, also_nope, nope]\nguardrails: [ghost]\ninput_guardrails: [spirit]\n")
    problems = default_registry().validate(s)
    assert len(problems) == 5
    with pytest.raises(SpecError) as e:
        default_registry().build(s)
    assert "nope" in str(e.value) and "ghost" in str(e.value) and "spirit" in str(e.value)


def test_duplicate_tool_registration_is_an_error():
    r = default_registry()
    r.tool(Tool("t", "d", In, lambda d, c: 1))
    with pytest.raises(SpecError):
        r.tool(Tool("t", "d", In, lambda d, c: 1))


def test_builds_agent_with_configured_guardrails():
    r = default_registry()
    r.tool(Tool("t", "d", In, lambda d, c: 1))
    s = parse_spec(MINIMAL + "tools: [t]\ninput_guardrails:\n  - name: pii_detection\n    config: {mask_pii: false}\n")
    agent = r.build(s)
    assert [t.name for t in agent.tools] == ["t"]
    assert agent.input_guardrails[0].mask_pii is False


def test_bad_guardrail_config_is_reported_not_raised_raw():
    s = parse_spec(MINIMAL + "input_guardrails:\n  - name: pii_detection\n    config: {nonsense: 1}\n")
    with pytest.raises(SpecError) as e:
        default_registry().build(s)
    assert "configuration" in str(e.value)


def test_llm_policy_needs_a_model_and_policies():
    s = parse_spec(MINIMAL + "guardrails:\n  - name: llm_policy\n    config: {policies: [be kind]}\n")
    with pytest.raises(SpecError):
        default_registry().build(s)
    agent = default_registry().build(s, BuildContext(llm=ScriptedLLM([text("{}")])))
    assert agent.guardrails[0].name == "llm-policy"
    with pytest.raises(SpecError):
        default_registry().build(parse_spec(MINIMAL + "guardrails: [llm_policy]\n"), BuildContext(llm=ScriptedLLM([])))


def test_spec_built_agent_matches_the_example_behaviour():
    agent = support_agent()
    assert agent.id == "support"
    assert [t.name for t in agent.tools] == ["lookup_order", "issue_refund"]
    assert [g.name for g in agent.guardrails] == ["no-card-numbers"]
    assert [g.name for g in agent.input_guardrails] == ["pii-detection", "prompt-injection"]
    refund = next(t for t in agent.tools if t.name == "issue_refund")
    assert refund.requires_approval is not None


def test_load_specs_rejects_duplicate_ids(tmp_path):
    (tmp_path / "a.yaml").write_text(MINIMAL)
    (tmp_path / "b.json").write_text(json.dumps({"id": "a", "instructions": "x"}))
    with pytest.raises(SpecError):
        load_specs(tmp_path)


def test_dump_is_stable_text():
    s = AgentSpec(id="a", instructions="x")
    assert dump_spec(s) == dump_spec(parse_spec(dump_spec(s)))


def test_load_specs_reports_missing_or_empty_directories(tmp_path):
    with pytest.raises(SpecError, match="not found"):
        load_specs(tmp_path / "nope")
    with pytest.raises(SpecError, match="No agent spec files"):
        load_specs(tmp_path)
