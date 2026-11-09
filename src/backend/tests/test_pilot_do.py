"""The Pilot's Think and Do styles. Do only proposes; the person confirms; permissions are checked when it happens."""
import asyncio
import json
import time

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
ADM = {"authorization": f"Bearer {KEY}"}


def world(script):
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=ac)
    key = lambda n, r="reviewer": {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    return TestClient(app), rt, key, app


def customer_chat(c, rt, sid="web-1", cid="amy@example.com"):
    tok = c.post("/v1/chat-tokens", json={"sessionId": sid, "customerId": cid}, headers=ADM).json()["token"]
    saved, rt.llm.script = rt.llm.script, [text("Hello.")]
    c.post("/v1/agents/support/chat", json={"sessionId": sid, "message": "hello"}, headers={"authorization": f"Bearer {tok}"})
    rt.llm.script = saved


def test_think_asks_for_a_careful_checked_answer_and_quick_does_not():
    c, rt, key, app = world([text("A careful answer."), text("A quick answer.")])
    ann = key("ann")
    assert c.post("/v1/workspace/chat", headers=ann, json={"message": "Why are refunds slow?", "style": "think"}).status_code == 200
    assert "What I could not verify" in rt.llm.requests[-1].system
    c.post("/v1/workspace/chat", headers=ann, json={"message": "Why are refunds slow?"})
    assert "What I could not verify" not in rt.llm.requests[-1].system


def test_do_offers_proposal_tools_only_in_do_and_only_those_the_person_may_use():
    c, rt, key, app = world([text("ok"), text("ok"), text("ok")])
    ann, view = key("ann"), key("vera", "viewer")
    c.post("/v1/workspace/chat", headers=ann, json={"message": "tag it", "style": "quick"})
    assert not [t for t in rt.llm.requests[-1].tools if t["name"].startswith("propose_")] if hasattr(rt.llm.requests[-1], "tools") and rt.llm.requests[-1].tools else True
    r = c.post("/v1/workspace/chat", headers=ann, json={"message": "tag it", "style": "do"}).json()
    names = {t["name"] for t in rt.llm.requests[-1].tools}
    assert {"propose_tag_conversation", "propose_add_customer_note", "propose_save_output"} <= names and "propose" in rt.llm.requests[-1].system.lower() and r["tools"].count("propose_save_output") == 1
    c.post("/v1/workspace/chat", headers=view, json={"message": "tag it", "style": "do"})
    viewer_names = {t["name"] for t in rt.llm.requests[-1].tools}
    assert "propose_save_output" in viewer_names and "propose_tag_conversation" not in viewer_names and "propose_add_customer_note" not in viewer_names     # a viewer may save outputs but not tag or note


def test_nothing_changes_until_the_person_confirms_and_then_it_runs_as_them():
    c, rt, key, app = world([])
    ann, ben = key("ann"), key("ben")
    customer_chat(c, rt)
    rt.llm.script = [tool_call("propose_tag_conversation", {"session_id": "web-1", "tag": "needs-follow-up"}, "t1"),
                     tool_call("propose_add_customer_note", {"session_id": "web-1", "note": "Asked for a callback on Tuesday."}, "t2"), text("I proposed a tag and a note; confirm them to apply.")]
    r = c.post("/v1/workspace/chat", headers=ann, json={"message": "Tag web-1 and note the callback request", "style": "do", "chatId": "chat1"}).json()
    assert r["status"] == "completed" and len(r["actions"]) == 2 and all(a["state"] == "proposed" for a in r["actions"])
    assert c.get("/v1/sessions/web-1/tags", headers=ann).json()["tags"] == []                                      # proposed, not done
    tag, note = r["actions"]
    assert c.post(f"/v1/workspace/actions/{tag['id']}/confirm", headers=ben).status_code == 404                  # someone else's proposal looks missing
    done = c.post(f"/v1/workspace/actions/{tag['id']}/confirm", headers=ann)
    assert done.status_code == 200 and done.json()["state"] == "done" and c.get("/v1/sessions/web-1/tags", headers=ann).json()["tags"] == ["pilot-needs-follow-up"]
    assert c.post(f"/v1/workspace/actions/{tag['id']}/confirm", headers=ann).status_code == 409                  # once
    note_done = c.post(f"/v1/workspace/actions/{note['id']}/confirm", headers=ann)
    assert note_done.status_code == 200, note_done.text
    assert note_done.json()["result"] == "Note added"
    looked = c.post("/v1/customers/lookup", headers=ann, json={"customerId": "amy@example.com"}).json()
    assert [n["note"] for n in looked["notes"]] == ["Asked for a callback on Tuesday."] and looked["notes"][0]["author"] == "ann"
    assert [a["id"] for a in c.get("/v1/workspace/actions?chat=chat1", headers=ann).json()["actions"]] == []      # nothing waiting any more
    actions = [e["action"] for e in c.get("/v1/audit?limit=40", headers=ADM).json()["entries"]]
    assert actions.count("workspace.pilot_action") == 2


def test_cancelling_expiry_and_a_changed_role_all_stop_an_action():
    c, rt, key, app = world([])
    ann = key("ann")
    customer_chat(c, rt)
    rt.llm.script = [tool_call("propose_save_output", {"title": "Findings", "body": "Three hand-offs were about delivery."}, "t1"), text("Proposed.")]
    a1 = c.post("/v1/workspace/chat", headers=ann, json={"message": "save this", "style": "do", "chatId": "c2"}).json()["actions"][0]
    assert c.post(f"/v1/workspace/actions/{a1['id']}/cancel", headers=ann).json()["state"] == "cancelled"
    assert c.post(f"/v1/workspace/actions/{a1['id']}/confirm", headers=ann).status_code == 409
    rt.llm.script = [tool_call("propose_save_output", {"title": "Findings", "body": "Three hand-offs were about delivery."}, "t1"), text("Proposed.")]
    a2 = c.post("/v1/workspace/chat", headers=ann, json={"message": "save this", "style": "do", "chatId": "c3"}).json()["actions"][0]
    stored = asyncio.new_event_loop().run_until_complete(rt.pilot_actions.repo.get(a2["id"]))
    stored.created_at = time.time() - 3600
    assert c.post(f"/v1/workspace/actions/{a2['id']}/confirm", headers=ann).status_code == 409 and stored.state == "expired"
    # permission is checked when it happens: a tag proposed by someone who can tag, confirmed after the right is gone, is refused
    from northcx.pilot_actions import PilotAction
    loop = asyncio.new_event_loop()
    view = key("vera", "viewer")
    ghost = PilotAction("vera", "c4", "tag_conversation", {"session_id": "web-1", "tag": "x"}, "Tag web-1")
    loop.run_until_complete(rt.pilot_actions.repo.put(ghost))
    r = c.post(f"/v1/workspace/actions/{ghost.id}/confirm", headers=view)
    assert r.status_code == 403 and "conversations:tag" in r.json()["error"]["message"]
    assert c.get("/v1/workspace/outputs", headers=ann).json()["outputs"] == []                                     # the cancelled and expired ones saved nothing


def test_a_proposal_can_be_refused_for_a_bad_target_and_the_pending_limit_holds():
    c, rt, key, app = world([])
    ann = key("ann")
    rt.llm.script = [tool_call("propose_tag_conversation", {"session_id": "no-such-chat", "tag": "x"}, "t1"), text("Proposed.")]
    a = c.post("/v1/workspace/chat", headers=ann, json={"message": "tag it", "style": "do"}).json()["actions"][0]
    r = c.post(f"/v1/workspace/actions/{a['id']}/confirm", headers=ann)
    assert r.status_code == 404 and "Unknown conversation" in r.json()["error"]["message"]
    rt.llm.script = [tool_call("propose_save_output", {"title": f"Note {i}", "body": "text"}, f"t{i}") for i in range(11)] + [text("done")]
    out = c.post("/v1/workspace/chat", headers=ann, json={"message": "save eleven notes", "style": "do"}).json()
    assert len(out["actions"]) <= 10
    assert c.post("/v1/workspace/chat", headers=ann, json={"message": "x", "style": "nonsense"}).status_code == 400
    tok = c.post("/v1/chat-tokens", json={"sessionId": "web-9", "customerId": "c"}, headers=ADM).json()["token"]
    assert c.post("/v1/workspace/actions/act-x/confirm", headers={"authorization": f"Bearer {tok}"}).status_code in (401, 403)


async def test_proposals_survive_the_database_and_stay_in_their_tenant(app_engine):
    from northcx.db import PgPilotActions
    from northcx.pilot_actions import PilotAction
    from northcx.tenancy import TENANT
    repo = PgPilotActions(app_engine)
    for tenant in ("acme", "globex"):
        token = TENANT.set(tenant)
        try:
            await repo.put(PilotAction("ann", "chat1", "save_output", {"title": "T", "body": "B"}, f"Save for {tenant}", id=f"act-{tenant}"))
        finally:
            TENANT.reset(token)
    token = TENANT.set("acme")
    try:
        got = await repo.get("act-acme")
        assert got.summary == "Save for acme" and got.input == {"title": "T", "body": "B"}
        got.state, got.result = "done", "Saved"
        await repo.put(got)
        assert [a.id for a in await repo.list("ann", "chat1", "proposed")] == [] and [a.id for a in await repo.list("ann", None, "done")] == ["act-acme"]
        assert await repo.get("act-globex") is None
    finally:
        TENANT.reset(token)
