"""Library items: prompts, macros, playbooks and canned answers. Masked, versioned, private until shared, counted, and suggested for a conversation."""
import asyncio

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.library_items import LibraryError, LibraryService, InMemoryLibrary, score, words
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
ADM = {"authorization": f"Bearer {KEY}"}


def world():
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=ac)
    key = lambda n, r="reviewer": {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    return TestClient(app), key


def mk(c, h, **kw):
    return c.post("/v1/workspace/library-items", headers=h, json={"title": "Late parcel apology", "body": "Sorry your parcel is late. We are chasing the carrier and will update you today.", "kind": "macro", **kw})


def test_an_item_is_masked_versioned_counted_and_private_until_shared():
    c, key = world()
    ann, ben = key("ann"), key("ben")
    r = mk(c, ann, body="Hi jo@example.com, sorry your parcel is late.")
    assert r.status_code == 201 and "jo@example.com" not in r.text
    iid = r.json()["id"]
    assert c.get(f"/v1/workspace/library-items/{iid}", headers=ben).status_code == 404
    assert c.put(f"/v1/workspace/library-items/{iid}", headers=ann, json={"body": "New wording for the apology."}).json()["version"] == 2
    assert c.put(f"/v1/workspace/library-items/{iid}", headers=ann, json={"body": "New wording for the apology."}).json()["version"] == 2
    c.put(f"/v1/workspace/library-items/{iid}", headers=ann, json={"visibility": "shared", "tags": ["delivery", "Late"]})
    got = c.get(f"/v1/workspace/library-items/{iid}", headers=ben).json()
    assert got["tags"] == ["delivery", "late"] and got["body"] == "New wording for the apology."
    used = c.post(f"/v1/workspace/library-items/{iid}/use", headers=ben).json()
    assert used["uses"] == 1 and used["body"] == "New wording for the apology."
    assert c.post(f"/v1/workspace/library-items/{iid}/use", headers=ann).json()["uses"] == 2
    assert c.put(f"/v1/workspace/library-items/{iid}", headers=ben, json={"title": "Mine"}).status_code == 403
    assert c.put(f"/v1/workspace/library-items/{iid}", headers=ann, json={"title": "Edited title"}).json()["uses"] == 2          # an edit never resets the count
    assert c.delete(f"/v1/workspace/library-items/{iid}", headers=ben).status_code == 403
    assert c.delete(f"/v1/workspace/library-items/{iid}", headers=ADM).status_code == 200


def test_validation_and_who_may_use_it():
    c, key = world()
    ann = key("ann")
    assert mk(c, ann, kind="poem").status_code == 400
    assert c.post("/v1/workspace/library-items", headers=ann, json={"title": "x", "body": "text"}).status_code in (400, 422)
    assert mk(c, ann, tags=["Bad Tag!"]).status_code == 400
    assert mk(c, ann, tags=[f"t{i}" for i in range(9)]).status_code in (400, 422)
    assert c.get("/v1/workspace/library-items").status_code == 401
    tok = c.post("/v1/chat-tokens", json={"sessionId": "w1", "customerId": "c"}, headers=ADM).json()["token"]
    assert c.get("/v1/workspace/library-items", headers={"authorization": f"Bearer {tok}"}).status_code in (401, 403)


def test_search_and_suggestions_find_the_macro_that_fits_the_customers_message():
    c, key = world()
    ann, ben = key("ann"), key("ben")
    mk(c, ann, visibility="shared", tags=["delivery"])
    mk(c, ann, title="Refund policy", body="Refunds are issued to the original payment method within five days of the return.", visibility="shared", tags=["refund"])
    mk(c, ann, title="Private macro about parcels", body="parcel parcel parcel late", visibility="private")
    c.post("/v1/workspace/library-items", headers=ann, json={"title": "Escalation playbook", "body": "Step one: calm. Step two: check the parcel carrier.", "kind": "playbook", "visibility": "shared"})
    s = c.post("/v1/workspace/library-items/suggest", headers=ben, json={"text": "Hello, where is my parcel? It is very late and I want an update."}).json()["suggestions"]
    assert [x["title"] for x in s] == ["Late parcel apology"]                                  # a playbook is not a reply, and someone else's private macro is not offered
    own = c.post("/v1/workspace/library-items/suggest", headers=ann, json={"text": "my parcel is late"}).json()["suggestions"]
    assert {x["title"] for x in own} == {"Late parcel apology", "Private macro about parcels"}
    assert c.post("/v1/workspace/library-items/suggest", headers=ben, json={"text": "How do I reset my password?"}).json()["suggestions"] == []
    found = c.get("/v1/workspace/library-items?q=refund%20return", headers=ben).json()["items"]
    assert [x["title"] for x in found] == ["Refund policy"]
    assert {x["kind"] for x in c.get("/v1/workspace/library-items?kind=playbook", headers=ben).json()["items"]} == {"playbook"}
    assert [x["title"] for x in c.get("/v1/workspace/library-items?mine=true", headers=ben).json()["items"]] == []


def test_scoring_prefers_titles_and_tags_and_ignores_filler_words():
    svc = LibraryService(InMemoryLibrary())
    a = asyncio.run(svc.create("ann", "Late parcel", "We are sorry.", "macro"))
    b = asyncio.run(svc.create("ann", "Greeting", "Your parcel is on its way and will be late.", "macro"))
    q = words("Where is my parcel? It is late, please help")
    assert "the" not in words("the and for") and q >= {"parcel", "late", "help"} and "where" not in q
    assert score(q, a) > score(q, b) > 0
    try:
        asyncio.run(svc.create("ann", "Empty", "   ", "macro"))
        raise AssertionError("empty text accepted")
    except LibraryError as e:
        assert e.status == 400


async def test_items_survive_the_database_and_stay_in_their_tenant(app_engine):
    from northcx.db import PgLibrary
    from northcx.tenancy import TENANT
    svc = LibraryService(PgLibrary(app_engine))
    ids = {}
    for tenant in ("acme", "globex"):
        token = TENANT.set(tenant)
        try:
            i = await svc.create("ann", "Shared title", "first wording", "macro", "shared", ["x"])
            await svc.edit(i.id, "ann", False, body="second wording")
            await svc.use(i.id, "ben", False)
            ids[tenant] = i.id
        finally:
            TENANT.reset(token)
    token = TENANT.set("acme")
    try:
        got = await svc.get(ids["acme"], "ben", False)
        assert [v["body"] for v in got.versions] == ["first wording", "second wording"] and got.uses == 1 and got.tags == ["x"]
        await svc.edit(ids["acme"], "ann", False, title="Renamed")
        assert (await svc.get(ids["acme"], "ben", False)).uses == 1
        try:
            await svc.get(ids["globex"], "ann", False)
            raise AssertionError("another tenant's item was readable")
        except LibraryError:
            pass
    finally:
        TENANT.reset(token)
    token = TENANT.set("nobody")
    try:
        assert await svc.list("ann", False) == []
    finally:
        TENANT.reset(token)
