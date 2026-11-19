"""Typed responses of the Agent API (Phase 1, WP 1.6a): every route that declares a response model is called for real and its
answer is checked against the model, so the API reference cannot describe a shape the route does not send."""
import json

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


def declared(app):
    """(method, path) -> response model for every route that declares one."""
    return {(m, r.path): r.responses[200]["model"] for r in app.routes if getattr(r, "responses", None) and 200 in r.responses and "model" in r.responses[200]
            for m in r.methods}


def test_every_typed_route_answers_with_its_declared_shape():
    script = [tool_call("issue_refund", {"order_id": "A-1042", "amount": 500, "reason": "late"}, "t1"),
              tool_call("handoff_to_human", {"reason": "asked"}, "t2"), text("passed")]
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    app = create_app(rt, rt.traces, {"support": support_agent()})
    c = TestClient(app)
    models, seen = declared(app), set()

    def call(method, path, template=None, **kw):
        r = c.request(method, path, **kw)
        assert r.status_code == 200, (method, path, r.text)
        models[(method, template or path)].model_validate(r.json())  # raises if a field the model promises is missing or has another type
        seen.add((method, template or path))
        return r.json()

    chat = call("POST", "/v1/agents/support/chat", "/v1/agents/{agent_id}/chat", json={"sessionId": "s1", "message": "refund A-1042 500", "customerId": "c1"})
    assert chat["status"] == "needs_approval"
    approval_id = call("GET", "/v1/approvals")["approvals"][0]["id"]
    call("POST", "/v1/approvals/expire", json={"olderThanSeconds": 99999})
    decision = call("POST", f"/v1/approvals/{approval_id}/decision", "/v1/approvals/{approval_id}/decision", json={"approved": False, "note": "no"})
    assert decision["resume"]["status"] == "escalated"
    handoff_id = call("GET", "/v1/handoffs")["handoffs"][0]["id"]
    for path, template in ((f"/v1/handoffs/{handoff_id}", "/v1/handoffs/{handoff_id}"), (f"/v1/handoffs/{handoff_id}/inbox", "/v1/handoffs/{handoff_id}/inbox")):
        call("GET", path, template)
    call("POST", f"/v1/handoffs/{handoff_id}/reply", "/v1/handoffs/{handoff_id}/reply", json={"text": "hello"})
    call("POST", f"/v1/handoffs/{handoff_id}/resolve", "/v1/handoffs/{handoff_id}/resolve", json={"note": "done"})
    call("GET", "/v1/traces")
    call("GET", f"/v1/traces/{chat['traceId']}", "/v1/traces/{trace_id}")
    call("GET", f"/v1/traces/{chat['traceId']}/exports", "/v1/traces/{trace_id}/exports")
    call("GET", "/v1/events/types")
    for leaf in ("outbox", "attachments", "tags", "transcript"):
        call("GET", f"/v1/sessions/s1/{leaf}", f"/v1/sessions/{{session_id}}/{leaf}")
    call("PUT", "/v1/sessions/s1/tags/vip", "/v1/sessions/{session_id}/tags/{tag}")
    call("DELETE", "/v1/sessions/s1/tags/vip", "/v1/sessions/{session_id}/tags/{tag}")
    assert seen == set(models), f"routes with a response model that this test did not call: {sorted(set(models) - seen)}"


def test_a_model_does_not_drop_fields_a_route_adds():
    from northcx.api.responses import Handoff
    assert json.loads(Handoff.model_validate({**HANDOFF, "newField": 1}).model_dump_json())["newField"] == 1


HANDOFF = {"id": "h", "sessionId": "s", "traceId": "t", "agentId": "a", "customerId": None, "trigger": "x", "reason": None, "topics": [], "state": "open", "createdAt": 1.0,
           "resolvedBy": None, "resolvedAt": None, "note": None, "summary": None, "queue": "general", "afterHours": False}
