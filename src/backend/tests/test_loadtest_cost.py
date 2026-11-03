"""The load test and cost estimator tools themselves (Q12)."""
import asyncio
import json
from pathlib import Path

import pytest

from northcx import cost, loadtest
from northcx.simulation.scenario import load_scenarios
from northcx.spec import BuildContext, load_specs

ROOT = Path(__file__).resolve().parents[1]


def test_a_small_in_process_load_run_reports_throughput_latency_and_no_errors():
    p = loadtest.Profile(users=8, conversations=16, turns=3, think_ms=5, ramp_s=0.2)
    s = asyncio.run(loadtest.in_process(p, model_ms=5)).summary()
    assert s["requests"] >= 16 + 16 and s["errorRate"] == 0 and s["latencyMs"]["mint-token"]["n"] == 16 and s["requestsPerSecond"] > 0
    assert {"mint-token", "chat"} <= set(s["latencyMs"]) and s["latencyMs"]["chat"]["p50"] >= 5          # the pretend model's delay shows in the reply time
    assert s["latencyMs"]["chat"]["p50"] <= s["latencyMs"]["chat"]["p95"] <= s["latencyMs"]["chat"]["max"]
    assert s["eventLoopLagMs"] is not None and s["memoryMb"]["after"] >= s["memoryMb"]["before"] > 0
    assert "requests/s" in loadtest.format_summary(s)


def test_the_command_exits_non_zero_when_targets_are_missed(tmp_path, capsys):
    out = tmp_path / "r.json"
    ok = loadtest.main(["--users", "4", "--conversations", "4", "--turns", "2", "--think-ms", "0", "--ramp-s", "0", "--json", str(out), "--max-p95-ms", "5000"])
    assert ok == 0 and json.loads(out.read_text())["requests"] > 0
    late = loadtest.main(["--users", "4", "--conversations", "4", "--turns", "2", "--think-ms", "0", "--ramp-s", "0", "--model-ms", "30", "--max-p95-ms", "1"])
    assert late == 1 and "MISSED TARGET" in capsys.readouterr().out
    assert loadtest.main(["--url", "http://localhost:1"]) == 2                                              # a server needs a key


def test_failures_to_connect_are_counted_not_raised():
    import httpx

    async def go():
        async with httpx.AsyncClient(base_url="http://127.0.0.1:1", timeout=1, follow_redirects=False) as c:
            return await loadtest.run(c, loadtest.Profile(users=2, conversations=2, turns=1, think_ms=0, ramp_s=0), "k")
    r = asyncio.run(go())
    assert r.statuses["network"] >= 2 and r.error_rate == 1.0 and r.failures


def test_tokens_are_estimated_from_text_size():
    assert cost.tokens("abcd") == 1 and cost.tokens("a" * 401) == 101 and cost.tokens({"a": [1, 2]}) > 0


def scenarios_and_factory():
    from examples.support_agent import registry
    reg = registry()
    specs = {s.id: s for s in load_specs(ROOT / "examples")}
    return [s for s in load_scenarios(ROOT / "examples" / "scenarios") if s.model is not None], lambda aid, llm: reg.build(specs[aid], BuildContext(llm=llm))


def test_the_cost_estimate_counts_what_the_model_is_sent_and_grows_with_history():
    scs, factory = scenarios_and_factory()
    m = asyncio.run(cost.measure(scs, factory))
    assert m.costs and all(c.input_tokens >= c.first_call_tokens > 0 and c.model_calls >= 1 for c in m.costs)
    multi = [c for c in m.costs if c.model_calls >= 2]
    assert multi and all(c.input_tokens > c.first_call_tokens * 1.5 for c in multi)                       # the conversation so far is re-sent on every call
    assert m.skipped                                                                                       # attack scenarios stopped by input checks cost nothing
    p = cost.project(m, 3.0, 15.0, 1000)
    assert p["perConversation"] > 0 and abs(p["perDay"] - p["perConversation"] * 1000) < 1e-9 and abs(p["perMonth"] - p["perDay"] * 30) < 1e-9
    text = cost.format_report(m, 3.0, 15.0, 1000)
    assert "per conversation" in text and "a month" in text and "fixed" in text


def test_a_cost_baseline_catches_growth(tmp_path):
    scs, factory = scenarios_and_factory()
    m = asyncio.run(cost.measure(scs, factory))
    baseline = {"costs": [c.to_dict() for c in m.costs]}
    assert cost.compare(m, baseline, 20) == []
    smaller = {"costs": [{**c.to_dict(), "inputTokens": int(c.input_tokens / 2)} for c in m.costs]}
    problems = cost.compare(m, smaller, 20)
    assert problems and "input tokens" in problems[0] and "+100%" in problems[0]
    assert cost.compare(m, smaller, 150) == []


def test_the_cost_command_checks_its_arguments_and_gates_on_a_baseline(tmp_path, capsys):
    common = [str(ROOT / "examples" / "scenarios"), "--specs", str(ROOT / "examples"), "--registry", "examples.support_agent:registry"]
    assert cost.main([*common, "--price-in", "3"]) == 2
    assert cost.main(["nonexistent-dir", "--specs", str(ROOT / "examples"), "--registry", "examples.support_agent:registry"]) == 2
    base = tmp_path / "base.json"
    assert cost.main([*common, "--price-in", "3", "--price-out", "15", "--conversations-per-day", "100", "--save", str(base)]) == 0
    assert "per conversation" in capsys.readouterr().out
    assert cost.main([*common, "--baseline", str(base)]) == 0
    data = json.loads(base.read_text())
    for c in data["costs"]:
        c["inputTokens"] = max(1, c["inputTokens"] // 3)
    base.write_text(json.dumps(data))
    assert cost.main([*common, "--baseline", str(base), "--max-increase", "10"]) == 1 and "COST INCREASE" in capsys.readouterr().out
