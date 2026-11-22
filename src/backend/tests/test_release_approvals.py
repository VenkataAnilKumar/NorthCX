"""WP3.5: the two-person rule for releases. A request, a different approver, the gate at approval time, and no way around it."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.release_requests import ApprovalError, ReleaseApprovals, principal
from northcx.rollout import InMemoryRollouts, RolloutService
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions
from tests.test_versions import Env

KEY = "boot" * 10
BOOT = {"authorization": f"Bearer {KEY}"}


def world(required=("production",)):
    e = Env(InMemoryVersions(), InMemoryReleases())
    e.svc.approvals = ReleaseApprovals(set(required))
    ac = AccessControl(bootstrap_key=KEY)
    traces = TraceStore()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), traces)
    c = TestClient(create_app(rt, traces, e.live, access=ac, simulations=e.sim, releases=e.svc, rollouts=RolloutService(InMemoryRollouts(), e.svc)))
    loop = asyncio.new_event_loop()
    def key(name, role="release_manager"):
        return {"authorization": "Bearer " + loop.run_until_complete(ac.issue(name, role, "root"))[1]}
    c.post("/v1/agents/support/versions", headers=BOOT, json={"fromBaseline": True})
    c.post("/v1/simulations/runs", headers=BOOT, json={"agent": "support", "version": 1, "mode": "scripted", "skipJudge": True})
    return c, e, key


def live(c, env="production"):
    return c.get("/v1/agents/support/live", headers=BOOT, params={"environment": env}).json()


def test_a_publish_in_a_held_environment_is_a_request_until_someone_else_approves():
    c, e, key = world()
    ann, ben = key("ann"), key("ben")
    r = c.post("/v1/agents/support/releases", headers=ann, json={"version": 1, "note": "go"})
    assert r.status_code == 202 and r.json()["status"] == "pending" and "second person" in r.json()["message"]
    rid = r.json()["id"]
    assert live(c).get("version") in (None, 0) or live(c).get("toBaseline", True)  # nothing was released
    assert [x["id"] for x in c.get("/v1/release-requests?status=pending", headers=ben).json()["requests"]] == [rid]
    me = c.post(f"/v1/release-requests/{rid}/approve", headers=ann, json={})
    assert me.status_code == 403 and "second person" in me.json()["error"]["message"]  # the person who asked cannot approve
    ok = c.post(f"/v1/release-requests/{rid}/approve", headers=ben, json={"note": "looks right"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["release"]["version"] == 1 and ok.json()["release"]["by"].startswith("ben")
    assert c.post(f"/v1/release-requests/{rid}/approve", headers=ben, json={}).status_code == 409  # decided once
    audit = [x["action"] for x in c.get("/v1/audit?limit=40", headers=BOOT).json()["entries"]]
    assert {"release.request", "release.approve"} <= set(audit)


def test_other_environments_release_directly_and_rollback_is_never_held_up():
    c, e, key = world(("production",))
    ann = key("ann")
    assert c.post("/v1/agents/support/releases", headers=ann, json={"version": 1, "environment": "staging"}).status_code == 200
    c2, e2, key2 = world(("staging", "production"))
    assert c2.post("/v1/agents/support/releases", headers=key2("ann"), json={"version": 1, "environment": "staging"}).status_code == 202
    # an emergency rollback does not wait for a second person
    c3, e3, key3 = world(())
    ann3 = key3("ann")
    assert c3.post("/v1/agents/support/releases", headers=ann3, json={"version": 1}).status_code == 200
    e3.svc.approvals = ReleaseApprovals({"production"})
    assert c3.post("/v1/agents/support/rollback", headers=ann3, json={}).status_code != 202  # rollback is not a request


def test_reject_cancel_and_duplicates():
    c, e, key = world()
    ann, ben, cat = key("ann"), key("ben"), key("cat", "developer")
    rid = c.post("/v1/agents/support/releases", headers=ann, json={"version": 1}).json()["id"]
    assert c.post("/v1/agents/support/releases", headers=ann, json={"version": 1}).status_code == 409  # already waiting
    assert c.post(f"/v1/release-requests/{rid}/cancel", headers=ben).status_code == 403            # only the requester withdraws
    assert c.post(f"/v1/release-requests/{rid}/approve", headers=cat, json={}).status_code == 403   # a developer cannot approve at all
    rej = c.post(f"/v1/release-requests/{rid}/reject", headers=ben, json={"note": "not yet"})
    assert rej.json()["status"] == "rejected" and rej.json()["decisionNote"] == "not yet"
    rid2 = c.post("/v1/agents/support/releases", headers=ann, json={"version": 1}).json()["id"]
    assert c.post(f"/v1/release-requests/{rid2}/cancel", headers=ann).json()["status"] == "cancelled"
    assert c.post("/v1/release-requests/nope/approve", headers=ben, json={}).status_code == 404


def test_the_gate_is_judged_when_the_second_person_approves():
    c, e, key = world()
    ann, ben = key("ann"), key("ben")
    spec = c.get("/v1/agents/support/versions/1", headers=BOOT).json()["spec"]
    assert c.post("/v1/agents/support/versions", headers=BOOT, json={"spec": {**spec, "max_steps": 9}}).status_code == 201  # version 2 has not been proven
    assert c.post("/v1/agents/support/releases", headers=ann, json={"version": 99}).status_code == 404  # nothing to release: refused at once
    rid = c.post("/v1/agents/support/releases", headers=ann, json={"version": 2}).json()["id"]
    r = c.post(f"/v1/release-requests/{rid}/approve", headers=ben, json={})
    assert r.status_code == 409 and "test" in r.text.lower()  # the release gate said no
    assert [x["status"] for x in c.get("/v1/release-requests", headers=BOOT).json()["requests"]] == ["failed"]


def test_staged_rollouts_cannot_skip_the_second_person():
    c, e, key = world()
    r = c.post("/v1/agents/support/rollouts", headers=key("ann"), json={"version": 1, "percent": 10})
    assert r.status_code == 409 and "second person" in r.json()["error"]["message"]


def test_without_the_rule_nothing_changes():
    c, e, key = world(())
    e.svc.approvals = None
    assert c.post("/v1/agents/support/releases", headers=key("ann"), json={"version": 1}).status_code == 200
    assert c.get("/v1/release-requests", headers=BOOT).json() == {"required": [], "requests": []}
    assert c.post("/v1/release-requests/x/approve", headers=BOOT, json={}).status_code == 501


def test_a_person_is_one_principal_across_sign_in_sessions():
    from northcx.access import Identity
    assert principal(Identity("sso: rae@corp.com", "release_manager", "k1")) == principal(Identity("sso: rae@corp.com", "release_manager", "k2")) == "sso: rae@corp.com"
    assert principal(Identity("ann", "release_manager", "k1")) != principal(Identity("ann", "release_manager", "k2"))


async def test_requests_survive_the_database_and_only_one_decision_wins(engine):
    from northcx.db import PgReleaseRequests
    a, b = ReleaseApprovals({"production"}, PgReleaseRequests(engine)), ReleaseApprovals({"production"}, PgReleaseRequests(engine))
    r = await a.request("support", "publish", "production", 3, "key:1", "n")
    with pytest.raises(ApprovalError):
        await a.request("support", "publish", "production", 3, "key:1", "n")
    results = await asyncio.gather(a.claim(r.id, "key:2", True, None), b.claim(r.id, "key:3", False, None), return_exceptions=True)
    assert sum(isinstance(x, ApprovalError) for x in results) == 1 and sum(not isinstance(x, Exception) for x in results) == 1
    assert (await b.repo.get(r.id)).status in ("approved", "rejected")
    assert [x.id for x in await b.repo.list("pending", None, 10)] == []
