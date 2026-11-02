"""The streaming chat endpoint: progress, approved reply in pieces, and the same safety as normal chat."""
import asyncio
import json

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import _pieces, create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10


def setup(script):
    llm = ScriptedLLM(script)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac)), ac, llm, rt


def H(t=KEY, **extra):
    return {"authorization": f"Bearer {t}", **extra}


def stream(c, msg="hi", session="s1", agent="support", headers=None):
    r = c.post(f"/v1/agents/{agent}/chat/stream", json={"sessionId": session, "message": msg}, headers=H() if headers is None else headers)
    events = []
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        for block in r.text.strip().split("\n\n"):
            ev, data = block.split("\n", 1)
            events.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return r, events


def test_pieces_rejoin_exactly():
    for s in ["", "short", "word " * 50, "a\n\nb   c\t d", "x" * 200, "  lead and trail  ", "日本語 のテキスト " * 10]:
        p = _pieces(s)
        assert "".join(p) == s and all(p)
        assert all(len(x) <= 40 or " " not in x.strip() for x in p)


def test_a_reply_is_streamed_after_progress_and_ends_with_the_full_result():
    reply = "Order 1042 was delivered on Monday and left at the front door as requested by the customer."
    c, ac, llm, rt = setup([tool_call("lookup_order", {"order_id": "1042"}, "t1"), text(reply)])
    r, ev = stream(c)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    kinds = [e[0] for e in ev]
    assert kinds[0] == "started" and kinds[-1] == "done" and "progress" in kinds
    assert ev[kinds.index("progress")][1] == {"type": "tool", "name": "lookup_order"}
    deltas = [e[1]["text"] for e in ev if e[0] == "delta"]
    assert len(deltas) > 1 and "".join(deltas) == reply
    done = ev[-1][1]
    assert done["reply"] == reply and done["status"] == "completed" and done["traceId"]
    assert kinds.index("progress") < kinds.index("delta")  # pieces come only after the work and the checks
    assert reply in json.dumps(await_history(rt, "s1")[-1]["content"])


def await_history(rt, sid):
    return asyncio.new_event_loop().run_until_complete(rt.store.load_messages(sid))


def test_text_that_fails_a_check_is_never_streamed():
    bad = "Your card 4111 1111 1111 1111 is on file."
    c, ac, llm, rt = setup([text(bad), text("Your card is on file.")])
    r, ev = stream(c)
    assert "4111" not in r.text and "".join(e[1]["text"] for e in ev if e[0] == "delta") == "Your card is on file."


def test_handoffs_and_approvals_arrive_in_done():
    c, ac, llm, rt = setup([tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1")])
    r, ev = stream(c, "refund 240")
    done = ev[-1][1]
    assert done["status"] == "needs_approval" and done["pendingApprovals"]
    c2, *_ = setup([tool_call("handoff_to_human", {"reason": "wants person"}, "t1")])
    done2 = stream(c2)[1][-1][1]
    assert done2["status"] == "escalated" and done2["handoffId"]


def test_failures_become_a_handoff_not_a_broken_stream():
    c, ac, llm, rt = setup([])  # the model fails
    r, ev = stream(c)
    assert ev[-1][0] == "done" and ev[-1][1]["status"] == "escalated"


def test_same_access_rules_as_normal_chat():
    c, ac, llm, rt = setup([text("ok")] * 5)
    loop = asyncio.new_event_loop()
    viewer = loop.run_until_complete(ac.issue("v", "viewer", "root"))[1]
    chan = loop.run_until_complete(ac.issue("c", "channel", "root"))[1]
    assert stream(c, headers={})[0].status_code == 401
    assert stream(c, headers=H(viewer))[0].status_code == 403
    assert stream(c, headers=H(chan))[0].status_code == 200
    token = c.post("/v1/chat-tokens", json={"sessionId": "mine", "customerId": "c1"}, headers=H(chan)).json()["token"]
    assert stream(c, session="mine", headers=H(token))[0].status_code == 200
    assert stream(c, session="theirs", headers=H(token))[0].status_code == 403
    assert stream(c, agent="nope")[0].status_code == 404
    r, _ = stream(c, headers=H(KEY, **{"idempotency-key": "k"}))
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported"
    assert c.post("/v1/agents/support/chat/stream", json={"sessionId": "s"}, headers=H()).status_code == 400


def test_conversations_continue_across_streamed_and_normal_requests():
    c, ac, llm, rt = setup([text("first"), text("second")])
    stream(c, "one", session="mix")
    r = c.post("/v1/agents/support/chat", json={"sessionId": "mix", "message": "two"}, headers=H())
    assert r.json()["reply"] == "second" and len(await_history(rt, "mix")) == 4
