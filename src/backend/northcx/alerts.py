"""Alerts (O9): watch recent behaviour and raise a monitoring finding (and optionally a signed webhook) when it goes wrong.

Rules compare a metric over a recent window with a threshold, ignore windows with too few conversations to mean anything, and stay
quiet for a cooldown after firing. An alert clears itself when the metric recovers. Only production traffic is watched.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
import yaml

from .monitor import Finding
from .notify import sign

log = logging.getLogger("northcx.alerts")
METRICS = {
    "error_rate": lambda o: (o["errorRate"]["value"], o["errorRate"]["denominator"]),
    "escalation_rate": lambda o: (o["escalationRate"]["value"], o["escalationRate"]["denominator"]),
    "guardrail_block_rate": lambda o: (o["guardrailBlockRate"]["value"], o["guardrailBlockRate"]["denominator"]),
    "tool_error_rate": lambda o: (o["toolErrorRate"]["value"], o["toolErrorRate"]["denominator"]),
    "fallback_model_rate": lambda o: (o["fallbackModelRate"]["value"], o["fallbackModelRate"]["denominator"]),
    "p95_latency_seconds": lambda o: (o["latencySeconds"]["p95"], o["latencySeconds"]["samples"]),
}


class AlertConfigError(ValueError):
    pass


@dataclass
class AlertRule:
    name: str
    metric: str
    threshold: float
    window_minutes: int = 15
    min_samples: int = 20
    severity: str = "warning"
    cooldown_minutes: int = 60
    above: bool = True  # fire when the metric is above the threshold (False: below)

    def __post_init__(self) -> None:
        if self.metric not in METRICS:
            raise AlertConfigError(f"rule '{self.name}': metric must be one of {', '.join(sorted(METRICS))}")
        if self.severity not in ("warning", "critical") or not 1 <= self.window_minutes <= 1440 or self.min_samples < 1 or self.cooldown_minutes < 0:
            raise AlertConfigError(f"rule '{self.name}': severity warning or critical, window 1-1440 minutes, min_samples >= 1, cooldown >= 0")


DEFAULT_RULES = [
    AlertRule("error-rate-high", "error_rate", 0.10, severity="critical"),
    AlertRule("escalation-spike", "escalation_rate", 0.50),
    AlertRule("guardrail-blocks-spike", "guardrail_block_rate", 0.30),
    AlertRule("tool-failures-high", "tool_error_rate", 0.20),
    AlertRule("fallback-model-in-use", "fallback_model_rate", 0.20),
    AlertRule("slow-replies", "p95_latency_seconds", 30.0),
]


def load_rules(path: str | Path) -> list[AlertRule]:
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise AlertConfigError(f"cannot read alert rules {path}: {e}") from e
    items = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise AlertConfigError("the alert rules file needs a 'rules' list")
    rules, problems = [], []
    for i, r in enumerate(items, 1):
        try:
            if not isinstance(r, dict) or set(r) - {"name", "metric", "threshold", "window_minutes", "min_samples", "severity", "cooldown_minutes", "above"}:
                raise AlertConfigError(f"rule {i}: unknown settings")
            rules.append(AlertRule(**r))
        except (TypeError, AlertConfigError) as e:
            problems.append(str(e))
    if problems:
        raise AlertConfigError("; ".join(problems))
    if len({r.name for r in rules}) != len(rules):
        raise AlertConfigError("rule names must be unique")
    return rules


@dataclass
class ActiveAlert:
    rule: str
    since: float
    last_fired: float
    value: float
    samples: int
    severity: str


class WebhookAlerts:
    """Signed POST of each alert event (same scheme as the other webhooks). Failures are logged, not retried: the finding is the record."""

    def __init__(self, url: str, secret: str, client: httpx.AsyncClient | None = None):
        if not url.startswith(("https://", "http://")) or not secret:
            raise ValueError("NORTHCX_ALERT_WEBHOOK_URL must be an http(s) URL and needs NORTHCX_ALERT_WEBHOOK_SECRET")
        self.url, self.secret = url, secret
        self._client = client or httpx.AsyncClient(timeout=8.0, follow_redirects=False)

    async def send(self, event: dict[str, Any]) -> None:
        body = json.dumps(event, sort_keys=True).encode()
        ts = str(int(time.time()))
        r = await self._client.post(self.url, content=body, headers={"content-type": "application/json", "x-northcx-timestamp": ts,
                                                                        "x-northcx-signature": sign(self.secret, ts, body), "x-northcx-event": event["event"]})
        if r.status_code >= 300:
            raise RuntimeError(f"alert webhook returned {r.status_code}")


class AlertManager:
    def __init__(self, insights: Any, monitor_repo: Any, rules: list[AlertRule] | None = None, notifier: WebhookAlerts | None = None,
                 clock: Callable[[], float] = time.time):
        self.insights, self.monitor, self.rules, self.notifier, self.clock = insights, monitor_repo, rules or list(DEFAULT_RULES), notifier, clock
        self.active: dict[str, ActiveAlert] = {}
        self.events: list[dict[str, Any]] = []
        self.last_run: float | None = None

    async def _emit(self, event: str, rule: AlertRule, detail: str, value: float | None, samples: int, now: float) -> None:
        e = {"event": event, "rule": rule.name, "metric": rule.metric, "severity": rule.severity, "value": value, "threshold": rule.threshold,
             "samples": samples, "windowMinutes": rule.window_minutes, "at": now, "detail": detail}
        self.events.append(e)
        del self.events[:-200]
        try:
            await self.monitor.add([Finding(f"alert:{rule.name}" if event == "alert.fired" else f"alert_cleared:{rule.name}",
                                            rule.severity if event == "alert.fired" else "info", detail, "-", "-", "-")])
        except Exception:
            log.exception("could not record alert finding")
        if self.notifier is not None:
            try:
                await self.notifier.send(e)
            except Exception as ex:
                log.error("alert webhook failed: %s", type(ex).__name__)

    async def evaluate(self) -> list[dict[str, Any]]:
        now = self.clock()
        self.last_run = now
        fired: list[dict[str, Any]] = []
        windows: dict[int, dict[str, Any]] = {}
        for rule in self.rules:
            if rule.window_minutes not in windows:
                windows[rule.window_minutes] = await self.insights.overview(now - rule.window_minutes * 60, now)
            value, samples = METRICS[rule.metric](windows[rule.window_minutes])
            breached = value is not None and samples >= rule.min_samples and ((value > rule.threshold) if rule.above else (value < rule.threshold))
            cur = self.active.get(rule.name)
            unit = "s" if rule.metric.endswith("seconds") else ""
            if breached:
                detail = f"{rule.metric} is {value:.3g}{unit} (limit {rule.threshold:g}{unit}) over the last {rule.window_minutes} min, {samples} samples"
                if cur is None:
                    self.active[rule.name] = ActiveAlert(rule.name, now, now, value, samples, rule.severity)
                    await self._emit("alert.fired", rule, detail, value, samples, now)
                    fired.append(self.events[-1])
                else:
                    cur.value, cur.samples = value, samples
                    if now - cur.last_fired >= rule.cooldown_minutes * 60:  # still bad: remind, but not every minute
                        cur.last_fired = now
                        await self._emit("alert.fired", rule, detail + " (still firing)", value, samples, now)
                        fired.append(self.events[-1])
            elif cur is not None and (value is None or samples >= 1):
                del self.active[rule.name]
                await self._emit("alert.cleared", rule, f"{rule.metric} is back within its limit", value, samples, now)
        return fired

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "lastRun": self.last_run, "webhook": self.notifier is not None,
                "rules": [{"name": r.name, "metric": r.metric, "threshold": r.threshold, "windowMinutes": r.window_minutes, "minSamples": r.min_samples,
                           "severity": r.severity, "cooldownMinutes": r.cooldown_minutes} for r in self.rules],
                "active": [a.__dict__ for a in self.active.values()], "recent": self.events[-20:][::-1]}
