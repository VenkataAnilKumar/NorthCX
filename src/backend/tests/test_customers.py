"""Customers tab (decision 158): found by the company's own identifier, masked, every open and reveal audited, notes screened, erased with the customer."""
import asyncio
import json

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text
from northcx.memory import InMemoryMemories
from northcx.privacy import customer_ref
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
ADM = {"authorization": f"Bearer {KEY}"}
JANE = "jane@example.com"


def world():
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([text("Happy to help.")] * 10), InMemoryStore(), TraceStore(), memories=InMemoryMemories())
    ac = AccessControl(bootstrap_key=KEY)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    key = lambda n, r: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    token = c.post("/v1/chat-tokens", json={"sessionId": "web-1", "customerId": JANE}, headers=ADM).json()["token"]
    c.post("/v1/agents/support/chat", json={"sessionId": "web-1", "message": f"hello, my email is {JANE}"}, headers={"authorization": f"Bearer {token}"})
    c.post("/v1/sessions/web-1/feedback", json={"rating": 5}, headers={"authorization": f"Bearer {token}"})
    loop.run_until_complete(rt.memories.remember(JANE, "Prefers email over phone calls", "web-1"))
    return c, rt, key, loop


def test_a_lead_finds_a_customer_by_their_identifier_and_sees_a_masked_cross_channel_view():
    c, rt, key, loop = world()
    rev = key("rev", "reviewer")
    r = c.post("/v1/customers/lookup", headers=rev, json={"customerId": JANE})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    out = r.json()
    assert out["ref"] == customer_ref(JANE) and out["idMasked"] is True and JANE not in r.text and out["sessions"] == 1
    assert out["timeline"][0]["sessionId"] == "web-1" and out["timeline"][0]["rating"] == 5 and JANE not in out["timeline"][0]["firstMessage"]
    assert out["satisfaction"]["average"] == 5.0 and out["satisfaction"]["rated"] == 1
    assert out["facts"][0]["text"] == "Prefers email over phone calls" and out["facts"][0]["addedBy"] == "the agent"
    assert c.post("/v1/customers/lookup", headers=rev, json={"customerId": "nobody"}).status_code == 404


def test_only_leads_and_reviewers_can_open_it_by_default_and_every_open_is_audited_without_the_id():
    c, rt, key, loop = world()
    assert c.post("/v1/customers/lookup", headers=key("view", "viewer"), json={"customerId": JANE}).status_code == 403
    assert c.post("/v1/customers/lookup", headers=key("dev", "developer"), json={"customerId": JANE}).status_code == 403
    assert c.post("/v1/customers/lookup", json={"customerId": JANE}).status_code == 401
    assert c.post("/v1/customers/lookup", headers=key("rev", "reviewer"), json={"customerId": JANE}).status_code == 200
    c.post("/v1/customers/lookup", headers=ADM, json={"customerId": "nobody"})
    entries = c.get("/v1/audit?limit=30", headers=ADM).json()["entries"]
    assert {"customers.open", "customers.lookup"} <= {e["action"] for e in entries}
    assert "jane" not in json.dumps(entries) and customer_ref(JANE) in json.dumps(entries)


def test_revealing_the_identifier_needs_a_reason_that_is_logged():
    c, rt, key, loop = world()
    rev = key("rev", "reviewer")
    assert c.post("/v1/customers/reveal", headers=rev, json={"customerId": JANE, "reason": "short"}).status_code == 400
    r = c.post("/v1/customers/reveal", headers=rev, json={"customerId": JANE, "reason": "Customer asked us to call back on this account"})
    assert r.status_code == 200 and r.json()["id"] == JANE and r.headers["cache-control"] == "no-store"
    entry = next(e for e in c.get("/v1/audit?limit=30", headers=ADM).json()["entries"] if e["action"] == "customers.reveal")
    assert "call back" in json.dumps(entry) and JANE not in json.dumps(entry)
    assert c.post("/v1/customers/reveal", headers=rev, json={"customerId": "nobody", "reason": "a long enough reason"}).status_code == 404


def test_notes_are_screened_attributed_and_removable_by_their_author_or_an_administrator():
    c, rt, key, loop = world()
    ann, ben = key("ann", "reviewer"), key("ben", "reviewer")
    n = c.post("/v1/customers/notes", headers=ann, json={"customerId": JANE, "note": "Asked for a call on Tuesday mornings only."})
    assert n.status_code == 201 and n.json()["author"] == "ann"
    assert c.post("/v1/customers/notes", headers=ann, json={"customerId": JANE, "note": "Card is 4242 4242 4242 4242 for next time"}).status_code == 400
    assert c.post("/v1/customers/notes", headers=ann, json={"customerId": "nobody", "note": "A note for a stranger."}).status_code == 404
    assert [x["note"] for x in c.post("/v1/customers/lookup", headers=ben, json={"customerId": JANE}).json()["notes"]] == ["Asked for a call on Tuesday mornings only."]
    assert c.post(f"/v1/customers/notes/{n.json()['id']}/delete", headers=ben, json={"customerId": JANE}).status_code == 403
    assert c.post(f"/v1/customers/notes/{n.json()['id']}/delete", headers=ADM, json={"customerId": JANE}).status_code == 200
    assert c.post("/v1/customers/notes", headers=key("v", "viewer"), json={"customerId": JANE, "note": "A viewer may not write."}).status_code == 403


def test_a_fact_can_be_removed_on_the_customers_request_with_a_logged_reason():
    c, rt, key, loop = world()
    rev = key("rev", "reviewer")
    fid = c.post("/v1/customers/lookup", headers=rev, json={"customerId": JANE}).json()["facts"][0]["id"]
    assert c.post(f"/v1/customers/facts/{fid}/remove", headers=rev, json={"customerId": JANE, "reason": "x"}).status_code == 400
    assert c.post(f"/v1/customers/facts/{fid}/remove", headers=rev, json={"customerId": JANE, "reason": "Customer asked"}).json() == {"removed": True}
    assert c.post("/v1/customers/lookup", headers=rev, json={"customerId": JANE}).json()["facts"] == []
    assert c.post(f"/v1/customers/facts/{fid}/remove", headers=rev, json={"customerId": JANE, "reason": "Customer asked"}).status_code == 404
    assert "customers.fact_remove" in [e["action"] for e in c.get("/v1/audit?limit=30", headers=ADM).json()["entries"]]


def test_an_administrator_can_switch_it_off_and_back_on():
    c, rt, key, loop = world()
    rev = key("rev", "reviewer")
    assert c.put("/v1/customers/settings", headers=rev, json={"enabled": False}).status_code == 403
    assert c.put("/v1/customers/settings", headers=ADM, json={"enabled": False}).json() == {"enabled": False}
    r = c.post("/v1/customers/lookup", headers=rev, json={"customerId": JANE})
    assert r.status_code == 403 and r.json()["error"]["code"] == "disabled"
    assert c.post("/v1/customers/notes", headers=rev, json={"customerId": JANE, "note": "Should not be saved."}).status_code == 403
    c.put("/v1/customers/settings", headers=ADM, json={"enabled": True})
    assert c.post("/v1/customers/lookup", headers=rev, json={"customerId": JANE}).status_code == 200


def test_a_deletion_request_removes_the_notes_too_and_an_export_includes_them():
    c, rt, key, loop = world()
    rev = key("rev", "reviewer")
    c.post("/v1/customers/notes", headers=rev, json={"customerId": JANE, "note": "A note that must go with the customer."})
    assert "A note that must go" in c.get(f"/v1/privacy/customers/{JANE}/export", headers=ADM).text
    assert c.delete(f"/v1/privacy/customers/{JANE}", headers=ADM).json()["removed"]["customerNotes"] == 1
    assert c.post("/v1/customers/lookup", headers=rev, json={"customerId": JANE}).status_code == 404


async def test_notes_and_the_switch_survive_the_database_and_stay_in_their_tenant(app_engine):
    from northcx.customers import CustomerNote, CustomerService
    from northcx.db import PgCustomerNotes, PgSettings
    from northcx.tenancy import TENANT
    svc = CustomerService(PgCustomerNotes(app_engine), PgSettings(app_engine))
    for tenant in ("acme", "globex"):
        token = TENANT.set(tenant)
        try:
            await svc.notes.add(CustomerNote("c1", f"Note for {tenant} only.", "ann"))
        finally:
            TENANT.reset(token)
    token = TENANT.set("acme")
    try:
        assert [n.note for n in await svc.notes.list("c1")] == ["Note for acme only."]
        await svc.set_enabled(False, "ann")
        assert await svc.enabled() is False
        assert await svc.notes.erase_customer("c1") == 1
    finally:
        TENANT.reset(token)
    token = TENANT.set("globex")
    try:
        assert len(await svc.notes.list("c1")) == 1 and await svc.enabled() is True
    finally:
        TENANT.reset(token)
