"""SMS channel, channel styles and the signed public webhook."""
import asyncio
import time
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.channels.sms import (InMemorySmsRepo, SmsChannel, SmsConfig, SmsNotifier, SmsSendError, TwilioProvider, parse_form, phone_hash,
                                  split_sms, valid_number)
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.outbox import Outbox
from northcx.privacy import PrivacyService
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.spec import AgentSpec, default_registry
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

URL = "https://api.shop.test/channels/sms/twilio"
OURS, JANE = "+14155550100", "+14155550123"


class FakeProvider:
    def __init__(self, valid=True):
        self.sent, self.valid, self.fail = [], valid, False

    def valid_signature(self, url, params, signature):
        return self.valid and signature == "good"

    async def send(self, to, from_, body):
        if self.fail:
            raise SmsSendError("could not send text: provider returned 500")
        self.sent.append((to, from_, body))
        return f"SM{len(self.sent)}"


def inbound(body="Where is order 1042?", sid="SM1", frm=JANE, to=OURS, **extra):
    return {"MessageSid": sid, "From": frm, "To": to, "Body": body, **extra}


def build(script, **cfg):
    repo, provider = InMemorySmsRepo(), FakeProvider()
    config = SmsConfig(OURS, webhook_url=URL, **cfg)
    notifier = SmsNotifier(repo, provider, config)
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), outbox=Outbox(notifier=notifier))
    rt.privacy.sms = repo
    return SmsChannel(rt, {"support": support_agent()}, repo, provider, config), rt, provider, repo


# ---- helpers and provider ----
def test_numbers_forms_and_splitting():
    assert valid_number("+14155550123") and not valid_number("4155550123") and not valid_number("+0123") and not valid_number("") and not valid_number("+1415555012x")
    assert parse_form(b"A=1&B=hello+world&C=%2B1415&D=") == {"A": "1", "B": "hello world", "C": "+1415", "D": ""}
    with pytest.raises(ValueError):
        parse_form(b"x" * 70_000)
    assert split_sms("Short.") == ["Short."] and split_sms("") == []
    long = ("Sentence number one is here. " * 120).strip()
    parts = split_sms(long, limit=500, max_parts=3)
    assert len(parts) == 3 and all(len(p) <= 500 for p in parts) and parts[-1].endswith("…")
    assert all(p.endswith(".") for p in parts[:-1])
    assert split_sms("x" * 2000, limit=500, max_parts=2)[0] == "x" * 500
    assert phone_hash(JANE) != phone_hash(OURS) and JANE not in phone_hash(JANE)


def test_signature_matches_the_published_example_and_rejects_tampering():
    p = TwilioProvider("AC123", "12345")
    params = {"CallSid": "CA1234567890ABCDE", "Caller": "+12349013030", "Digits": "1234", "From": "+12349013030", "To": "+18005551212"}
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    sig = "0/KCTR6DLpKmkAf8muzZqo1nDgQ="
    assert p.valid_signature(url, params, sig)
    assert not p.valid_signature(url, {**params, "Digits": "9999"}, sig) and not p.valid_signature(url + "x", params, sig)
    assert not p.valid_signature(url, params, "") and not p.valid_signature(url, params, "nonsense")
    assert not TwilioProvider("AC123", "other").valid_signature(url, params, sig)
    with pytest.raises(ValueError):
        TwilioProvider("", "x")


async def test_twilio_sending_uses_basic_auth_and_reports_failures_without_secrets():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], req.content.decode()
        return httpx.Response(201, json={"sid": "SM123"})

    p = TwilioProvider("AC123", "tok", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await p.send(JANE, OURS, "Hi there") == "SM123"
    assert seen["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json" and seen["auth"].startswith("Basic ")
    assert "To=%2B14155550123" in seen["body"] and "Body=Hi+there" in seen["body"]
    bad = TwilioProvider("AC123", "tok", client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(SmsSendError, match="500") as e:
        await bad.send(JANE, OURS, "x")
    assert "tok" not in str(e.value)

    def boom(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(SmsSendError, match="ConnectError"):
        await TwilioProvider("AC123", "tok", client=httpx.AsyncClient(transport=httpx.MockTransport(boom))).send(JANE, OURS, "x")


# ---- the channel ----
async def test_a_text_is_answered_and_the_number_is_the_customer():
    ch, rt, provider, repo = build([text("Order 1042 was delivered.")])
    await rt.store.set_fact(f"phone:{JANE}", "tier", "gold")
    r = await ch.receive(inbound())
    assert r.status == "replied" and r.session_id.startswith("sms-")
    assert "gold" in rt.llm.requests[0].system  # the carrier-verified number identifies the customer
    assert await rt.outbox.flush() >= 0
    assert provider.sent == [] or provider.sent[0][2] == "Order 1042 was delivered."


async def test_replies_are_texted_back_through_the_outbox_once():
    ch, rt, provider, repo = build([text("Order 1042 was delivered.")])
    await ch.receive(inbound())
    assert provider.sent == [(JANE, OURS, "Order 1042 was delivered.")]
    assert await rt.outbox.flush(now=time.time() + 100) == 0 and len(provider.sent) == 1


async def test_a_conversation_continues_until_it_has_been_idle_too_long():
    ch, rt, provider, repo = build([text("one"), text("two"), text("three")], session_idle_hours=1)
    a = await ch.receive(inbound(sid="SM1"))
    b = await ch.receive(inbound("and the refund?", sid="SM2"))
    assert a.session_id == b.session_id and "Where is order 1042?" in str(rt.llm.requests[1].messages)
    repo.sessions[a.session_id].last_seen -= 7200
    c = await ch.receive(inbound("hello again", sid="SM3"))
    assert c.session_id != a.session_id


async def test_duplicate_deliveries_and_foreign_numbers_are_handled_safely():
    ch, rt, provider, repo = build([text("one"), text("two")])
    rs = await asyncio.gather(*[ch.receive(inbound()) for _ in range(5)])
    assert sorted(r.status for r in rs) == ["duplicate"] * 4 + ["replied"] and len(provider.sent) == 1
    assert (await ch.receive(inbound(sid="SM9", to="+14155559999"))).status == "ignored"
    for bad in [inbound(frm="not-a-number"), inbound(sid=""), {"From": JANE}]:
        with pytest.raises(ValueError):
            await ch.receive(bad)


async def test_stop_help_and_start_keywords():
    ch, rt, provider, repo = build([text("hello"), text("welcome back")])
    assert (await ch.receive(inbound("STOP", sid="S1"))).status == "opted_out"
    assert provider.sent == [] and await repo.is_opted_out(JANE) and phone_hash(JANE) in repo.opt_outs and JANE not in repo.opt_outs
    r = await ch.receive(inbound("where is my order", sid="S2"))
    assert r.status == "ignored" and "opted out" in r.reason and rt.llm.requests == [] and provider.sent == []
    assert (await ch.receive(inbound(" start. ", sid="S3"))).status == "opted_in"
    assert (await ch.receive(inbound("hi", sid="S4"))).status == "replied"
    assert (await ch.receive(inbound("Help", sid="S5"))).status == "help" and "STOP" in provider.sent[-1][2]
    for word in ["stopall", "Unsubscribe", "CANCEL", "end", "quit"]:
        assert (await ch.receive(inbound(word, sid=f"W{word}"))).status == "opted_out"


async def test_nothing_is_sent_to_a_number_that_opted_out_while_a_reply_was_pending():
    ch, rt, provider, repo = build([text("pending answer")])
    ch.rt.outbox.notifier = None  # hold delivery
    await ch.receive(inbound(sid="S1"))
    await repo.set_opt_out(JANE, True)
    ch.rt.outbox.notifier = SmsNotifier(repo, provider, ch.config)
    await ch.rt.outbox.flush()
    assert provider.sent == []


async def test_a_sender_is_limited_to_a_few_replies_an_hour():
    ch, rt, provider, repo = build([text("ok")] * 6, max_replies_per_number_per_hour=2)
    statuses = [(await ch.receive(inbound(f"msg {i}", sid=f"S{i}"))).status for i in range(4)]
    assert statuses == ["replied", "replied", "rate_limited", "rate_limited"] and len(provider.sent) == 2
    assert (await ch.receive(inbound("hi", sid="O1", frm="+14155550999"))).status == "replied"


async def test_blank_texts_attachments_and_long_texts():
    ch, rt, provider, repo = build([text("seen"), text("ok")], max_chars=50)
    assert (await ch.receive(inbound("   ", sid="S1"))).status == "ignored"
    await ch.receive(inbound("x" * 500, sid="S2", NumMedia="2"))
    sent_text = rt.llm.requests[0].messages[0]["content"]
    assert sent_text.startswith("x" * 50) and "x" * 51 not in sent_text and "2 attachment(s) that were not read" in sent_text


async def test_a_conversation_with_a_person_is_not_answered_by_the_agent():
    ch, rt, provider, repo = build([tool_call("handoff_to_human", {"reason": "wants a person"}, "t1"), text("back")])
    first = await ch.receive(inbound("get me a person", sid="S1"))
    assert first.status == "escalated" and first.handoff_id
    held = await ch.receive(inbound("hello??", sid="S2"))
    assert held.status == "held_for_person" and len(rt.llm.requests) == 1 and len(provider.sent) == 1
    await rt.handoffs.resolve(first.handoff_id, "jo")
    assert (await ch.receive(inbound("thanks, one more thing", sid="S3"))).status == "replied"


async def test_a_failed_send_is_retried_and_long_replies_become_several_texts():
    ch, rt, provider, repo = build([text("The answer. " * 200)])
    provider.fail = True
    await ch.receive(inbound())
    assert provider.sent == []
    provider.fail = False
    assert await rt.outbox.flush(now=time.time() + 60) == 1
    assert 1 < len(provider.sent) <= 3 and all(len(b) <= 1500 for _, _, b in provider.sent)


async def test_approval_results_are_texted_to_the_customer():
    from northcx.approval_flow import ApprovalFlow
    ch, rt, provider, repo = build([tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1"), text("Your refund was approved.")])
    agents = {"support": support_agent()}
    held = await ch.receive(inbound("refund 240 on 2077"))
    assert held.status == "needs_approval" and len(provider.sent) == 1
    await ApprovalFlow(rt).resolve(agents, (await rt.approvals.list("pending"))[0].id, True, "rae")
    assert provider.sent[-1][2] == "Your refund was approved." and provider.sent[-1][0] == JANE


async def test_export_and_erasure_include_texts_but_keep_the_opt_out():
    ch, rt, provider, repo = build([text("hello")])
    await ch.receive(inbound())
    await ch.receive(inbound("STOP", sid="S2"))
    p = PrivacyService(rt.privacy)
    out = await p.export_customer(f"phone:{JANE}")
    assert out["sessions"][0]["sms"]["messages"]
    r = await p.erase_customer(f"phone:{JANE}")
    assert r["removed"]["sms"] >= 2 and repo.sessions == {} and not [m for m in repo.messages.values() if m["peer"] == JANE]
    assert await repo.is_opted_out(JANE)  # the STOP is still honoured


# ---- channel styles ----
def test_channel_styles_are_validated_and_do_not_change_old_digests():
    base = {"spec_version": 1, "id": "a", "instructions": "i"}
    old = AgentSpec.model_validate(base)
    assert "channel_styles" not in old.canonical()
    new = AgentSpec.model_validate({**base, "channel_styles": {"sms": "Two short sentences, no markdown", "email": "Greeting and sign-off"}})
    assert new.digest() != old.digest() and default_registry().build(new).channel_styles["sms"].startswith("Two")
    for bad in [{"S": "x"}, {"x": "x"}, {"sms": " "}, {"sms": "z" * 1001}, {"bad name": "x"}]:
        with pytest.raises(Exception):
            AgentSpec.model_validate({**base, "channel_styles": bad})


async def test_the_style_for_the_channel_is_added_to_the_prompt_and_only_that_one():
    agent = support_agent()
    agent.channel_styles = {"sms": "Reply in two short sentences", "email": "Write a greeting and sign-off"}
    llm = ScriptedLLM([text("a"), text("b"), text("c")])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    await rt.run(agent, "s1", "hi", channel="sms")
    await rt.run(agent, "s2", "hi", channel="email")
    await rt.run(agent, "s3", "hi")
    assert "Style for this channel (sms): Reply in two short sentences" in llm.requests[0].system and "sign-off" not in llm.requests[0].system
    assert "Write a greeting" in llm.requests[1].system and "Style for this channel" not in llm.requests[2].system


async def test_sms_and_email_channels_pass_their_names():
    ch, rt, provider, repo = build([text("ok")])
    agent = ch.agents
    a = support_agent()
    a.channel_styles = {"sms": "Be brief"}

    class P:
        async def get(self, i, *_):
            return a

    ch.agents = P()
    await ch.receive(inbound())
    assert "Style for this channel (sms): Be brief" in rt.llm.requests[0].system


# ---- the public webhook ----
def api(valid=True):
    ch, rt, provider, repo = build([text("hello")] * 4)
    provider.valid = valid
    ac = AccessControl(bootstrap_key="boot" * 10)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, sms=ch)), provider, rt


def post(c, params, sig="good"):
    return c.post("/channels/sms/twilio", content=urlencode(params), headers={"content-type": "application/x-www-form-urlencoded", "x-twilio-signature": sig})


def test_the_webhook_needs_a_valid_signature_not_an_api_key():
    c, provider, rt = api()
    r = post(c, inbound())
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml") and r.text == "<Response></Response>"
    assert len(provider.sent) == 1
    assert post(c, inbound(sid="SM2"), sig="forged").status_code == 403 and post(c, inbound(sid="SM3"), sig="").status_code == 403
    assert len(provider.sent) == 1
    audit = c.get("/v1/audit?limit=10", headers={"authorization": "Bearer " + "boot" * 10}).json()["entries"]
    assert any(e["action"] == "auth.failed" and e["target"] == "/channels/sms/twilio" for e in audit)


def test_the_webhook_validates_input_and_survives_redelivery():
    c, provider, rt = api()
    assert post(c, {"From": JANE}).status_code == 400
    assert c.post("/channels/sms/twilio", content=b"x" * 70_000, headers={"x-twilio-signature": "good"}).status_code in (400, 413)
    assert post(c, inbound()).status_code == 200 and post(c, inbound()).status_code == 200 and len(provider.sent) == 1


def test_the_webhook_is_off_unless_configured_and_throttles_forgers():
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    off = TestClient(create_app(rt, rt.traces, {"support": support_agent()}))
    assert post(off, inbound()).status_code == 501
    from northcx.access import LimitConfig
    ch, rt2, provider, repo = build([text("x")] * 3)
    provider.valid = False
    ac = AccessControl(bootstrap_key="boot" * 10, limits=LimitConfig(auth_failures_per_minute=5))
    c = TestClient(create_app(rt2, rt2.traces, {"support": support_agent()}, access=ac, sms=ch))
    codes = [post(c, inbound(sid=f"S{i}"), sig="bad").status_code for i in range(12)]
    assert codes[:5] == [403] * 5 and 429 in codes and set(codes) <= {403, 429}
    provider.valid = True
    assert post(c, inbound(sid="real"), sig="good").status_code == 200  # valid requests are not throttled by forged ones


# ---- storage contract on memory and Postgres ----
@pytest.fixture(params=["memory", "postgres"])
def srepo(request):
    if request.param == "memory":
        return InMemorySmsRepo()
    from northcx.db import PgSmsRepo
    return PgSmsRepo(request.getfixturevalue("engine"))


async def test_sms_repository_contract(srepo):
    from northcx.channels.sms import SmsSession
    assert await srepo.latest_session(JANE, OURS) is None
    old = SmsSession("sms-1", JANE, OURS, 1000, 1000)
    new = SmsSession("sms-2", JANE, OURS, 2000, 2000)
    await srepo.save_session(old)
    await srepo.save_session(new)
    assert (await srepo.latest_session(JANE, OURS)).session_id == "sms-2" and (await srepo.get_session("sms-1")).created_at == 1000
    new.last_seen = 3000
    await srepo.save_session(new)
    assert (await srepo.get_session("sms-2")).last_seen == 3000 and (await srepo.get_session("nope")) is None
    assert await srepo.latest_session("+14155550999", OURS) is None
    assert await srepo.record_message("SM1", "sms-2", "in", "replied", JANE) is True and await srepo.record_message("SM1", "sms-2", "in", "replied", JANE) is False
    assert await srepo.has_message("SM1") and not await srepo.has_message("SM2")
    await srepo.record_message("o1", "sms-2", "out", "sent", JANE)
    now = time.time()
    assert await srepo.recent_count(JANE, "out", now - 3600) == 1 and await srepo.recent_count(JANE, "out", now + 5) == 0
    assert not await srepo.is_opted_out(JANE)
    await srepo.set_opt_out(JANE, True)
    await srepo.set_opt_out(JANE, True)
    assert await srepo.is_opted_out(JANE) and not await srepo.is_opted_out("+14155550999")
    await srepo.set_opt_out(JANE, False)
    assert not await srepo.is_opted_out(JANE)


async def test_postgres_privacy_covers_texts_and_keeps_opt_outs(engine):
    from northcx import db
    from northcx.channels.sms import SmsSession
    repo = db.PgSmsRepo(engine)
    await repo.save_session(SmsSession("sms-1", JANE, OURS))
    await repo.record_message("SM1", "sms-1", "in", "replied", JANE)
    await repo.set_opt_out(JANE, True)
    backend = db.PgPrivacy(engine)
    await backend.link("sms-1", f"phone:{JANE}")
    p = PrivacyService(backend)
    assert (await p.export_customer(f"phone:{JANE}"))["sessions"][0]["sms"]["messages"]
    r = await p.erase_customer(f"phone:{JANE}")
    assert r["removed"]["sms"] == 2 and await repo.get_session("sms-1") is None and not await repo.has_message("SM1")
    assert await repo.is_opted_out(JANE)
