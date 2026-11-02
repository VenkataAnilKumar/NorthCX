from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.demo import DemoLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


def client():
    traces = TraceStore()
    rt = Runtime(DemoLLM(), InMemoryStore(), traces)
    return TestClient(create_app(rt, traces, {"support": support_agent()}))


def say(c, msg, sid="s"):
    return c.post("/v1/agents/support/chat", json={"sessionId": sid, "message": msg}).json()


def test_lookup_refund_approval_and_handoff():
    c = client()
    assert "delivered" in say(c, "where is order 1042?")["reply"]
    assert "refunded 60" in say(c, "refund 60 for order 1042", "b")["reply"].lower().replace("refunded 60.0", "refunded 60")
    assert say(c, "refund 240 for order 2077", "c")["status"] == "needs_approval"
    assert say(c, "I want a human", "d")["status"] == "escalated"


def test_demo_model_reports_approval_outcomes():
    c = client()
    assert say(c, "refund 240 for order 2077", "d1")["status"] == "needs_approval"
    aid = c.get("/v1/approvals?state=pending").json()["approvals"][0]["id"]
    out = c.post(f"/v1/approvals/{aid}/decision", json={"approved": True, "by": "rae"}).json()
    assert out["resume"]["status"] == "completed" and "refund of 240" in out["resume"]["reply"]
    assert say(c, "refund 300 for order 2077", "d2")["status"] == "needs_approval"
    aid = c.get("/v1/approvals?state=pending").json()["approvals"][0]["id"]
    rej = c.post(f"/v1/approvals/{aid}/decision", json={"approved": False, "by": "rae"}).json()
    assert "couldn't approve" in rej["resume"]["reply"]
