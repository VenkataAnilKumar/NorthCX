"""E16: organization policies. Proof before proposing, a second person to approve, locked and applied to every customer agent, versioned."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.org_policies import OrgPolicyError, OrgPolicyService, prove
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
BOOT = {"authorization": f"Bearer {KEY}"}
REFUND_LIMIT = {"name": "Refund ceiling", "policy": "tool_limit", "config": {"tool": "issue_refund", "field": "amount", "max": 50},
                "cases": [{"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 40}}, "expected": "allowed"},
                          {"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 60}}, "expected": "blocked"}]}


def world(script=None):
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM(script or []), InMemoryStore(), TraceStore())
    rt.org_policies = OrgPolicyService()
    ac = AccessControl(bootstrap_key=KEY)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    key = lambda name, role="release_manager": {"authorization": "Bearer " + loop.run_until_complete(ac.issue(name, role, "t"))[1]}  # noqa: E731
    return c, rt, key, loop


async def test_a_policy_is_proven_with_its_own_cases():
    ok = await prove(REFUND_LIMIT["policy"], REFUND_LIMIT["config"], REFUND_LIMIT["cases"])
    assert ok["passed"] and [r["got"] for r in ok["results"]] == ["allowed", "blocked"]
    wrong = await prove("tool_limit", REFUND_LIMIT["config"], [{"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 60}}, "expected": "allowed"},
                                                                 {"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 10}}, "expected": "blocked"}])
    assert not wrong["passed"] and len(wrong["problems"]) == 2
    only_allow = await prove("forbidden_phrases", {"phrases": ["guarantee"]}, [{"on": "reply", "input": "hello", "expected": "allowed"}])
    assert not only_allow["passed"] and "one that is blocked" in only_allow["problems"][0]
    broken = await prove("forbidden_phrases", {"phrases": ["guarantee"]}, [{"on": "nope"}])
    assert not broken["passed"] and broken["results"][0]["ok"] is False
    with pytest.raises(OrgPolicyError, match="Unknown policy"):
        await prove("nonsense", {}, [])
    with pytest.raises(OrgPolicyError, match="Invalid setting"):
        await prove("tool_limit", {}, [])


def test_it_cannot_be_proposed_until_its_cases_pass_and_needs_a_second_person_to_approve():
    c, rt, key, loop = world()
    ann, ben = key("ann"), key("ben")
    bad = c.post("/v1/org-policies", headers=ann, json={**REFUND_LIMIT, "name": "Broken ceiling", "cases": REFUND_LIMIT["cases"][:1]})
    assert bad.status_code == 201 and bad.json()["proof"]["passed"] is False
    assert c.post(f"/v1/org-policies/{bad.json()['id']}/propose", headers=ann).status_code == 409           # no block case: cannot be proposed
    p = c.post("/v1/org-policies", headers=ann, json=REFUND_LIMIT).json()
    assert p["status"] == "draft" and p["proof"]["passed"] and p["locked"] is False
    assert c.post(f"/v1/org-policies/{p['id']}/approve", headers=ann, json={}).status_code == 409           # not proposed yet
    assert c.post(f"/v1/org-policies/{p['id']}/propose", headers=ann).json()["status"] == "proposed"
    me = c.post(f"/v1/org-policies/{p['id']}/approve", headers=ann, json={})
    assert me.status_code == 403 and "second person" in me.json()["error"]["message"]
    done = c.post(f"/v1/org-policies/{p['id']}/approve", headers=ben, json={"note": "agreed"})
    assert done.status_code == 200 and done.json()["status"] == "active" and done.json()["locked"] is True and done.json()["decidedBy"] != done.json()["proposedBy"]
    assert c.post(f"/v1/org-policies/{p['id']}/approve", headers=ben, json={}).status_code == 409           # decided once
    audit = [e["action"] for e in c.get("/v1/audit?limit=30", headers=BOOT).json()["entries"]]
    assert {"org_policy.create", "org_policy.propose", "org_policy.approve"} <= set(audit)
    dev = key("dev", "developer")
    assert c.post(f"/v1/org-policies/{p['id']}/retire", headers=dev, json={}).status_code == 403           # a developer cannot take a locked policy out of force


def test_an_active_policy_applies_to_every_customer_agent_whatever_its_own_definition_says():
    script = [tool_call("issue_refund", {"order_id": "1042", "amount": 80}, "t1"), text("done")]
    c, rt, key, loop = world(script)
    ann, ben = key("ann"), key("ben")
    p = c.post("/v1/org-policies", headers=ann, json=REFUND_LIMIT).json()
    c.post(f"/v1/org-policies/{p['id']}/propose", headers=ann)
    c.post(f"/v1/org-policies/{p['id']}/approve", headers=ben, json={})
    agent = support_agent()                                    # this agent's own definition has no such limit
    res = loop.run_until_complete(rt.run(agent, "s1", "refund 80 on order 1042"))
    guard = [e for e in res.trace.events if e.type == "guardrail"]
    assert guard and guard[0].data["guardrail"] == "org:Refund ceiling" and "above the limit" in guard[0].data["reason"]
    assert not any(e.type == "tool_result" and e.data["name"] == "issue_refund" for e in res.trace.events)   # the refund never ran


def test_a_policy_can_be_limited_to_named_agents_and_never_touches_staff_agents():
    c, rt, key, loop = world()
    ann, ben = key("ann"), key("ben")
    p = c.post("/v1/org-policies", headers=ann, json={**REFUND_LIMIT, "appliesTo": ["billing"]}).json()
    c.post(f"/v1/org-policies/{p['id']}/propose", headers=ann)
    c.post(f"/v1/org-policies/{p['id']}/approve", headers=ben, json={})
    assert loop.run_until_complete(rt.org_policies.guardrails_for("support")) == []              # not covered
    assert [g.name for g in loop.run_until_complete(rt.org_policies.guardrails_for("billing"))] == ["org:Refund ceiling"]


def test_changing_an_active_policy_makes_a_new_version_and_the_old_one_stays_in_force_until_approved():
    c, rt, key, loop = world()
    ann, ben = key("ann"), key("ben")
    p = c.post("/v1/org-policies", headers=ann, json=REFUND_LIMIT).json()
    c.post(f"/v1/org-policies/{p['id']}/propose", headers=ann)
    c.post(f"/v1/org-policies/{p['id']}/approve", headers=ben, json={})
    v2 = c.put(f"/v1/org-policies/{p['id']}", headers=ann, json={"config": {"tool": "issue_refund", "field": "amount", "max": 100},
                                                                 "cases": [{"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 90}}, "expected": "allowed"},
                                                                           {"on": "tool", "input": {"tool": "issue_refund", "input": {"amount": 120}}, "expected": "blocked"}]}).json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    listed = c.get("/v1/org-policies", headers=ann).json()["policies"][0]
    assert [(v["version"], v["status"]) for v in listed["versions"]] == [(2, "draft"), (1, "active")]
    rt.org_policies._invalidate()
    assert len(loop.run_until_complete(rt.org_policies.guardrails_for("support"))) == 1          # version 1 is still the one in force
    assert c.put(f"/v1/org-policies/{p['id']}", headers=ann, json={"config": {}}).status_code == 400      # a bad setting is refused and the draft is untouched
    c.post(f"/v1/org-policies/{p['id']}/propose", headers=ann)
    c.post(f"/v1/org-policies/{p['id']}/approve", headers=ben, json={})
    after = c.get("/v1/org-policies", headers=ann).json()["policies"][0]
    assert [(v["version"], v["status"]) for v in after["versions"]] == [(2, "active"), (1, "superseded")]


def test_retiring_is_deliberate_and_takes_the_policy_out_of_force():
    c, rt, key, loop = world()
    ann, ben, rel = key("ann"), key("ben"), key("rel")
    p = c.post("/v1/org-policies", headers=ann, json=REFUND_LIMIT).json()
    c.post(f"/v1/org-policies/{p['id']}/propose", headers=ann)
    c.post(f"/v1/org-policies/{p['id']}/approve", headers=ben, json={})
    assert c.post(f"/v1/org-policies/{p['id']}/retire", headers=rel, json={"note": "replaced by the new refund rules"}).json()["status"] == "retired"
    rt.org_policies._invalidate()
    assert loop.run_until_complete(rt.org_policies.guardrails_for("support")) == []
    assert c.post(f"/v1/org-policies/{p['id']}/retire", headers=rel, json={}).status_code == 404       # nothing active any more


def test_names_are_unique_while_in_use_and_bad_settings_are_refused():
    c, rt, key, loop = world()
    ann = key("ann")
    assert c.post("/v1/org-policies", headers=ann, json=REFUND_LIMIT).status_code == 201
    assert c.post("/v1/org-policies", headers=ann, json=REFUND_LIMIT).status_code == 409
    assert c.post("/v1/org-policies", headers=ann, json={**REFUND_LIMIT, "name": "x"}).status_code == 400
    assert c.post("/v1/org-policies", headers=ann, json={**REFUND_LIMIT, "name": "Other", "policy": "nonsense"}).status_code == 400
    assert c.post("/v1/org-policies", headers=ann, json={**REFUND_LIMIT, "name": "Other", "config": {}}).status_code == 400
    pr = c.post("/v1/org-policies/prove", headers=ann, json={"policy": REFUND_LIMIT["policy"], "config": REFUND_LIMIT["config"], "cases": REFUND_LIMIT["cases"]}).json()
    assert pr["passed"] and len(c.get("/v1/org-policies", headers=ann).json()["policies"]) == 1          # proving saves nothing
    assert c.get("/v1/org-policies").status_code == 401


async def test_policies_survive_the_database_and_stay_in_their_tenant(app_engine):
    from contextlib import contextmanager

    from northcx.db import PgOrgPolicies
    from northcx.tenancy import TENANT

    @contextmanager
    def as_tenant(name):
        token = TENANT.set(name)
        try:
            yield
        finally:
            TENANT.reset(token)
    s = OrgPolicyService(PgOrgPolicies(app_engine))
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            p = await s.create("Refund ceiling", REFUND_LIMIT["policy"], REFUND_LIMIT["config"], REFUND_LIMIT["cases"], None, "key:1")    # the same name in both tenants
            await s.propose(p.id, "key:1")
            await s.decide(p.id, True, "key:2", None)
    with as_tenant("acme"):
        assert [p.name for p in await s.repo.active()] == ["Refund ceiling"] and len(await s.guardrails_for("support")) == 1
        v2 = await s.revise((await s.repo.list())[0].id, {"tool": "issue_refund", "field": "amount", "max": 10}, REFUND_LIMIT["cases"], None, "key:1")
        assert v2.version == 2 and [x.status for x in await s.repo.versions(v2.id)] == ["draft", "active"]
    with as_tenant("globex"):
        assert [v.version for v in await s.repo.versions((await s.repo.list())[0].id)] == [1]
    with as_tenant("nobody"):
        assert await s.repo.list() == [] and await s.repo.active() == []
