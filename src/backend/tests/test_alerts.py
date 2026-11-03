"""Alerts: thresholds, minimum samples, cooldown, recovery, webhook and API."""
import asyncio

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.alerts import AlertConfigError, AlertManager, AlertRule, DEFAULT_RULES, METRICS, WebhookAlerts, load_rules
from northcx.insights import InMemoryFeedback, InMemoryInsightsSource, InsightsService
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.monitor import InMemoryMonitor
from northcx.notify import verify
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


class FakeInsights:
    """Returns an overview shaped like the real one, with whatever numbers a test wants."""

    def __init__(self):
        self.err = (0.0, 100)
        self.esc = (0.0, 100)
        self.lat = (1.0, 100)
        self.calls = []

    async def overview(self, since, until, agent=None, environment="production"):
        self.calls.append((since, until, environment))
        r = lambda v: {"value": v[0], "denominator": v[1]}  # noqa: E731
        return {"errorRate": r(self.err), "escalationRate": r(self.esc), "guardrailBlockRate": r((0.0, 100)), "toolErrorRate": r((0.0, 100)),
                "fallbackModelRate": r((0.0, 100)), "latencySeconds": {"p95": self.lat[0], "samples": self.lat[1]}}


def manager(rules=None, clock=None, notifier=None):
    ins, mon = FakeInsights(), InMemoryMonitor()
    now = [1_800_000_000.0]
    m = AlertManager(ins, mon, rules, notifier, clock=lambda: now[0])
    return m, ins, mon, now


async def test_a_breach_fires_once_then_reminds_after_the_cooldown_and_clears_on_recovery():
    m, ins, mon, now = manager([AlertRule("errors", "error_rate", 0.1, severity="critical", cooldown_minutes=30)])
    assert await m.evaluate() == [] and m.active == {}
    ins.err = (0.25, 80)
    assert [e["event"] for e in await m.evaluate()] == ["alert.fired"] and "error_rate is 0.25 (limit 0.1) over the last 15 min, 80 samples" in m.events[-1]["detail"]
    now[0] += 60
    assert await m.evaluate() == [] and len(m.events) == 1  # still firing, but not every minute
    now[0] += 31 * 60
    assert "still firing" in (await m.evaluate())[0]["detail"]
    ins.err = (0.02, 90)
    now[0] += 60
    await m.evaluate()
    assert m.active == {} and m.events[-1]["event"] == "alert.cleared"
    found = await mon.list()
    assert sorted(f.rule for f in found) == ["alert:errors", "alert:errors", "alert_cleared:errors"] and {f.severity for f in found} == {"critical", "info"}


async def test_too_few_samples_never_alert_and_thresholds_can_be_lower_limits():
    m, ins, mon, now = manager([AlertRule("esc", "escalation_rate", 0.5, min_samples=20), AlertRule("quiet", "escalation_rate", 0.1, above=False, min_samples=5, severity="warning")])
    ins.esc = (1.0, 3)  # everything escalated, but only three conversations
    assert await m.evaluate() == []
    ins.esc = (0.05, 50)
    assert [e["rule"] for e in await m.evaluate()] == ["quiet"]  # below the lower limit: something stopped escalating
    ins.esc = (0.8, 50)
    assert [e["event"] for e in await m.evaluate()] == ["alert.fired"] and {a for a in m.active} == {"esc"}


async def test_latency_alert_and_shared_windows():
    m, ins, mon, now = manager([AlertRule("slow", "p95_latency_seconds", 30), AlertRule("err", "error_rate", 0.5), AlertRule("long", "error_rate", 0.5, window_minutes=60)])
    ins.lat = (45.5, 200)
    fired = await m.evaluate()
    assert [e["rule"] for e in fired] == ["slow"] and "45.5s (limit 30s)" in fired[0]["detail"]
    assert len(ins.calls) == 2 and all(c[2] == "production" for c in ins.calls)  # one load per distinct window; production only


async def test_the_webhook_is_signed_and_a_broken_one_never_stops_alerting():
    seen = []

    def handler(req):
        seen.append((req.content, dict(req.headers)))
        return httpx.Response(200)

    hook = WebhookAlerts("https://hooks.example.com/a", "s3cret", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    m, ins, mon, now = manager([AlertRule("errors", "error_rate", 0.1)], notifier=hook)
    ins.err = (0.5, 100)
    await m.evaluate()
    body, h = seen[0]
    assert verify("s3cret", h["x-northcx-timestamp"], body, h["x-northcx-signature"]) and h["x-northcx-event"] == "alert.fired" and b'"rule": "errors"' in body

    class Down:
        async def send(self, e):
            raise RuntimeError("down")

    m2, ins2, mon2, _ = manager([AlertRule("errors", "error_rate", 0.1)], notifier=Down())
    ins2.err = (0.5, 100)
    assert len(await m2.evaluate()) == 1 and len(await mon2.list()) == 1  # the finding is recorded even when the webhook is not
    for url, secret in [("ftp://x", "s"), ("https://x", "")]:
        with pytest.raises(ValueError):
            WebhookAlerts(url, secret)


def test_rules_are_validated_and_loadable(tmp_path):
    assert {r.metric for r in DEFAULT_RULES} <= set(METRICS) and len({r.name for r in DEFAULT_RULES}) == len(DEFAULT_RULES)
    f = tmp_path / "r.yaml"
    f.write_text(yaml.safe_dump({"rules": [{"name": "a", "metric": "error_rate", "threshold": 0.2, "window_minutes": 30}, {"name": "b", "metric": "p95_latency_seconds", "threshold": 10, "severity": "critical"}]}))
    assert [r.window_minutes for r in load_rules(f)] == [30, 15]
    for bad in [{"rules": [{"name": "a", "metric": "nope", "threshold": 1}]}, {"rules": [{"name": "a", "metric": "error_rate", "threshold": 1, "colour": 1}]},
                {"rules": [{"name": "a", "metric": "error_rate", "threshold": 1, "severity": "loud"}]}, {"rules": [{"name": "a", "metric": "error_rate", "threshold": 1}] * 2}, {"rules": "x"}, []]:
        f.write_text(yaml.safe_dump(bad))
        with pytest.raises(AlertConfigError):
            load_rules(f)
    with pytest.raises(AlertConfigError, match="cannot read"):
        load_rules(tmp_path / "missing.yaml")


async def test_alerts_fire_from_real_conversations():
    class Down:
        async def complete(self, req):
            raise RuntimeError("model down")

    rt = Runtime(Down(), InMemoryStore(), TraceStore())
    for i in range(25):  # every turn fails at the model and is handed to a person
        await rt.run(support_agent(), f"s{i}", "hello")
    svc = InsightsService(InMemoryInsightsSource(rt, InMemoryFeedback()))
    m = AlertManager(svc, rt.monitor.repo, [AlertRule("errors", "error_rate", 0.1, severity="critical"), AlertRule("esc", "escalation_rate", 0.5)])
    assert sorted(e["rule"] for e in await m.evaluate()) == ["errors", "esc"]


def test_api_status_and_permissions():
    ins, mon = FakeInsights(), InMemoryMonitor()
    m = AlertManager(ins, mon, [AlertRule("errors", "error_rate", 0.1)])
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key="boot" * 10)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, alerts=m))
    H = {"authorization": "Bearer " + "boot" * 10}
    ins.err = (0.9, 100)
    asyncio.new_event_loop().run_until_complete(m.evaluate())
    s = c.get("/v1/alerts", headers=H).json()
    assert s["enabled"] and s["active"][0]["rule"] == "errors" and s["recent"][0]["event"] == "alert.fired" and s["rules"][0]["threshold"] == 0.1
    chan = asyncio.new_event_loop().run_until_complete(ac.issue("c", "channel", "root"))[1]
    assert c.get("/v1/alerts", headers={"authorization": f"Bearer {chan}"}).status_code == 403
    off = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {"support": support_agent()}))
    assert off.get("/v1/alerts").json() == {"enabled": False}
