"""Human inbox integration: signed webhook, Chatwoot adapter, queued delivery with retries, and visibility."""
import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.handoffs import Handoff
from northcx.inbox import ChatwootInbox, InboxDispatcher, InboxError, InMemoryInbox, WebhookInbox, event_payload
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.notify import verify
from northcx.routing import load_router
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


def handoff(**kw):
    pkg = {"summary": "Agent handed off. Reason: wants a person.", "transcript": [{"from": "customer", "text": "refund please"}, {"from": "agent", "text": "Let me check"}],
           "actions": [{"tool": "lookup_order", "outcome": "ok"}], "customerFacts": {"plan": "pro"}}
    return Handoff(session_id="s1", trace_id="t1", agent_id="support", trigger="agent_handoff", reason="wants a person", package=pkg,
                   customer_id=kw.pop("customer_id", "jane@example.com"), queue="general", **kw)


def transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_example_routing_file_is_valid():
    r = load_router(Path(__file__).parent.parent / "examples" / "config" / "routing.example.yaml")
    assert {q["name"] for q in r.describe()["queues"]} == {"billing", "urgent", "general"}


# ---- webhook connector ----
async def test_webhook_delivery_is_signed_and_carries_the_package():
    seen = []

    def handler(req):
        seen.append((req.content, dict(req.headers)))
        return httpx.Response(200, json={"ref": "TICKET-77"})

    wh = WebhookInbox("https://helpdesk.example.com/hook", "s3cret", "https://console.example.com", client=transport(handler))
    h = handoff()
    assert await wh.created(h) == "TICKET-77"
    body, headers = seen[0]
    assert verify("s3cret", headers["x-northcx-timestamp"], body, headers["x-northcx-signature"])
    sent = json.loads(body)
    assert sent["event"] == "handoff.created" and sent["handoff"]["package"]["transcript"][0]["text"] == "refund please" and sent["handoff"]["queue"] == "general"
    assert sent["consoleUrl"] == f"https://console.example.com/handoffs?open={h.id}" and headers["x-northcx-delivery"] == f"{h.id}:handoff.created"
    await wh.resolved(h, "TICKET-77")
    assert json.loads(seen[1][0])["event"] == "handoff.resolved"


async def test_webhook_without_a_reference_falls_back_to_the_handoff_id_and_failures_are_clean():
    h = handoff()
    ok = WebhookInbox("https://x.example.com/h", "s", client=transport(lambda r: httpx.Response(204)))
    assert await ok.created(h) == h.id
    for resp in [httpx.Response(500), httpx.Response(302, headers={"location": "https://evil.test"}), httpx.Response(401, text="secret body")]:
        bad = WebhookInbox("https://x.example.com/h?token=abc", "s", client=transport(lambda r, resp=resp: resp))
        with pytest.raises(InboxError) as e:
            await bad.created(h)
        assert "abc" not in str(e.value) and "secret body" not in str(e.value) and "x.example.com" not in str(e.value)

    def boom(req):
        raise httpx.ConnectError("refused to https://x.example.com/h?token=abc")

    with pytest.raises(InboxError, match="ConnectError") as e:
        await WebhookInbox("https://x.example.com/h?token=abc", "s", client=transport(boom)).created(h)
    assert "abc" not in str(e.value)
    for url, secret in [("ftp://x", "s"), ("x.example.com", "s"), ("https://x", "")]:
        with pytest.raises(ValueError):
            WebhookInbox(url, secret)
    assert event_payload("x", h, None)["consoleUrl"] is None


# ---- Chatwoot connector ----
def chatwoot_handler(log, contact_status=200, existing=None):
    def handler(req):
        path, body = req.url.path, (json.loads(req.content) if req.content else {})
        log.append((req.method, path, body, req.headers.get("api_access_token")))
        if path.endswith("/contacts") and req.method == "POST":
            if contact_status == 422:
                return httpx.Response(422, json={"message": "Identifier has already been taken"})
            return httpx.Response(200, json={"payload": {"contact": {"id": 41, "contact_inboxes": []}, "contact_inbox": {"source_id": "src-1", "inbox": {"id": 9}}}})
        if path.endswith("/contacts/search"):
            return httpx.Response(200, json={"payload": existing if existing is not None else []})
        if path.endswith("/conversations"):
            return httpx.Response(200, json={"id": 123})
        return httpx.Response(200, json={})
    return handler


async def test_chatwoot_creates_a_conversation_with_a_private_note():
    log = []
    cw = ChatwootInbox("https://chat.example.com/", "1", "9", "tok", client=transport(chatwoot_handler(log)))
    ref = await cw.created(handoff())
    assert ref == "123"
    assert [(m, p) for m, p, *_ in log] == [("POST", "/api/v1/accounts/1/contacts"), ("POST", "/api/v1/accounts/1/conversations"), ("POST", "/api/v1/accounts/1/conversations/123/messages")]
    assert all(t == "tok" for *_, t in log)
    assert log[0][2] == {"inbox_id": 9, "name": "jane@example.com", "identifier": "jane@example.com"}
    assert log[1][2]["contact_id"] == 41 and log[1][2]["source_id"] == "src-1" and log[1][2]["additional_attributes"]["northcx_queue"] == "general"
    note = log[2][2]
    assert note["private"] is True and "refund please" in note["content"] and "lookup_order: ok" in note["content"] and "plan: pro" in note["content"]
    await cw.resolved(handoff(), "123")
    assert log[-1][1].endswith("/conversations/123/toggle_status") and log[-1][2] == {"status": "resolved"}
    await cw.resolved(handoff(), None)
    await cw.resolved(handoff(), "not-a-number")
    assert len(log) == 4  # nothing was sent for a missing or malformed reference


async def test_chatwoot_reuses_a_known_contact_and_names_anonymous_visitors():
    log = []
    existing = [{"id": 77, "contact_inboxes": [{"source_id": "old-src", "inbox": {"id": 9}}]}]
    cw = ChatwootInbox("https://chat.example.com", "1", "9", "tok", client=transport(chatwoot_handler(log, 422, existing)))
    await cw.created(handoff())
    assert [p.rsplit("/", 1)[-1] for _, p, *_ in log][:3] == ["contacts", "search", "conversations"]
    assert log[2][2]["contact_id"] == 77 and log[2][2]["source_id"] == "old-src"
    log.clear()
    anon = ChatwootInbox("https://chat.example.com", "1", "9", "tok", client=transport(chatwoot_handler(log)))
    await anon.created(handoff(customer_id=None))
    assert log[0][2] == {"inbox_id": 9, "name": "Website visitor"}


async def test_chatwoot_errors_never_reveal_the_token_and_configuration_is_checked():
    cw = ChatwootInbox("https://chat.example.com", "1", "9", "tok-SECRET", client=transport(lambda r: httpx.Response(401, json={"echo": "tok-SECRET"})))
    with pytest.raises(InboxError, match="401") as e:
        await cw.created(handoff())
    assert "tok-SECRET" not in str(e.value)
    for args in [("ftp://x", "1", "9", "t"), ("https://x", "one", "9", "t"), ("https://x", "1", "", "t"), ("https://x", "1", "9", "")]:
        with pytest.raises(ValueError):
            ChatwootInbox(*args)


# ---- queued delivery ----
class Hands:
    def __init__(self, *hs):
        self.items = {h.id: h for h in hs}

    async def get(self, i):
        return self.items.get(i)


class Fake:
    def __init__(self, name="fake", fail=0):
        self.name, self.fail, self.calls = name, fail, []

    async def created(self, h):
        self.calls.append(("created", h.id))
        if self.fail:
            self.fail -= 1
            raise InboxError("fake: returned 503")
        return f"ref-{h.id[:4]}"

    async def resolved(self, h, ref):
        self.calls.append(("resolved", h.id, ref))


async def test_delivery_retries_with_back_off_and_never_duplicates():
    h = handoff()
    repo, conn = InMemoryInbox(), Fake(fail=2)
    d = InboxDispatcher(repo, [conn])
    await d.enqueue(h, "created")
    t0 = time.time()
    assert await d.flush(Hands(h), t0) == 0 and (await repo.for_handoff(h.id))[0].error == "fake: returned 503"
    assert await d.flush(Hands(h), t0 + 5) == 0 and len(conn.calls) == 1  # still backing off
    assert await d.flush(Hands(h), t0 + 31) == 0 and len(conn.calls) == 2  # second failure, longer wait
    assert await d.flush(Hands(h), t0 + 60) == 0 and len(conn.calls) == 2
    assert await d.flush(Hands(h), t0 + 100) == 1
    e = (await repo.for_handoff(h.id))[0]
    assert e.delivered_at and e.external_ref == f"ref-{h.id[:4]}" and e.error is None and e.attempts == 3
    assert await d.flush(Hands(h), t0 + 10_000) == 0 and len(conn.calls) == 3


async def test_resolution_waits_for_creation_and_carries_the_reference():
    h = handoff()
    repo, conn = InMemoryInbox(), Fake(fail=1)
    d = InboxDispatcher(repo, [conn])
    await d.enqueue(h, "created")
    await d.enqueue(h, "resolved")
    t0 = time.time()
    assert await d.flush(Hands(h), t0) == 0 and conn.calls == [("created", h.id)]  # resolved is not sent before created
    assert await d.flush(Hands(h), t0 + 40) == 2
    assert conn.calls[-1] == ("resolved", h.id, f"ref-{h.id[:4]}")


async def test_each_connector_is_tracked_separately_and_gives_up_eventually():
    h = handoff()
    repo = InMemoryInbox()
    good, bad = Fake("good"), Fake("bad", fail=999)
    d = InboxDispatcher(repo, [good, bad])
    await d.enqueue(h, "created")
    now = time.time()
    for i in range(20):
        await d.flush(Hands(h), now + i * 4000)
    by = {e.connector: e for e in await repo.for_handoff(h.id)}
    assert by["good"].delivered_at and not by["bad"].delivered_at and by["bad"].attempts == 12 and len(bad.calls) == 12
    assert "503" in by["bad"].error


async def test_events_for_erased_hand_offs_are_dropped_not_retried():
    h = handoff()
    repo = InMemoryInbox()
    d = InboxDispatcher(repo, [Fake()])
    await d.enqueue(h, "created")
    assert await d.flush(Hands(), time.time()) == 0
    assert (await repo.pending()) == []


# ---- through the runtime and API ----
def wired(script, connectors):
    repo = InMemoryInbox()
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), inbox=InboxDispatcher(repo, connectors))
    ac = AccessControl(bootstrap_key="boot" * 10)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac)), rt, repo, ac


H = {"authorization": "Bearer " + "boot" * 10}


async def test_a_hand_off_is_queued_for_the_inbox_and_resolution_follows():
    conn = Fake()
    repo = InMemoryInbox()
    rt = Runtime(ScriptedLLM([tool_call("handoff_to_human", {"reason": "wants a person"}, "t1")]), InMemoryStore(), TraceStore(), inbox=InboxDispatcher(repo, [conn]))
    r = await rt.run(support_agent(), "s1", "person please", "jane")
    events = await repo.for_handoff(r.handoff_id)
    assert [e.event for e in events] == ["created"]
    assert await rt.inbox.flush(rt.handoffs) == 1 and conn.calls[0] == ("created", r.handoff_id)


async def test_a_broken_inbox_queue_never_breaks_the_conversation():
    class Broken(InMemoryInbox):
        async def enqueue(self, events):
            raise OSError("db down")

    rt = Runtime(ScriptedLLM([tool_call("handoff_to_human", {"reason": "x"}, "t1")]), InMemoryStore(), TraceStore(), inbox=InboxDispatcher(Broken(), [Fake()]))
    r = await rt.run(support_agent(), "s1", "person please", "jane")
    assert r.status == "escalated" and r.handoff_id and any(e.type == "error" and e.data.get("stage") == "inbox" for e in r.trace.events)


def test_api_shows_deliveries_and_queues_the_resolution():
    c, rt, repo, ac = wired([tool_call("handoff_to_human", {"reason": "x"}, "t1")], [Fake()])
    hid = c.post("/v1/agents/support/chat", json={"sessionId": "s1", "message": "person"}, headers=H).json()["handoffId"]
    d = c.get(f"/v1/handoffs/{hid}/inbox", headers=H).json()
    assert d["configured"] and [x["event"] for x in d["deliveries"]] == ["created"] and d["deliveries"][0]["delivered"] is False
    loop = asyncio.new_event_loop()
    loop.run_until_complete(rt.inbox.flush(rt.handoffs))
    assert c.get(f"/v1/handoffs/{hid}/inbox", headers=H).json()["deliveries"][0]["delivered"] is True
    assert c.post(f"/v1/handoffs/{hid}/resolve", json={"note": "done"}, headers=H).status_code == 200
    assert [x["event"] for x in c.get(f"/v1/handoffs/{hid}/inbox", headers=H).json()["deliveries"]] == ["created", "resolved"]
    assert c.get("/v1/handoffs/nope/inbox", headers=H).status_code == 404
    chan = loop.run_until_complete(ac.issue("c", "channel", "root"))[1]
    assert c.get(f"/v1/handoffs/{hid}/inbox", headers={"authorization": f"Bearer {chan}"}).status_code == 403
    off = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {"support": support_agent()}))
    assert off.get("/v1/handoffs/x/inbox").status_code == 404


async def test_erasing_a_customer_removes_queued_inbox_events():
    from northcx.privacy import PrivacyService
    repo = InMemoryInbox()
    rt = Runtime(ScriptedLLM([tool_call("handoff_to_human", {"reason": "x"}, "t1")]), InMemoryStore(), TraceStore(), inbox=InboxDispatcher(repo, [Fake()]))
    r = await rt.run(support_agent(), "s1", "person", "jane")
    assert (await PrivacyService(rt.privacy).erase_customer("jane"))["removed"]["inbox"] == 1 and await repo.for_handoff(r.handoff_id) == []


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        return InMemoryInbox()
    from northcx.db import PgInbox
    return PgInbox(request.getfixturevalue("engine"))


async def test_inbox_repository_contract(store):
    from northcx.inbox import InboxEvent
    a, b = InboxEvent("h1", "webhook", "created", created_at=1), InboxEvent("h1", "webhook", "resolved", created_at=2)
    other = InboxEvent("h2", "chatwoot", "created", created_at=3)
    await store.enqueue([a, b, other])
    await store.enqueue([])
    assert [e.id for e in await store.pending()] == [a.id, b.id, other.id]
    await store.record(a.id, False, None, "boom", 10.0)
    await store.record(b.id, True, "REF", None, 11.0)
    got = {e.id: e for e in await store.for_handoff("h1")}
    assert got[a.id].attempts == 1 and got[a.id].error == "boom" and got[a.id].delivered_at is None and got[a.id].last_attempt_at == 10.0
    assert got[b.id].delivered_at == 11.0 and got[b.id].external_ref == "REF"
    await store.record(a.id, True, "R2", None, 20.0)
    assert (await store.for_handoff("h1"))[0].error is None and [e.id for e in await store.pending()] == [other.id]
    assert await store.erase_handoffs(["h1"]) == 2 and await store.for_handoff("h1") == [] and len(await store.for_handoff("h2")) == 1
    assert await store.erase_handoffs([]) == 0
    for _ in range(12):
        await store.record(other.id, False, None, "x", 30.0)
    assert await store.pending() == []  # gave up after the attempt limit
