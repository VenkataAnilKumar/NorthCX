"""Choices: options the agent offers, shown as buttons or a numbered list, checked with the reply, remembered in the conversation."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.agent import Agent
from northcx.channels.email import EmailConfig, EmailNotifier, InMemoryEmailRepo
from northcx.channels.sms import InMemorySmsRepo, SmsConfig, SmsNotifier, SmsSession
from northcx.channels.telegram import TelegramNotifier, TelegramProvider, parse_update
from northcx.channels.whatsapp import WhatsAppProvider
from northcx.choices import OfferChoices, history_note, numbered, offer_choices_tool, telegram_callback, telegram_keyboard, whatsapp_payload
from northcx.guardrails import Guardrail, Verdict
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.outbox import OutboxMessage
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- the tool and the plain functions ----
def test_the_tool_takes_two_to_ten_different_short_options_and_is_read_only():
    assert OfferChoices(options=[" Yes ", "No"]).options == ["Yes", "No"]
    assert offer_choices_tool().effect == "read" and offer_choices_tool().name == "offer_choices"
    for bad in (["only one"], [f"o{i}" for i in range(11)], ["a", "A"], ["ok", ""], ["ok", "x" * 21], ["ok", "   "]):
        with pytest.raises(ValidationError):
            OfferChoices(options=bad)


def test_the_text_forms():
    assert history_note(["Yes", "No"]) == "[Options offered: 1. Yes, 2. No]"
    assert numbered("Which order?", ["1042", "1043"]) == "Which order?\n\n1. 1042\n2. 1043\nReply with a number or write your own answer."
    assert numbered("Hello.", []) == "Hello."


def test_whatsapp_uses_reply_buttons_up_to_three_and_a_list_beyond():
    b = whatsapp_payload("+14155550123", "Which order?", ["1042", "1043", "1044"])
    assert b["to"] == "14155550123" and b["type"] == "interactive" and b["interactive"]["type"] == "button"
    assert b["interactive"]["action"]["buttons"][1] == {"type": "reply", "reply": {"id": "c2", "title": "1043"}}
    l = whatsapp_payload("+14155550123", "x" * 2000, [f"opt {i}" for i in range(5)])
    assert l["interactive"]["type"] == "list" and len(l["interactive"]["body"]["text"]) == 1024
    assert [r["title"] for r in l["interactive"]["action"]["sections"][0]["rows"]] == [f"opt {i}" for i in range(5)] and l["interactive"]["action"]["button"] == "Choose"


def test_telegram_callback_data_is_cut_at_a_character_boundary_within_64_bytes():
    assert telegram_callback("Yes") == "Yes"
    cut = telegram_callback("😀" * 20)                                        # 80 bytes of four-byte characters
    assert len(cut.encode()) <= 64 and cut == "😀" * 16
    assert telegram_keyboard(["Yes", "No"]) == {"inline_keyboard": [[{"text": "Yes", "callback_data": "Yes"}], [{"text": "No", "callback_data": "No"}]]}


# ---- the runtime and the API ----
def choosing_agent(**kw):
    a = support_agent()
    return Agent(**{**a.__dict__, "tools": [*a.tools, offer_choices_tool()], **kw})


def setup(script, agent=None):
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    return TestClient(create_app(rt, rt.traces, {"support": agent or choosing_agent()}, access=AccessControl(bootstrap_key=KEY))), rt


def H():
    return {"authorization": f"Bearer {KEY}"}


OFFER = tool_call("offer_choices", {"options": ["1042", "1043"]}, "t1")


def test_the_options_come_back_with_the_reply_in_every_api_and_the_conversation_remembers_them():
    c, rt = setup([OFFER, text("Which order do you mean?")] * 3)
    r = c.post("/v1/agents/support/chat", json={"sessionId": "a", "message": "where is my order?"}, headers=H()).json()
    assert r["reply"] == "Which order do you mean?" and r["choices"] == ["1042", "1043"] and r["status"] == "completed"
    stream = c.post("/v1/agents/support/chat/stream", json={"sessionId": "b", "message": "where is my order?"}, headers=H()).text
    done = json.loads(stream.split("event: done\ndata: ")[1].split("\n")[0])
    assert done["choices"] == ["1042", "1043"]
    agui = c.post("/v1/agents/support/agui", json={"threadId": "c", "runId": "r", "messages": [{"role": "user", "content": "where?"}]}, headers=H()).text
    assert '"choices": ["1042", "1043"]' in agui
    assert "[Options offered: 1. 1042, 2. 1043]" in json.dumps(run(rt.store.load_messages("a")))


def test_a_reply_without_the_tool_has_no_options():
    c, _ = setup([text("Hello!")])
    assert c.post("/v1/agents/support/chat", json={"sessionId": "a", "message": "hi"}, headers=H()).json()["choices"] == []


def test_the_options_meet_the_reply_checks_and_a_check_that_stops_them_stops_the_reply():
    class NoSecretWord(Guardrail):
        name = "no-secret-word"

        async def check_reply(self, reply, ctx):
            return Verdict(False, "that word is not allowed") if "BLOCKME" in reply else Verdict.ok()

    agent = choosing_agent()
    agent.guardrails = [NoSecretWord()]
    bad = tool_call("offer_choices", {"options": ["BLOCKME", "fine"]}, "t1")
    c, _ = setup([bad, text("Which one?")] + [text("Which one?")] * 6, agent)
    r = c.post("/v1/agents/support/chat", json={"sessionId": "a", "message": "hi"}, headers=H()).json()
    assert r["choices"] == [] and r["status"] != "completed"


def test_no_options_go_out_with_a_hand_off_a_held_action_or_a_draft():
    c, _ = setup([OFFER, tool_call("handoff_to_human", {"reason": "wants a person"}, "t2"), text("unused")])
    assert c.post("/v1/agents/support/chat", json={"sessionId": "a", "message": "a person please"}, headers=H()).json()["choices"] == []
    c2, _ = setup([OFFER, tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t2")])
    r2 = c2.post("/v1/agents/support/chat", json={"sessionId": "b", "message": "refund 240"}, headers=H()).json()
    assert r2["status"] == "needs_approval" and r2["choices"] == []
    shadow = choosing_agent(shadow=True)
    c3, _ = setup([OFFER, text("Which order?")], shadow)
    r3 = c3.post("/v1/agents/support/chat", json={"sessionId": "c", "message": "hi"}, headers=H()).json()
    assert r3["status"] == "in_review" and r3["choices"] == [] and r3["reply"] == ""


# ---- the channels ----
class Fake:
    def __init__(self, buttons=True):
        self.sent, self.interactive = [], []
        if buttons:
            self.send_choices = self._send_choices

    async def send(self, to, from_, body):
        self.sent.append((to, from_, body))
        return "1"

    async def _send_choices(self, to, from_, body, choices):
        self.interactive.append((to, from_, body, choices))
        return "2"


def sms_world(prov, notifier_cls=SmsNotifier):
    repo = InMemorySmsRepo()
    run(repo.save_session(SmsSession("sms-1", "+14155550123", "+14155550100")))
    return repo, notifier_cls(repo, prov, SmsConfig("+14155550100"))


def msg(payload, kind="sms_reply"):
    return OutboxMessage("sms-1", kind, payload, id=1)


def test_sms_gets_the_options_as_a_numbered_list_and_a_reply_without_options_is_unchanged():
    prov = Fake(buttons=False)
    _, n = sms_world(prov)
    run(n.deliver(msg({"reply": "Which order?", "choices": ["1042", "1043"]})))
    assert prov.sent == [("+14155550123", "+14155550100", "Which order?\n\n1. 1042\n2. 1043\nReply with a number or write your own answer.")]
    prov2 = Fake(buttons=False)
    _, n2 = sms_world(prov2)
    run(n2.deliver(msg({"reply": "Plain.", "choices": []})))
    assert prov2.sent == [("+14155550123", "+14155550100", "Plain.")]


def test_a_channel_with_buttons_sends_them_and_a_long_reply_goes_first_as_text():
    prov = Fake()
    _, n = sms_world(prov)
    run(n.deliver(msg({"reply": "Which order?", "choices": ["1042", "1043"]})))
    assert prov.interactive == [("+14155550123", "+14155550100", "Which order?", ["1042", "1043"])] and prov.sent == []
    prov2 = Fake()
    _, n2 = sms_world(prov2)
    long = "Words. " * 300                                                              # longer than a button's body can hold
    run(n2.deliver(msg({"reply": long, "choices": ["Yes", "No"]})))
    assert "".join(b for _, _, b in prov2.sent).strip().startswith("Words.") and prov2.interactive[-1][2] == "Choose one:"


def test_whatsapp_posts_the_interactive_message_the_api_describes():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((str(req.url), json.loads(req.content)))
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    p = WhatsAppProvider("tok", "secret", "verify", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert run(p.send_choices("+14155550123", "109876543210", "Which order?", ["1042", "1043"])) == "wamid.1"
    url, body = seen[0]
    assert url.endswith("/109876543210/messages") and body["interactive"]["type"] == "button" and body["interactive"]["body"]["text"] == "Which order?"
    refused = WhatsAppProvider("tok", "secret", "verify", client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400))))
    from northcx.channels.sms import PermanentSendError
    with pytest.raises(PermanentSendError):
        run(refused.send_choices("+14155550123", "109876543210", "x", ["a", "b"]))


TOKEN, SECRET = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345", "s3cret-token-value-1234"


def test_telegram_sends_an_inline_keyboard_and_reads_a_tap_as_the_customers_message():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.path.rsplit("/", 1)[-1], json.loads(req.content)))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    p = TelegramProvider(TOKEN, SECRET, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert run(p.send_choices("tg:777", "123456789", "Which order?", ["1042", "1043"])) == "9"
    method, body = seen[0]
    assert method == "sendMessage" and body["chat_id"] == 777 and body["reply_markup"]["inline_keyboard"][0][0] == {"text": "1042", "callback_data": "1042"}
    tap = {"update_id": 5, "callback_query": {"id": "cb1", "from": {"id": 777, "is_bot": False}, "data": "1043", "message": {"message_id": 9, "chat": {"id": 777, "type": "private"}}}}
    got = parse_update(json.dumps(tap).encode())
    assert got == {"id": "tg:5", "user": "tg:777", "text": "1043", "media": 0, "callback": "cb1"}
    run(p.answer_callback("cb1"))
    assert seen[-1] == ("answerCallbackQuery", {"callback_query_id": "cb1"})
    assert parse_update(json.dumps({"update_id": 6, "callback_query": {"id": "x", "from": {"id": 5, "is_bot": True}, "data": "a", "message": {"chat": {"id": 5, "type": "private"}}}}).encode()) is None


def test_email_gets_the_numbered_list_in_the_text():
    class Sender:
        sent = []

        async def send(self, message):
            self.sent.append(message)

    repo, sender = InMemoryEmailRepo(), Sender()
    cfg = EmailConfig("support@shop.test")
    from northcx.channels.email import EmailSession
    run(repo.save_session(EmailSession("email-1", "jane@example.com", "Order", "<m1@x>")))
    run(EmailNotifier(repo, sender, cfg).deliver(OutboxMessage("email-1", "email_reply", {"reply": "Which order?", "choices": ["1042", "1043"]}, id=1)))
    assert "1. 1042\n2. 1043" in sender.sent[0].get_content()


async def test_a_telegram_tap_is_acknowledged_and_answered_like_a_typed_message_once():
    from tests.test_telegram import build as tg_build
    ch, rt, cap, repo = tg_build([text("Order 1043 is on its way.")])
    answered = []

    async def answer(callback_id):
        answered.append(callback_id)

    ch.provider.answer_callback = answer
    tap = {"update_id": 40, "callback_query": {"id": "cb9", "from": {"id": 777, "is_bot": False}, "data": "1043", "message": {"message_id": 3, "chat": {"id": 777, "type": "private"}}}}
    res = await ch.receive_body(json.dumps(tap).encode())
    assert res[0].status == "replied" and answered == ["cb9"]
    assert cap.sent == [("tg:777", ch.config.from_number, "Order 1043 is on its way.")]
    assert "1043" in json.dumps(await rt.store.load_messages(res[0].session_id))              # the agent was told the customer chose 1043
    assert (await ch.receive_body(json.dumps(tap).encode()))[0].status == "duplicate"           # a repeated delivery of the same tap does nothing
