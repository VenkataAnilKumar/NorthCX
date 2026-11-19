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
    """(method, path) -> response model for every route that declares one (under its first 2xx code)."""
    out = {}
    for r in app.routes:
        for code, spec in sorted((getattr(r, "responses", None) or {}).items()):
            if isinstance(code, int) and 200 <= code < 300 and "model" in spec:
                for m in r.methods:
                    out[(m, r.path)] = (code, spec["model"])
                break
    return out


def make_caller(client, models, seen):
    def call(method, path, template=None, **kw):
        r = client.request(method, path, **kw)
        code, model = models[(method, template or path)]
        assert r.status_code == code, (method, path, r.status_code, r.text)
        model.model_validate(r.json())  # raises if a field the model promises is missing or has another type
        seen.add((method, template or path))
        return r.json()
    return call


def conversation_flow(call):
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
    for leaf in ("outbox", "attachments", "tags", "transcript", "scenario-draft"):
        call("GET", f"/v1/sessions/s1/{leaf}", f"/v1/sessions/{{session_id}}/{leaf}")
    call("PUT", "/v1/sessions/s1/tags/vip", "/v1/sessions/{session_id}/tags/{tag}")
    call("DELETE", "/v1/sessions/s1/tags/vip", "/v1/sessions/{session_id}/tags/{tag}")


def release_flow(call):
    A = "/v1/agents/support"
    call("GET", "/v1/agents")
    call("POST", f"{A}/versions", "/v1/agents/{agent_id}/versions", json={"fromBaseline": True, "by": "dev"})
    call("POST", f"{A}/versions", "/v1/agents/{agent_id}/versions", json={"spec": {"id": "support", "instructions": "Be brief.", "tools": ["lookup_order"]}, "by": "dev"})
    call("GET", f"{A}/versions", "/v1/agents/{agent_id}/versions")
    call("GET", f"{A}/versions/1", "/v1/agents/{agent_id}/versions/{number}")
    call("POST", f"{A}/versions/preview", "/v1/agents/{agent_id}/versions/preview", json={"spec": {"id": "support", "instructions": "hi"}})
    call("GET", f"{A}/versions/1/diff/2", "/v1/agents/{agent_id}/versions/{a}/diff/{b}")
    call("GET", f"{A}/versions/1/checklist", "/v1/agents/{agent_id}/versions/{number}/checklist")
    call("GET", "/v1/simulations/gate")
    scenarios = call("GET", "/v1/simulations/scenarios")["scenarios"]
    call("GET", f"/v1/simulations/scenarios/{scenarios[0]['name']}", "/v1/simulations/scenarios/{name}")
    call("POST", "/v1/simulations/scenarios/validate", json={"yaml": "name: tmp-one\ndescription: x\nagent: support\nrequired: false\nmodel:\n- text: hi\nturns:\n- say: hello\n  expect:\n    status: completed\n"})
    run = call("POST", "/v1/simulations/runs", json={"agent": "support", "version": 1, "skipJudge": True})
    call("GET", "/v1/simulations/runs")
    call("GET", f"/v1/simulations/runs/{run['id']}", "/v1/simulations/runs/{run_id}")
    call("GET", f"{A}/environments", "/v1/agents/{agent_id}/environments")
    call("GET", f"{A}/live", "/v1/agents/{agent_id}/live")
    rollout = call("POST", f"{A}/rollouts", "/v1/agents/{agent_id}/rollouts", json={"version": 1, "percent": 50})
    rid = rollout["id"]
    call("GET", f"{A}/rollouts", "/v1/agents/{agent_id}/rollouts")
    call("GET", f"{A}/rollouts/{rid}/comparison", "/v1/agents/{agent_id}/rollouts/{rollout_id}/comparison")
    call("PUT", f"{A}/rollouts/{rid}/percent", "/v1/agents/{agent_id}/rollouts/{rollout_id}/percent", json={"percent": 20})
    call("POST", f"{A}/rollouts/{rid}/abort", "/v1/agents/{agent_id}/rollouts/{rollout_id}/abort")
    call("POST", f"{A}/releases", "/v1/agents/{agent_id}/releases", json={"version": 1, "environment": "dev"})
    call("GET", f"{A}/releases", "/v1/agents/{agent_id}/releases")
    call("POST", f"{A}/promote", "/v1/agents/{agent_id}/promote", json={"version": 1, "from": "dev", "to": "staging"})
    call("POST", f"{A}/rollback", "/v1/agents/{agent_id}/rollback", json={"environment": "dev"})
    rollout = call("POST", f"{A}/rollouts", "/v1/agents/{agent_id}/rollouts", json={"version": 1, "percent": 30})
    call("POST", f"{A}/rollouts/{rollout['id']}/promote", "/v1/agents/{agent_id}/rollouts/{rollout_id}/promote")
    call("POST", "/v1/sessions/s1/feedback", "/v1/sessions/{session_id}/feedback", json={"rating": 5})
    call("PUT", "/v1/sessions/s1/review", "/v1/sessions/{session_id}/review", json={"verdict": "correct"})


def test_every_typed_route_answers_with_its_declared_shape():
    from tests.test_rollout import H, api
    script = [tool_call("issue_refund", {"order_id": "A-1042", "amount": 500, "reason": "late"}, "t1"),
              tool_call("handoff_to_human", {"reason": "asked"}, "t2"), text("passed")]
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    app = create_app(rt, rt.traces, {"support": support_agent()})
    models, seen = declared(app), set()
    conversation_flow(make_caller(TestClient(app), models, seen))
    client, _, _ = api()
    client.headers.update(H)
    client.post("/v1/agents/support/chat", json={"sessionId": "s1", "message": "hi"})  # a conversation for the review and draft routes
    release_flow(make_caller(client, models, seen))
    assert seen == set(models), f"routes with a response model that this test did not call: {sorted(set(models) - seen)}"


def test_a_model_does_not_drop_fields_a_route_adds():
    from northcx.api.responses import Handoff
    assert json.loads(Handoff.model_validate({**HANDOFF, "newField": 1}).model_dump_json())["newField"] == 1


HANDOFF = {"id": "h", "sessionId": "s", "traceId": "t", "agentId": "a", "customerId": None, "trigger": "x", "reason": None, "topics": [], "state": "open", "createdAt": 1.0,
           "resolvedBy": None, "resolvedAt": None, "note": None, "summary": None, "queue": "general", "afterHours": False}
