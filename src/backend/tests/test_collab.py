"""Collaboration (H6, H7): the agent stays quiet while a person has the conversation, person replies, hand-back, and agent assist."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.assist import AssistError, AssistService, build_prompt, parse
from northcx.handoffs import HOLD_REPLY, PERSON_PREFIX, return_note, transcript
from northcx.inbox import ChatwootInbox, InboxDispatcher, InMemoryInbox, WebhookInbox
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}
SUGGESTION = {"suggestedReply": "Hi Jane, I've checked order 1042 and can refund it today.", "nextSteps": ["Confirm the delivery date", "Issue the refund"],
              "keyFacts": ["Order 1042 was delivered", "Customer is on the pro plan"], "cautions": ["The agent already promised a callback"]}


def build(script, assist_script=None, auto=False):
    llm = ScriptedLLM(list(script))
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    if assist_script is not None:
        rt.assist = AssistService(ScriptedLLM(list(assist_script)))
        rt.assist_auto = auto
    return llm, rt


async def handed_off(rt, sid="s1", msg="I want my order 1042 refunded, my email is jane@example.com"):
    agent = support_agent()
    r = await rt.run(agent, sid, msg, "c1")
    assert r.status == "escalated"
    return agent, r.handoff_id


async def test_the_agent_stays_quiet_while_a_person_has_the_conversation():
    llm, rt = build([tool_call("handoff_to_human", {"reason": "wants a person"}, "h"), text("Welcome back!")])
    agent, hid = await handed_off(rt)
    calls = len(llm.requests)
    r = await rt.run(agent, "s1", "Hello? my card is 4111 1111 1111 1111")
    assert (r.reply, r.status, r.handoff_id) == (HOLD_REPLY, "with_person", hid) and len(llm.requests) == calls  # no model call
    msgs = await rt.store.load_messages("s1")
    assert "4111" not in json.dumps(msgs) and msgs[-1] == {"role": "assistant", "content": HOLD_REPLY}
    assert [e.type for e in r.trace.events if e.type != "guardrail"] == ["user", "held", "reply"]  # the input checks still ran
    shown = transcript(msgs)
    assert shown[-2]["from"] == "customer" and "4111" not in shown[-2]["text"]


async def test_handing_back_tells_the_agent_what_the_person_did():
    llm, rt = build([tool_call("handoff_to_human", {"reason": "x"}, "h"), text("Anything else?")])
    agent, hid = await handed_off(rt)
    c = TestClient(create_app(rt, rt.traces, {"support": agent}))
    assert c.post(f"/v1/handoffs/{hid}/resolve", json={"by": "Sam", "note": "Refunded order 1042 by hand"}).status_code == 200
    r = await rt.run(agent, "s1", "thanks, one more question")
    assert r.status == "completed"
    seen = json.dumps([m["content"] for m in llm.requests[-1].messages])
    assert "handed this conversation back" in seen and "Refunded order 1042 by hand" in seen and "Sam" in seen and PERSON_PREFIX in seen
    assert "handed this conversation back" in return_note("Sam", None) and "Their note" not in return_note("Sam", "  ")


async def test_a_person_can_keep_the_conversation():
    llm, rt = build([tool_call("handoff_to_human", {"reason": "x"}, "h"), text("unused")])
    agent, hid = await handed_off(rt)
    c = TestClient(create_app(rt, rt.traces, {"support": agent}))
    c.post(f"/v1/handoffs/{hid}/resolve", json={"by": "Sam", "returnToAgent": False})
    assert "handed this conversation back" not in json.dumps(await rt.store.load_messages("s1"))


def api(script=None, assist_script=None, auto=False, **kw):
    llm, rt = build(script or [tool_call("handoff_to_human", {"reason": "x"}, "h")], assist_script, auto)
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, **kw)), ac, rt


def chat(c, sid="w1", msg="refund please"):
    return c.post("/v1/agents/support/chat", headers=H, json={"sessionId": sid, "message": msg, "customerId": "cu"}).json()


def test_person_replies_reach_the_customer_through_the_outbox():
    c, ac, rt = api()
    r = chat(c)
    hid = r["handoffId"]
    held = chat(c, msg="hello?")
    assert held["status"] == "with_person" and held["reply"] == HOLD_REPLY
    sent = c.post(f"/v1/handoffs/{hid}/reply", headers=H, json={"text": "Hi, this is Sam. I'm on it.", "by": "Sam"})
    assert sent.status_code == 200 and sent.json()["sent"] is True
    box = c.get("/v1/sessions/w1/outbox", headers=H).json()["messages"]
    assert [(m["kind"], m["reply"], m["by"]) for m in box] == [("person_reply", "Hi, this is Sam. I'm on it.", "bootstrap")]  # the key's name, never a typed one
    assert c.post(f"/v1/handoffs/{hid}/reply", headers=H, json={"text": ""}).status_code == 400
    assert c.post("/v1/handoffs/nope/reply", headers=H, json={"text": "x"}).status_code == 404
    msgs = asyncio.new_event_loop().run_until_complete(rt.store.load_messages("w1"))
    assert any(m["role"] == "assistant" and str(m["content"]).startswith(PERSON_PREFIX) for m in msgs)
    assert {"from": "person", "text": "Hi, this is Sam. I'm on it."} in transcript(msgs)
    c.post(f"/v1/handoffs/{hid}/resolve", headers=H, json={})
    assert c.post(f"/v1/handoffs/{hid}/reply", headers=H, json={"text": "late"}).status_code == 409
    assert "handoff.reply" in [e["action"] for e in c.get("/v1/audit?limit=30", headers=H).json()["entries"]]


def test_who_may_reply_and_ask_for_help():
    c, ac, rt = api(assist_script=[text(json.dumps(SUGGESTION))] * 5)
    hid = chat(c)["handoffId"]
    loop = asyncio.new_event_loop()
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    for role, code in [("reviewer", 200), ("admin", 200), ("developer", 403), ("viewer", 403), ("auditor", 403), ("channel", 403)]:
        h = {"authorization": f"Bearer {key(role)}"}
        assert c.post(f"/v1/handoffs/{hid}/reply", headers=h, json={"text": "hello"}).status_code == code, role
        assert c.post(f"/v1/handoffs/{hid}/assist", headers=h).status_code == code, role


def test_parsing_suggestions():
    ok = parse("Here you go:\n" + json.dumps({**SUGGESTION, "nextSteps": ["a"] * 9, "cautions": ["c" * 500]}))
    assert len(ok["nextSteps"]) == 5 and len(ok["cautions"][0]) == 220 and ok["suggestedReply"].startswith("Hi Jane")
    assert parse(json.dumps({"suggestedReply": "", "nextSteps": ["call them"]}))["nextSteps"] == ["call them"]
    assert parse(json.dumps({"suggestedReply": "x" * 900, "nextSteps": "not a list"}))["suggestedReply"] == "x" * 700
    for bad in ["no json", "{oops}", json.dumps({"keyFacts": ["only facts"]}), json.dumps([1, 2]), "{}"]:
        with pytest.raises(AssistError):
            parse(bad)


def test_the_prompt_masks_personal_data_and_marks_the_conversation_as_data():
    p = build_prompt({"trigger": "agent_handoff", "triggerDescription": "The agent handed over", "reason": "wants a person", "language": "es",
                      "transcript": [{"from": "customer", "text": "mail jane@example.com card 4111 1111 1111 1111 ssn 123-45-6789"}],
                      "actions": [{"tool": "lookup_order", "outcome": "succeeded"}], "customerFacts": {"phone": "415-555-0199", "plan": "pro"}})
    assert "jane@example.com" not in p and "4111 1111" not in p and "123-45-6789" not in p and "415-555-0199" not in p
    assert "<conversation>" in p and "lookup_order succeeded" in p and "writes in: es" in p and "plan" in p


def test_assist_on_demand_stores_suggestions_with_the_handoff():
    c, ac, rt = api(assist_script=[text(json.dumps(SUGGESTION)), text("I cannot do that")])
    hid = chat(c)["handoffId"]
    out = c.post(f"/v1/handoffs/{hid}/assist", headers=H).json()["assist"]
    assert out["suggestedReply"].startswith("Hi Jane") and out["nextSteps"][0] == "Confirm the delivery date" and "Nothing is sent" in out["note"]
    assert c.get(f"/v1/handoffs/{hid}", headers=H).json()["package"]["assist"]["keyFacts"][0] == "Order 1042 was delivered"
    bad = c.post(f"/v1/handoffs/{hid}/assist", headers=H)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unusable_suggestions"
    assert c.post("/v1/handoffs/nope/assist", headers=H).status_code == 404
    assert "handoff.assist" in [e["action"] for e in c.get("/v1/audit?limit=30", headers=H).json()["entries"]]


def test_assist_can_be_switched_off():
    c, ac, rt = api()
    hid = chat(c)["handoffId"]
    assert c.post(f"/v1/handoffs/{hid}/assist", headers=H).status_code == 501


async def test_auto_assist_drafts_suggestions_and_queues_them_for_the_inbox():
    llm, rt = build([tool_call("handoff_to_human", {"reason": "x"}, "h")], [text(json.dumps(SUGGESTION))], auto=True)
    rt.inbox = InboxDispatcher(InMemoryInbox(), [WebhookInbox("https://crm.example.com/hook", "s3cret")])
    agent, hid = await handed_off(rt)
    await asyncio.gather(*list(rt._background))
    h = await rt.handoffs.get(hid)
    assert h.package["assist"]["suggestedReply"].startswith("Hi Jane")
    assert [e.event for e in rt.inbox.repo.events] == ["created", "assist"]


async def test_a_failing_model_never_breaks_the_handoff():
    llm, rt = build([tool_call("handoff_to_human", {"reason": "x"}, "h")], [text("nonsense")], auto=True)
    agent, hid = await handed_off(rt)
    await asyncio.gather(*list(rt._background))
    assert "assist" not in (await rt.handoffs.get(hid)).package


def transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


async def test_chatwoot_gets_the_suggestions_as_a_private_note_after_the_conversation_exists():
    log = []

    def handler(req):
        body = json.loads(req.content) if req.content else {}
        log.append((req.url.path, body))
        if req.url.path.endswith("/contacts"):
            return httpx.Response(200, json={"payload": {"contact": {"id": 4, "contact_inboxes": []}, "contact_inbox": {"source_id": "s", "inbox": {"id": 9}}}})
        return httpx.Response(200, json={"id": 77})
    llm, rt = build([tool_call("handoff_to_human", {"reason": "x"}, "h")], [text(json.dumps(SUGGESTION))], auto=True)
    cw = ChatwootInbox("https://chat.example.com", "1", "9", "tok", client=transport(handler))
    rt.inbox = InboxDispatcher(InMemoryInbox(), [cw])
    agent, hid = await handed_off(rt)
    await asyncio.gather(*list(rt._background))
    assert await rt.inbox.flush(rt.handoffs) == 2
    note = [b for p, b in log if p.endswith("/conversations/77/messages")][-1]
    assert note["private"] is True and "Suggested reply" in note["content"] and "Issue the refund" in note["content"] and "nothing has been sent" in note["content"]
    # nothing is posted for a hand-off without suggestions
    h = await rt.handoffs.get(hid)
    h.package.pop("assist")
    n = len(log)
    await cw.assist(h, "77")
    assert len(log) == n


@pytest.fixture(params=["memory", "postgres"])
def handoff_repo(request):
    from northcx.handoffs import InMemoryHandoffs
    if request.param == "memory":
        return InMemoryHandoffs()
    from northcx.db import PgHandoffs
    return PgHandoffs(request.getfixturevalue("engine"))


async def test_set_package_field_contract(handoff_repo):
    from northcx.handoffs import Handoff
    h = await handoff_repo.add(Handoff("s", "t", "support", "agent_handoff", "r", {"summary": "x"}))
    assert await handoff_repo.set_package_field(h.id, "assist", {"nextSteps": ["a"]}) is True
    got = await handoff_repo.get(h.id)
    assert got.package["assist"] == {"nextSteps": ["a"]} and got.package["summary"] == "x"
    assert await handoff_repo.set_package_field("nope", "assist", {}) is False
