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
    assert out["budget"] == {"dailyTokenLimit": 1000, "dailyMoneyLimit": 5.0, "currency": "USD", "tokensToday": 120, "moneyToday": 0.25}
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
