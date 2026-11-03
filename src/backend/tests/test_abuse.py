"""Abuse detection: calm handling first, a person for threats and persistence, a slow-down for bursts, and no false alarms on ordinary anger."""
import json

import pytest

from examples.support_agent import registry, support_agent
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.safety.abuse import CALM_HANDOFF, NOTE, SLOW_DOWN, AbuseDetection
from northcx.spec import AgentSpec, BuildContext
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def detector(**kw):
    return AbuseDetection(clock=Clock(), **kw)


@pytest.mark.parametrize("msg", ["You are an idiot", "this is f*cking useless, you stupid bot", "shut up", "what a piece of shit service", "you're worthless"])
async def test_abusive_language_is_noticed_but_allowed_the_first_time(msg):
    r = await detector().check_input_ctx(msg.replace("f*cking", "fucking"), "s", [])
    assert r.allow and "abusive" in r.kinds and r.note == NOTE and r.strikes == 1


@pytest.mark.parametrize("msg", ["I am very angry about my order", "This is the third time my parcel is late!!", "Your service is terrible and I want a refund", "I'm furious", "the assistant keeps saying shutdown", "Please don't hurt my feelings lol",
                                 "My class is on the Scunthorpe road", "bombastic offers in your store", "I assumed the passage was fine"])
async def test_ordinary_anger_and_lookalike_words_are_not_abuse(msg):
    r = await detector().check_input_ctx(msg, "s", [])
    assert r.allow and not r.kinds and r.note is None


@pytest.mark.parametrize("msg", ["I'm going to kill you", "i will find you and hurt you", "I know where you live", "there is a bomb in your office"])
async def test_threats_go_to_a_person_immediately_without_the_model(msg):
    r = await detector().check_input_ctx(msg, "s", [])
    assert not r.allow and r.trigger == "abuse" and r.status == "escalated" and r.reply == CALM_HANDOFF and "threat" in r.kinds


async def test_persistent_abuse_is_handed_to_a_person_on_the_third_message():
    d = detector()
    earlier = []
    outcomes = []
    for msg in ("you idiot", "useless bot, shut up", "you are pathetic garbage"):
        r = await d.check_input_ctx(msg, "s", earlier)
        outcomes.append((r.allow, r.strikes))
        earlier.append(msg)
    assert outcomes == [(True, 1), (True, 2), (False, 3)]
    assert (await detector(max_strikes=2).check_input_ctx("you idiot", "s", ["you moron"])).allow is False
    assert (await detector(hand_off=False).check_input_ctx("you idiot", "s", ["you moron"] * 5)).allow is True  # warn only


async def test_repeating_the_same_message_is_noted_then_handed_off():
    d = detector()
    r = await d.check_input_ctx("Where is my order", "s", ["where is my order!", "Where is my order"])
    assert r.allow and r.kinds == ["repeat"] and "repeat" in r.note.lower() or "same message" in r.note
    r = await d.check_input_ctx("where is my order", "s", ["where is my order"] * 5)
    assert not r.allow and r.trigger == "abuse" and "6 times" in r.reason
    assert not (await d.check_input_ctx("a new question", "s", ["where is my order"] * 5)).kinds


async def test_a_burst_gets_a_slow_down_reply_not_a_hand_off_and_other_conversations_are_unaffected():
    clock = Clock()
    d = AbuseDetection(burst_limit=3, burst_seconds=60, clock=clock)
    res = [await d.check_input_ctx(f"message {i}", "s1", []) for i in range(5)]
    assert [r.allow for r in res] == [True, True, True, False, False]
    assert res[3].reply == SLOW_DOWN and res[3].status == "completed" and res[3].kinds == ["burst"] and res[3].trigger is None
    assert (await d.check_input_ctx("hello", "s2", [])).allow
    clock.t += 61
    assert (await d.check_input_ctx("hello again", "s1", [])).allow  # the window passed


def test_configuration_is_validated_and_extra_terms_work():
    for kw in ({"max_strikes": 0}, {"repeat_limit": 1}, {"burst_limit": 1}, {"burst_seconds": 1}, {"extra_terms": ["x" * 80]}, {"extra_terms": [" "]}, {"extra_terms": ["a"] * 201}):
        with pytest.raises(ValueError):
            AbuseDetection(**kw)
    d = AbuseDetection(extra_terms=["knobhead", "c++ guru"])
    assert d.kinds_in("what a knobhead") == ["abusive"] and d.kinds_in("you c++ guru") == ["abusive"] and d.kinds_in("knob") == []


# ---- inside a conversation ----
def agent_with_abuse(**cfg):
    r = registry()
    spec = AgentSpec(id="shop", instructions="You help Acme customers with orders.", tools=["lookup_order"], input_guardrails=[{"name": "abuse_detection", "config": cfg}])
    assert r.validate(spec) == []
    return r.build(spec, BuildContext())


async def test_the_agent_is_told_to_stay_calm_and_a_threat_never_reaches_the_model():
    rt = Runtime(ScriptedLLM([text("I'm sorry about the trouble. I can check your order or connect you with a person.")]), InMemoryStore(), TraceStore())
    agent = agent_with_abuse()
    r = await rt.run(agent, "s1", "you useless idiot, where is my order", "cust-1")
    assert r.status == "completed" and "Stay calm" in rt.llm.requests[0].system
    t = await rt.traces.get(r.trace_id)
    assert [e.data for e in t.events if e.type == "abuse"] == [{"kinds": ["abusive"], "strikes": 1, "blocked": False}]
    assert not any(e.type == "guardrail" for e in t.events)  # noticing is not counted as a block
    n = len(rt.llm.requests)
    r2 = await rt.run(agent, "s2", "I'm going to kill you", "cust-2")
    assert r2.status == "escalated" and r2.handoff_id and len(rt.llm.requests) == n and "colleague" in r2.reply
    h = await rt.handoffs.get(r2.handoff_id)
    assert h.trigger == "abuse" and "abuse" in json.dumps(h.package).lower()


async def test_three_abusive_messages_in_a_conversation_end_in_a_hand_off():
    rt = Runtime(ScriptedLLM([text("ok")] * 3), InMemoryStore(), TraceStore())
    agent = agent_with_abuse()
    statuses = [(await rt.run(agent, "s1", m, "c")).status for m in ("you idiot", "shut up you moron", "you are pathetic garbage")]
    assert statuses == ["completed", "completed", "escalated"]


async def test_a_flood_is_slowed_without_a_hand_off_or_model_call():
    rt = Runtime(ScriptedLLM([text("ok")] * 3), InMemoryStore(), TraceStore())
    agent = agent_with_abuse(burst_limit=2)
    out = [await rt.run(agent, "s1", f"hello {i}", "c") for i in range(4)]
    assert [r.status for r in out] == ["completed"] * 4 and out[2].reply == SLOW_DOWN and out[2].handoff_id is None
    assert len(rt.llm.requests) == 2
