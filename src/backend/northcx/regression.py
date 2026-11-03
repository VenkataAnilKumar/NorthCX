"""Regression testing from real conversations (Q5) and re-running simulations when knowledge changes (Q7)."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import yaml

from .monitor import Finding
from .simulation.scenario import Scenario, ScenarioError, parse_scenario
from .trace import Trace
from .trace_export import Redactor

log = logging.getLogger("northcx.regression")
_MASK = Redactor("masked")


@dataclass
class Draft:
    scenario: dict[str, Any]
    yaml: str
    warnings: list[str] = field(default_factory=list)


def scenario_from_traces(traces: list[Trace], session_id: str) -> Draft:
    """Turn the recorded turns of one conversation into a scenario draft: the customer's messages, a scripted replay of what
    the model did, and expectations about the outcome. Personal data is masked. The draft is for a person to review: it is
    not required, so it never blocks a release until someone sets `required: true`."""
    if not traces:
        raise ScenarioError("this conversation has no recorded turns")
    traces = sorted(traces, key=lambda t: t.events[0].t if t.events else 0)
    agent = traces[0].agent_id
    warnings: list[str] = []
    model: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    for t in traces:
        if t.agent_id != agent:
            warnings.append(f"turns by another agent ('{t.agent_id}') were left out")
            continue
        user = next((e for e in t.events if e.type == "user"), None)
        if user is None:
            warnings.append("a platform-written turn (for example an approval outcome) was skipped")
            continue
        status = t.status()
        expect: dict[str, Any] = {"status": status}
        called = [e.data["name"] for e in t.events if e.type == "tool_call" and e.data.get("name") != "handoff_to_human"]
        if called:
            expect["tools_called"] = list(dict.fromkeys(called))
        hits = sorted({e.data["guardrail"] for e in t.events if e.type == "guardrail" and e.data.get("guardrail") and e.data.get("stage") != "tool_output"})
        if hits:
            expect["guardrail_hits"] = hits
        if status == "needs_approval":
            warnings.append("a held action needs a 'decide' step with the reviewer's decision; add one if you want to cover what happens next")
        calls = 0
        for e in t.events:
            if e.type == "tool_call":
                if e.data.get("name") == "handoff_to_human":
                    model.append({"tool_call": {"name": "handoff_to_human", "input": _MASK.value(e.data.get("input") or {})}})
                else:
                    model.append({"tool_call": {"name": e.data["name"], "input": _MASK.value(e.data.get("input") or {}, "input")}})
                calls += 1
            elif e.type == "reply" and status == "completed":
                model.append({"text": _MASK.text(str(e.data.get("reply", "")))})
                calls += 1
        llm_calls = sum(1 for e in t.events if e.type == "llm")
        if llm_calls > calls:
            warnings.append("a model draft was rejected or rewritten in this conversation; rejected drafts are not recorded, so the script may not replay exactly")
        reply = next((e.data.get("reply") for e in reversed(t.events) if e.type == "reply"), "")
        if status == "escalated":
            reason = next((e.data.get("reason") for e in t.events if e.type == "handoff"), None)
            if reason:
                expect["handoff"] = {}
        turns.append({"say": _MASK.text(str(user.data.get("message", ""))), "expect": expect})
        del reply
    if not turns:
        raise ScenarioError("no customer messages were recorded")
    data: dict[str, Any] = {
        "name": f"regression-{session_id[-8:].lower().replace('_', '-')}"[:60],
        "description": f"Drafted from conversation {session_id} ({len(turns)} turn(s)) on {time.strftime('%Y-%m-%d', time.gmtime())}. Review the expectations before relying on it.",
        "agent": agent, "required": False, "tags": ["regression"], "model": model or None, "turns": turns}
    data = {k: v for k, v in data.items() if v is not None}
    try:
        parse_scenario(data, "draft")  # a draft that would not load is not worth showing
    except ScenarioError as e:
        raise ScenarioError(f"could not build a valid scenario from this conversation: {e}") from e
    return Draft(data, yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), list(dict.fromkeys(warnings)))


class RegressionRunner:
    """Re-runs tagged scenarios after the knowledge changes. Changes arriving close together are batched into one run, and a
    run in progress asks for one more afterwards instead of overlapping. A failing run is raised as a critical monitoring finding."""

    def __init__(self, simulations: Any, monitor_repo: Any, mode: str = "scripted", tag: str = "knowledge", debounce: float = 60.0):
        if mode not in ("scripted", "live"):
            raise ValueError("mode must be 'scripted' or 'live'")
        self.sim, self.monitor, self.mode, self.tag, self.debounce = simulations, monitor_repo, mode, tag, debounce
        self._task: asyncio.Task | None = None
        self._again = False
        self.reasons: set[str] = set()
        self.last: dict[str, Any] | None = None

    def trigger(self, reason: str) -> None:
        self.reasons.add(reason)
        if self._task is not None and not self._task.done():
            self._again = True
            return
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            self._again = False
            await asyncio.sleep(self.debounce)
            reasons, self.reasons = sorted(self.reasons), set()
            await self.run_now(reasons)
            if not (self._again or self.reasons):
                return

    async def run_now(self, reasons: list[str]) -> dict[str, Any]:
        started = time.time()
        try:
            run = await self.sim.run(self.mode, tag=self.tag, skip_judge=self.mode == "scripted", source="regression", meta={"trigger": "knowledge", "reasons": reasons[:10]})
        except Exception as e:  # nothing tagged, a run already in progress, a model outage
            self.last = {"at": started, "ok": None, "mode": self.mode, "reasons": reasons, "note": str(e)[:200]}
            return self.last
        failed = [r for r in run.results if not r.get("passed", False)]
        ok = not failed  # every tagged scenario counts here, required or not
        self.last = {"at": started, "ok": ok, "mode": self.mode, "reasons": reasons, "runId": run.id,
                     "scenarios": len(run.results), "failed": [r.get("name") for r in failed][:20]}
        if not ok:
            await self.monitor.add([Finding("regression_failed", "critical",
                                            f"{len(failed)} of {len(run.results)} scenarios failed after knowledge changed ({', '.join(reasons)[:150]})",
                                            run.id, "-", "-")])
        return self.last

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "mode": self.mode, "tag": self.tag, "debounceSeconds": self.debounce,
                "pending": self._task is not None and not self._task.done(), "last": self.last}
