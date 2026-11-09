"""Budgets in currency: every answer is costed from the operator's own prices; the daily limit stops model calls and hands off."""
from types import SimpleNamespace

import pytest

from examples.support_agent import support_agent
from northcx.llm import ScriptedLLM, text
from northcx.providers import Price
from northcx.reliability import UsageLedger
from northcx.runtime import Runtime
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


def priced(resp, n_in, n_out, provider="p", model="m"):
    resp.usage, resp.provider, resp.model = {"input_tokens": n_in, "output_tokens": n_out}, provider, model
    return resp


def runtime(script, limit, prices, currency="USD"):
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), ledger=UsageLedger(None, limit, currency))
    rt.pricing = lambda provider, model: prices.get((provider, model))
    return rt


async def test_the_cost_is_recorded_and_the_limit_hands_off():
    rt = runtime([priced(text("one"), 600_000, 100_000), text("never")], 1.00, {("p", "m"): Price(1.0, 4.0)})  # 0.60 + 0.40 = 1.00
    r = await rt.run(support_agent(), "s1", "hi")
    assert r.status == "completed" and rt.ledger.money_today("support") == pytest.approx(1.0)
    llm = next(e for e in r.trace.events if e.type == "llm")
    assert llm.data["cost"] == pytest.approx(1.0) and llm.data["currency"] == "USD"
    r2 = await rt.run(support_agent(), "s2", "again")
    assert r2.status == "escalated" and len(rt.llm.requests) == 1
    b = next(e for e in r2.trace.events if e.type == "budget").data
    assert b["scope"] == "daily" and b["money_limit"] == 1.0 and b["currency"] == "USD"


async def test_a_model_without_a_price_in_the_budget_currency_is_flagged_not_hidden():
    rt = runtime([priced(text("hi"), 1000, 1000)], 5.0, {("p", "m"): Price(1.0, 1.0, "EUR")})
    r = await rt.run(support_agent(), "s", "hi")
    llm = next(e for e in r.trace.events if e.type == "llm").data
    assert llm.get("unpriced") is True and "cost" not in llm and rt.ledger.money_today() == 0


async def test_no_money_limit_means_no_costing():
    rt = Runtime(ScriptedLLM([priced(text("hi"), 1000, 1000)]), InMemoryStore(), TraceStore())
    r = await rt.run(support_agent(), "s", "hi")
    llm = next(e for e in r.trace.events if e.type == "llm").data
    assert "cost" not in llm and "unpriced" not in llm


def test_money_days_and_pruning():
    L = UsageLedger(None, 1.0)
    L.add_money("a", 0.6, at=0)
    L.add_money("a", 0.5, at=86400 * 10)
    assert L.money_today(None, at=86400 * 10) == pytest.approx(0.5) and len(L._micros) == 1
    assert L.exhausted(at=86400 * 10) is False
    L.add_money("a", 0.5, at=86400 * 10)
    assert L.exhausted(at=86400 * 10)


# ---------- startup ----------
def load(monkeypatch, tmp_path, price):
    from northcx.bootstrap.settings import load_settings
    f = tmp_path / "p.yaml"
    f.write_text(f"""
providers:
  - name: local
    type: openai-compatible
    baseUrl: http://localhost:11434/v1
    defaultModel: m
    default: true
{price}""")
    for k in ("NORTHCX_DEMO", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NORTHCX_PROVIDERS_FILE", str(f))
    monkeypatch.setenv("NORTHCX_API_KEY", "a-long-enough-key-123456")
    c = SimpleNamespace()
    load_settings(c)
    return c.providers


def test_a_budget_is_refused_when_a_provider_has_no_price_in_the_currency(monkeypatch, tmp_path):
    from northcx.providers.budget import check_money_budget
    with pytest.raises(ValueError, match="provider 'local' has no price"):
        check_money_budget(load(monkeypatch, tmp_path, ""), "USD")
    eur = '    prices: {m: {inputPerMillion: 1, outputPerMillion: 2, currency: EUR}}\n'
    with pytest.raises(ValueError, match="in USD"):
        check_money_budget(load(monkeypatch, tmp_path, eur), "USD")
    check_money_budget(load(monkeypatch, tmp_path, eur), "EUR")
    assert load(monkeypatch, tmp_path, eur).price_for("local", "m") == Price(1.0, 2.0, "EUR")
