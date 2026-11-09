"""Templates: parameters, validation, scenarios that really pass, missing tools, and the API."""
import asyncio

import pytest
import yaml
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.knowledge import InMemoryKnowledge, knowledge_tool
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, parse_scenario, run_scenarios
from northcx.spec import BuildContext
from northcx.store import InMemoryStore
from northcx.templates import LIBRARY, TemplateError, load_templates, parse_template, render
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

TEMPLATES = load_templates(LIBRARY)


def reg():
    from pydantic import BaseModel

    from northcx.agent import Tool

    class Ref(BaseModel):
        invoice_id: str = ""
        account_id: str = ""
    r = registry()
    r.tool(knowledge_tool(InMemoryKnowledge()))
    r.tool(Tool("lookup_invoice", "Look up an invoice", Ref, lambda i, c: {"status": "paid"}, effect="read"))   # tools the billing and account templates need
    r.tool(Tool("lookup_appointments", "Look up appointments", Ref, lambda i, c: {"next": "Tuesday 10:00"}, effect="read"))
    r.tool(Tool("lookup_plan", "Look up an account's plan", Ref, lambda i, c: {"plan": "Standard"}, effect="read"))
    r.tool(Tool("lookup_account", "Look up an account's status", Ref, lambda i, c: {"status": "active"}, effect="read"))
    from northcx.workspace import WorkspaceService, register_staff_tools     # the staff tools, for the staff assistants
    from northcx.llm import ScriptedLLM
    from northcx.runtime import Runtime
    from northcx.store import InMemoryStore
    from northcx.trace import TraceStore
    register_staff_tools(r, WorkspaceService(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), None, InMemoryKnowledge(), None, None, None))
    return r


def test_the_library_ships_fifteen_templates_with_clear_parameters():
    assert sorted(TEMPLATES) == ["account-help", "appointments", "billing-and-invoices", "complaints", "conversation-analyst", "delivery-problems", "front-door", "handoff-assistant", "human-triage", "knowledge-faq", "order-status", "plan-changes", "policy-guide", "returns-and-refunds", "shift-briefing"]
    for t in TEMPLATES.values():
        info = t.info()
        assert info["title"] and info["intent"] and info["description"] and info["scenarios"] >= 1
        assert all(p["description"] for p in info["parameters"]) and all(not p["required"] for p in info["parameters"])  # every parameter has a default


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
async def test_every_template_renders_a_valid_agent_whose_scenarios_pass(template_id):
    r = reg()
    out = render(TEMPLATES[template_id], "my-agent", {}, r)
    assert out.missing_tools == [] and out.warnings == [] and out.spec.id == "my-agent"
    assert "{{" not in out.spec_yaml and "{{" not in out.scenarios_yaml
    scenarios = [parse_scenario(s, "t") for s in out.scenarios]
    assert all(s.agent == "my-agent" for s in scenarios)
    suite = await run_scenarios(scenarios, lambda aid, llm: r.build(out.spec, BuildContext(llm=llm)))
    assert all(x.passed for x in suite.results), [(x.name, x.failures) for x in suite.results if not x.passed]
    assert yaml.safe_load(out.spec_yaml)["id"] == "my-agent"


def test_parameters_fill_the_text_and_tool_names():
    out = render(TEMPLATES["returns-and-refunds"], "refunds", {"company_name": "Acme", "return_window_days": 14, "order_tool": "orders_lookup", "refund_tool": "orders_refund"}, registry())
    assert "returns assistant for Acme" in out.spec.instructions and "within 14 days" in out.spec.instructions
    assert out.spec.tools == ["orders_lookup", "orders_refund"] and out.missing_tools == ["orders_lookup", "orders_refund"]
    assert "no tool named 'orders_lookup', 'orders_refund'" in out.warnings[-1]
    assert "orders_refund" in out.scenarios_yaml  # scenarios follow the chosen tools


def test_bad_parameters_are_reported_together():
    t = TEMPLATES["order-status"]
    with pytest.raises(TemplateError) as e:
        render(t, "BAD ID", {"colour": "red", "company_name": "x" * 400})
    msg = str(e.value)
    assert "unknown parameter 'colour'" in msg and "company_name" in msg and "agentId" in msg
    for bad in ["two\nlines", "has {{ braces }}"]:
        with pytest.raises(TemplateError, match="one line"):
            render(t, "ok-agent", {"company_name": bad})
    req = parse_template({"id": "needs-one", "parameters": {"name": {"description": "Your name"}}, "spec": {"instructions": "Hi {{name}}"}})
    with pytest.raises(TemplateError, match="'name' is required"):
        render(req, "ok-agent", {})
    assert "Hi Jo" in render(req, "ok-agent", {"name": "Jo"}).spec.instructions


def test_values_are_data_not_code():
    out = render(TEMPLATES["order-status"], "ok-agent", {"company_name": "Acme: {evil: [1, 2]} \"quoted\" # comment"})
    assert yaml.safe_load(out.spec_yaml)["instructions"].count('Acme: {evil: [1, 2]} "quoted" # comment') >= 1  # survives YAML round-trip untouched
    assert out.spec.tools == ["lookup_order"] and len(out.spec.forced_handoff) == 1  # a value cannot add settings


def test_bad_templates_are_refused():
    for bad in [{"id": "X"}, {"id": "ok-id", "colour": 1, "spec": {}}, {"id": "ok-id"}, {"id": "ok-id", "spec": {"instructions": "{{ghost}}"}}, {"id": "ok-id", "parameters": {"Bad": {}}, "spec": {"instructions": "x"}},
                "not a map"]:
        with pytest.raises(TemplateError):
            parse_template(bad)
    broken = parse_template({"id": "ok-id", "spec": {"instructions": "x", "max_steps": 999}})
    with pytest.raises(TemplateError, match="invalid agent spec"):
        render(broken, "ok-agent", {})
    bad_sc = parse_template({"id": "ok-id", "spec": {"instructions": "x"}, "scenarios": [{"name": "s", "turns": []}]})
    with pytest.raises(TemplateError):
        render(bad_sc, "ok-agent", {})


def test_directories_can_add_or_replace_templates(tmp_path):
    (tmp_path / "mine.yaml").write_text(yaml.safe_dump({"id": "order-status", "title": "My order status", "spec": {"instructions": "custom"}}))
    (tmp_path / "other.yaml").write_text(yaml.safe_dump({"id": "my-new-one", "spec": {"instructions": "x"}}))
    merged = load_templates(LIBRARY, tmp_path)
    assert merged["order-status"].title == "My order status" and "my-new-one" in merged and len(merged) == 16
    (tmp_path / "bad.yaml").write_text(": : :\n\t")
    with pytest.raises(TemplateError, match="not valid"):
        load_templates(tmp_path)


# ---- API ----
KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def api(with_releases=True):
    r = reg()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, {}, SimulationService([], lambda a, l: None, InMemorySimRuns(), {})) if with_releases else None
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc, templates=TEMPLATES)), ac, svc


def test_api_lists_describes_and_renders():
    c, ac, _ = api()
    listed = c.get("/v1/templates", headers=H).json()["templates"]
    assert {t["id"] for t in listed} == set(TEMPLATES)
    assert c.get("/v1/templates/order-status", headers=H).json()["requiresTools"] == ["lookup_order"]  # with default parameters
    assert c.get("/v1/templates/nope", headers=H).status_code == 404
    r = c.post("/v1/templates/order-status/render", json={"agentId": "orders-bot", "params": {"company_name": "Acme"}}, headers=H)
    assert r.status_code == 200 and "Acme" in r.json()["specYaml"] and r.json()["missingTools"] == [] and r.json()["scenarios"] == 3
    assert c.post("/v1/templates/order-status/render", json={"agentId": "BAD"}, headers=H).status_code == 400
    assert c.post("/v1/templates/nope/render", json={"agentId": "orders-bot"}, headers=H).status_code == 404
    missing = c.post("/v1/templates/order-status/render", json={"agentId": "orders-bot", "params": {"order_tool": "crm_orders"}}, headers=H).json()
    assert missing["missingTools"] == ["crm_orders"] and "crm_orders" in missing["warnings"][-1]


def test_api_create_version_and_its_limits():
    c, ac, svc = api()
    r = c.post("/v1/templates/knowledge-faq/create-version", json={"agentId": "faq-bot", "params": {"company_name": "Acme"}}, headers=H)
    assert r.status_code == 201 and r.json()["number"] == 1 and r.json()["agentId"] == "faq-bot" and "Acme" in r.json()["specYaml"] and r.json()["scenarios"] == 1
    again = c.post("/v1/templates/knowledge-faq/create-version", json={"agentId": "faq-bot", "params": {"company_name": "Acme"}}, headers=H)
    assert again.status_code == 409  # nothing changed since version 1
    changed = c.post("/v1/templates/knowledge-faq/create-version", json={"agentId": "faq-bot", "params": {"company_name": "Beta"}}, headers=H)
    assert changed.status_code == 201 and changed.json()["number"] == 2
    gone = c.post("/v1/templates/order-status/create-version", json={"agentId": "o-bot", "params": {"order_tool": "nope_tool"}}, headers=H)
    assert gone.status_code == 400 and gone.json()["error"]["code"] == "missing_tools"
    publish = c.post("/v1/agents/faq-bot/releases", json={"version": 1}, headers=H)
    assert publish.status_code == 409 and publish.json()["error"]["code"] == "gate_not_satisfied"  # no scenario files for it yet: the gate still applies
    actions = {e["action"] for e in c.get("/v1/audit?limit=20", headers=H).json()["entries"]}
    assert "template.create_version" in actions
    off, _, _ = api(with_releases=False)
    assert off.post("/v1/templates/knowledge-faq/create-version", json={"agentId": "faq-bot"}, headers=H).status_code == 501
    assert off.post("/v1/templates/knowledge-faq/render", json={"agentId": "faq-bot"}, headers=H).status_code == 200


def test_api_permissions():
    c, ac, _ = api()
    loop = asyncio.new_event_loop()
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    for role, read, write in [("viewer", 200, 403), ("reviewer", 200, 403), ("developer", 200, 200), ("channel", 403, 403)]:
        h = {"authorization": f"Bearer {key(role)}"}
        assert c.get("/v1/templates", headers=h).status_code == read, role
        assert c.post("/v1/templates/human-triage/render", json={"agentId": "tri-bot"}, headers=h).status_code == write, role
    assert c.get("/v1/templates").status_code == 401
