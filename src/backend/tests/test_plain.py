"""Plain-language checks: every message an author can meet says what is wrong and what to change, in the author's words."""
import re

import pytest
from pydantic import BaseModel, ValidationError

from northcx.agent import Tool
from northcx.plain import explain_errors
from northcx.spec import AgentSpec, Registry

BANNED = re.compile(r"tool_scopes|forced_handoff|input_guardrail|output_guardrail|guardrails|audience:|\bspec\b|schema|\bYAML\b|\bJSON\b|registered|regex|regular expression|'\w+': ", re.I)


class In(BaseModel):
    x: str


def registry():
    r = Registry()
    r.add_tools("registry", [Tool("lookup_order", "Look up an order", In, lambda d, c: {}, effect="read"),
                             Tool("staff_note", "A staff note", In, lambda d, c: {}, effect="read", audience="staff", permission="notes:read")])
    return r


def messages(**spec):
    return registry().validate(AgentSpec(id="a", instructions="help", **spec))


def test_every_check_has_a_plain_message_with_what_to_change_and_no_developer_words():
    cases = {
        "tool that does not exist": messages(tools=["nope"]),
        "tool listed twice": messages(tools=["lookup_order", "lookup_order"]),
        "staff tool on a customer agent": messages(tools=["staff_note"]),
        "customer tool on a staff agent": messages(audience="staff", tools=["lookup_order"]),
        "shadow on a staff agent": messages(audience="staff", shadow=True),
        "same always-send-to-a-person name": messages(forced_handoff=[{"name": "legal", "patterns": ["lawyer"]}, {"name": "legal", "patterns": ["sue"]}]),
        "reply check that does not exist": messages(guardrails=[{"name": "nope"}]),
        "customer message check that does not exist": messages(input_guardrails=[{"name": "nope"}]),
        "tool answer check that does not exist": messages(output_guardrails=[{"name": "nope"}]),
        "skill listed twice": messages(skills=[{"name": "ss"}, {"name": "ss"}]),
        "skill that does not exist": messages(skills=[{"name": "nope"}]),
        "journeys with the same name": messages(journeys=[{"name": "jj", "goal": "g", "steps": [{"purpose": "p"}]}, {"name": "jj", "goal": "g", "steps": [{"purpose": "p"}]}]),
        "journey needing a missing tool": messages(journeys=[{"name": "jj", "goal": "g", "steps": [{"purpose": "p", "tool": "nope"}]}]),
        "strict journey using a tool twice": messages(journeys=[{"name": "jj", "goal": "g", "flexibility": "strict", "steps": [{"purpose": "p", "tool": "lookup_order"}, {"purpose": "q", "tool": "lookup_order"}]}]),
        "limit on a missing tool": messages(tool_scopes={"nope": {"requires_customer": True}}),
        "approval on a missing tool": messages(approvals={"always": ["nope"]}),
        "specialist listed twice": messages(routes=[{"agent": "b", "when": "billing"}, {"agent": "b", "when": "refunds"}]),
        "route to itself": messages(routes=[{"agent": "a", "when": "x"}]),
    }
    for what, problems in cases.items():
        assert problems, f"no message for: {what}"
        for p in problems:
            assert not BANNED.search(p), f"developer words in the message for {what}: {p}"
            assert p[0].isupper() and p.rstrip().endswith((".", ")")), f"a message is a sentence: {p}"
            assert len(p) > 40, f"too short to say what to change: {p}"


def test_the_messages_name_the_thing_and_say_what_to_do():
    (p,) = messages(tools=["nope"])
    assert "nope" in p and "remove" in p.lower() and "lookup_order" in p
    (q,) = messages(approvals={"always": ["nope"]})
    assert "nope" in q and "add the tool" in q.lower()


def errors(**kw):
    with pytest.raises(ValidationError) as e:
        AgentSpec(**kw)
    return explain_errors(e.value.errors())


def test_field_errors_use_the_names_on_the_screen_and_say_what_is_allowed():
    assert errors(id="a", instructions="x", max_steps=99) == ["Most steps per message must be at most 50."]
    assert errors(id="a", instructions="x", max_steps=0) == ["Most steps per message must be at least 1."]
    assert errors(id="a") == ["Instructions are required."]
    assert errors(id="a", instructions="") == ["Instructions cannot be empty."]
    assert errors(id="bad id!", instructions="x") == ["Agent id can only use letters, digits, dots, dashes and underscores."]
    assert errors(id="a", instructions="x", max_steps="many") == ["Most steps per message must be a whole number."]
    assert errors(id="a", instructions="x", shadow="maybe") == ["Shadow mode must be yes or no."]
    assert errors(id="a", instructions="x", audience="robots") == ["Audience must be one of: customer, staff."]
    assert errors(id="a", instructions="x", colour="blue") == ["'colour' is not something an agent can have. Remove it."]
    assert errors(id="a", instructions="x", journeys=[{"name": "jj", "goal": "g", "steps": []}])[0].startswith("Journeys, item 1")
    assert not any(BANNED.search(m) for m in errors(id="a", instructions="x", max_steps=99))


# ---- the plain summary (R2) ----
from northcx.plain import summarize, tool_label  # noqa: E402

CATALOG = [{"name": "lookup_order", "effect": "read", "approval": False}, {"name": "issue_refund", "effect": "write", "approval": True},
           {"name": "update_address", "effect": "write", "approval": False}, {"name": "shop__orders_lookup", "effect": "read", "approval": False}]


def said(**kw):
    return summarize(AgentSpec(id="a", instructions="help", **kw), CATALOG)


def test_tool_names_are_written_as_words():
    assert tool_label("lookup_order") == "lookup order" and tool_label("shop__orders_lookup") == "orders lookup from shop"


def test_the_summary_says_who_it_serves_what_it_can_look_up_and_what_it_can_change():
    s = said(tools=["lookup_order", "issue_refund", "update_address"], approvals={"always": ["update_address"]})
    assert s[0] == "This agent answers customers."
    assert "It can look up: lookup order." in s
    assert "It can change things: issue refund, update address." in s
    assert "A person approves every use of update address." in s
    assert "issue refund has its own rule that can hold a call for a person." in s


def test_a_tool_that_changes_things_and_runs_without_a_person_is_said_plainly():
    s = said(tools=["update_address"])
    assert "update address changes things and runs without a person's OK." in s


def test_it_says_what_always_goes_to_a_person_what_it_follows_and_how_it_replies():
    s = said(tools=["lookup_order"], forced_handoff=[{"name": "legal", "patterns": ["lawyer"]}, {"name": "safety", "patterns": ["fire"]}],
             journeys=[{"name": "refunds", "goal": "g", "steps": [{"purpose": "p"}]}], languages=["en", "es"], routes=[{"agent": "billing", "when": "billing"}],
             guardrails=[{"name": "no_card_numbers"}], input_guardrails=[{"name": "pii_detection"}], shadow=True)
    assert "Conversations about legal, safety always go to a person." in s
    assert "It follows 1 journey: refunds." in s
    assert "It replies in en, es." in s
    assert "It can pass a conversation to: billing." in s
    assert "1 check on replies and tool calls, 1 on customer messages." in s
    assert "Shadow mode is on: a person approves every reply before the customer sees it." in s


def test_an_agent_with_no_tools_says_so_and_a_staff_agent_says_who_it_helps():
    s = summarize(AgentSpec(id="a", instructions="help", audience="staff"), [])
    assert s[0] == "This agent helps your staff." and "It has no tools, so it cannot look anything up or change anything." in s


def test_the_summary_names_every_tool_and_every_approval_rule_in_the_definition():
    import itertools
    names = [c["name"] for c in CATALOG]
    for r in range(len(names) + 1):
        for tools in itertools.combinations(names, r):
            for always in ([], list(tools)[:1]):
                text = " ".join(said(tools=list(tools), approvals={"always": always}))
                assert all(tool_label(t) in text for t in tools)
                assert all(f"A person approves every use of {tool_label(t)}." in text for t in always)


def test_topic_names_are_written_as_words():
    s = said(forced_handoff=[{"name": "formal_complaint", "patterns": ["complain"]}])
    assert "Conversations about formal complaint always go to a person." in s
