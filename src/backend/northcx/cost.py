"""Cost estimates (Q12): how many model tokens a conversation costs, from the scenarios you already have.

    python -m northcx.cost SCENARIOS --specs DIR --registry module:function --price-in 3 --price-out 15 --conversations-per-day 2000

Each scenario is run with its scripted model, and what is sent to the model on every call is measured: the agent's instructions, the tool
descriptions, and the whole conversation so far (which is re-sent on every call, so long conversations cost more than the sum of their parts).
Tokens are estimated as characters divided by four, which is within roughly 25% for English text and less accurate for other languages and
for code. The answers the scripted model gives are shorter than a real model's, so output tokens are a floor. Prices are yours to supply (per
million tokens); nothing here knows any provider's price list. Prompt caching, if you use it, lowers real input costs and is not modelled.

Use `--save FILE` to keep a baseline and `--baseline FILE --max-increase 20` to fail a build when a change makes conversations noticeably dearer.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import math
import sys
from dataclasses import dataclass, field
from typing import Any

from .simulation.runner import RecordingLLM, SimConfig, SimulationRunner
from .simulation.scenario import Scenario, ScenarioError, load_scenarios
from .spec import BuildContext, SpecError, load_specs

CHARS_PER_TOKEN = 4


def tokens(value: Any) -> int:
    """Estimated tokens in a string or JSON-like structure."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, separators=(",", ":"))
    return math.ceil(len(text) / CHARS_PER_TOKEN)


@dataclass
class ScenarioCost:
    name: str
    model_calls: int
    input_tokens: int
    output_tokens: int
    first_call_tokens: int  # what the very first call costs: the fixed part (instructions + tools)
    turns: int = 1

    def dollars(self, price_in: float, price_out: float) -> float:
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1e6

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "modelCalls": self.model_calls, "inputTokens": self.input_tokens, "outputTokens": self.output_tokens, "firstCallTokens": self.first_call_tokens, "turns": self.turns}


@dataclass
class Measure:
    costs: list[ScenarioCost] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def totals(self) -> dict[str, float]:
        n = max(1, len(self.costs))
        return {"scenarios": len(self.costs), "avgModelCalls": sum(c.model_calls for c in self.costs) / n, "avgInputTokens": sum(c.input_tokens for c in self.costs) / n,
                "avgOutputTokens": sum(c.output_tokens for c in self.costs) / n}


async def measure(scenarios: list[Scenario], agent_factory: Any) -> Measure:
    """Runs each scenario (scripted model) and counts what the model would have been sent and what it answered."""
    out = Measure()
    for sc in scenarios:
        recs: list[RecordingLLM] = []

        def factory(agent_id: str, llm: Any, _recs: list[RecordingLLM] = recs) -> Any:
            if isinstance(llm, RecordingLLM):
                _recs.append(llm)
            return agent_factory(agent_id, llm)
        suite = await SimulationRunner(factory, SimConfig("scripted", None, None, True, True), {}).run_suite([sc])
        rec = recs[-1] if recs else None
        if rec is None or not rec.requests:
            out.skipped.append(sc.name)  # no model calls (for example, blocked by an input check): costs nothing
            continue
        i = sum(tokens([r.system, r.messages, r.tools]) for r in rec.requests)
        o = sum(tokens(res.content) for res in rec.responses)
        first = tokens([rec.requests[0].system, rec.requests[0].messages, rec.requests[0].tools])
        out.costs.append(ScenarioCost(sc.name, len(rec.requests), i, o, first, len(sc.turns)))
        _ = suite
    return out


def project(m: Measure, price_in: float, price_out: float, per_day: int) -> dict[str, float]:
    n = max(1, len(m.costs))
    per_conv = sum(c.dollars(price_in, price_out) for c in m.costs) / n
    return {"perConversation": per_conv, "perDay": per_conv * per_day, "perMonth": per_conv * per_day * 30}


def compare(current: Measure, baseline: dict[str, Any], max_increase: float) -> list[str]:
    """Scenarios whose input tokens grew by more than `max_increase` percent since the baseline."""
    base = {c["name"]: c["inputTokens"] for c in baseline.get("costs", [])}
    problems = []
    for c in current.costs:
        b = base.get(c.name)
        if b and c.input_tokens > b * (1 + max_increase / 100):
            problems.append(f"{c.name}: input tokens {b} -> {c.input_tokens} (+{(c.input_tokens / b - 1) * 100:.0f}%)")
    return problems


def format_report(m: Measure, price_in: float | None, price_out: float | None, per_day: int | None) -> str:
    rows = [f"{'scenario':58} {'calls':>5} {'input':>8} {'output':>7} {'fixed':>6}"]
    for c in sorted(m.costs, key=lambda c: -c.input_tokens):
        rows.append(f"{c.name[:58]:58} {c.model_calls:>5} {c.input_tokens:>8} {c.output_tokens:>7} {c.first_call_tokens:>6}")
    t = m.totals()
    rows += ["", f"{int(t['scenarios'])} scenarios measured, average {t['avgModelCalls']:.1f} model calls, {t['avgInputTokens']:.0f} input and {t['avgOutputTokens']:.0f} output tokens per scenario",
             "'fixed' is the first call's size: instructions and tool descriptions that are re-sent on every call.",
             "Estimates (characters / 4); scripted answers are shorter than a real model's, so output is a floor."]
    if m.skipped:
        rows.append(f"{len(m.skipped)} scenarios made no model call (stopped by input checks or forced topics) and cost nothing.")
    if price_in is not None and price_out is not None:
        p = project(m, price_in, price_out, per_day or 0)
        rows.append(f"At {price_in} in / {price_out} out per million tokens: {p['perConversation']:.4f} per conversation" + (f", {p['perDay']:.2f} a day, {p['perMonth']:.0f} a month at {per_day} conversations a day" if per_day else ""))
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="northcx.cost", description="Estimate model-token cost per conversation from scenarios.")
    p.add_argument("scenarios")
    p.add_argument("--specs", required=True)
    p.add_argument("--registry", required=True)
    p.add_argument("--price-in", type=float, help="price per million input tokens (your currency)")
    p.add_argument("--price-out", type=float, help="price per million output tokens")
    p.add_argument("--conversations-per-day", type=int)
    p.add_argument("--save", help="write the measurements to this JSON file (a baseline)")
    p.add_argument("--baseline", help="compare with a saved baseline")
    p.add_argument("--max-increase", type=float, default=20.0, help="fail if a scenario's input tokens grow by more than this percent over the baseline")
    a = p.parse_args(argv)
    if (a.price_in is None) != (a.price_out is None):
        print("error: give both --price-in and --price-out, or neither", file=sys.stderr)
        return 2
    try:
        scenarios = load_scenarios(a.scenarios)
        mod, _, fn = a.registry.partition(":")
        registry = getattr(importlib.import_module(mod), fn)()
        specs = {s.id: s for s in load_specs(a.specs)}
    except (ScenarioError, SpecError, ImportError, AttributeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    def agent_factory(agent_id: str, llm: Any) -> Any:
        return registry.build(specs[agent_id], BuildContext(llm=llm))
    m = asyncio.run(measure([s for s in scenarios if s.model is not None], agent_factory))
    print(format_report(m, a.price_in, a.price_out, a.conversations_per_day))
    if a.save:
        with open(a.save, "w") as f:
            json.dump({"costs": [c.to_dict() for c in m.costs]}, f, indent=1)
    if a.baseline:
        with open(a.baseline) as f:
            problems = compare(m, json.load(f), a.max_increase)
        for line in problems:
            print("COST INCREASE", line)
        if problems:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
