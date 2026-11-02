"""Runs the scenario suite on request and records the result. One run at a time per process."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from ..agent import Agent
from ..spec import AgentSpec
from ..types import LLM
from .gate import GateStatus, evaluate_gate
from .runner import AgentFactory, SimConfig, SimulationRunner
from .scenario import Scenario
from .store import SimRun, SimRunRepo, run_from_suite


class Busy(RuntimeError):
    pass


class SimulationService:
    def __init__(self, scenarios: list[Scenario], agent_factory: AgentFactory, runs: SimRunRepo,
                 agent_digests: dict[str, str], live_llm: LLM | None = None, judge_llm: LLM | None = None,
                 spec_builder: Callable[[AgentSpec, LLM], Agent] | None = None):
        self.scenarios, self.agent_factory, self.runs = scenarios, agent_factory, runs
        self.spec_builder = spec_builder
        self.agent_digests, self.live_llm, self.judge_llm = agent_digests, live_llm, judge_llm
        self._lock = asyncio.Lock()

    @property
    def modes(self) -> list[str]:
        return ["scripted", "demo"] + (["live"] if self.live_llm else [])

    async def run(self, mode: str = "scripted", only: str | None = None, skip_judge: bool = False, source: str = "api",
                  meta: dict[str, Any] | None = None, spec: AgentSpec | None = None) -> SimRun:
        """Run scenarios. With `spec`, only that agent's scenarios run, against that exact spec (a version to be released)."""
        if mode not in self.modes:
            raise ValueError(f"mode '{mode}' is not available (have: {', '.join(self.modes)})")
        chosen = [s for s in self.scenarios if (not only or only in s.name) and (spec is None or s.agent == spec.id)]
        if not chosen:
            raise ValueError(f"no scenario name contains {only!r}" if only else "no scenarios for this agent")
        factory, digests = self.agent_factory, self.agent_digests
        if spec is not None:
            if self.spec_builder is None:
                raise ValueError("running a specific version is not configured")
            build = self.spec_builder
            factory = lambda agent_id, llm: build(spec, llm)  # noqa: E731
            digests = {spec.id: spec.digest()}
            meta = {**(meta or {}), "agent": spec.id}
        if self._lock.locked():
            raise Busy("a simulation run is already in progress")
        async with self._lock:
            cfg = SimConfig(mode, self.live_llm, self.judge_llm, skip_judge)
            suite = await SimulationRunner(factory, cfg, digests).run_suite(chosen)
            return await self.runs.add(run_from_suite(suite, source, meta))

    async def gate(self, agent_id: str) -> GateStatus:
        return await self.gate_for(agent_id, self.agent_digests.get(agent_id))

    async def gate_for(self, agent_id: str, digest: str | None) -> GateStatus:
        return evaluate_gate(agent_id, digest, self.scenarios, await self.runs.list(100))
