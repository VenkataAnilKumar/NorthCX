"""Voice calls (C5, C6): disclosure and consent, barge-in, speakable replies, keypad, hand-off to a phone queue, silence, language switching, the bridge protocol."""
import asyncio
import dataclasses
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.routing import Route
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.types import LLMRequest, LLMResponse
from northcx.voice import (DEFAULT_STYLE, CallSession, InMemoryCalls, VoiceConfig, consent_answer, say_phrase, speakable)

KEY = "boot" * 10


def test_replies_are_made_speakable():
    assert speakable("**Your order** is *delivered*. See https://shop.example.com/o/1042 for details.") == "Your order is delivered. See for details."
    assert speakable("Options:\n- Refund it\n- Replace it\n1. Or wait") == "Options:. Refund it. Replace it. Or wait"
    long = "First sentence here. " * 60
    out = speakable(long, 100)
    assert len(out) <= 100 and out.endswith(".") and "First sentence here." in out
    assert speakable("`code` and # heading > quote") == "code and heading quote"
    assert speakable("   ") == ""


def test_consent_answers_in_several_languages():
    for yes in ("yes", "Yeah sure", "sí claro", "oui", "ja klar", "okay"):
        assert consent_answer(yes) is True, yes
    for no in ("no", "no thanks", "nein", "non", "nope"):
        assert consent_answer(no) is False, no
    for unclear in ("what", "hmm maybe later", "yes no", ""):
        assert consent_answer(unclear) is None, unclear


def test_phrases_fall_back_to_english_and_names_are_filled_in():
    assert "Acme" in say_phrase("disclosure", "en", brand="Acme") and "automated" in say_phrase("disclosure", "en", brand="Acme")
    assert say_phrase("goodbye", "es") != say_phrase("goodbye", "en") and say_phrase("goodbye", "ja") == say_phrase("goodbye", "en")


def test_the_configuration_is_checked():
    VoiceConfig("support", transfer={"default": "+15551230000", "billing": "sip:billing@pbx.example.com"})
    for kw in ({"recording": "always"}, {"transfer": {"default": "555-1234"}}, {"transfer": {"x": "+0123"}}, {"default_language": "xx"}):
        with pytest.raises(ValueError):
            VoiceConfig("support", **kw)


class Slow:
    """A model that answers only when told to, to test what happens while the agent is still thinking."""

    def __init__(self, *replies):
        self.replies, self.gate, self.requests = list(replies), None, []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        if self.gate is not None:
            await self.gate.wait()
        return self.replies.pop(0)


class Harness:
    def __init__(self, script, agent=None, router=None, **cfg):
        self.llm = script if hasattr(script, "complete") else ScriptedLLM(list(script))
        self.rt = Runtime(self.llm, InMemoryStore(), TraceStore())
        if router:
            self.rt.router = router
        self.agent = agent or support_agent()
        self.sent: list[dict] = []
        self.repo = InMemoryCalls()
        self.now = [1000.0]
        self.cfg = VoiceConfig("support", brand="Acme support", filler_after=0.05, **cfg)

        async def send(m):
            self.sent.append(m)

        async def resolve(agent_id, session_id):
            return self.agent
        self.call = CallSession(self.rt, resolve, self.cfg, self.repo, send, lambda: self.now[0])

    async def do(self, **msg):
        await self.call.handle(msg)

    async def settle(self):
        while self.call._turn is not None and not self.call._turn.done():
            await asyncio.sleep(0.005)

    async def start(self, **kw):
        await self.do(type="start", callId="c1", **{"from": "+15551112222", "to": "+15559998888", **kw})

    async def say(self, t, final=True, **kw):
        await self.do(type="transcript", text=t, final=final, **kw)
        await self.settle()

    def says(self):
        return [m["text"] for m in self.sent if m["type"] == "say"]

    def kinds(self):
        return [m["type"] for m in self.sent]


async def test_the_call_opens_by_saying_it_is_an_automated_assistant_and_keeps_no_number():
    h = Harness([])
    await h.start()
    assert "Acme support" in h.says()[0] and "automated assistant" in h.says()[0] and "How can I help" in h.says()[0]
    rec = await h.repo.get("c1")
    assert rec.caller_hash and "+1555" not in json.dumps(rec.summary()) and "+1555" not in rec.caller_hash and rec.outcome == "in_progress"
    assert h.call.customer_id is None
    h2 = Harness([], trust_caller_id=True)
    await h2.start()
    assert h2.call.customer_id == "phone:+15551112222"


async def test_nothing_counts_before_the_call_starts_or_after_it_ends():
    h = Harness([text("hi")])
    await h.say("hello?")
    assert h.sent == [] and h.llm.requests == []
    await h.start()
    await h.do(type="end")
    n = len(h.sent)
    await h.say("anyone there?")
    assert len(h.sent) == n and (await h.repo.get("c1")).outcome == "caller_hung_up" and (await h.repo.get("c1")).ended_at


async def test_recording_starts_only_after_a_yes():
    h = Harness([text("ok")], recording="consent")
    await h.start()
    assert "record" in h.says()[0].lower() and "record" not in h.kinds()
    await h.say("yes please")
    assert {"type": "record", "on": True} in h.sent and "This call is being recorded" in h.says()[-1]
    rec = await h.repo.get("c1")
    assert rec.consent == "granted" and rec.recorded is True

    n = Harness([], recording="consent")
    await n.start()
    await n.say("no")
    assert not any(m["type"] == "record" for m in n.sent) and "will not be recorded" in n.says()[-1] and (await n.repo.get("c1")).consent == "refused"


async def test_an_unclear_answer_is_asked_again_once_and_then_means_no():
    h = Harness([], recording="consent")
    await h.start()
    await h.say("hmm what")
    assert "Sorry, I did not catch that" in h.says()[-1] and h.call.state == "consent"
    await h.say("maybe")
    assert not any(m["type"] == "record" for m in h.sent) and (await h.repo.get("c1")).consent == "unclear" and h.call.state == "listening"


async def test_the_keypad_can_answer_the_consent_question():
    a = Harness([], recording="consent")
    await a.start()
    await a.do(type="dtmf", digits="1")
    assert {"type": "record", "on": True} in a.sent
    b = Harness([], recording="consent")
    await b.start()
    await b.do(type="dtmf", digits="2")
    assert not any(m["type"] == "record" for m in b.sent) and (await b.repo.get("c1")).consent == "refused"


async def test_a_turn_speaks_a_short_plain_reply_and_the_agent_is_told_it_is_a_phone_call():
    h = Harness([text("**Your order 1042** is *delivered*. Details: https://x.example.com/1042")])
    await h.start()
    await h.say("where is order 1042?")
    assert h.says()[-1] == "Your order 1042 is delivered. Details:"
    assert DEFAULT_STYLE.split(".")[0] in h.llm.requests[0].system and "Style for this channel (voice)" in h.llm.requests[0].system
    rec = await h.repo.get("c1")
    assert rec.turns == 1 and len(rec.latency_ms) == 1 and rec.summary()["latencyMs"]["samples"] == 1


async def test_an_agents_own_voice_style_wins_over_the_default():
    agent = dataclasses.replace(support_agent(), channel_styles={"voice": "Speak like a pirate"})
    h = Harness([text("Arr")], agent=agent)
    await h.start()
    await h.say("hi")
    assert "Speak like a pirate" in h.llm.requests[0].system and "This is a phone call" not in h.llm.requests[0].system


async def test_partial_transcripts_are_ignored_while_listening():
    h = Harness([text("ok")])
    await h.start()
    h.call.state = "listening"
    await h.say("where is my", final=False)
    assert h.llm.requests == []
    await h.say("where is my order", final=True)
    assert len(h.llm.requests) == 1


async def test_barge_in_stops_the_agent_and_keeps_only_what_the_caller_heard():
    h = Harness([text("Your order 1042 was delivered on Monday and signed for by a neighbour."), text("Sure, what else?")])
    await h.start()
    await h.do(type="speech_ended", completed=True)        # the greeting finished
    await h.say("where is order 1042?")
    said = h.sent[-1]
    assert said["interruptible"] is True and h.call.playing
    await h.say("wait", final=False)
    assert h.sent[-1] == {"type": "stop_speaking"} and not h.call.playing
    await h.do(type="speech_ended", utteranceId=said["id"], completed=False, spokenChars=21)
    msgs = await h.rt.store.load_messages("voice-c1")
    assert msgs[-1]["content"] == "Your order 1042 was [interrupted]" or msgs[-1]["content"].endswith("[interrupted]")
    assert msgs[-1]["content"].startswith("Your order 1042")
    await h.say("no I meant order 7")
    assert h.says()[-1] == "Sure, what else?" and (await h.repo.get("c1")).barge_ins == 1


async def test_a_short_noise_does_not_cut_the_agent_off():
    h = Harness([text("Your order is delivered, and here is some detail.")])
    await h.start()
    await h.say("where is order 1042?")
    n = len(h.sent)
    await h.say("uh", final=False)
    assert len(h.sent) == n and h.call.playing


async def test_what_the_caller_says_while_the_agent_is_thinking_is_answered_once_not_read_out_of_order():
    llm = Slow(text("Delivered."), text("Order 7 is shipped."))
    llm.gate = asyncio.Event()
    h = Harness(llm)
    await h.start()
    await h.do(type="transcript", text="where is order 1042", final=True)
    await asyncio.sleep(0.01)
    assert h.call.state == "thinking"
    await h.do(type="transcript", text="actually order 7", final=True)
    llm.gate.set()
    await h.settle()
    assert h.says()[-1] == "Order 7 is shipped." and "Delivered." not in h.says()
    msgs = json.dumps(await h.rt.store.load_messages("voice-c1"))
    assert "order 1042" in msgs and "order 7" in msgs                                    # nothing the caller said is lost


async def test_a_long_wait_gets_one_polite_filler():
    llm = Slow(text("Found it."))
    llm.gate = asyncio.Event()
    h = Harness(llm)
    await h.start()
    await h.do(type="transcript", text="where is order 1042", final=True)
    await asyncio.sleep(0.2)
    assert h.says().count(say_phrase("filler", "en")) == 1
    llm.gate.set()
    await h.settle()
    assert h.says()[-1] == "Found it."


async def test_pressing_zero_hands_the_call_to_a_person_and_transfers_it():
    h = Harness([], transfer={"default": "+15550001111"})
    await h.start()
    await h.do(type="dtmf", digits="0")
    hand = (await h.rt.handoffs.list(None, "voice-c1", 5))[0]
    assert hand.trigger == "customer_request" and "keypad" in hand.reason
    assert h.sent[-1] == {"type": "transfer", "to": "+15550001111", "queue": "general"} and "connecting you" in h.says()[-1]
    assert (await h.repo.get("c1")).outcome == "handed_off" and (await h.repo.get("c1")).handoff_id == hand.id


async def test_the_agents_own_handoff_goes_to_the_right_queue_number():
    class R:
        def route(self, topics, trigger, at=None):
            return Route("billing", True, None, None)
    h = Harness([tool_call("handoff_to_human", {"reason": "refund dispute"}, "t")], router=R(), transfer={"default": "+15550001111", "billing": "+15550002222"})
    await h.start()
    await h.say("I want to dispute a charge")
    assert h.sent[-1]["type"] == "transfer" and h.sent[-1]["to"] == "+15550002222"


async def test_outside_hours_or_with_no_number_the_caller_is_promised_a_callback():
    class Closed:
        def route(self, topics, trigger, at=None):
            return Route("general", False, None, "closed")
    h = Harness([tool_call("handoff_to_human", {"reason": "x"}, "t")], router=Closed(), transfer={"default": "+15550001111"})
    await h.start()
    await h.say("get me a person")
    assert h.sent[-1] == {"type": "hangup", "reason": "callback"} and "call you back" in h.says()[-1] and (await h.repo.get("c1")).outcome == "callback"
    h2 = Harness([tool_call("handoff_to_human", {"reason": "x"}, "t")])
    await h2.start()
    await h2.say("get me a person")
    assert h2.sent[-1] == {"type": "hangup", "reason": "callback"}


async def test_nine_repeats_and_other_keys_are_explained():
    h = Harness([text("Your order is delivered.")])
    await h.start()
    await h.say("where is my order?")
    await h.do(type="dtmf", digits="9")
    assert h.says()[-1] == h.says()[-2] == "Your order is delivered."
    await h.do(type="dtmf", digits="5")
    assert "Press zero for a person" in h.says()[-1]
    r = Harness([])
    await r.start()
    await r.do(type="dtmf", digits="*")
    assert r.says()[-1].count("Hello") == 1                                              # repeats the greeting when nothing else was said


async def test_silence_is_prompted_twice_and_then_the_call_ends_politely():
    h = Harness([])
    await h.start()
    await h.do(type="speech_ended", completed=True)
    for _ in range(2):
        await h.do(type="silence", seconds=8)
        await h.do(type="speech_ended", completed=True)
    assert h.says().count(say_phrase("reprompt", "en")) == 2
    await h.do(type="silence", seconds=8)
    assert h.sent[-1] == {"type": "hangup", "reason": "silence"} and "Goodbye" in h.says()[-1] and (await h.repo.get("c1")).outcome == "silence"


async def test_speaking_resets_the_silence_count():
    h = Harness([text("ok"), text("ok")])
    await h.start()
    await h.do(type="speech_ended", completed=True)
    await h.do(type="silence", seconds=8)
    await h.do(type="speech_ended", completed=True)
    await h.say("where is my order?")
    await h.do(type="speech_ended", completed=True)
    assert h.call._silence_prompts == 0


async def test_the_call_switches_language_when_the_caller_does():
    agent = dataclasses.replace(support_agent(), languages=["en", "es"])
    h = Harness([text("Hello!"), text("Su pedido está entregado."), text("Con gusto.")], agent=agent)
    await h.start()
    await h.say("Hello, where is my order please?")
    assert h.sent[-1]["language"] == "en"
    await h.say("¿Dónde está mi pedido? Necesito ayuda, gracias")
    assert h.sent[-1]["language"] == "es" and h.sent[-1]["text"] == "Su pedido está entregado."
    await h.do(type="speech_ended", completed=True)
    await h.do(type="silence", seconds=8)
    assert h.says()[-1] == say_phrase("reprompt", "es")                                    # the platform's own phrases follow the caller too
    assert (await h.repo.get("c1")).languages == ["en", "es"]


async def test_the_bridge_can_tell_us_the_language_up_front():
    h = Harness([])
    await h.start(language="fr")
    assert "assistant automatique" in h.says()[0] and h.sent[0]["language"] == "fr" and (await h.repo.get("c1")).languages == ["fr"]


async def test_a_call_that_runs_too_long_is_ended_politely():
    h = Harness([text("ok")], )
    h.cfg.max_minutes = 1
    await h.start()
    h.now[0] += 120
    await h.say("still here")
    assert h.sent[-1] == {"type": "hangup", "reason": "time_limit"} and (await h.repo.get("c1")).outcome == "time_limit" and h.llm.requests == []


async def test_if_the_agent_cannot_answer_the_caller_is_told_and_passed_on():
    h = Harness([])
    async def none(agent_id, session_id):
        return None
    h.call.resolve_agent = none
    await h.start()
    await h.say("hello")
    assert any("something went wrong" in t for t in h.says()) and h.sent[-1]["type"] == "hangup" and (await h.repo.get("c1")).outcome == "callback"


@pytest.fixture(params=["memory", "postgres"])
def calls(request):
    if request.param == "memory":
        return InMemoryCalls()
    from northcx.db import PgCalls
    return PgCalls(request.getfixturevalue("engine"))


async def test_call_record_repository_contract(calls):
    from northcx.voice import CallRecord
    c = CallRecord("c1", "voice-c1", "support", "h" * 64, started_at=10.0, languages=["en"])
    await calls.save(c)
    c.outcome, c.turns, c.latency_ms, c.recorded, c.ended_at, c.languages = "resolved", 3, [100, 300, 200], True, 99.0, ["en", "es"]
    await calls.save(c)
    await calls.save(CallRecord("c2", "voice-c2", "support", "g" * 64, started_at=20.0))
    got = await calls.get("c1")
    assert (got.outcome, got.turns, got.latency_ms, got.recorded, got.languages, got.ended_at) == ("resolved", 3, [100, 300, 200], True, ["en", "es"], 99.0)
    assert [r.call_id for r in await calls.recent(10)] == ["c2", "c1"] and await calls.get("nope") is None
    assert got.summary()["latencyMs"] == {"median": 200, "p95": 300, "samples": 3}
    assert await calls.erase_session("voice-c1") == 1 and await calls.erase_session("voice-c1") == 0


# ---- the bridge protocol over a WebSocket ----
def api(script, **kw):
    rt = Runtime(ScriptedLLM(list(script)), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    cfg = VoiceConfig("support", brand="Acme support", filler_after=5, **kw) if kw.get("_on", True) is not None else None
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, voice=cfg)), ac, rt


def recv(ws, n=1):
    return [ws.receive_json() for _ in range(n)]


def test_a_bridge_can_run_a_whole_call_over_the_websocket():
    c, ac, rt = api([text("Your order is delivered.")])
    with c.websocket_connect("/v1/voice/stream", headers={"authorization": f"Bearer {KEY}"}) as ws:
        ws.send_json({"type": "start", "callId": "ws1", "from": "+15551112222"})
        greeting = ws.receive_json()
        assert "automated assistant" in greeting["text"]
        ws.send_json({"type": "speech_ended", "utteranceId": greeting["id"], "completed": True})
        ws.send_json({"type": "transcript", "text": "where is my order?", "final": True})
        out = ws.receive_json()
        assert out["type"] == "say" and out["text"] == "Your order is delivered." and out["interruptible"] is True
        ws.send_json({"type": "end"})
    calls = c.get("/v1/voice/calls", headers={"authorization": f"Bearer {KEY}"}).json()
    assert calls["enabled"] is True and calls["calls"][0]["callId"] == "ws1" and calls["calls"][0]["outcome"] == "caller_hung_up" and calls["calls"][0]["turns"] == 1
    assert "+1555" not in json.dumps(calls)
    actions = [e["action"] for e in c.get("/v1/audit?limit=20", headers={"authorization": f"Bearer {KEY}"}).json()["entries"]]
    assert "voice.call" in actions


def test_only_channel_keys_may_open_a_call_stream():
    c, ac, rt = api([])
    loop = asyncio.new_event_loop()
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    for headers, code in [({}, 4401), ({"authorization": "Bearer nope"}, 4401), ({"authorization": f"Bearer {key('viewer')}"}, 4403), ({"authorization": f"Bearer {key('developer')}"}, 4403)]:
        with pytest.raises(WebSocketDisconnect) as e:
            with c.websocket_connect("/v1/voice/stream", headers=headers) as ws:
                ws.receive_json()
        assert e.value.code == code, headers
    with c.websocket_connect("/v1/voice/stream", headers={"authorization": f"Bearer {key('channel')}"}) as ws:
        ws.send_json({"type": "start", "callId": "ok1"})
        assert ws.receive_json()["type"] == "say"
    denied = [e["action"] for e in c.get("/v1/audit?limit=20", headers={"authorization": f"Bearer {KEY}"}).json()["entries"]]
    assert "auth.failed" in denied and "auth.denied" in denied


def test_voice_is_off_unless_configured():
    c, ac, rt = api([], _on=None)
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect("/v1/voice/stream", headers={"authorization": f"Bearer {KEY}"}) as ws:
            ws.receive_json()
    assert e.value.code == 4404
    assert c.get("/v1/voice/calls", headers={"authorization": f"Bearer {KEY}"}).json() == {"enabled": False, "calls": []}


def test_a_bridge_that_sends_rubbish_does_not_break_the_call():
    c, ac, rt = api([text("ok")])
    with c.websocket_connect("/v1/voice/stream", headers={"authorization": f"Bearer {KEY}"}) as ws:
        ws.send_text("not json")
        ws.send_text(json.dumps([1, 2, 3]))
        ws.send_json({"type": "transcript", "text": "hello before start", "final": True})
        ws.send_json({"type": "start", "callId": "r1"})
        greeting = ws.receive_json()
        assert greeting["type"] == "say"
        ws.send_json({"type": "speech_ended", "utteranceId": greeting["id"], "completed": True})
        ws.send_json({"type": "bogus"})
        ws.send_json({"type": "dtmf", "digits": "5"})
        assert "Press zero" in ws.receive_json()["text"]


def test_a_dropped_connection_ends_the_call_record_and_erasure_removes_it():
    c, ac, rt = api([])
    with c.websocket_connect("/v1/voice/stream", headers={"authorization": f"Bearer {KEY}"}) as ws:
        ws.send_json({"type": "start", "callId": "drop1"})
        ws.receive_json()
    h = {"authorization": f"Bearer {KEY}"}
    assert c.get("/v1/voice/calls", headers=h).json()["calls"][0]["outcome"] == "caller_hung_up"
    assert c.delete("/v1/privacy/sessions/voice-drop1", headers=h).status_code == 200
    assert c.get("/v1/voice/calls", headers=h).json()["calls"] == []
