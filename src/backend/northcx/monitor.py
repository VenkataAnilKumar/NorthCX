"""Always-on monitoring: every finished conversation turn is checked by deterministic rules, not a sample.

Rules read the trace only (no model calls, no extra cost, nothing sent anywhere). A finding is a flag for people to
look at; monitoring never changes what the customer is told. A broken rule or store never breaks a conversation.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol

from .trace import Trace

log = logging.getLogger("northcx.monitor")
SEVERITIES = ("info", "warning", "critical")


@dataclass
class Finding:
    rule: str
    severity: str
    detail: str
    trace_id: str
    session_id: str
    agent_id: str
    agent_version: int | None = None
    created_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Observation:
    """What a rule sees about one finished turn."""
    trace: Trace
    status: str
    trigger: str | None = None


Rule = Callable[[Observation], "list[tuple[str, str]]"]  # -> [(severity, detail)]

_ANGRY = re.compile(r"\b(ridiculous|unacceptable|worst|useless|furious|outraged|scam|fraud|lawyer|sue you|disgusting|terrible service)\b|!{3,}", re.I)


def escalation(o: Observation) -> list[tuple[str, str]]:
    if o.status != "escalated":
        return []
    sev = "warning" if o.trigger in ("step_limit", "supervisor_rejections") else "info"
    return [(sev, f"Handed to a person ({o.trigger or 'agent_handoff'})")]


def guardrail_hits(o: Observation) -> list[tuple[str, str]]:
    out = []
    for e in o.trace.events:
        if e.type == "guardrail" and e.data.get("reason") and "masked" not in str(e.data["reason"]).lower():
            out.append(("warning", f"{e.data.get('guardrail', 'guardrail')} ({e.data.get('stage', 'reply')}): {e.data['reason']}"[:300]))
    return out


def tool_errors(o: Observation) -> list[tuple[str, str]]:
    return [("warning", f"Tool '{e.data.get('tool', '?')}' failed") for e in o.trace.events if e.type == "error"]


def repeated_calls(o: Observation) -> list[tuple[str, str]]:
    calls = Counter((e.data.get("name"), repr(sorted((e.data.get("input") or {}).items()))) for e in o.trace.events if e.type == "tool_call")
    return [("warning", f"'{name}' called {n} times with the same input") for (name, _), n in calls.items() if n >= 3]


def frustration(o: Observation) -> list[tuple[str, str]]:
    for e in o.trace.events:
        if e.type == "user" and _ANGRY.search(str(e.data.get("message", ""))):
            return [("warning", "Customer sounds frustrated")]
    return []


def approvals_requested(o: Observation) -> list[tuple[str, str]]:
    return [("info", f"Approval requested for '{e.data.get('tool', '?')}'") for e in o.trace.events if e.type == "approval"]


DEFAULT_RULES: dict[str, Rule] = {
    "escalation": escalation, "guardrail_hit": guardrail_hits, "tool_error": tool_errors,
    "repeated_tool_call": repeated_calls, "frustrated_customer": frustration, "approval_requested": approvals_requested,
}


class MonitorRepo(Protocol):
    async def add(self, findings: list[Finding]) -> None: ...
    async def list(self, *, rule: str | None = None, severity: str | None = None, agent_id: str | None = None,
                   session_id: str | None = None, since: float | None = None, limit: int = 100) -> list[Finding]: ...
    async def counts(self, since: float | None = None) -> dict[str, dict[str, int]]: ...


class InMemoryMonitor:
    def __init__(self) -> None:
        self.items: list[Finding] = []

    async def add(self, findings: list[Finding]) -> None:
        self.items.extend(findings)

    async def list(self, *, rule=None, severity=None, agent_id=None, session_id=None, since=None, limit=100) -> list[Finding]:
        rows = [f for f in self.items if (not rule or f.rule == rule) and (not severity or f.severity == severity)
                and (not agent_id or f.agent_id == agent_id) and (not session_id or f.session_id == session_id)
                and (since is None or f.created_at >= since)]
        return sorted(rows, key=lambda f: f.created_at, reverse=True)[:limit]

    async def counts(self, since: float | None = None) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for f in self.items:
            if since is None or f.created_at >= since:
                out.setdefault(f.rule, {}).setdefault(f.severity, 0)
                out[f.rule][f.severity] += 1
        return out


class Monitor:
    def __init__(self, repo: MonitorRepo | None = None, rules: dict[str, Rule] | None = None):
        self.repo = repo or InMemoryMonitor()
        self.rules = dict(DEFAULT_RULES if rules is None else rules)

    async def observe(self, trace: Trace, status: str, trigger: str | None = None) -> list[Finding]:
        obs, found = Observation(trace, status, trigger), []
        for name, rule in self.rules.items():
            try:
                for sev, detail in rule(obs):
                    found.append(Finding(name, sev if sev in SEVERITIES else "warning", detail, trace.id, trace.session_id,
                                         trace.agent_id, trace.agent_version))
            except Exception:  # a broken rule must not break the conversation, and must itself be visible
                log.exception("monitor rule %s failed", name)
                found.append(Finding("monitor_error", "warning", f"Rule '{name}' failed", trace.id, trace.session_id, trace.agent_id, trace.agent_version))
        if found:
            try:
                await self.repo.add(found)
            except Exception:
                log.exception("could not store monitor findings")
        return found
