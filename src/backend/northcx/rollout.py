"""Staged rollouts (Q11): send a share of new conversations to a candidate version while the rest keep the live one, then compare.

A conversation is assigned to an arm (control or candidate) once, when it first reaches the agent, and keeps that arm for its whole life,
even if the share changes later. Only one rollout can run per agent and environment, and publishing or rolling back in that environment
is refused until it ends, so "control" always means the same thing. Promoting releases the candidate to everyone through the normal gate.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .insights import FeedbackFacts, HandoffFacts, TurnFacts, compute
from .reviews import Review, quality
from .versions import Conflict, GateBlocked, NotFound, ReleaseService, check_environment

ROLLOUT_ENVIRONMENTS = ("staging", "production")
MIN_PERCENT, MAX_PERCENT = 1, 99
ENOUGH = 30  # conversations per arm before the comparison is worth reading
CONTROL, CANDIDATE = "control", "candidate"


@dataclass
class Rollout:
    agent_id: str
    environment: str
    candidate_number: int
    control_number: int | None  # None: the baseline spec file
    percent: int
    started_by: str
    note: str | None = None
    state: str = "active"  # active | promoted | aborted
    ended_by: str | None = None
    ended_at: float | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.time)


class RolloutRepo(Protocol):
    async def add(self, r: Rollout) -> None: ...
    async def save(self, r: Rollout) -> None: ...
    async def active(self, agent_id: str, environment: str) -> Rollout | None: ...
    async def get(self, rollout_id: str) -> Rollout | None: ...
    async def history(self, agent_id: str, limit: int = 50) -> list[Rollout]: ...
    async def assign(self, rollout_id: str, session_id: str, arm: str) -> str: ...  # the arm the conversation actually has
    async def arm_sessions(self, rollout_id: str, limit: int = 5000) -> dict[str, list[str]]: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryRollouts:
    def __init__(self) -> None:
        self.items: dict[str, Rollout] = {}
        self.assigned: dict[tuple[str, str], str] = {}

    async def add(self, r: Rollout) -> None:
        if await self.active(r.agent_id, r.environment) is not None:
            raise Conflict(f"A rollout is already running for {r.agent_id} in {r.environment}")
        self.items[r.id] = r

    async def save(self, r: Rollout) -> None:
        self.items[r.id] = r

    async def active(self, agent_id, environment) -> Rollout | None:
        return next((r for r in self.items.values() if r.agent_id == agent_id and r.environment == environment and r.state == "active"), None)

    async def get(self, rollout_id) -> Rollout | None:
        return self.items.get(rollout_id)

    async def history(self, agent_id, limit=50) -> list[Rollout]:
        return sorted((r for r in self.items.values() if r.agent_id == agent_id), key=lambda r: -r.started_at)[:limit]

    async def assign(self, rollout_id, session_id, arm) -> str:
        return self.assigned.setdefault((rollout_id, session_id), arm)

    async def arm_sessions(self, rollout_id, limit=5000) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {CONTROL: [], CANDIDATE: []}
        for (rid, sid), arm in self.assigned.items():
            if rid == rollout_id and len(out[arm]) < limit:
                out[arm].append(sid)
        return out

    async def erase_session(self, session_id) -> int:
        keys = [k for k in self.assigned if k[1] == session_id]
        for k in keys:
            del self.assigned[k]
        return len(keys)


def bucket(rollout_id: str, session_id: str) -> float:
    """A stable position from 0 to 100 for this conversation in this rollout."""
    return int(hashlib.sha256(f"{rollout_id}:{session_id}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF * 100


def check_percent(percent: int) -> int:
    if not MIN_PERCENT <= percent <= MAX_PERCENT:
        raise ValueError(f"The share must be between {MIN_PERCENT} and {MAX_PERCENT} percent")
    return percent


class RolloutService:
    def __init__(self, repo: RolloutRepo, releases: ReleaseService):
        self.repo, self.releases = repo, releases
        releases.rollouts, releases.rollout_service = repo, self  # publishing and rolling back consult it; live agents ask it for the arm

    async def start(self, agent_id: str, candidate: int, percent: int, by: str, environment: str = "production", note: str | None = None) -> Rollout:
        if environment not in ROLLOUT_ENVIRONMENTS:
            raise ValueError(f"Rollouts run in {' or '.join(ROLLOUT_ENVIRONMENTS)}")
        check_percent(percent)
        check_environment(environment)
        if await self.repo.active(agent_id, environment) is not None:
            raise Conflict(f"A rollout is already running for {agent_id} in {environment}; end it first")
        cl = await self.releases.checklist(agent_id, candidate, environment)  # raises NotFound for an unknown version
        failed = [c["detail"] or c["title"] for c in cl["checks"] if c["status"] == "fail" and c["key"] != "permission"]
        if failed:
            raise GateBlocked(failed)
        live_v, _ = await self.releases.live(agent_id, environment)
        r = Rollout(agent_id, environment, candidate, live_v.number if live_v else None, percent, by, note)
        await self.repo.add(r)
        return r

    async def _active(self, agent_id: str, rollout_id: str) -> Rollout:
        r = await self.repo.get(rollout_id)
        if r is None or r.agent_id != agent_id:
            raise NotFound("Unknown rollout")
        if r.state != "active":
            raise Conflict(f"This rollout already ended ({r.state})")
        return r

    async def set_percent(self, agent_id: str, rollout_id: str, percent: int) -> Rollout:
        r = await self._active(agent_id, rollout_id)
        r.percent = check_percent(percent)
        await self.repo.save(r)
        return r

    async def abort(self, agent_id: str, rollout_id: str, by: str) -> Rollout:
        r = await self._active(agent_id, rollout_id)
        r.state, r.ended_by, r.ended_at = "aborted", by, time.time()
        await self.repo.save(r)
        return r

    async def promote(self, agent_id: str, rollout_id: str, by: str, note: str | None = None) -> Rollout:
        """Release the candidate to everyone. The normal gate applies; if it fails, the rollout keeps running."""
        r = await self._active(agent_id, rollout_id)
        await self.releases.publish(agent_id, r.candidate_number, by, note or f"promoted after a {r.percent}% rollout", r.environment, during_rollout=True)
        r.state, r.ended_by, r.ended_at = "promoted", by, time.time()
        await self.repo.save(r)
        return r

    async def choose(self, agent_id: str, environment: str, session_id: str) -> tuple[Rollout, str] | None:
        """Which arm this conversation is on, if a rollout is running here."""
        r = await self.repo.active(agent_id, environment)
        if r is None:
            return None
        arm = CANDIDATE if bucket(r.id, session_id) < r.percent else CONTROL
        return r, await self.repo.assign(r.id, session_id, arm)


def rollout_json(r: Rollout) -> dict[str, Any]:
    return {"id": r.id, "agentId": r.agent_id, "environment": r.environment, "candidateVersion": r.candidate_number, "controlVersion": r.control_number,
            "percent": r.percent, "state": r.state, "startedBy": r.started_by, "startedAt": r.started_at, "endedBy": r.ended_by, "endedAt": r.ended_at, "note": r.note}


def compare(arms: dict[str, list[str]], turns: list[TurnFacts], handoffs: list[HandoffFacts], feedback: list[FeedbackFacts],
            reviews: dict[str, Review], since: float, until: float) -> dict[str, Any]:
    """The same measures for each arm, with how many conversations each is based on. No significance is claimed."""
    out: dict[str, Any] = {}
    for arm, sessions in arms.items():
        ids = set(sessions)
        t = [x for x in turns if x.session_id in ids]
        m = compute(t, [h for h in handoffs if h.session_id in ids], [f for f in feedback if f.session_id in ids], since, until)
        q = quality([r for s, r in reviews.items() if s in ids])
        out[arm] = {"assigned": len(ids), "conversations": m["conversations"], "containmentRate": m["containmentRate"], "escalationRate": m["escalationRate"],
                    "guardrailBlockRate": m["guardrailBlockRate"], "toolErrorRate": m["toolErrorRate"], "satisfaction": m["satisfaction"]["average"],
                    "ratings": m["satisfaction"]["responses"], "tokensPerConversation": m["tokens"]["perConversation"],
                    "reviewed": q["reviewed"], "judgedCorrect": q["correctRate"]}
    enough = all(a["conversations"] >= ENOUGH for a in out.values())
    return {"arms": out, "enoughData": enough,
            "note": (f"Each arm has at least {ENOUGH} conversations, but differences can still be chance; check the numerators before acting." if enough else
                     f"Fewer than {ENOUGH} conversations in at least one arm: treat differences as noise.")}
