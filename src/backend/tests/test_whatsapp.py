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
from northcx.channels.whatsapp import TemplateRefused, WhatsAppChannel, WhatsAppNotifier, WhatsAppProvider, parse_webhook
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
    assert got == [{"id": "wamid.1", "phone": "+14155550123", "to": PHONE_ID, "text": "Where is order 1042?", "media": 0, "items": []}]
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


# ---- several numbers, media, templates ----
SECOND = "209876543210"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00" + b"\x1f\x15\xc4\x89" + b"\x00\x00\x00\x00IEND\xaeB`\x82"


def multi(script, agent_attachments=None, http=None, templates=None, optin=None):
    from northcx.attachments import InMemoryAttachments
    repo, atts = InMemorySmsRepo(), InMemoryAttachments()
    real = WhatsAppProvider("tok", SECRET, VERIFY, client=httpx.AsyncClient(transport=httpx.MockTransport(http)) if http else None)
    cap = Capture()
    real.send = cap.send  # type: ignore[method-assign]
    sent_t = []

    async def send_template(to, from_, name, language, params):
        sent_t.append((to, from_, name, language, params))
        return "wamid.t"
    real.send_template = send_template  # type: ignore[method-assign]
    cfgs = {PHONE_ID: SmsConfig(PHONE_ID, "support"), SECOND: SmsConfig(SECOND, "billing")}
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), outbox=Outbox(notifier=WhatsAppNotifier(repo, real, cfgs)))
    rt.privacy.sms = repo
    agent = support_agent()
    if agent_attachments:
        agent.attachments = agent_attachments
    billing = support_agent()
    billing.id = "billing"
    ch = WhatsAppChannel(rt, {"support": agent, "billing": billing}, repo, real, cfgs, atts, None, templates or {"order_update": "en_US"}, optin)
    return ch, rt, cap, repo, atts, sent_t


async def test_each_number_has_its_own_agent_and_replies_leave_from_the_number_they_came_in_on():
    ch, rt, cap, repo, *_ = multi([text("from support"), text("from billing")])
    a = await ch.receive_body(json.dumps(payload(mid="m1", to=PHONE_ID)).encode())
    b = await ch.receive_body(json.dumps(payload(mid="m2", to=SECOND)).encode())
    assert a[0].session_id != b[0].session_id
    assert cap.sent == [("+14155550123", PHONE_ID, "from support"), ("+14155550123", SECOND, "from billing")]
    assert (await repo.get_session(a[0].session_id)).our_number == PHONE_ID and (await repo.get_session(b[0].session_id)).our_number == SECOND
    assert await ch.receive_body(json.dumps(payload(mid="m3", to="999999")).encode()) == []


async def test_pictures_are_read_only_when_the_agent_accepts_them_and_only_from_whatsapp_hosts():
    def handler(req):
        u = str(req.url)
        if u.endswith("/12345"):
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=12345", "mime_type": "image/png"})
        if "fbsbx.com" in u:
            return httpx.Response(200, content=PNG)
        return httpx.Response(404)
    msg = payload(kind="image", mid="img1", image={"id": "12345", "mime_type": "image/png", "caption": "my parcel"})
    ch, rt, cap, repo, atts, _ = multi([text("I can see it.")], agent_attachments=["image"], http=handler)
    res = await ch.receive_body(json.dumps(msg).encode())
    assert res[0].status == "replied" and len(atts.items) == 1 and "my parcel" in json.dumps(rt.llm.requests[0].messages)
    ch, rt, cap, repo, atts, _ = multi([text("I cannot see it.")], http=handler)  # the agent did not opt in to attachments
    await ch.receive_body(json.dumps(msg).encode())
    sent = json.dumps(rt.llm.requests[0].messages)
    assert not atts.items and "does not read attachments" in sent


async def test_a_media_address_outside_whatsapp_is_never_fetched():
    fetched = []

    def handler(req):
        fetched.append(str(req.url))
        if str(req.url).endswith("/12345"):
            return httpx.Response(200, json={"url": "https://evil.example.net/steal", "mime_type": "image/png"})
        return httpx.Response(200, content=PNG)
    ch, rt, cap, repo, atts, _ = multi([text("ok")], agent_attachments=["image"], http=handler)
    await ch.receive_body(json.dumps(payload(kind="image", mid="img2", image={"id": "12345"})).encode())
    assert not any("evil" in u for u in fetched) and not atts.items and "could not be fetched" in json.dumps(rt.llm.requests[0].messages)


async def test_a_template_goes_only_to_people_who_messaged_us_or_opted_in():
    ch, rt, cap, repo, atts, sent = multi([text("hi")], optin={"+4915112345678"})
    with pytest.raises(TemplateRefused, match="not messaged"):
        await ch.send_template(PHONE_ID, "+14155550123", "order_update", ["1042"])
    await ch.receive_body(json.dumps(payload(mid="m1")).encode())  # now they have
    assert await ch.send_template(PHONE_ID, "+14155550123", "order_update", ["1042"]) == "wamid.t"
    assert await ch.send_template(None, "+4915112345678", "order_update", []) == "wamid.t"  # on the opt-in list
    assert sent[0] == ("+14155550123", PHONE_ID, "order_update", "en_US", ["1042"])
    for args, msg in (((PHONE_ID, "+14155550123", "unlisted", []), "approved"), (("111", "+14155550123", "order_update", []), "Unknown WhatsApp number"),
                      ((PHONE_ID, "4155550123", "order_update", []), "international"), ((PHONE_ID, "+14155550123", "order_update", ["x"] * 11), "Too many")):
        with pytest.raises(TemplateRefused, match=msg):
            await ch.send_template(*args)
    await ch.receive_body(json.dumps(payload("STOP", mid="m2")).encode())
    with pytest.raises(TemplateRefused, match="opted out"):
        await ch.send_template(PHONE_ID, "+14155550123", "order_update", [])


async def test_templates_are_rate_limited_per_person():
    ch, *_ = multi([text("hi")])
    ch.configs[PHONE_ID].max_replies_per_number_per_hour = 3  # the reply to the first message counts too
    await ch.receive_body(json.dumps(payload(mid="m1")).encode())
    for _ in range(2):
        await ch.send_template(PHONE_ID, "+14155550123", "order_update", [])
    with pytest.raises(TemplateRefused, match="Too many messages"):
        await ch.send_template(PHONE_ID, "+14155550123", "order_update", [])


async def test_the_real_provider_builds_template_messages():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(seen.get("status", 200), json={"messages": [{"id": "wamid.5"}]})
    p = WhatsAppProvider("tok", SECRET, VERIFY, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await p.send_template("+14155550123", PHONE_ID, "order_update", "en_US", ["1042"]) == "wamid.5"
    t = seen["body"]["template"]
    assert seen["body"]["type"] == "template" and t["name"] == "order_update" and t["language"] == {"code": "en_US"} and t["components"][0]["parameters"] == [{"type": "text", "text": "1042"}]
    seen["status"] = 400
    with pytest.raises(PermanentSendError):
        await p.send_template("+14155550123", PHONE_ID, "order_update", "en_US", [])


def test_the_template_endpoint_needs_a_channel_or_admin_key_and_reports_refusals():
    ch, rt, cap, repo, atts, sent = multi([text("hi")])
    ac = AccessControl(bootstrap_key="boot" * 10)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, whatsapp=ch))
    h = {"authorization": "Bearer " + "boot" * 10}
    body = {"to": "+14155550123", "template": "order_update", "params": ["1042"]}
    assert c.post("/v1/channels/whatsapp/templates/send", json=body, headers=h).status_code == 403  # nobody has messaged this number yet
    import asyncio
    asyncio.run(ch.receive_body(json.dumps(payload(mid="m1")).encode()))
    r = c.post("/v1/channels/whatsapp/templates/send", json=body, headers=h)
    assert r.status_code == 200 and r.json() == {"sent": True, "messageId": "wamid.t"}
    assert c.post("/v1/channels/whatsapp/templates/send", json={**body, "template": "Bad Name"}, headers=h).status_code == 400
    assert c.post("/v1/channels/whatsapp/templates/send", json=body).status_code == 401
    audit = c.get("/v1/audit?limit=10", headers=h).json()["entries"]
    assert any(e["action"] == "whatsapp.template" for e in audit) and "14155550123" not in json.dumps(audit)
