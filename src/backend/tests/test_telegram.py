"""Telegram channel: secret-token webhook, private chats only, shared conversation engine."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.channels.sms import InMemorySmsRepo, PermanentSendError, SmsConfig, SmsSendError
from northcx.channels.telegram import TelegramChannel, TelegramNotifier, TelegramProvider, parse_update
from northcx.llm import ScriptedLLM, text
from northcx.outbox import Outbox
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

TOKEN, SECRET = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345", "s3cret-token-value-1234"


def update(body="Where is order 1042?", uid=777, uid_chat=None, update_id=1, **extra):
    return {"update_id": update_id, "message": {"message_id": 5, "from": {"id": uid, "is_bot": False}, "chat": {"id": uid_chat or uid, "type": "private"}, "text": body, **extra}}


class Capture:
    def __init__(self):
        self.sent, self.fail = [], None

    async def send(self, to, from_, body):
        if self.fail:
            raise self.fail
        self.sent.append((to, from_, body))
        return "1"


def build(script):
    repo = InMemorySmsRepo()
    prov = TelegramProvider(TOKEN, SECRET)
    cap = Capture()
    prov.send = cap.send  # type: ignore[method-assign]
    cfg = SmsConfig(prov.bot_id)
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), outbox=Outbox(notifier=TelegramNotifier(repo, prov, cfg)))
    rt.privacy.sms = repo
    return TelegramChannel(rt, {"support": support_agent()}, repo, prov, cfg), rt, cap, repo


def test_updates_are_parsed_and_non_private_or_non_message_updates_are_ignored():
    got = parse_update(json.dumps(update()).encode())
    assert got == {"id": "tg:1", "user": "tg:777", "text": "Where is order 1042?", "media": 0}
    group = update(); group["message"]["chat"]["type"] = "group"
    bot = update(); bot["message"]["from"]["is_bot"] = True
    mismatch = update(uid=5, uid_chat=6)
    for u in (group, bot, mismatch, {"update_id": 2, "edited_message": {}}, {"update_id": 3}, {"update_id": 4, "message": "x"}):
        assert parse_update(json.dumps(u).encode()) is None
    for bad in (b"nope", b"[]", b'{"x":1}', b'{"update_id":"1"}'):
        with pytest.raises(ValueError):
            parse_update(bad)
    photo = update(); photo["message"].pop("text"); photo["message"]["photo"] = [{}]; photo["message"]["caption"] = "my parcel"
    assert parse_update(json.dumps(photo).encode()) == {"id": "tg:1", "user": "tg:777", "text": "my parcel", "media": 1}


async def test_a_message_is_answered_as_a_telegram_customer_with_no_phone_number():
    ch, rt, cap, repo = build([text("It ships tomorrow.")])
    res = await ch.receive_body(json.dumps(update()).encode())
    assert res[0].status == "replied" and res[0].session_id.startswith("tg-")
    assert cap.sent == [("tg:777", ch.config.from_number, "It ships tomorrow.")]
    sess = await repo.get_session(res[0].session_id)
    assert sess.customer_id == "tg:777" and sess.phone == "tg:777"
    assert (await ch.receive_body(json.dumps(update()).encode()))[0].status == "duplicate" and len(cap.sent) == 1


async def test_slash_commands_work_as_opt_out_words():
    ch, rt, cap, repo = build([text("ok")] * 3)
    assert (await ch.receive_body(json.dumps(update("/stop@my_bot", update_id=1)).encode()))[0].status == "opted_out"
    assert (await ch.receive_body(json.dumps(update("hello", update_id=2)).encode()))[0].status == "ignored"
    assert (await ch.receive_body(json.dumps(update("/start", update_id=3)).encode()))[0].status == "opted_in"
    assert (await ch.receive_body(json.dumps(update("hello", update_id=4)).encode()))[0].status == "replied"


async def test_a_blocked_bot_is_recorded_not_retried_and_other_failures_retry():
    ch, rt, cap, repo = build([text("hi")])
    cap.fail = PermanentSendError("refused (403)")
    assert (await ch.receive_body(json.dumps(update()).encode()))[0].status == "replied"
    assert any(m["outcome"] == "undeliverable" for m in repo.messages.values())


async def test_the_provider_never_leaks_the_token_and_classifies_errors():
    seen = {}

    def handler(req):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        if seen.get("boom"):
            raise httpx.ConnectError("failed for " + str(req.url))
        return httpx.Response(seen.get("status", 200), json={"result": {"message_id": 9}})
    p = TelegramProvider(TOKEN, SECRET, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await p.send("tg:777", p.bot_id, "hello") == "9" and seen["url"].endswith("/sendMessage") and seen["body"]["chat_id"] == 777
    seen["status"] = 403
    with pytest.raises(PermanentSendError):
        await p.send("tg:777", p.bot_id, "x")
    seen["status"] = 429
    with pytest.raises(SmsSendError) as ei:
        await p.send("tg:777", p.bot_id, "x")
    assert not isinstance(ei.value, PermanentSendError)
    seen["boom"] = True
    with pytest.raises(SmsSendError) as ei:
        await p.send("tg:777", p.bot_id, "x")
    assert TOKEN not in str(ei.value) and "123456789" not in str(ei.value)
    with pytest.raises(ValueError):
        await p.send("tg:../x", p.bot_id, "x")


@pytest.mark.parametrize("token,secret", [("", SECRET), ("not-a-token", SECRET), (TOKEN, ""), (TOKEN, "short"), (TOKEN, "has space in it 1234567890")])
def test_configuration_is_checked(token, secret):
    with pytest.raises(ValueError):
        TelegramProvider(token, secret)
    with pytest.raises(ValueError):
        TelegramProvider(TOKEN, SECRET, base_url="http://api.example.com")


def api():
    ch, rt, cap, repo = build([text("hello")] * 4)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key="boot" * 10), telegram=ch)), cap


def post(c, body, secret=SECRET):
    return c.post("/channels/telegram/webhook", content=json.dumps(body).encode(), headers={"content-type": "application/json", **({"x-telegram-bot-api-secret-token": secret} if secret is not None else {})})


def test_the_webhook_needs_the_secret_token_not_an_api_key():
    c, cap = api()
    assert post(c, update()).status_code == 200 and len(cap.sent) == 1
    assert post(c, update(update_id=2), secret="wrong-secret-value-123").status_code == 403 and post(c, update(update_id=3), secret=None).status_code == 403
    assert len(cap.sent) == 1
    assert any(e["action"] == "auth.failed" and e["target"] == "/channels/telegram/webhook" for e in c.get("/v1/audit?limit=10", headers={"authorization": "Bearer " + "boot" * 10}).json()["entries"])
    assert c.post("/channels/telegram/webhook", content=b"nope", headers={"x-telegram-bot-api-secret-token": SECRET}).status_code == 400
    assert post(c, {"update_id": 9, "edited_message": {}}).status_code == 200  # nothing to answer is still a success so Telegram does not retry


def test_it_is_off_unless_configured():
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key="boot" * 10)))
    assert c.post("/channels/telegram/webhook", content=b"{}").status_code == 501
