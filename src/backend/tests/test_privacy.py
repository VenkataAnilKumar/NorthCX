"""Customer export, erasure and retention, on memory and Postgres."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl, ROLES
from northcx.approval_flow import ApprovalFlow
from northcx.channels.email import EmailChannel, EmailConfig, EmailNotifier, InMemoryEmailRepo
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.outbox import Outbox
from northcx.privacy import PrivacyService, customer_ref
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from tests.test_email import Sink, mail

KEY = "boot" * 10
DAY = 86400


def build(env, script):
    """A runtime over either the in-memory stores or Postgres, plus the privacy service and idempotency store for it."""
    from northcx.idempotency import InMemoryIdempotency
    if env[0] == "memory":
        rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
        idem = InMemoryIdempotency()
        rt.privacy.idempotency = idem
        return rt, idem
    from northcx import db
    e = env[1]
    from northcx.monitor import Monitor
    rt = Runtime(ScriptedLLM(script), db.PgMemoryStore(e), db.PgTraceStore(e), db.PgApprovalStore(e), Outbox(db.PgOutbox(e)), db.PgHandoffs(e),
                 monitor=Monitor(db.PgMonitor(e)), privacy=db.PgPrivacy(e))
    return rt, db.PgIdempotency(e)


@pytest.fixture(params=["memory", "postgres"])
def kind(request):
    """Resolved before the test's event loop starts (the database fixture cannot be created inside one)."""
    return ("memory", None) if request.param == "memory" else ("postgres", request.getfixturevalue("engine"))


async def talk(rt, session, customer, msg="where is order 1042?", agent=None):
    return await rt.run(agent or support_agent(), session, msg, customer)


async def test_export_collects_everything_held_for_one_customer_and_nothing_else(kind):
    rt, _ = build(kind, [tool_call("lookup_order", {"order_id": "1042"}, "t1"), text("Delivered."), tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t2"),
                         text("Hi!")])
    await talk(rt, "s-alice-1", "alice")
    held = await talk(rt, "s-alice-2", "alice", "refund 240 on 2077")
    await rt.store.set_fact("alice", "tier", "gold")
    await talk(rt, "s-bob", "bob", "hello")
    svc = PrivacyService(rt.privacy)
    out = await svc.export_customer("alice")
    assert out["customerId"] == "alice" and out["facts"] == {"tier": "gold"}
    assert [s["sessionId"] for s in out["sessions"]] == ["s-alice-1", "s-alice-2"]
    first, second = out["sessions"]
    assert "Delivered." in json.dumps(first["messages"]) and first["traces"] and first["traces"][0]["events"]
    assert second["approvals"][0]["tool"] == "issue_refund" and held.status == "needs_approval"
    assert "bob" not in json.dumps(out) and "hello" not in json.dumps(out)
    assert (await svc.export_customer("nobody"))["sessions"] == []


async def test_erasing_a_customer_removes_every_trace_of_their_conversations(kind):
    rt, idem = build(kind, [tool_call("handoff_to_human", {"reason": "wants person"}, "t1"), tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t2"), text("Hi bob")])
    await talk(rt, "s-alice-1", "alice", "I want a person, my email is alice@example.com")
    await talk(rt, "s-alice-2", "alice", "refund 240 on 2077")
    await rt.outbox.publish("s-alice-2", "approval_result", {"reply": "done"})
    await idem.begin("scope-1", "h", session_id="s-alice-1")
    await rt.store.set_fact("alice", "tier", "gold")
    await talk(rt, "s-bob", "bob", "hello")
    await rt.store.set_fact("bob", "tier", "silver")
    svc = PrivacyService(rt.privacy)
    before = await svc.export_customer("alice")
    assert before["sessions"][0]["handoffs"] and before["sessions"][1]["approvals"] and before["sessions"][1]["outbox"]
    r = await svc.erase_customer("alice")
    assert r["sessions"] == 2 and r["removed"]["messages"] >= 4 and r["removed"]["traces"] == 2 and r["removed"]["approvals"] == 1
    assert r["removed"]["handoffs"] == 1 and r["removed"]["outbox"] == 1 and r["removed"]["facts"] == 1 and r["removed"]["replies"] == 1
    again = await svc.export_customer("alice")
    assert again["sessions"] == [] and again["facts"] == {}
    for sid in ("s-alice-1", "s-alice-2"):
        assert await rt.store.load_messages(sid) == [] and await rt.traces.summaries(sid) == [] and await rt.outbox.list(sid) == []
        assert await rt.handoffs.list(session_id=sid) == [] and await rt.monitor.repo.list(session_id=sid) == []
    assert not [a for a in await rt.approvals.list() if a.session_id.startswith("s-alice")]
    assert (await idem.begin("scope-1", "h")).state == "new"  # the stored reply is gone
    bob = await svc.export_customer("bob")  # other customers are untouched
    assert bob["facts"] == {"tier": "silver"} and bob["sessions"][0]["messages"]
    assert (await svc.erase_customer("alice"))["sessions"] == 0


async def test_one_conversation_can_be_erased_on_its_own(kind):
    rt, _ = build(kind, [text("a"), text("b")])
    await talk(rt, "s1", "carol", "one")
    await talk(rt, "s2", "carol", "two")
    r = await PrivacyService(rt.privacy).erase_session("s1")
    assert r["messages"] == 2 and r["traces"] == 1
    assert await rt.store.load_messages("s1") == [] and await rt.store.load_messages("s2")
    assert [s["sessionId"] for s in (await PrivacyService(rt.privacy).export_customer("carol"))["sessions"]] == ["s2"]
    assert (await PrivacyService(rt.privacy).erase_session("never-existed")) == {k: 0 for k in r}


async def test_retention_removes_only_conversations_idle_longer_than_the_limit(kind):
    rt, _ = build(kind, [text("x")] * 4)
    now = time.time()
    await rt.privacy.link("old-1", "dan", now - 40 * DAY)
    await talk(rt, "old-1", "dan")
    await rt.privacy.link("old-1", "dan", now - 40 * DAY)  # pretend it was last active long ago
    await talk(rt, "recent", "dan")
    await rt.privacy.link("anon-old", None, now - 60 * DAY)
    await rt.store.save_messages("anon-old", [{"role": "user", "content": "hi"}])
    svc = PrivacyService(rt.privacy)
    r = await svc.purge_idle(30, now=now)
    assert r["sessions"] == 2 and r["removed"]["messages"] >= 2
    assert await rt.store.load_messages("old-1") == [] and await rt.store.load_messages("anon-old") == [] and await rt.store.load_messages("recent")
    assert (await svc.purge_idle(30, now=now))["sessions"] == 0
    assert (await svc.purge_idle(0.0001, now=now + 10 * DAY))["sessions"] == 1  # now the recent one has aged out too


async def test_a_session_that_changed_customer_is_erased_for_either(kind):
    rt, _ = build(kind, [text("x"), text("y")])
    await talk(rt, "shared", "eve", "first")
    await talk(rt, "shared", "frank", "second")
    svc = PrivacyService(rt.privacy)
    assert [s["sessionId"] for s in (await svc.export_customer("eve"))["sessions"]] == ["shared"]
    assert (await svc.erase_customer("frank"))["sessions"] == 1
    assert (await svc.export_customer("eve"))["sessions"] == [] and await rt.store.load_messages("shared") == []


async def test_email_threads_are_included_for_verified_senders():
    from northcx.channels.email import EmailChannel
    repo, sink = InMemoryEmailRepo(), Sink()
    cfg = EmailConfig("support@shop.test", trust_gateway=True)
    rt = Runtime(ScriptedLLM([text("Hello Jane")]), InMemoryStore(), TraceStore(), outbox=Outbox(notifier=EmailNotifier(repo, sink, cfg)))
    rt.privacy.email = repo
    ch = EmailChannel(rt, {"support": support_agent()}, repo, cfg)
    res = await ch.receive(mail(headers={"Authentication-Results": "mx; dmarc=pass header.from=example.com"}))
    svc = PrivacyService(rt.privacy)
    out = await svc.export_customer("email:jane@example.com")
    assert [s["sessionId"] for s in out["sessions"]] == [res.session_id] and out["sessions"][0]["email"]["messages"]
    r = await svc.erase_customer("email:jane@example.com")
    assert r["removed"]["email"] >= 2 and repo.sessions == {} and repo.messages == {}


def test_customer_references_are_one_way_and_stable():
    assert customer_ref("jane@example.com") == customer_ref("jane@example.com") and "jane" not in customer_ref("jane@example.com")
    assert customer_ref("a") != customer_ref("b") and customer_ref("a").startswith("cust_")


async def test_the_trace_file_mirror_is_scrubbed_too(tmp_path):
    rt = Runtime(ScriptedLLM([text("a"), text("b")]), InMemoryStore(), TraceStore(str(tmp_path)))
    await talk(rt, "s1", "gina", "my secret question")
    await talk(rt, "s2", "hank", "other")
    assert "my secret question" in (tmp_path / "traces.jsonl").read_text()
    await PrivacyService(rt.privacy).erase_customer("gina")
    body = (tmp_path / "traces.jsonl").read_text()
    assert "my secret question" not in body and "other" in body


# ---- API ----
def api(script=None):
    rt = Runtime(ScriptedLLM(script or [text("hi")] * 5), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac)), ac, rt


def H(k=KEY):
    return {"authorization": f"Bearer {k}"}


def test_api_export_erase_and_audit_without_the_customer_id_in_the_log():
    c, ac, rt = api()
    token = c.post("/v1/chat-tokens", json={"sessionId": "web-1", "customerId": "jane@example.com"}, headers=H()).json()["token"]
    c.post("/v1/agents/support/chat", json={"sessionId": "web-1", "message": "hello there"}, headers=H(token))
    exp = c.get("/v1/privacy/customers/jane@example.com/export", headers=H())
    assert exp.status_code == 200 and exp.headers["cache-control"] == "no-store" and "attachment" in exp.headers["content-disposition"]
    assert exp.json()["sessions"][0]["sessionId"] == "web-1" and "hello there" in exp.text
    r = c.delete("/v1/privacy/customers/jane@example.com", headers=H()).json()
    assert r["sessions"] == 1 and r["removed"]["messages"] == 2
    assert c.get("/v1/privacy/customers/jane@example.com/export", headers=H()).json()["sessions"] == []
    entries = c.get("/v1/audit?limit=20", headers=H()).json()["entries"]
    actions = {e["action"] for e in entries}
    assert {"privacy.export", "privacy.erase.customer"} <= actions
    assert "jane" not in json.dumps(entries) and customer_ref("jane@example.com") in json.dumps(entries)
    assert c.delete("/v1/privacy/sessions/web-1", headers=H()).json()["removed"]["messages"] == 0


def test_api_retention_and_permissions():
    c, ac, rt = api()
    c.post("/v1/agents/support/chat", json={"sessionId": "s1", "message": "hi"}, headers=H())
    asyncio.new_event_loop().run_until_complete(rt.privacy.link("s1", None, time.time() - 90 * DAY))
    r = c.post("/v1/privacy/retention/run", json={"olderThanDays": 30}, headers=H())
    assert r.status_code == 200 and r.json()["sessions"] == 1
    assert c.post("/v1/privacy/retention/run", json={"olderThanDays": 0}, headers=H()).status_code == 400
    assert c.post("/v1/privacy/retention/run", json={}, headers=H()).status_code == 400
    loop = asyncio.new_event_loop()
    assert "privacy:manage" in ROLES["admin"] and all("privacy:manage" not in p for n, p in ROLES.items() if n != "admin")
    for role in ("developer", "reviewer", "auditor", "viewer", "channel", "release_manager"):
        k = loop.run_until_complete(ac.issue(role, role, "root"))[1]
        for method, path in [("GET", "/v1/privacy/customers/x/export"), ("DELETE", "/v1/privacy/customers/x"), ("DELETE", "/v1/privacy/sessions/x")]:
            assert c.request(method, path, headers=H(k)).status_code == 403, (role, path)
    assert c.get("/v1/privacy/customers/x/export").status_code == 401
