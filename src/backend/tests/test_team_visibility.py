"""Sharing with a team: outputs, spaces and library items can be seen by people signed in under the same team as their owner, and by nobody in another team."""
import asyncio

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
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
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    person = lambda name, *groups: {"authorization": "Bearer " + loop.run_until_complete(ac.issue_session(name, "reviewer", 8, groups=list(groups)))[1]}  # noqa: E731
    return c, person


def test_an_output_shared_with_a_team_is_seen_by_that_team_only():
    c, person = world()
    ann, ben, cy, dee = person("Ann", "billing"), person("Ben", "billing"), person("Cy", "returns"), person("Dee")
    r = c.post("/v1/workspace/outputs", headers=ann, json={"title": "Billing notes", "body": "Chargeback process.", "visibility": "team"})
    assert r.status_code == 201 and r.json()["team"] == "billing" and r.json()["visibility"] == "team"
    oid = r.json()["id"]
    assert c.get(f"/v1/workspace/outputs/{oid}", headers=ben).status_code == 200                      # same team
    assert c.get(f"/v1/workspace/outputs/{oid}", headers=cy).status_code == 404                       # another team
    assert c.get(f"/v1/workspace/outputs/{oid}", headers=dee).status_code == 404                      # no team at all
    assert [o["id"] for o in c.get("/v1/workspace/outputs", headers=ben).json()["outputs"]] == [oid] and c.get("/v1/workspace/outputs", headers=cy).json()["outputs"] == []
    assert c.put(f"/v1/workspace/outputs/{oid}", headers=ben, json={"body": "mine"}).status_code == 403          # visible is not editable
    assert c.put(f"/v1/workspace/outputs/{oid}", headers=ann, json={"visibility": "private"}).json()["team"] is None
    assert c.get(f"/v1/workspace/outputs/{oid}", headers=ben).status_code == 404                      # back to private
    assert c.get(f"/v1/workspace/outputs/{oid}", headers=ADM).status_code == 200                      # an administrator can always see it


def test_someone_in_no_team_cannot_share_with_one_and_a_team_is_the_first_group_alphabetically():
    c, person = world()
    dee, ann = person("Dee"), person("Ann", "returns", "billing")
    r = c.post("/v1/workspace/outputs", headers=dee, json={"title": "Notes", "body": "text", "visibility": "team"})
    assert r.status_code == 400 and "not in a team" in r.json()["error"]["message"]
    assert c.post("/v1/workspace/library-items", headers=dee, json={"title": "Macro", "body": "text", "kind": "macro", "visibility": "team"}).status_code == 400
    assert c.post("/v1/workspace/spaces", headers=dee, json={"name": "Space", "visibility": "team"}).status_code == 400
    assert c.post("/v1/workspace/outputs", headers=ann, json={"title": "Notes", "body": "text", "visibility": "team"}).json()["team"] == "billing"


def test_library_items_and_spaces_follow_the_same_rule_and_the_pilot_uses_a_teams_space_only_for_that_team():
    c, person = world()
    ann, ben, cy = person("Ann", "billing"), person("Ben", "billing"), person("Cy", "returns")
    item = c.post("/v1/workspace/library-items", headers=ann, json={"title": "Chargeback reply", "body": "We are reviewing the chargeback and will reply today.", "kind": "macro", "visibility": "team", "tags": ["chargeback"]}).json()
    assert c.get(f"/v1/workspace/library-items/{item['id']}", headers=ben).status_code == 200 and c.get(f"/v1/workspace/library-items/{item['id']}", headers=cy).status_code == 404
    assert [x["title"] for x in c.post("/v1/workspace/library-items/suggest", headers=ben, json={"text": "I disputed a chargeback, any news?"}).json()["suggestions"]] == ["Chargeback reply"]
    assert c.post("/v1/workspace/library-items/suggest", headers=cy, json={"text": "I disputed a chargeback, any news?"}).json()["suggestions"] == []
    space = c.post("/v1/workspace/spaces", headers=ann, json={"name": "Billing room", "instructions": "Be brief.", "visibility": "team"}).json()
    assert c.get(f"/v1/workspace/spaces/{space['id']}", headers=ben).status_code == 200 and c.get(f"/v1/workspace/spaces/{space['id']}", headers=cy).status_code == 404
    assert c.post("/v1/workspace/chat", headers=cy, json={"message": "hi", "spaceId": space["id"]}).status_code == 404            # another team cannot work in it
    assert c.post(f"/v1/workspace/spaces/{space['id']}/files", headers=ben, json={"name": "a.txt", "text": "x"}).status_code == 403   # only the owner adds files
    assert c.post("/v1/workspace/outputs", headers=ben, json={"title": "Into the room", "body": "x", "spaceId": space["id"]}).status_code == 201     # a team member can add an output to the team's space
    assert c.post("/v1/workspace/outputs", headers=cy, json={"title": "Into the room", "body": "x", "spaceId": space["id"]}).status_code == 404


async def test_the_team_is_kept_in_the_database(app_engine):
    from northcx.db import PgContent, PgLibrary
    from northcx.decision_teams import VIEWER_TEAM
    from northcx.library_items import LibraryService
    from northcx.outputs import ContentError, ContentService
    from northcx.tenancy import TENANT
    token = TENANT.set("acme")
    team = VIEWER_TEAM.set("billing")
    try:
        content, lib = ContentService(PgContent(app_engine)), LibraryService(PgLibrary(app_engine))
        o = await content.create_output("ann", "Team note", "text", visibility="team")
        i = await lib.create("ann", "Macro", "text", "macro", "team")
        s = await content.create_space("ann", "Room", visibility="team")
        VIEWER_TEAM.set("billing")
        assert (await content.get_output(o.id, "ben", False)).team == "billing" and (await lib.get(i.id, "ben", False)).team == "billing" and (await content.get_space(s.id, "ben", False)).team == "billing"
        VIEWER_TEAM.set("returns")
        for call in (lambda: content.get_output(o.id, "cy", False), lambda: lib.get(i.id, "cy", False), lambda: content.get_space(s.id, "cy", False)):
            try:
                await call()
                raise AssertionError("another team could read it")
            except Exception as e:
                assert type(e).__name__ in ("ContentError", "LibraryError")
    finally:
        VIEWER_TEAM.reset(team)
        TENANT.reset(token)
