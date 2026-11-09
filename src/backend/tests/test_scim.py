"""WP3.3: SCIM 2.0 users and groups. The messages follow RFC 7644 (the examples identity providers actually send, including Azure's string booleans)."""
import pytest

from northcx.access import hash_secret
from northcx.groups import GroupService
from northcx.scim import ScimService
from test_sso import KEY, build, sign_in

TOKEN = "scim-token-" + "x" * 30
H = {"authorization": f"Bearer {TOKEN}", "content-type": "application/scim+json"}
ADMIN = {"authorization": f"Bearer {KEY}"}
USER = "urn:ietf:params:scim:schemas:core:2.0:User"
PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


def stack(**cfg):
    c, idp, ac = build(use_groups=True, role_map={}, **cfg)
    ac.groups = GroupService()
    ac.scim = ScimService(None, ac.groups, ac, "/scim/v2")
    ac.scim.token_hash = hash_secret(TOKEN)
    return c, idp, ac


def new_user(c, name="rae@corp.com", **kw):
    r = c.post("/scim/v2/Users", headers=H, json={"schemas": [USER], "userName": name, "displayName": "Rae", "externalId": "ext-1", "active": True, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_the_provisioning_token_is_required_and_failures_are_audited():
    c, _, _ = stack()
    assert c.get("/scim/v2/Users").status_code == 401
    assert c.get("/scim/v2/Users", headers={"authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/scim/v2/Users", headers={"authorization": f"Bearer {KEY}"}).status_code == 401  # an API key is not a provisioning token
    r = c.get("/scim/v2/Users", headers=H)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/scim+json") and r.json()["totalResults"] == 0
    assert any(e["action"] == "scim.auth.failed" for e in c.get("/v1/audit?limit=20", headers=ADMIN).json()["entries"])
    assert TOKEN not in c.get("/v1/audit?limit=50", headers=ADMIN).text


def test_without_scim_configured_the_routes_say_so():
    c, _, ac = stack()
    ac.scim = None
    r = c.get("/scim/v2/Users", headers=H)
    assert r.status_code == 404 and r.json()["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]


def test_discovery_endpoints():
    c, _, _ = stack()
    spc = c.get("/scim/v2/ServiceProviderConfig", headers=H).json()
    assert spc["patch"]["supported"] and not spc["bulk"]["supported"] and spc["filter"]["supported"]
    assert {r["id"] for r in c.get("/scim/v2/ResourceTypes", headers=H).json()["Resources"]} == {"User", "Group"}
    assert len(c.get("/scim/v2/Schemas", headers=H).json()["Resources"]) == 2


def test_create_read_filter_and_uniqueness():
    c, _, _ = stack()
    u = new_user(c, "Rae@Corp.com")
    assert u["userName"] == "rae@corp.com" and u["active"] is True and u["emails"][0]["value"] == "rae@corp.com" and u["meta"]["resourceType"] == "User" and u["id"]
    assert c.get(f"/scim/v2/Users/{u['id']}", headers=H).json()["externalId"] == "ext-1"
    assert c.post("/scim/v2/Users", headers=H, json={"userName": "rae@corp.com"}).json()["scimType"] == "uniqueness"
    assert c.post("/scim/v2/Users", headers=H, json={"userName": "not an email"}).status_code == 400
    new_user(c, "sam@corp.com")
    got = c.get('/scim/v2/Users?filter=userName eq "sam@corp.com"', headers=H).json()
    assert got["totalResults"] == 1 and got["Resources"][0]["userName"] == "sam@corp.com"
    assert c.get("/scim/v2/Users?filter=userName co \"x\"", headers=H).json()["scimType"] == "invalidFilter"
    page = c.get("/scim/v2/Users?startIndex=2&count=1", headers=H).json()
    assert page["totalResults"] == 2 and page["itemsPerPage"] == 1 and page["startIndex"] == 2
    assert c.get("/scim/v2/Users/nope", headers=H).status_code == 404


def test_deactivation_ends_access_in_one_request_and_blocks_the_next_sign_in():
    c, idp, ac = stack()
    u = new_user(c)
    asyncio_run(ac.groups.add_member(asyncio_run(ac.groups.create("Ops", ["developer"], "t")).id, "rae@corp.com"))
    token = sign_in(c, idp).headers["location"].split("token=")[1]
    me = {"authorization": f"Bearer {token}"}
    assert c.get("/v1/me", headers=me).status_code == 200
    # Azure sends the boolean as a string, with a capitalised operation
    r = c.patch(f"/scim/v2/Users/{u['id']}", headers=H, json={"schemas": [PATCH], "Operations": [{"op": "Replace", "path": "active", "value": "False"}]})
    assert r.status_code == 200 and r.json()["active"] is False
    assert c.get("/v1/me", headers=me).status_code == 401  # the session ended with that one request
    denied = sign_in(c, idp)
    assert denied.headers["location"].startswith("/sso?error=")
    audit = c.get("/v1/audit?limit=30", headers=ADMIN).json()["entries"]
    assert any(e["action"] == "scim.user.update" and e["detail"]["sessionsRevoked"] == 1 for e in audit)
    c.patch(f"/scim/v2/Users/{u['id']}", headers=H, json={"schemas": [PATCH], "Operations": [{"op": "replace", "value": {"active": True}}]})
    assert sign_in(c, idp).headers["location"].startswith("/sso#token=")  # reactivated


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


def test_delete_removes_the_person_from_groups_and_ends_sessions():
    c, idp, ac = stack()
    u = new_user(c)
    g = c.post("/scim/v2/Groups", headers=H, json={"displayName": "Support", "members": [{"value": u["id"]}]}).json()
    assert [m["value"] for m in g["members"]] == [u["id"]]
    asyncio_run(ac.groups.update(g["id"], roles=["developer"]))
    token = sign_in(c, idp).headers["location"].split("token=")[1]
    assert c.delete(f"/scim/v2/Users/{u['id']}", headers=H).status_code == 204
    assert c.get("/v1/me", headers={"authorization": f"Bearer {token}"}).status_code == 401
    assert c.get(f"/scim/v2/Groups/{g['id']}", headers=H).json()["members"] == []
    assert c.get(f"/scim/v2/Users/{u['id']}", headers=H).status_code == 404


def test_put_replaces_and_a_rename_to_an_existing_name_is_refused():
    c, _, _ = stack()
    a, b = new_user(c, "a@corp.com"), new_user(c, "b@corp.com")
    r = c.put(f"/scim/v2/Users/{a['id']}", headers=H, json={"userName": "a2@corp.com", "displayName": "A Two", "active": True})
    assert r.json()["userName"] == "a2@corp.com" and r.json()["displayName"] == "A Two"
    assert c.put(f"/scim/v2/Users/{b['id']}", headers=H, json={"userName": "a2@corp.com"}).json()["scimType"] == "uniqueness"


def test_group_membership_patch_add_remove_replace_and_no_roles_through_scim():
    c, _, ac = stack()
    u1, u2 = new_user(c, "a@corp.com"), new_user(c, "b@corp.com")
    g = c.post("/scim/v2/Groups", headers=H, json={"displayName": "Team", "roles": ["admin"]}).json()
    assert asyncio_run(ac.groups.repo.get(g["id"])).roles == []  # a provisioning token can never grant a role
    patch = lambda ops: c.patch(f"/scim/v2/Groups/{g['id']}", headers=H, json={"schemas": [PATCH], "Operations": ops})  # noqa: E731
    r = patch([{"op": "add", "path": "members", "value": [{"value": u1["id"]}, {"value": u2["id"]}]}])
    assert {m["value"] for m in r.json()["members"]} == {u1["id"], u2["id"]}
    r = patch([{"op": "remove", "path": f'members[value eq "{u1["id"]}"]'}])
    assert [m["value"] for m in r.json()["members"]] == [u2["id"]]
    r = patch([{"op": "replace", "path": "members", "value": [{"value": u1["id"]}]}])
    assert [m["value"] for m in r.json()["members"]] == [u1["id"]]
    assert patch([{"op": "add", "path": "members", "value": [{"value": "ghost"}]}]).status_code == 400
    assert patch([{"op": "replace", "path": "displayName", "value": "New"}]).json()["scimType"] == "mutability"
    assert c.patch(f"/scim/v2/Groups/{g['id']}", headers=H, json={"Operations": []}).status_code == 400
    refs = c.get(f"/scim/v2/Users/{u1['id']}", headers=H).json()["groups"]
    assert refs == [{"value": g["id"], "display": "Team"}]
    assert c.post("/scim/v2/Groups", headers=H, json={"displayName": "Team"}).status_code == 409
    assert c.delete(f"/scim/v2/Groups/{g['id']}", headers=H).status_code == 204 and c.get(f"/scim/v2/Groups/{g['id']}", headers=H).status_code == 404


def test_provisioned_membership_gives_the_group_roles_at_sign_in():
    c, idp, ac = stack()
    u = new_user(c)
    g = c.post("/scim/v2/Groups", headers=H, json={"displayName": "Reviewers", "members": [{"value": u["id"]}]}).json()
    assert sign_in(c, idp, groups=[]).headers["location"].startswith("/sso?error=")  # in a group with no role: no access yet
    asyncio_run(ac.groups.update(g["id"], roles=["reviewer"]))
    t = sign_in(c, idp, groups=[]).headers["location"].split("token=")[1]
    assert c.get("/v1/me", headers={"authorization": f"Bearer {t}"}).json()["role"] == "reviewer"


def test_require_provisioned_refuses_people_the_provider_never_sent():
    c, idp, ac = stack()
    ac.scim.require_provisioned = True
    asyncio_run(ac.groups.add_member(asyncio_run(ac.groups.create("Ops", ["viewer"], "t")).id, "rae@corp.com"))
    assert sign_in(c, idp).headers["location"].startswith("/sso?error=")
    new_user(c)
    assert sign_in(c, idp).headers["location"].startswith("/sso#token=")


@pytest.mark.parametrize("body", [{}, {"schemas": [PATCH]}, {"schemas": [PATCH], "Operations": [{"nope": 1}]}, {"schemas": [PATCH], "Operations": [{"op": "remove", "path": "active"}]},
                                  {"schemas": [PATCH], "Operations": [{"op": "replace", "path": "active", "value": "maybe"}]}])
def test_bad_patches_are_refused_with_a_scim_error(body):
    c, _, _ = stack()
    u = new_user(c)
    r = c.patch(f"/scim/v2/Users/{u['id']}", headers=H, json=body)
    assert r.status_code == 400 and r.json()["status"] == "400" and r.json()["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]


async def test_scim_users_survive_the_database(engine):
    from northcx.db import PgScimUsers
    s = ScimService(PgScimUsers(engine), GroupService(), None)
    u = await s.create_user({"userName": "rae@corp.com", "displayName": "Rae"}, "t")
    other = ScimService(PgScimUsers(engine), GroupService(), None)
    assert await other.may_sign_in("rae@corp.com") and (await other.users.get(u.id)).display_name == "Rae"
    await other.patch_user(u.id, {"schemas": [PATCH], "Operations": [{"op": "replace", "path": "active", "value": False}]})
    assert not await s.may_sign_in("rae@corp.com") and await s.may_sign_in("stranger@corp.com")
    assert [x.user_name for x in (await s.list_users('userName eq "RAE@corp.com"', 1, 10))[0]] == ["rae@corp.com"]
