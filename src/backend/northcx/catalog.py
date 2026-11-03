"""Where the server finds the agent to run. Static for tests; versioned (see versions.LiveAgents) in production."""
from __future__ import annotations

from typing import Any, Protocol

from .agent import Agent


class AgentUnavailable(RuntimeError):
    """The agent exists but cannot be loaded right now (for example its live version no longer builds)."""


class AgentProvider(Protocol):
    async def get(self, agent_id: str, environment: str = "production", session_id: str | None = None) -> Agent | None: ...
    async def all(self) -> list[Agent]: ...


class StaticAgents:
    def __init__(self, agents: dict[str, Agent]):
        self._agents = agents

    async def get(self, agent_id: str, environment: str = "production", session_id: str | None = None) -> Agent | None:
        return self._agents.get(agent_id)  # a plain set of agents has one environment

    async def all(self) -> list[Agent]:
        return list(self._agents.values())


def as_provider(agents: Any) -> AgentProvider:
    """Accept a plain dict of agents (convenient in tests) or a provider."""
    return StaticAgents(agents) if isinstance(agents, dict) else agents
