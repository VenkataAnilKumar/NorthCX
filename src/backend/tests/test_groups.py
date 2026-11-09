"""WP3.2: groups with roles; effective permissions are the union; identity-provider groups map onto them."""
import pytest

from northcx.access import AccessControl, Identity, ROLES
from northcx.groups import GroupError, GroupService
from test_sso import KEY, build, sign_in

ADMIN = {"authorization": f"Bearer {KEY}"}


async def test_effective_roles_are_the_union_over_every_group_the_person_is_in():
    s = GroupService()
    support = await s.create("Support leads", ["reviewer"], "t", external_name="idp-support")
    rel = await s.create("Release", ["release_manager"], "t")
    await s.create("Everyone", ["viewer"], "t", external_name="idp-all")
    await s.add_member(rel.id, "Rae@Corp.com")
    roles, names = await s.effective_roles(["rae@corp.com", "u-1"], ["idp-support", "idp-all", "other"])
    assert roles == ["release_manager", "reviewer", "viewer"] and sorted(names) == ["Everyone", "Release", "Support leads"]
    assert await s.effective_roles(["nobody"], []) == ([], [])
    await s.remove_member(rel.id, "rae@corp.com")
    assert (await s.effective_roles(["rae@corp.com"], []))[0] == []
    assert support.external_name == "idp-support"


@pytest.mark.parametrize("call,why", [
    (lambda s: s.create("bad name!", ["viewer"], "t"), "Group names"),
    (lambda s: s.create("g", ["channel"], "t"), "roles must be"),
    (lambda s: s.create("g", ["viewer", "viewer"], "t"), "roles must be"),
    (lambda s: s.create("dup", ["viewer"], "t"), "already exists"),
    (lambda s: s.create("g2", ["viewer"], "t", external_name="x"), "already maps"),
])
async def test_group_rules(call, why):
    s = GroupService()
    await s.create("dup", ["viewer"], "t", external_name="x")
    with pytest.raises(GroupError, match=why):
        await call(s)


def test_an_identity_with_extra_roles_gets_the_union_of_permissions():
    a = Identity("n", "viewer", "k", extra_roles=("release_manager",))
    assert a.can("releases:publish") and a.can("traces:read") and not a.can("keys:manage")
    assert Identity("n", "viewer", "k").permissions == ROLES["viewer"]


async def test_a_session_key_keeps_its_extra_roles_but_not_a_forbidden_one():
    ac = AccessControl(bootstrap_key=KEY)
    key, secret = await ac.issue_session("rae", "reviewer", 4, ["viewer", "release_manager", "reviewer"])
    who = await ac.authenticate(secret)
    assert who.role == "reviewer" and who.extra_roles == ("viewer", "release_manager") and who.can("releases:publish")
    with pytest.raises(ValueError):
        await ac.issue_session("rae", "reviewer", 4, ["channel"])


def test_the_groups_api_manages_groups_and_needs_the_key_permission():
    c, idp, ac = build()
    ac.groups = GroupService()
    dev = c.post("/v1/keys", headers=ADMIN, json={"name": "dev", "role": "developer"}).json()["key"]
    assert c.get("/v1/groups", headers={"authorization": f"Bearer {dev}"}).status_code == 403
    g = c.post("/v1/groups", headers=ADMIN, json={"name": "Support", "roles": ["reviewer"], "externalName": "cx-support"})
    assert g.status_code == 201
    gid = g.json()["id"]
    assert c.post("/v1/groups", headers=ADMIN, json={"name": "Support", "roles": []}).status_code == 400
    assert c.put(f"/v1/groups/{gid}", headers=ADMIN, json={"roles": ["reviewer", "auditor"], "externalName": ""}).json()["externalName"] is None
    assert c.post(f"/v1/groups/{gid}/members", headers=ADMIN, json={"subject": "Rae@Corp.com"}).json()["members"] == ["rae@corp.com"]
    assert c.post(f"/v1/groups/{gid}/members", headers=ADMIN, json={"subject": "has space"}).status_code == 400
    assert c.delete(f"/v1/groups/{gid}/members/rae@corp.com", headers=ADMIN).json()["members"] == []
    assert c.get("/v1/groups", headers=ADMIN).json()["groups"][0]["roles"] == ["reviewer", "auditor"]
    assert c.delete(f"/v1/groups/{gid}", headers=ADMIN).json() == {"deleted": True} and c.delete(f"/v1/groups/{gid}", headers=ADMIN).status_code == 404
    audit = [e["action"] for e in c.get("/v1/audit?limit=30", headers=ADMIN).json()["entries"]]
    assert {"group.create", "group.update", "group.member.add", "group.member.remove", "group.delete"} <= set(audit)


def test_sign_in_unions_the_role_map_and_the_groups_and_refuses_a_person_with_none():
    c, idp, ac = build(use_groups=True, role_map={"cx-readers": "viewer"})
    ac.groups = s = GroupService()
    import asyncio
    asyncio.run(s.create("Releasers", ["release_manager"], "t", external_name="cx-release"))
    t = sign_in(c, idp, groups=["cx-readers", "cx-release"]).headers["location"].split("token=")[1]
    me = c.get("/v1/me", headers={"authorization": f"Bearer {t}"}).json()
    assert me["roles"] == ["release_manager", "viewer"] and "releases:publish" in me["permissions"] and me["role"] == "release_manager"
    r = sign_in(c, idp, groups=["unknown"])
    assert r.headers["location"].startswith("/sso?error=")
    # the group alone is enough, with no role map entry at all
    c2, idp2, ac2 = build(use_groups=True, role_map={})
    ac2.groups = s2 = GroupService()
    asyncio.run(s2.add_member((asyncio.run(s2.create("Ops", ["auditor"], "t"))).id, "rae@corp.com"))
    t2 = sign_in(c2, idp2, groups=[]).headers["location"].split("token=")[1]
    assert c2.get("/v1/me", headers={"authorization": f"Bearer {t2}"}).json()["role"] == "auditor"


def test_without_use_groups_nothing_changes():
    c, idp, ac = build()
    ac.groups = s = GroupService()
    import asyncio
    asyncio.run(s.create("Releasers", ["release_manager"], "t", external_name="cx-editors"))
    t = sign_in(c, idp).headers["location"].split("token=")[1]
    assert c.get("/v1/me", headers={"authorization": f"Bearer {t}"}).json()["roles"] == ["developer"]


async def test_groups_and_session_roles_survive_the_database(engine):
    from northcx.db import PgGroups, PgKeys
    s = GroupService(PgGroups(engine))
    g = await s.create("Ops", ["auditor", "viewer"], "t", external_name="idp-ops")
    await s.add_member(g.id, "rae@corp.com")
    other = GroupService(PgGroups(engine))
    assert (await other.effective_roles(["rae@corp.com"], []))[0] == ["auditor", "viewer"]
    assert (await other.effective_roles([], ["idp-ops"]))[1] == ["Ops"]
    await other.update(g.id, roles=["viewer"])
    assert (await s.effective_roles(["rae@corp.com"], []))[0] == ["viewer"]
    assert await s.delete(g.id) and not await s.delete(g.id)
    ac = AccessControl(keys=PgKeys(engine))
    _, secret = await ac.issue_session("rae", "reviewer", 4, ["viewer"])
    assert (await AccessControl(keys=PgKeys(engine)).authenticate(secret)).extra_roles == ("viewer",)
