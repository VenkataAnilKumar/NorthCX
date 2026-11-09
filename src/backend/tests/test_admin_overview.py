"""Read-only views behind the Admin pages: Models and budgets, Usage, the policy library."""
import asyncio

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text
from northcx.providers import Capabilities, Price, ProviderRegistry
from northcx.providers.selection import parse_routing
from northcx.reliability import ReliableLLM, UsageLedger
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.types import LLMResponse

KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


class Fake:
    def __init__(self, name, model, prices=None):
        self.name, self.default_model, self.capabilities, self.prices = name, model, Capabilities(tools=True, images=name == "pub", max_context_tokens=100000), prices or {}

    async def complete(self, req):
        return LLMResponse(content=[{"type": "text", "text": "ok"}], model=req.model or self.default_model, usage={"input_tokens": 1000, "output_tokens": 500}, provider=self.name)


def app_with(llm, ledger=None):
    rt = Runtime(llm, InMemoryStore(), TraceStore(), ledger=ledger)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY))), rt


def test_without_providers_the_models_page_says_so():
    c, _ = app_with(ScriptedLLM([]))
    out = c.get("/v1/models/overview", headers=H).json()
    assert out["configured"] is False and out["providers"] == [] and "demo" in out["note"]


def test_providers_tiers_prices_rules_and_budget_are_shown_without_any_key():
    reg = ProviderRegistry()
    reg.register(Fake("pub", "big", {"big": Price(3.0, 15.0, "USD")}), default=True)
    reg.register(Fake("loc", "small", {"small": Price(0.0, 0.0, "USD")}))
    sel = parse_routing("policy: {sensitive: [local]}\nsensitiveTopics: [payment]\nqualification: {required: true, exempt: ['pub:big']}\nrules:\n  - {name: simple, when: {sensitive: false}, use: {tier: local}}\n",
                        reg, {"pub": "public-cloud", "loc": "local"})
    rel = ReliableLLM(reg, ["pub:big"], retries=0, timeout=None)
    rel.selector = sel
    c, rt = app_with(rel, UsageLedger(1000, 5.0, "USD"))
    asyncio.run(rt.ledger.charge("support", 120, 0.25))
    out = c.get("/v1/models/overview", headers=H).json()
    assert out["configured"] is True and [p["name"] for p in out["providers"]] == ["loc", "pub"] and out["fallbacks"] == ["pub:big"]
    pub = next(p for p in out["providers"] if p["name"] == "pub")
    assert pub["tier"] == "public-cloud" and pub["isDefault"] and pub["prices"]["big"]["outputPerMillion"] == 15.0 and pub["capabilities"]["images"] is True
    assert next(p for p in out["providers"] if p["name"] == "loc")["tier"] == "local"
    assert out["routing"]["policy"]["sensitive"] == ["local"] and out["routing"]["rules"][0] == {"name": "simple", "when": {"sensitive": False}, "use": {"tier": "local"}}
    assert out["routing"]["qualification"] == {"required": True, "exempt": ["pub:big"]} and "payment" in out["routing"]["sensitiveTopics"]
    assert out["budget"] == {"dailyTokenLimit": 1000, "dailyMoneyLimit": 5.0, "currency": "USD", "setHere": {}, "tokensToday": 120, "moneyToday": 0.25}
    assert "key" not in str(out).lower().replace("keys are never shown", "")


def test_usage_by_agent_and_day_with_totals_and_limits():
    ledger = UsageLedger(None, 10.0, "EUR")
    c, rt = app_with(ScriptedLLM([text("x")]), ledger)
    asyncio.run(ledger.charge("support", 500, 0.5))
    asyncio.run(ledger.charge("billing", 200, 0.2))
    asyncio.run(ledger.charge("support", 100, 0.1))
    out = c.get("/v1/usage?days=7", headers=H).json()
    assert out["currency"] == "EUR" and out["totals"] == {"tokens": 800, "cost": 0.8} and out["limits"]["dailyMoneyLimit"] == 10.0
    assert [(a["agent"], a["tokens"]) for a in out["byAgent"]] == [("support", 600), ("billing", 200)]
    assert c.get("/v1/usage?days=0", headers=H).status_code == 400 and c.get("/v1/usage?days=91", headers=H).status_code == 400
    assert c.get("/v1/usage").status_code == 401


def test_the_policy_library_lists_every_policy_with_allow_and_block_cases():
    c, _ = app_with(ScriptedLLM([]))
    out = c.get("/v1/policies", headers=H).json()
    names = {p["name"] for p in out["policies"]}
    assert {"tool_limit", "forbidden_phrases", "required_phrase", "no_personal_data_in_reply", "max_reply_length"} <= names
    tl = next(p for p in out["policies"] if p["name"] == "tool_limit")
    assert tl["description"] and tl["exampleConfig"]["tool"] == "issue_refund" and {x["expected"] for x in tl["cases"]} == {"allowed", "blocked"}
    assert all(p["cases"] for p in out["policies"])                                  # no policy ships without its proof


async def test_usage_comes_from_the_database_for_the_callers_tenant(app_engine):
    from contextlib import contextmanager

    from northcx.db import PgUsageLedger
    from northcx.tenancy import TENANT

    @contextmanager
    def as_tenant(name):
        token = TENANT.set(name)
        try:
            yield
        finally:
            TENANT.reset(token)
    led = PgUsageLedger(app_engine, None, 5.0, "USD")
    with as_tenant("acme"):
        await led.charge("support", 300, 0.3)
        await led.charge("billing", 50, 0.05)
    with as_tenant("globex"):
        await led.charge("support", 7, 0.01)
    with as_tenant("acme"):
        rows = await led.usage_rows(7)
        assert sorted((r["agent"], r["tokens"]) for r in rows) == [("billing", 50), ("support", 300)] and abs(sum(r["cost"] for r in rows) - 0.35) < 1e-9
    with as_tenant("globex"):
        assert [(r["agent"], r["tokens"]) for r in await led.usage_rows(7)] == [("support", 7)]


# ---------- usage by model and team, budgets from the page ----------
def providers_stack(prices=True):
    reg = ProviderRegistry()
    reg.register(Fake("pub", "big", {"big": Price(3.0, 15.0, "USD")} if prices else {}), default=True)
    rel = ReliableLLM(reg, [], retries=0, timeout=None)
    return rel, reg


def test_usage_is_counted_by_model_and_by_team_for_staff():
    from northcx.budget_settings import BudgetSettings
    rel, reg = providers_stack()
    ledger = UsageLedger()
    ledger.settings = BudgetSettings()
    c, rt = app_with(rel, ledger)
    rt.pricing = reg.price_for
    ac = c.app  # noqa: F841
    loop = asyncio.new_event_loop()
    from northcx.access import Identity
    agent = support_agent()
    loop.run_until_complete(rt.run(agent, "s1", "hello"))                         # a customer conversation: counted by model, no team
    from northcx.workspace import WorkspaceService
    ws = WorkspaceService(rt, rt.traces, None, None, None, None)
    ann = Identity("ann", "developer", "k1", groups=("Support leads", "Billing"))
    loop.run_until_complete(rt.run(ws.agent(ann), "staff:1:c", "hi", "staff:1", actor=ann))
    loop.run_until_complete(rt.run(ws.agent(Identity("bob", "viewer", "k2")), "staff:2:c", "hi", "staff:2", actor=Identity("bob", "viewer", "k2")))
    out = c.get("/v1/usage?days=7", headers=H).json()
    assert [m["name"] for m in out["byModel"]] == ["pub:big"] and out["byModel"][0]["tokens"] == 4500 and out["byModel"][0]["cost"] > 0
    assert {t["name"]: t["tokens"] for t in out["byTeam"]} == {"Billing": 1500, "(no team)": 1500}      # counted once, under the first group alphabetically


def test_a_budget_set_from_the_page_replaces_the_environment_default_for_that_tenant_and_can_be_cleared():
    from northcx.budget_settings import BudgetSettings
    rel, reg = providers_stack()
    ledger = UsageLedger(None, None, "USD")
    ledger.settings = BudgetSettings()
    c, rt = app_with(rel, ledger)
    rt.budget_settings = ledger.settings
    rt.pricing = reg.price_for
    assert c.get("/v1/models/overview", headers=H).json()["budget"]["dailyTokenLimit"] is None
    assert c.put("/v1/budgets", headers=H, json={"dailyTokenLimit": 2000, "dailyMoneyLimit": 0.01, "currency": "usd"}).json() == {"saved": True, "setHere": {"dailyTokenLimit": 2000, "dailyMoneyLimit": 0.01, "currency": "USD"}}
    b = c.get("/v1/models/overview", headers=H).json()["budget"]
    assert b["dailyTokenLimit"] == 2000 and b["dailyMoneyLimit"] == 0.01 and b["setHere"]["currency"] == "USD"
    loop = asyncio.new_event_loop()
    agent = support_agent()
    first = loop.run_until_complete(rt.run(agent, "s1", "hello"))
    assert first.status == "completed"                                                    # 1500 tokens, 0.0105 money: over the 0.01 limit now
    ledger.settings._cache.clear()
    second = loop.run_until_complete(rt.run(agent, "s2", "hello"))
    assert second.status == "escalated" and next(e for e in second.trace.events if e.type == "budget").data["money_limit"] == 0.01
    assert c.delete("/v1/budgets", headers=H).json() == {"cleared": True}
    ledger.settings._cache.clear()
    assert loop.run_until_complete(rt.run(agent, "s3", "hello")).status == "completed"      # back to no limit


def test_bad_budgets_are_refused_with_a_reason_and_a_spending_limit_needs_prices():
    from northcx.budget_settings import BudgetSettings
    rel, reg = providers_stack(prices=False)
    ledger = UsageLedger()
    ledger.settings = BudgetSettings()
    c, rt = app_with(rel, ledger)
    rt.budget_settings = ledger.settings
    for body, why in [({"dailyTokenLimit": 5}, "1,000"), ({"dailyTokenLimit": "many"}, "whole number"), ({"dailyMoneyLimit": -1}, "positive"), ({"currency": "dollars"}, "three-letter")]:
        r = c.put("/v1/budgets", headers=H, json=body)
        assert r.status_code == 400 and why in r.json()["error"]["message"], (body, r.text)
    r = c.put("/v1/budgets", headers=H, json={"dailyMoneyLimit": 5})
    assert r.status_code == 400 and "no price" in r.json()["error"]["message"] and c.get("/v1/models/overview", headers=H).json()["budget"]["dailyMoneyLimit"] is None
    assert c.put("/v1/budgets", headers=H, json={"dailyTokenLimit": 5000}).status_code == 200            # a token limit needs no price
    loop = asyncio.new_event_loop()
    key = lambda role: {"authorization": "Bearer " + loop.run_until_complete(c.app.state.access.issue(role, role, "t"))[1]} if hasattr(c.app.state, "access") else None  # noqa: E731
    assert c.put("/v1/budgets", json={"dailyTokenLimit": 5000}).status_code == 401


async def test_settings_usage_dims_and_groups_survive_the_database_per_tenant(app_engine):
    from contextlib import contextmanager

    from northcx.access import AccessControl
    from northcx.budget_settings import BudgetSettings
    from northcx.db import PgKeys, PgSettings, PgUsageLedger
    from northcx.tenancy import TENANT

    @contextmanager
    def as_tenant(name):
        token = TENANT.set(name)
        try:
            yield
        finally:
            TENANT.reset(token)
    s = BudgetSettings(PgSettings(app_engine))
    led = PgUsageLedger(app_engine, None, None, "USD")
    led.settings = s
    for tenant, limit in (("acme", 5000), ("globex", 9000)):
        with as_tenant(tenant):
            await s.put({"dailyTokenLimit": limit}, "rae")
            await led.charge("support", 100, 0.1, model="pub:big", team="Support")
    with as_tenant("acme"):
        assert (await led.limits())[0] == 5000 and [(d["kind"], d["key"], d["tokens"]) for d in await led.usage_dims(7)] == [("model", "pub:big", 100), ("team", "Support", 100)]
        assert await s.clear() and (await led.limits())[0] is None
    with as_tenant("globex"):
        assert (await led.limits())[0] == 9000
    ac = AccessControl(keys=PgKeys(app_engine))
    _, secret = await ac.issue_session("rae", "developer", 4, groups=["Support", "Billing"])
    assert (await AccessControl(keys=PgKeys(app_engine)).authenticate(secret)).groups == ("Billing", "Support")
