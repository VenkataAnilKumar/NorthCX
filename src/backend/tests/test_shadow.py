"""Shadow mode: the agent drafts, a person sends, edits or rejects, and nothing reaches a customer or an external system without a person."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.agent import Agent, Tool
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.shadow import ShadowFlow
from northcx.spec import AgentSpec, Registry, SpecError
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
REFUND = tool_call("issue_refund", {"order_id": "2077", "amount": 20}, "t1")   # small: needs no approval outside shadow mode


def shadow_agent():
    return Agent(**{**support_agent().__dict__, "shadow": True})


def setup(script, agent=None):
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    agents = {"support": agent or shadow_agent()}
    return TestClient(create_app(rt, rt.traces, agents, access=ac)), ac, rt


def H(t=KEY):
    return {"authorization": f"Bearer {t}"}


def chat(c, msg="hi", session="s1", headers=None):
    return c.post("/v1/agents/support/chat", json={"sessionId": session, "message": msg}, headers=H() if headers is None else headers)


def drafts(c, state="pending", headers=None):
    return c.get(f"/v1/shadow/drafts?state={state}", headers=H() if headers is None else headers).json()["drafts"]


def decide(c, did, action, headers=None, **body):
    return c.post(f"/v1/shadow/drafts/{did}/decision", json={"action": action, **body}, headers=H() if headers is None else headers)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- S1: the spec ----
def test_the_flag_defaults_off_is_for_customer_agents_and_does_not_change_old_digests():
    base = dict(id="a", instructions="help")
    assert AgentSpec(**base).shadow is False
    assert AgentSpec(**base).digest() == AgentSpec(**base, shadow=False).digest()
    assert AgentSpec(**base).digest() != AgentSpec(**base, shadow=True).digest()
    reg = Registry()
    assert reg.build(AgentSpec(**base, shadow=True)).shadow is True
    problems = reg.validate(AgentSpec(**base, audience="staff", shadow=True))
    assert any("shadow" in p and "customer" in p for p in problems)


# ---- S2: nothing the agent wrote reaches the customer ----
def test_a_reply_is_held_as_a_draft_and_not_returned():
    c, _, _ = setup([text("Order 1042 shipped on Monday.")])
    r = chat(c, "where is 1042?").json()
    assert r["reply"] == "" and r["status"] == "in_review" and r["pendingApprovals"] == []
    (d,) = drafts(c)
    assert d["draft"] == "Order 1042 shipped on Monday." and d["customerMessage"] == "where is 1042?" and d["state"] == "pending" and d["sessionId"] == "s1"


def test_no_path_returns_or_publishes_the_draft_text():
    secret = "ZEBRA-DRAFT-TEXT"
    c, _, rt = setup([text(secret)] * 4)
    plain = chat(c, "one", session="a")
    stream = c.post("/v1/agents/support/chat/stream", json={"sessionId": "b", "message": "two"}, headers=H())
    agui = c.post("/v1/agents/support/agui", json={"threadId": "c", "runId": "r", "messages": [{"role": "user", "content": "three"}]}, headers=H())
    assert secret not in plain.text and secret not in stream.text and secret not in agui.text
    assert '"outcome": "success"' in agui.text and '"status": "in_review"' in agui.text
    for s in ("a", "b", "c"):
        assert run(rt.outbox.list(s)) == []
    assert len(drafts(c)) == 3


def test_a_shadow_agent_in_a_simulation_answers_as_it_will_live():
    from northcx.runtime import Runtime as R
    rt = R(ScriptedLLM([text("visible")]), InMemoryStore(), TraceStore(), dry_run=True)
    r = run(rt.run(shadow_agent(), "s", "hi", "c"))
    assert r.reply == "visible" and r.status == "completed"


# ---- S3: nothing that changes something runs without a person ----
def test_a_write_is_held_as_an_approval_and_never_runs_but_a_read_does():
    c, _, rt = setup([tool_call("lookup_order", {"order_id": "1042"}, "t0"), REFUND, text("unused")])
    r = chat(c, "refund order 2077 please").json()
    assert r["status"] == "in_review" and r["reply"] == ""
    (a,) = run(rt.approvals.list("pending"))
    assert a.tool == "issue_refund" and "Shadow mode" in a.reason
    tr = run(rt.traces.get(r["traceId"]))
    types = [e.type for e in tr.events]
    assert "tool_result" in types and "approval" in types and "shadow_draft" in types       # the read ran, the write was held
    assert [e.data["name"] for e in tr.events if e.type == "tool_result"] == ["lookup_order"]


# ---- S5, S6, S7, S10: decisions ----
def test_send_publishes_the_draft_once_and_a_second_decision_is_refused():
    c, _, rt = setup([text("Order 1042 shipped.")])
    chat(c, "where is 1042?")
    did = drafts(c)[0]["id"]
    r = decide(c, did, "send")
    assert r.status_code == 200 and r.json()["state"] == "sent"
    (m,) = run(rt.outbox.list("s1"))
    assert m.kind == "shadow_reply" and m.payload["reply"] == "Order 1042 shipped." and m.payload["traceId"]
    again = decide(c, did, "send")
    assert again.status_code == 409 and len(run(rt.outbox.list("s1"))) == 1
    hist = run(rt.store.load_messages("s1"))
    assert hist[-1] == {"role": "assistant", "content": "Order 1042 shipped."}
    audit = c.get("/v1/audit", headers=H()).json()["entries"]
    assert any(e["action"] == "shadow.send" and e["target"] == did for e in audit) and "shipped" not in json.dumps(audit)


def test_an_edit_sends_the_persons_text_keeps_the_draft_and_replaces_it_in_the_history():
    c, _, rt = setup([text("Your order is on its way.")])
    chat(c, "where is it?")
    did = drafts(c)[0]["id"]
    r = decide(c, did, "edit", text="Your order is on its way and should arrive Monday.", reasons=["incomplete"], note="added the day")
    assert r.status_code == 200
    d = r.json()
    assert d["state"] == "edited" and d["draft"] == "Your order is on its way." and d["finalText"].endswith("Monday.") and d["reasons"] == ["incomplete"] and d["decidedBy"]
    (m,) = run(rt.outbox.list("s1"))
    assert m.payload["reply"].endswith("Monday.") and m.payload["edited"] is True
    assert run(rt.store.load_messages("s1"))[-1]["content"].endswith("Monday.")
    tr = run(rt.traces.get(m.payload["traceId"]))
    assert any(e.type == "shadow_decision" and e.data["action"] == "edit" for e in tr.events)


def test_an_edit_goes_through_the_agents_checks_and_secrets_are_removed():
    c, _, rt = setup([text("Hello.")])
    chat(c, "hi")
    did = drafts(c)[0]["id"]
    assert decide(c, did, "edit", text="   ").status_code == 400
    assert decide(c, did, "edit", text="Hello.").status_code == 400                       # the same text: use send
    assert decide(c, did, "edit", text="x" * 5000).status_code == 400
    assert drafts(c)[0]["state"] == "pending" and run(rt.outbox.list("s1")) == []         # refusals change nothing


def test_reject_sends_nothing_and_the_history_does_not_keep_words_the_customer_never_saw():
    c, _, rt = setup([text("A wrong answer."), text("A better answer.")])
    chat(c, "question")
    did = drafts(c)[0]["id"]
    assert decide(c, did, "reject", reasons=["wrong", "made-up"]).status_code == 400      # only the listed reasons
    r = decide(c, did, "reject", reasons=["wrong"], note="that is not our policy")
    assert r.status_code == 200 and r.json()["state"] == "rejected" and run(rt.outbox.list("s1")) == []
    hist = run(rt.store.load_messages("s1"))
    assert "A wrong answer." not in json.dumps(hist) and [m["role"] for m in hist] == ["user", "assistant"]


# ---- S8: expiry ----
def test_a_draft_nobody_reviews_expires_and_the_conversation_goes_to_a_person():
    c, _, rt = setup([text("Draft.")])
    chat(c, "hi")
    did = drafts(c)[0]["id"]
    flow = ShadowFlow(rt)
    assert run(flow.expire_stale({"support": shadow_agent()}, 3600)) == []                # too young
    done = run(flow.expire_stale({"support": shadow_agent()}, 3600, now=__import__("time").time() + 7200))
    assert [d.id for d in done] == [did] and done[0].state == "expired"
    (m,) = run(rt.outbox.list("s1"))
    assert m.kind == "shadow_expired" and m.payload["handoffId"] and "Draft." not in m.payload["reply"]
    assert len(run(rt.handoffs.list("open", "s1", 5))) == 1
    assert decide(c, did, "send").status_code == 409


# ---- S9: the agreement figure ----
def test_the_summary_counts_decisions_with_the_denominator_and_gives_no_figure_without_any():
    c, _, rt = setup([text("one"), text("two"), text("three"), text("four")])
    assert c.get("/v1/shadow/summary", headers=H()).json()["agreement"] == {"value": None, "numerator": 0, "denominator": 0}
    for i in range(4):
        chat(c, f"q{i}", session=f"s{i}")
    ids = [d["id"] for d in drafts(c)]
    decide(c, ids[0], "send"); decide(c, ids[1], "send")
    decide(c, ids[2], "edit", text="three, edited"); decide(c, ids[3], "reject", reasons=["tone"])
    s = c.get("/v1/shadow/summary", headers=H()).json()
    assert s["sent"] == 2 and s["edited"] == 1 and s["rejected"] == 1 and s["expired"] == 0 and s["pending"] == 0 and s["decided"] == 4
    assert s["agreement"] == {"value": 0.5, "numerator": 2, "denominator": 4} and s["rejectReasons"] == {"tone": 1}


# ---- S11: who may ----
def test_only_people_who_may_review_reach_the_routes_and_a_customer_token_cannot():
    c, ac, _ = setup([text("d")] * 2)
    loop = asyncio.new_event_loop()
    viewer = loop.run_until_complete(ac.issue("v", "viewer", "root"))[1]
    reviewer = loop.run_until_complete(ac.issue("r", "reviewer", "root"))[1]
    chan = loop.run_until_complete(ac.issue("c", "channel", "root"))[1]
    token = c.post("/v1/chat-tokens", json={"sessionId": "mine", "customerId": "c1"}, headers=H(chan)).json()["token"]
    chat(c, "hi", session="mine", headers=H(token))
    did = drafts(c)[0]["id"]
    for h in ({}, H(viewer), H(token)):
        assert c.get("/v1/shadow/drafts", headers=h).status_code in (401, 403)
        assert decide(c, did, "send", headers=h).status_code in (401, 403)
    assert c.get("/v1/shadow/drafts", headers=H(reviewer)).status_code == 200
    assert decide(c, did, "send", headers=H(reviewer)).status_code == 200


# ---- S12: privacy ----
def test_drafts_are_exported_and_erased_with_their_conversation():
    c, _, rt = setup([text("Private draft text.")])
    chat(c, "hello", session="s9")
    exported = run(rt.privacy.export_session("s9"))
    assert [d["draft"] for d in exported["shadow_drafts"]] == ["Private draft text."]
    run(rt.privacy.erase_session("s9"))
    assert drafts(c) == [] and run(rt.shadow.list(session_id="s9")) == []


# ---- S13: voice ----
def test_the_voice_channel_refuses_a_shadow_agent_before_it_runs():
    from northcx.voice import refuse_shadow
    with pytest.raises(RuntimeError, match="shadow"):
        refuse_shadow(shadow_agent())
    refuse_shadow(support_agent())


# ---- the store, in memory and in Postgres ----
@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        from northcx.shadow import InMemoryShadowDrafts
        return InMemoryShadowDrafts()
    from northcx.db import PgShadowDrafts
    return PgShadowDrafts(request.getfixturevalue("engine"))


async def _add(repo, **kw):
    base = dict(session_id="s1", agent_id="support", trace_id="t1", customer_message="hi", draft="hello", agent_version=3, customer_id="c1")
    return await repo.add(**{**base, **kw})


async def test_the_store_keeps_drafts_and_moves_each_out_of_pending_only_once(repo):
    a, b = await _add(repo), await _add(repo, session_id="s2", draft="two")
    assert (await repo.get(a.id)) == a and [d.id for d in await repo.list("pending")] == [a.id, b.id] and [d.id for d in await repo.list(session_id="s2")] == [b.id]
    done = await repo.decide(a.id, "edited", "ann", "hello there", ["tone"], "friendlier")
    assert (done.state, done.final_text, done.reasons, done.decided_by, done.note) == ("edited", "hello there", ["tone"], "ann", "friendlier") and done.decided_at
    assert done.draft == "hello" and (await repo.get(a.id)).draft == "hello"                        # the draft stays as the agent wrote it
    with pytest.raises(ValueError):
        await repo.decide(a.id, "sent", "bob", "hello", [], None)                                   # a second decision loses
    with pytest.raises(KeyError):
        await repo.decide("nope", "sent", "bob", "x", [], None)
    assert await repo.expire(a.id) is None and (await repo.expire(b.id)).state == "expired" and await repo.expire(b.id) is None
    assert [d.state for d in await repo.list(since=0)] == ["edited", "expired"] and await repo.list("pending") == []


async def test_two_people_deciding_at_once_send_only_once(repo):
    d = await _add(repo)
    results = await asyncio.gather(*[repo.decide(d.id, "sent", f"p{i}", "hello", [], None) for i in range(5)], return_exceptions=True)
    assert sum(isinstance(r, Exception) for r in results) == 4 and (await repo.get(d.id)).state == "sent"


async def test_erasing_a_session_removes_its_drafts_only(repo):
    a, b = await _add(repo), await _add(repo, session_id="s2")
    assert await repo.erase_session("s1") == 1 and await repo.get(a.id) is None and await repo.get(b.id) is not None


async def test_one_tenant_cannot_read_another_tenants_drafts(repo):
    from northcx.shadow import InMemoryShadowDrafts
    from northcx.tenancy import TENANT
    if isinstance(repo, InMemoryShadowDrafts):
        pytest.skip("row-level security is the database's; the in-memory twin has no tenants")
    d = await _add(repo)
    token = TENANT.set("acme")
    try:
        assert await repo.list() == [] and await repo.get(d.id) is None
    finally:
        TENANT.reset(token)


# ---- an edit meets the agent's reply checks ----
def test_an_edit_that_a_reply_check_stops_is_refused_with_the_reason():
    from northcx.guardrails import Guardrail, Verdict

    class NoPromises(Guardrail):
        name = "no-promises"

        async def check_reply(self, reply, ctx):
            return Verdict(False, "never promise a delivery day") if "guarantee" in reply else Verdict.ok()

    agent = shadow_agent()
    agent.guardrails = [NoPromises()]
    c, _, rt = setup([text("It will arrive soon.")], agent)
    chat(c, "when?")
    did = drafts(c)[0]["id"]
    r = decide(c, did, "edit", text="We guarantee it arrives Monday.")
    assert r.status_code == 400 and "never promise a delivery day" in r.json()["error"]["message"]
    assert drafts(c)[0]["state"] == "pending" and run(rt.outbox.list("s1")) == []
    assert decide(c, did, "edit", text="It should arrive in a few days.").status_code == 200


# ---- SMS: the same guarantee on a messaging channel ----
async def test_a_text_is_not_sent_until_a_person_approves_the_draft_and_then_once():
    from tests.test_sms import JANE, OURS, build, inbound
    ch, rt, provider, repo_ = build([text("Order 1042 was delivered.")])
    from northcx.catalog import as_provider
    ch.agents = as_provider({"support": shadow_agent()})
    r = await ch.receive(inbound())
    assert r.status == "in_review" and provider.sent == []                                            # nothing reached the customer's phone
    assert await rt.outbox.flush(now=__import__("time").time() + 4000) == 0 and provider.sent == []
    (d,) = await rt.shadow.list("pending")
    await ShadowFlow(rt).decide(ch.agents, d.id, "send", "ann")
    assert provider.sent == [(JANE, OURS, "Order 1042 was delivered.")]
    await rt.outbox.flush(now=__import__("time").time() + 8000)
    assert len(provider.sent) == 1


async def test_postgres_export_and_erasure_cover_the_drafts_of_a_conversation(engine):
    from northcx.db import PgPrivacy, PgShadowDrafts
    drafts_ = PgShadowDrafts(engine)
    await _add(drafts_, draft="Private draft text.")
    await _add(drafts_, session_id="s2", draft="Another conversation.")
    privacy = PgPrivacy(engine)
    assert [d["draft"] for d in (await privacy.export_session("s1"))["shadow_drafts"]] == ["Private draft text."]
    assert (await privacy.erase_session("s1"))["shadow_drafts"] == 1
    assert [d.session_id for d in await drafts_.list()] == ["s2"]
