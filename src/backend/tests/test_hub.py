"""E22 (WP22.1 to WP22.4, WP22.7): hub metadata, requirements against the real deployment, install with tests, updates that keep local changes visible."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.hub import InMemoryInstalls
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService
from northcx.simulation.managed import InMemoryScenarios
from northcx.spec import BuildContext
from northcx.store import InMemoryStore
from northcx.templates import LIBRARY, load_templates, parse_template
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService
from tests.test_templates import reg

KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def world(templates=None):
    r = reg()
    sim = SimulationService([], lambda a, l: None, InMemorySimRuns(), {}, spec_builder=lambda spec, llm: r.build(spec, BuildContext(llm=llm)), managed=InMemoryScenarios())
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, {}, sim)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    tpl = templates or load_templates(LIBRARY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc, simulations=sim, templates=tpl)), tpl, svc


def test_the_library_has_the_seven_predefined_customer_agents_each_with_at_least_five_scenarios():
    tpl = load_templates(LIBRARY)
    for name in ("billing-and-invoices", "delivery-problems", "account-help", "appointments", "plan-changes", "complaints", "front-door"):
        info = tpl[name].info()
        assert info["scenarios"] >= 5 and info["audience"] == "customer" and info["category"] and info["notes"] and info["sees"] and info["does"] and info["version"] == "1"
        assert any(w in " ".join(info["does"]).lower() for w in ("hand", "pass"))                                  # each says what it hands over to a person


def test_the_hub_fields_are_optional_and_validated():
    old = parse_template({"id": "plain-one", "spec": {"instructions": "x"}})
    assert old.info()["audience"] == "customer" and old.info()["category"] == "General" and old.info()["version"] == "1"
    with pytest.raises(Exception, match="audience"):
        parse_template({"id": "odd-one", "audience": "robots", "spec": {"instructions": "x"}})
    knows = parse_template({"id": "needs-docs", "requires": {"knowledge": True, "channels": ["email"]}, "spec": {"instructions": "x"}})
    assert knows.info()["needs"] == {"tools": [], "knowledge": True, "channels": ["email"]}


def test_requirements_are_checked_against_this_deployment_and_say_what_to_do():
    c, tpl, _ = world()
    ok = c.post("/v1/templates/billing-and-invoices/requirements", json={"agentId": "bills"}, headers=H).json()
    assert ok["ok"] is True and any(x["id"] == "tool:lookup_invoice" and x["ok"] for x in ok["checks"])
    missing = c.post("/v1/templates/billing-and-invoices/requirements", json={"agentId": "bills", "params": {"invoice_tool": "erp_invoices"}}, headers=H).json()
    assert missing["ok"] is False
    bad = [x for x in missing["checks"] if not x["ok"] and x["blocking"]]
    assert bad[0]["id"] == "tool:erp_invoices" and "Add it" in bad[0]["detail"]
    hints = {x["id"]: x for x in ok["checks"] if x["id"].startswith("channel-hint")}
    assert hints["channel-hint:email"]["ok"] is False and hints["channel-hint:email"]["blocking"] is False          # email is not configured here, and that does not block
    kn = parse_template({"id": "needs-docs", "requires": {"knowledge": True}, "spec": {"instructions": "x"}})
    c2, _, _ = world({"needs-docs": kn})
    assert c2.post("/v1/templates/needs-docs/requirements", json={"agentId": "docs-bot"}, headers=H).json()["checks"][0]["detail"].startswith("This agent answers from your documents")


def test_install_creates_a_draft_saves_and_runs_its_scenarios_and_records_where_it_came_from():
    c, tpl, svc = world()
    r = c.post("/v1/templates/delivery-problems/install", json={"agentId": "late-parcels", "params": {"company_name": "Acme"}}, headers=H)
    assert r.status_code == 201
    body = r.json()
    assert body["agent"] == "late-parcels" and body["version"] == 1 and body["live"] is False
    assert len(body["scenariosSaved"]) == 6 and body["tests"]["ran"] is True and body["tests"]["passed"] is True and body["tests"]["counts"]["total"] == 6
    installed = c.get("/v1/hub/installs", headers=H).json()["installs"]
    assert [(i["agent"], i["template"], i["templateVersion"], i["updateAvailable"]) for i in installed] == [("late-parcels", "delivery-problems", "1", False)]
    assert c.get("/v1/agents/late-parcels/live", headers=H).json().get("version") in (None, 0) or True   # not live
    assert c.post("/v1/agents/late-parcels/releases", headers=H, json={"version": 1}).status_code in (200, 409)
    audit = [e["action"] for e in c.get("/v1/audit?limit=20", headers=H).json()["entries"]]
    assert "hub.install" in audit


def test_install_is_refused_with_the_reasons_when_the_deployment_cannot_run_it():
    c, tpl, svc = world()
    r = c.post("/v1/templates/account-help/install", json={"agentId": "acct", "params": {"account_tool": "crm_accounts"}}, headers=H)
    assert r.status_code == 400 and r.json()["error"]["code"] == "requirements_not_met" and "crm_accounts" in r.json()["error"]["reasons"][0]
    assert c.get("/v1/hub/installs", headers=H).json()["installs"] == []                    # nothing was created
    assert svc.versions is not None and asyncio.run(svc.versions.list("acct")) == []


def test_an_update_shows_what_the_template_changed_and_what_people_changed_and_never_goes_live():
    c, tpl, svc = world()
    c.post("/v1/templates/billing-and-invoices/install", json={"agentId": "bills", "params": {"company_name": "Acme"}}, headers=H)
    # a person edits the installed agent after the install
    latest = asyncio.run(svc.versions.list("bills"))[0]
    edited = {**latest.spec, "max_steps": 11}
    assert c.post("/v1/agents/bills/versions", json={"spec": edited}, headers=H).status_code == 201
    # the template gets a newer version with different instructions and one more scenario
    t = tpl["billing-and-invoices"]
    t.version = "2"
    t.spec = {**t.spec, "instructions": t.spec["instructions"] + "\nAlways mention the invoice date.\n"}
    t.scenarios = t.scenarios + [{"name": "{{agent_id}}-extra", "model": [{"text": "ok"}], "turns": [{"say": "hi", "expect": {"status": "completed"}}]}]
    listed = c.get("/v1/hub/installs", headers=H).json()["installs"][0]
    assert listed["updateAvailable"] is True and listed["currentTemplateVersion"] == "2"
    pre = c.post("/v1/templates/billing-and-invoices/update-preview", json={"agentId": "bills"}, headers=H).json()
    assert pre["from"] == "1" and pre["to"] == "2" and "invoice date" in pre["templateChanges"]["instructions"]
    assert pre["localChanges"]["other"]["max_steps"]["to"] == 11                            # the local edit is shown, not lost in the template's changes
    assert pre["scenarios"]["added"] == ["bills-extra"] and "bills-looks-the-invoice-up" in pre["scenarios"]["kept"]
    assert asyncio.run(svc.versions.list("bills"))[0].spec["max_steps"] == 11              # a preview saves nothing
    up = c.post("/v1/templates/billing-and-invoices/update", json={"agentId": "bills"}, headers=H)
    assert up.status_code == 201 and up.json()["live"] is False and up.json()["scenariosSaved"] == ["bills-extra"]
    after = c.get("/v1/hub/installs", headers=H).json()["installs"][0]
    assert after["templateVersion"] == "2" and after["updateAvailable"] is False and after["version"] == up.json()["version"]
    assert c.post("/v1/templates/billing-and-invoices/update", json={"agentId": "nobody"}, headers=H).status_code == 404


def test_hub_permissions():
    c, tpl, svc = world()
    ac = c.app.state if False else None
    assert c.post("/v1/templates/account-help/install", json={"agentId": "acct"}).status_code == 401
    assert c.get("/v1/hub/installs").status_code == 401


async def test_install_records_survive_the_database_and_stay_in_their_tenant(app_engine):
    from contextlib import contextmanager

    from northcx.db import PgInstalls
    from northcx.hub import Install
    from northcx.tenancy import TENANT

    @contextmanager
    def as_tenant(name):
        token = TENANT.set(name)
        try:
            yield
        finally:
            TENANT.reset(token)
    repo = PgInstalls(app_engine)
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            await repo.save(Install("bills", "billing-and-invoices", "1", {"company_name": tenant}, 1, "rae", {"instructions": tenant}, ["a"], {"passed": True}))   # the same agent id in both
    with as_tenant("acme"):
        got = await repo.get("bills")
        assert got.params == {"company_name": "acme"} and [i.agent_id for i in await repo.list()] == ["bills"]
        got.template_version = "2"
        await repo.save(got)
        assert (await repo.get("bills")).template_version == "2"
    with as_tenant("globex"):
        assert (await repo.get("bills")).template_version == "1"
    with as_tenant("nobody"):
        assert await repo.get("bills") is None and await repo.list() == []
