"""Stored simulation runs. A run records what was tested (agent digests, scenario digests) so a later release gate can
tell whether a given agent version really passed the scenarios that matter."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SimRun:
    mode: str
    passed: bool
    counts: dict[str, int]
    agent_digests: dict[str, str]
    results: list[dict[str, Any]]
    seconds: float = 0.0
    source: str = "api"  # api | cli | ci
    meta: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


class SimRunRepo(Protocol):
    async def add(self, run: SimRun) -> SimRun: ...
    async def get(self, run_id: str) -> SimRun | None: ...
    async def list(self, limit: int = 50) -> list[SimRun]: ...


class InMemorySimRuns:
    def __init__(self) -> None:
        self._runs: dict[str, SimRun] = {}

    async def add(self, run: SimRun) -> SimRun:
        self._runs[run.id] = run
        return run

    async def get(self, run_id: str) -> SimRun | None:
        return self._runs.get(run_id)

    async def list(self, limit: int = 50) -> list[SimRun]:
        return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)[:limit]


def run_from_suite(suite: Any, source: str = "api", meta: dict[str, Any] | None = None) -> SimRun:
    d = suite.to_dict()
    return SimRun(mode=d["mode"], passed=d["passed"], counts=d["counts"], agent_digests=d["agentDigests"],
                  results=d["results"], seconds=d["seconds"], source=source, meta=meta or {})
