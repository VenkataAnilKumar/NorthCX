"""The AG-UI endpoint: the same run as the existing stream, a held action as an interrupt, and resume only by staff.

The interrupt and resume field names are directional (docs/01-chat/NorthCX_AG-UI-Check.md); the tests pin what this server sends and accepts."""
import asyncio
import json

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
REFUND = tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1")


def setup(script):
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac)), ac, rt


def H(t=KEY):
    return {"authorization": f"Bearer {t}"}


def parse(r):
    return [json.loads(b.removeprefix("data: ")) for b in r.text.strip().split("\n\n") if b]


def run(c, msg="hi", thread="s1", agent="support", headers=None, **extra):
    body = {"threadId": thread, "runId": "r1", "messages": [{"id": "m1", "role": "user", "content": msg}], **extra}
    return c.post(f"/v1/agents/{agent}/agui", json=body, headers=H() if headers is None else headers)


def resume(c, answers, thread="s1", headers=None):
    return c.post("/v1/agents/support/agui", json={"threadId": thread, "runId": "r2", "messages": [], "resume": answers}, headers=H() if headers is None else headers)


def test_a_run_gives_the_same_text_and_tool_calls_as_the_existing_stream():
    reply = "Order 1042 was delivered on Monday and left at the front door as requested by the customer."
    script = [tool_call("lookup_order", {"order_id": "1042"}, "t1"), text(reply)]
    c, _, _ = setup(script)
    ev = parse(run(c))
    kinds = [e["type"] for e in ev]
    assert kinds[0] == "RUN_STARTED" and ev[0]["threadId"] == "s1" and ev[0]["runId"] == "r1"
    assert kinds[-1] == "RUN_FINISHED" and ev[-1]["outcome"] == "success" and "interrupts" not in ev[-1]
    start = next(e for e in ev if e["type"] == "TOOL_CALL_START")
    assert start["toolCallName"] == "lookup_order" and any(e["type"] == "TOOL_CALL_END" and e["toolCallId"] == start["toolCallId"] for e in ev)
    text_ids = {e["messageId"] for e in ev if e["type"].startswith("TEXT_MESSAGE")}
    assert len(text_ids) == 1 and kinds.index("TOOL_CALL_END") < kinds.index("TEXT_MESSAGE_START") < kinds.index("TEXT_MESSAGE_END") < kinds.index("RUN_FINISHED")
    agui_text = "".join(e["delta"] for e in ev if e["type"] == "TEXT_MESSAGE_CONTENT")
    c2, _, _ = setup(script)
    old = c2.post("/v1/agents/support/chat/stream", json={"sessionId": "s1", "message": "hi"}, headers=H()).text
    old_text = "".join(json.loads(b.split("data: ", 1)[1])["text"] for b in old.strip().split("\n\n") if b.startswith("event: delta"))
    assert agui_text == old_text == reply


def test_a_held_action_ends_the_run_with_an_interrupt_naming_the_approval():
    c, _, rt = setup([REFUND])
    ev = parse(run(c, "refund 240"))
    fin = ev[-1]
    assert fin["type"] == "RUN_FINISHED" and fin["outcome"] == "interrupt" and len(fin["interrupts"]) == 1
    i = fin["interrupts"][0]
    pending = asyncio.new_event_loop().run_until_complete(rt.approvals.list("pending"))
    assert i["id"] == pending[0].id and i["reason"] == "approval_required" and i["toolCallName"] == "issue_refund" and i["input"]["amount"] == 240


def test_resume_approves_through_the_same_decision_code_and_streams_the_follow_up():
    c, _, rt = setup([REFUND, text("Your refund of 240 went through.")])
    aid = parse(run(c, "refund 240"))[-1]["interrupts"][0]["id"]
    ev = parse(resume(c, [{"interruptId": aid, "approved": True, "note": "ok"}]))
    assert [e["type"] for e in ev][0] == "RUN_STARTED" and ev[-1]["outcome"] == "success"
    assert "".join(e["delta"] for e in ev if e["type"] == "TEXT_MESSAGE_CONTENT") == "Your refund of 240 went through."
    a = asyncio.new_event_loop().run_until_complete(rt.approvals.get(aid))
    assert a.state in ("executed", "approved") and a.note == "ok"
    audit = c.get("/v1/audit", headers=H()).json()
    assert any(e["action"] == "approval.decide" and e["target"] == aid for e in audit["entries"])


def test_resume_can_reject_and_a_second_resume_is_refused_without_running_the_tool_again():
    c, _, rt = setup([REFUND, text("I could not refund that.")])
    aid = parse(run(c, "refund 240"))[-1]["interrupts"][0]["id"]
    assert parse(resume(c, [{"interruptId": aid, "approved": False}]))[-1]["outcome"] == "success"
    assert asyncio.new_event_loop().run_until_complete(rt.approvals.get(aid)).state == "rejected"
    again = resume(c, [{"interruptId": aid, "approved": True}])
    assert again.status_code == 409 and "nothing is waiting" in again.json()["error"]["message"].lower()


def test_resume_must_answer_every_open_interrupt_once_and_only_known_ones():
    c, _, _ = setup([REFUND, text("done")])
    aid = parse(run(c, "refund 240"))[-1]["interrupts"][0]["id"]
    assert resume(c, [{"interruptId": "nope", "approved": True}]).status_code == 400
    assert resume(c, [{"interruptId": aid, "approved": True}, {"interruptId": aid, "approved": True}]).status_code == 400
    assert resume(c, []).status_code == 400                                         # an empty answer is not an answer
    assert resume(c, [{"interruptId": aid, "approved": True}]).status_code == 200


def test_two_held_actions_in_one_conversation_are_two_interrupts_and_one_answer_must_cover_both():
    c, _, _ = setup([REFUND, tool_call("issue_refund", {"order_id": "2078", "amount": 300}, "t2"), text("both handled"), text("both handled")])
    ids = [parse(run(c, "refund one"))[-1]["interrupts"][0]["id"], parse(run(c, "refund two"))[-1]["interrupts"][0]["id"]]
    r = resume(c, [{"interruptId": ids[0], "approved": True}])
    assert r.status_code == 400 and ids[1] in r.json()["error"]["message"]          # names what still needs an answer
    assert parse(resume(c, [{"interruptId": i, "approved": True} for i in ids]))[-1]["type"] == "RUN_FINISHED"


def test_only_staff_who_may_decide_can_resume_and_a_customer_token_cannot():
    c, ac, _ = setup([REFUND, text("done")])
    loop = asyncio.new_event_loop()
    chan = loop.run_until_complete(ac.issue("c", "channel", "root"))[1]
    viewer = loop.run_until_complete(ac.issue("v", "viewer", "root"))[1]
    token = c.post("/v1/chat-tokens", json={"sessionId": "mine", "customerId": "c1"}, headers=H(chan)).json()["token"]
    aid = parse(run(c, "refund 240", thread="mine", headers=H(token)))[-1]["interrupts"][0]["id"]
    assert resume(c, [{"interruptId": aid, "approved": True}], thread="mine", headers=H(token)).status_code == 403
    assert resume(c, [{"interruptId": aid, "approved": True}], thread="mine", headers=H(viewer)).status_code == 403
    assert resume(c, [{"interruptId": aid, "approved": True}], thread="mine").status_code == 200


def test_the_endpoint_follows_the_chat_access_rules_and_refuses_a_run_with_no_user_message():
    c, ac, _ = setup([text("ok")] * 3)
    loop = asyncio.new_event_loop()
    viewer = loop.run_until_complete(ac.issue("v", "viewer", "root"))[1]
    chan = loop.run_until_complete(ac.issue("c", "channel", "root"))[1]
    token = c.post("/v1/chat-tokens", json={"sessionId": "mine", "customerId": "c1"}, headers=H(chan)).json()["token"]
    assert run(c, headers={}).status_code == 401 and run(c, headers=H(viewer)).status_code == 403
    assert run(c, thread="mine", headers=H(token)).status_code == 200 and run(c, thread="theirs", headers=H(token)).status_code == 403
    assert run(c, agent="nope").status_code == 404
    none = c.post("/v1/agents/support/agui", json={"threadId": "s", "runId": "r", "messages": [{"id": "a", "role": "assistant", "content": "hi"}]}, headers=H())
    assert none.status_code == 400 and "user message" in none.json()["error"]["message"]
    assert c.post("/v1/agents/support/agui", json={"threadId": "s", "runId": "r", "messages": [{"id": "a", "role": "user", "content": "x"}], "resume": [{"interruptId": "i", "approved": True}]},
                  headers=H()).status_code == 400                                  # a run is a message or an answer, not both


def test_a_failed_model_ends_with_a_handoff_outcome_not_a_broken_stream():
    c, _, _ = setup([])
    ev = parse(run(c))
    assert ev[-1]["type"] == "RUN_FINISHED" and ev[-1]["outcome"] == "success" and ev[-1]["result"]["status"] == "escalated" and ev[-1]["result"]["traceId"]
