"""Read-only views for the Admin pages: Models and budgets, Usage, and the policy library."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from northcx.api.common import _err
from northcx.api.deps import AppDeps


def register(app: FastAPI, d: AppDeps) -> None:
    runtime = d.runtime

    @app.get("/v1/models/overview")
    async def models_overview() -> Any:
        """The model providers (never their keys), the data policy and routing rules, the fallback order and today's spending against its limits."""
        llm = runtime.llm
        registry = getattr(llm, "inner", None)
        ledger = runtime.ledger
        budget = {"dailyTokenLimit": getattr(ledger, "daily_limit", None), "dailyMoneyLimit": getattr(ledger, "money_limit", None), "currency": getattr(ledger, "currency", "USD"),
                  "tokensToday": await ledger.spent(), "moneyToday": await ledger.money_spent() if hasattr(ledger, "money_spent") else 0.0}
        if registry is None or not hasattr(registry, "names"):
            return {"configured": False, "providers": [], "budget": budget, "note": "No model providers are configured (the offline demo model is in use)."}
        sel = getattr(llm, "selector", None)
        tiers = getattr(sel, "tiers", {}) if sel is not None else {}
        out = []
        for name in registry.names:
            p = registry.get(name)
            caps = p.capabilities
            out.append({"name": name, "defaultModel": p.default_model, "isDefault": registry.default.name == name, "tier": tiers.get(name, "public-cloud" if sel is None else "public-cloud"),
                        "capabilities": {"tools": caps.tools, "parallelTools": caps.parallel_tools, "images": caps.images, "documents": caps.documents, "maxContextTokens": caps.max_context_tokens},
                        "prices": {m: {"inputPerMillion": pr.input_per_million, "outputPerMillion": pr.output_per_million, "currency": pr.currency} for m, pr in p.prices.items()}})
        routing: dict[str, Any] | None = None
        if sel is not None:
            routing = {"policy": {"sensitive": list(sel.policy.sensitive), "normal": list(sel.policy.normal), "publicCloudAllowedAgents": sorted(sel.policy.public_agents)},
                       "sensitiveTopics": list(sel.topics),
                       "rules": [{"name": r.name, "when": r.when, "use": {"tier": r.tier} if r.tier else {"model": r.model}} for r in sel.rules],
                       "qualification": {"required": sel.qualification_required, "exempt": sorted(sel.exempt)}}
        return {"configured": True, "providers": out, "fallbacks": list(getattr(llm, "models", [])), "routing": routing, "budget": budget,
                "note": "Keys are never shown. Providers, prices and rules are set in the providers and routing files."}

    @app.get("/v1/usage")
    async def usage(days: int = 7) -> Any:
        """Tokens and money per agent per day for the caller's tenant, with totals. Money counts only answers from models that have a price in the budget currency."""
        if not 1 <= days <= 90:
            return _err(400, "bad_request", "days must be from 1 to 90")
        ledger = runtime.ledger
        rows = await ledger.usage_rows(days) if hasattr(ledger, "usage_rows") else []
        by_agent: dict[str, dict[str, float]] = {}
        for r in rows:
            a = by_agent.setdefault(r["agent"], {"tokens": 0, "cost": 0.0})
            a["tokens"] += r["tokens"]
            a["cost"] += r["cost"]
        return {"days": days, "currency": getattr(ledger, "currency", "USD"), "rows": rows,
                "byAgent": [{"agent": k, **v} for k, v in sorted(by_agent.items(), key=lambda kv: -kv[1]["tokens"])],
                "totals": {"tokens": sum(r["tokens"] for r in rows), "cost": round(sum(r["cost"] for r in rows), 6)},
                "limits": {"dailyTokenLimit": getattr(ledger, "daily_limit", None), "dailyMoneyLimit": getattr(ledger, "money_limit", None)}}

    @app.get("/v1/policies")
    async def policies() -> Any:
        """The policy library: what each ready-made policy does, an example setting, and the allow and block cases that prove it."""
        from northcx.policies import CASES, DESCRIPTIONS
        out: dict[str, Any] = {}
        for name, config, kind, payload, allow in CASES:
            p = out.setdefault(name, {"name": name, "description": DESCRIPTIONS.get(name, ""), "exampleConfig": config, "cases": []})
            shown = payload if isinstance(payload, str) else {"tool": payload[0], "input": {k: ("not a number" if isinstance(v, float) and v != v else v) for k, v in payload[1].items()}}
            p["cases"].append({"on": kind, "input": shown, "expected": "allowed" if allow else "blocked"})
        for name, desc in DESCRIPTIONS.items():
            out.setdefault(name, {"name": name, "description": desc, "exampleConfig": {}, "cases": []})
        return {"policies": sorted(out.values(), key=lambda p: p["name"]),
                "note": "Every policy ships with cases that the test suite runs; a change that weakens a policy fails a test. Policies are chosen per agent in its definition."}
