"""Status events: what is emitted, what is never in them, signed delivery, polling and failure isolation."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.audit import AuditEntry, InMemoryAudit
from northcx.events import EVENTS, FROM_AUDIT, EventFeed, EventingAudit, EventWebhook, scalars
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.notify import verify
from northcx.outbox import InMemoryOutbox, Outbox, OutboxMessage
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}
SECRET = "event-secret-0123456789"


def test_scalars_keep_only_short_plain_values():
    out = scalars({"a": 1, "b": "x", "c": [1], "d": {"x": 1}, "e": "y" * 300, "f": True, "g": None})
    assert out == {"a": 1, "b": "x", "f": True}
    assert len(scalars({str(i): i for i in range(50)})) == 12


async def test_audited_staff_actions_become_events_but_failures_and_unmapped_actions_do_not():
    feed = EventFeed(Outbox(InMemoryOutbox()))
    audit = EventingAudit(InMemoryAudit(), feed)
    await audit.append(AuditEntry(actor="alice", role="admin", action="release.publish", target="support@production", outcome="success", detail={"version": 3, "note": {"deep": 1}}))
    await audit.append(AuditEntry(actor="alice", role="admin", action="release.publish", target="support@production", outcome="denied"))
    await audit.append(AuditEntry(actor="alice", role="admin", action="insights.ask", target="insights", outcome="success"))
    got = await feed.listing()
    assert [e["type"] for e in got] == ["release.published"]
    assert got[0]["data"] == {"action": "release.publish", "target": "support@production", "actor": "alice", "version": 3}
    assert (await audit.verify()).ok  # the wrapper leaves the audit log itself untouched


def test_every_mapped_audit_action_has_a_documented_event_type():
    assert set(FROM_AUDIT.values()) <= set(EVENTS)
    assert {"handoff.created", "approval.requested", "conversation.rated", "alert.fired"} <= set(EVENTS)


async def test_unsubscribed_types_are_dropped_and_a_broken_outbox_never_raises():
    feed = EventFeed(Outbox(InMemoryOutbox()), {"handoff.created"})
    await feed.emit("approval.requested", {"x": 1})
    await feed.emit("nonsense.type", {})
    await feed.emit("handoff.created", {"x": 1}, "s1")
    assert [e["type"] for e in await feed.listing()] == ["handoff.created"]

    class Broken:
        async def add(self, *a, **k):
            raise RuntimeError("db down")
    await EventFeed(Outbox(Broken())).emit("handoff.created", {})  # must not raise


async def test_runtime_moments_are_events_with_ids_and_no_message_text():
    ob = Outbox(InMemoryOutbox())
    feed = EventFeed(ob)
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "1042", "amount": 900}, "t1")]), InMemoryStore(), TraceStore(), outbox=ob)
    rt.events = feed
    await rt.run(support_agent(), "s-1", "please refund order 1042, secret-phrase-xyz", "cust-1")
    types = [e["type"] for e in await feed.listing()]
    assert "approval.requested" in types
    blob = json.dumps(await feed.listing())
    assert "secret-phrase-xyz" not in blob and "1042" not in blob.replace('"sessionId"', "")  # no conversation text or tool inputs
    rt2 = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore(), outbox=Outbox(InMemoryOutbox()))
    rt2.events = EventFeed(rt2.outbox)
    await rt2.run(support_agent(), "s-2", "I want to speak to a person now", "cust-2")
    ev = await rt2.events.listing()
    assert [e["type"] for e in ev] == ["handoff.created"] and ev[0]["sessionId"] == "s-2" and ev[0]["data"]["trigger"] and "person" not in json.dumps(ev[0]["data"]).replace("customer_asked", "")


async def test_simulations_do_not_emit_events():
    ob = Outbox(InMemoryOutbox())
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore(), outbox=ob, dry_run=True)
    rt.events = EventFeed(ob)
    await rt.run(support_agent(), "s-3", "I want a person", "c")
    assert await rt.events.listing() == []


async def test_the_events_webhook_signs_each_call_and_only_sends_events():
    calls = []

    def handler(req):
        calls.append((req.headers["x-northcx-timestamp"], req.content, req.headers["x-northcx-signature"], req.headers["x-northcx-event"]))
        return httpx.Response(200)
    hook = EventWebhook("https://hooks.example.com/e", SECRET, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), types={"handoff.created"}, backoff=0)
    await hook.deliver(OutboxMessage("s1", "approval_result", {"reply": "a customer reply"}, id=1))  # not an event
    await hook.deliver(OutboxMessage("-", "event:key.created", {"type": "key.created", "data": {}}, id=2))  # not subscribed
    await hook.deliver(OutboxMessage("-", "event:handoff.created", {"type": "handoff.created", "sessionId": "s1", "data": {"queue": "billing"}}, id=3))
    assert len(calls) == 1
    ts, body, sig, ev = calls[0]
    assert verify(SECRET, ts, body, sig) and ev == "handoff.created"
    assert json.loads(body)["data"] == {"queue": "billing"} and json.loads(body)["type"] == "handoff.created"


async def test_a_failing_receiver_is_retried_by_the_outbox_and_the_general_webhook_ignores_events():
    state = {"up": False, "got": []}

    def handler(req):
        if not state["up"]:
            return httpx.Response(500)
        state["got"].append(json.loads(req.content)["type"])
        return httpx.Response(200)
    hook = EventWebhook("https://hooks.example.com/e", SECRET, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), attempts=1)
    ob = Outbox(InMemoryOutbox(), hook)
    await EventFeed(ob).emit("alert.fired", {"rule": "errors"})
    assert state["got"] == [] and len(await ob.repo.undelivered()) == 1
    state["up"] = True
    await ob.flush(now=1e12)  # past the back-off
    assert state["got"] == ["alert.fired"] and not await ob.repo.undelivered()
    from northcx.notify import WebhookNotifier
    general = []
    wn = WebhookNotifier("https://hooks.example.com/g", "x" * 20, client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: general.append(1) or httpx.Response(200))))
    await wn.deliver(OutboxMessage("-", "event:alert.fired", {}, id=9))
    assert general == []


def api(events=True):
    ob = Outbox(InMemoryOutbox())
    rt = Runtime(ScriptedLLM([text("hi")]), InMemoryStore(), TraceStore(), outbox=ob)
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), registry(), {}, SimulationService([], lambda a, l: None, InMemorySimRuns(), {}))
    feed = EventFeed(ob) if events else None
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), releases=svc, events=feed)), feed


def test_the_api_lists_types_and_polls_events_including_ratings_and_key_changes():
    c, feed = api()
    t = c.get("/v1/events/types", headers=H).json()
    assert t["enabled"] and {x["type"] for x in t["types"]} == set(EVENTS) and all(x["subscribed"] for x in t["types"])
    kid = c.post("/v1/keys", json={"name": "ci", "role": "viewer"}, headers=H).json()
    assert c.post("/v1/agents/support/chat", json={"sessionId": "s9", "message": "hello"}, headers=H).status_code == 200
    assert c.post("/v1/sessions/s9/feedback", json={"rating": 4, "comment": "private words"}, headers=H).status_code == 201
    got = c.get("/v1/events", headers=H).json()["events"]
    assert [e["type"] for e in got] == ["key.created", "conversation.rated"] and got[1]["data"] == {"rating": 4, "replaced": False} and "private" not in json.dumps(got)
    again = c.get(f"/v1/events?after={got[0]['id']}", headers=H).json()["events"]
    assert [e["type"] for e in again] == ["conversation.rated"]
    assert c.get("/v1/events").status_code == 401 and c.get("/v1/events", headers={"authorization": "Bearer nope"}).status_code in (401, 403)
    assert kid is not None


def test_without_events_configured_the_feed_says_so():
    c, _ = api(events=False)
    assert c.get("/v1/events", headers=H).status_code == 501 and c.get("/v1/events/types", headers=H).json()["enabled"] is False


# ---------- WP0.8: webhook tester ----------
def api_with_webhook(handler, role_key=None):
    c, feed = api()
    feed.webhook = EventWebhook("https://hooks.example.com/e", SECRET, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), backoff=0)
    return c, feed


def test_a_test_event_is_signed_marked_as_a_test_and_audited_but_not_stored():
    seen = []

    def handler(req):
        seen.append((req.headers["x-northcx-timestamp"], req.content, req.headers["x-northcx-signature"], req.headers["x-northcx-event"], req.headers["x-northcx-test"]))
        return httpx.Response(200, text="secret receiver body")
    c, feed = api_with_webhook(handler)
    r = c.post("/v1/events/test", json={"type": "handoff.created"}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["httpStatus"] == 200 and r.json()["type"] == "handoff.created"
    assert "secret receiver body" not in r.text  # the receiver's answer is never echoed back
    ts, body, sig, ev, flag = seen[0]
    assert verify(SECRET, ts, body, sig) and ev == "handoff.created" and flag == "1"
    sent = json.loads(body)
    assert sent["test"] is True and sent["type"] == "handoff.created" and sent["data"]["test"] is True and sent["sessionId"] is None
    assert c.get("/v1/events", headers=H).json()["events"] == []  # not in the feed, so pollers never see a sample
    audit = c.get("/v1/audit", headers=H).json()
    assert any(e["action"] == "events.test" and e["target"] == "handoff.created" for e in audit["entries"])


def test_a_receiver_that_refuses_or_is_unreachable_is_reported_plainly():
    c, _ = api_with_webhook(lambda req: httpx.Response(500))
    r = c.post("/v1/events/test", json={"type": "alert.fired"}, headers=H).json()
    assert r["status"] == "failed" and r["httpStatus"] == 500 and "500" in r["error"]

    def boom(req):
        raise httpx.ConnectError("no route")
    c, _ = api_with_webhook(boom)
    r = c.post("/v1/events/test", json={"type": "alert.fired"}, headers=H).json()
    assert r["status"] == "failed" and r["httpStatus"] is None and "Could not reach" in r["error"]


def test_the_tester_checks_its_input_the_configuration_the_role_and_the_rate():
    c, _ = api_with_webhook(lambda req: httpx.Response(200))
    assert c.post("/v1/events/test", json={"type": "not.an.event"}, headers=H).status_code == 400
    assert c.post("/v1/events/test", json={}, headers=H).status_code == 400
    assert c.post("/v1/events/test", json={"type": "alert.fired"}).status_code == 401
    codes = [c.post("/v1/events/test", json={"type": "alert.fired"}, headers=H).status_code for _ in range(8)]
    assert codes[:6] == [200] * 6 and codes[-1] == 429  # at most six a minute per key
    unconfigured, _ = api()  # events on, but no webhook address
    assert unconfigured.post("/v1/events/test", json={"type": "alert.fired"}, headers=H).status_code == 501
    none, _ = api(events=False)
    assert none.post("/v1/events/test", json={"type": "alert.fired"}, headers=H).status_code == 501


def test_only_a_key_manager_can_send_a_test_event():
    c, _ = api_with_webhook(lambda req: httpx.Response(200))
    viewer = c.post("/v1/keys", json={"name": "v", "role": "viewer"}, headers=H).json()["key"]
    assert c.post("/v1/events/test", json={"type": "alert.fired"}, headers={"authorization": f"Bearer {viewer}"}).status_code == 403
