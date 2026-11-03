"""WhatsApp channel: signed JSON webhook, one-time verification, shared conversation engine, undeliverable replies."""
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.channels.sms import InMemorySmsRepo, PermanentSendError, SmsConfig, SmsNotifier, SmsSendError
from northcx.channels.whatsapp import WhatsAppChannel, WhatsAppNotifier, WhatsAppProvider, parse_webhook
from northcx.llm import ScriptedLLM, text
from northcx.outbox import Outbox
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

PHONE_ID, SECRET, VERIFY = "109876543210", "app-secret", "verify-me"


def payload(body="Where is order 1042?", mid="wamid.1", frm="14155550123", to=PHONE_ID, kind="text", **extra):
    msg = {"id": mid, "from": frm, "type": kind, **({"text": {"body": body}} if kind == "text" else {}), **extra}
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"metadata": {"phone_number_id": to}, "messages": [msg]}}]}]}


def sign(raw: bytes, secret=SECRET):
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


class Capture:
    def __init__(self):
        self.sent, self.fail = [], None

    async def send(self, to, from_, body):
        if self.fail:
            raise self.fail
        self.sent.append((to, from_, body))
        return "wamid.out"


def build(script, http=None):
    repo = InMemorySmsRepo()
    real = WhatsAppProvider("tok", SECRET, VERIFY, client=httpx.AsyncClient(transport=httpx.MockTransport(http)) if http else None)
    cap = Capture()
    real.send = cap.send  # type: ignore[method-assign]
    cfg = SmsConfig(PHONE_ID)
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), outbox=Outbox(notifier=WhatsAppNotifier(repo, real, cfg)))
    rt.privacy.sms = repo
    return WhatsAppChannel(rt, {"support": support_agent()}, repo, real, cfg), rt, cap, repo, real


def test_parsing_extracts_messages_and_skips_receipts_and_garbage():
    got = parse_webhook(json.dumps(payload()).encode())
    assert got == [{"id": "wamid.1", "phone": "+14155550123", "to": PHONE_ID, "text": "Where is order 1042?", "media": 0}]
    assert parse_webhook(json.dumps(payload(kind="image"))  .encode())[0]["media"] == 1
    receipt = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PHONE_ID}, "statuses": [{"id": "x"}]}}]}]}
    assert parse_webhook(json.dumps(receipt).encode()) == []
    for bad in (b"nope", b"[]", b'{"object":"page"}'):
        with pytest.raises(ValueError):
            parse_webhook(bad)
    junk = {"object": "whatsapp_business_account", "entry": [None, {"changes": [None, {"value": 5}, {"value": {"messages": [1, {"id": 5}, {"id": "a", "from": "abc"}]}}]}]}
    assert parse_webhook(json.dumps(junk).encode()) == []


async def test_a_message_is_answered_and_replies_go_out_through_whatsapp():
    ch, rt, cap, repo, _ = build([text("It ships tomorrow.")])
    res = await ch.receive_body(json.dumps(payload()).encode())
    assert res[0].status == "replied" and res[0].session_id.startswith("wa-")
    assert cap.sent == [("+14155550123", PHONE_ID, "It ships tomorrow.")]
    again = await ch.receive_body(json.dumps(payload()).encode())
    assert again[0].status == "duplicate" and len(cap.sent) == 1


async def test_stop_words_and_other_numbers_and_the_sms_notifier_stay_in_their_lane():
    ch, rt, cap, repo, real = build([text("ok")] * 3)
    assert (await ch.receive_body(json.dumps(payload("STOP", mid="m1")).encode()))[0].status == "opted_out"
    assert (await ch.receive_body(json.dumps(payload("hello", mid="m2")).encode()))[0].status == "ignored"
    assert await ch.receive_body(json.dumps(payload("hi", mid="m3", to="999999")).encode()) == []
    assert cap.sent == []
    # an SMS notifier on the same store does not deliver a WhatsApp conversation
    await ch.receive_body(json.dumps(payload("START", mid="m4")).encode())
    res = await ch.receive_body(json.dumps(payload("hello", mid="m5")).encode())
    sms_cap = Capture()
    other = type("P", (), {"send": sms_cap.send})()
    from northcx.outbox import OutboxMessage
    await SmsNotifier(repo, other, SmsConfig("+14155550100")).deliver(OutboxMessage(res[0].session_id, "approval_result", {"reply": "x"}, id=99))
    assert sms_cap.sent == []


async def test_an_undeliverable_reply_is_recorded_not_retried_forever():
    ch, rt, cap, repo, _ = build([text("hi")])
    cap.fail = PermanentSendError("refused (400)")
    res = await ch.receive_body(json.dumps(payload()).encode())
    assert res[0].status == "replied"
    assert any(m["outcome"] == "undeliverable" for m in repo.messages.values())


async def test_temporary_failures_raise_so_the_outbox_retries():
    ch, rt, cap, repo, real = build([text("hi")])
    cap.fail = SmsSendError("provider returned 500")
    n = WhatsAppNotifier(repo, real, SmsConfig(PHONE_ID))
    res = await ch.receive_body(json.dumps(payload()).encode())
    from northcx.outbox import OutboxMessage
    with pytest.raises(SmsSendError):
        await n.deliver(OutboxMessage(res[0].session_id, "approval_result", {"reply": "later"}, id=77))


async def test_the_real_provider_posts_to_the_graph_api_and_classifies_errors():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(seen.get("status", 200), json={"messages": [{"id": "wamid.9"}]})
    p = WhatsAppProvider("tok", SECRET, VERIFY, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await p.send("+14155550123", PHONE_ID, "hello") == "wamid.9"
    assert seen["url"].endswith(f"/{PHONE_ID}/messages") and seen["auth"] == "Bearer tok" and seen["body"]["to"] == "14155550123" and seen["body"]["text"]["body"] == "hello"
    seen["status"] = 400
    with pytest.raises(PermanentSendError):
        await p.send("+14155550123", PHONE_ID, "x")
    seen["status"] = 429
    with pytest.raises(SmsSendError) as ei:
        await p.send("+14155550123", PHONE_ID, "x")
    assert not isinstance(ei.value, PermanentSendError)
    with pytest.raises(ValueError):
        await p.send("+14155550123", "../etc", "x")


def test_configuration_is_checked():
    for args in (("", SECRET, VERIFY), ("t", "", VERIFY), ("t", SECRET, "")):
        with pytest.raises(ValueError):
            WhatsAppProvider(*args)
    with pytest.raises(ValueError):
        WhatsAppProvider("t", SECRET, VERIFY, base_url="http://graph.example.com")


# ---- the public webhook ----
def api():
    ch, rt, cap, repo, _ = build([text("hello")] * 4)
    ac = AccessControl(bootstrap_key="boot" * 10)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, whatsapp=ch)), cap


def post(c, body, sig=None):
    raw = json.dumps(body).encode()
    return c.post("/channels/whatsapp/meta", content=raw, headers={"content-type": "application/json", "x-hub-signature-256": sig if sig is not None else sign(raw)})


def test_the_webhook_needs_the_body_signature_not_an_api_key():
    c, cap = api()
    assert post(c, payload()).status_code == 200 and len(cap.sent) == 1
    assert post(c, payload(mid="2"), sig="sha256=bad").status_code == 403 and post(c, payload(mid="3"), sig="").status_code == 403
    assert post(c, payload(mid="4"), sig=sign(json.dumps(payload(mid="4")).encode(), "other-secret")).status_code == 403
    assert len(cap.sent) == 1
    audit = c.get("/v1/audit?limit=10", headers={"authorization": "Bearer " + "boot" * 10}).json()["entries"]
    assert any(e["action"] == "auth.failed" and e["target"] == "/channels/whatsapp/meta" for e in audit)


def test_the_webhook_validates_input_and_survives_redelivery():
    c, cap = api()
    raw = b"not json"
    assert c.post("/channels/whatsapp/meta", content=raw, headers={"x-hub-signature-256": sign(raw)}).status_code == 400
    big = b"x" * 300_000
    assert c.post("/channels/whatsapp/meta", content=big, headers={"x-hub-signature-256": sign(big)}).status_code in (400, 413)
    assert post(c, payload()).status_code == 200 and post(c, payload()).status_code == 200 and len(cap.sent) == 1


def test_verification_echoes_the_challenge_only_for_the_right_token():
    c, _ = api()
    ok = c.get("/channels/whatsapp/meta", params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345" and ok.headers["content-type"].startswith("text/plain")
    for params in ({"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}, {"hub.mode": "subscribe", "hub.challenge": "1"},
                   {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"},
                   {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "<script>alert(1)</script>"}):
        assert c.get("/channels/whatsapp/meta", params=params).status_code == 403


def test_it_is_off_unless_configured():
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key="boot" * 10)))
    assert c.post("/channels/whatsapp/meta", content=b"{}").status_code == 501 and c.get("/channels/whatsapp/meta").status_code == 501
