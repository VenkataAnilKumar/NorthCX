"""The release gate: has this exact agent version passed every required scenario?

A pass only counts when it was recorded for the same agent digest and the same scenario definition, with a model that
exercises the agent (scripted or live; the offline demo model proves nothing), and with no check skipped."""
from __future__ import annotations

from dataclasses import dataclass, field

from .scenario import Scenario
from .store import SimRun

COUNTING_MODES = {"scripted", "live"}


@dataclass
class GateStatus:
    agent_id: str
    agent_digest: str | None
    satisfied: bool
    required: int
    covered: int
    reasons: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)


def evaluate_gate(agent_id: str, agent_digest: str | None, scenarios: list[Scenario], runs: list[SimRun],
                  allow_empty: bool = False) -> GateStatus:
    """`runs` must be newest first. Each required scenario is judged by its most recent matching result."""
    required = [s for s in scenarios if s.agent == agent_id and s.required]
    status = GateStatus(agent_id, agent_digest, False, len(required), 0)
    if agent_digest is None:
        status.reasons.append(f"agent '{agent_id}' has no spec digest, so a pass cannot be tied to a version")
        return status
    if not required:
        if allow_empty:
            status.satisfied = True
        else:
            status.reasons.append(f"agent '{agent_id}' has no required scenarios")
        return status
    for sc in required:
        match = None
        for run in runs:
            if run.mode not in COUNTING_MODES:
                continue
            for r in run.results:
                if r["name"] == sc.name and r.get("scenario_digest") == sc.digest() and r.get("agent_digest") == agent_digest:
                    match = (run, r)
                    break
            if match:
                break
        if match is None:
            status.reasons.append(f"{sc.name}: not run against this agent version and scenario definition")
            continue
        run, r = match
        if not r["passed"]:
            status.reasons.append(f"{sc.name}: failed in run {run.id[:8]}")
        elif any("skipped" in n for n in r.get("notes", [])):
            status.reasons.append(f"{sc.name}: a check was skipped in run {run.id[:8]}")
        else:
            status.covered += 1
            if run.id not in status.run_ids:
                status.run_ids.append(run.id)
    status.satisfied = status.covered == status.required
    return status
