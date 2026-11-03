"""Scenarios kept in the database (Studio's scenario editor), alongside the scenario files.

File scenarios are read-only and win on a name clash. A managed scenario is validated exactly like a file one, runs in the same
simulations, and counts toward the release gate when it is marked required; editing one changes its digest, so earlier proof for
it no longer applies. Marking a scenario required, or changing or deleting a required one, weakens or strengthens the gate and
therefore needs a stronger permission than writing an ordinary scenario.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import yaml

from .scenario import Scenario, ScenarioError, parse_scenario


@dataclass
class ManagedScenario:
    name: str
    agent: str
    required: bool
    definition: dict[str, Any]
    created_by: str
    updated_by: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    revision: int = 1


class ScenarioRepo(Protocol):
    async def list(self) -> list[ManagedScenario]: ...
    async def get(self, name: str) -> ManagedScenario | None: ...
    async def put(self, scenario: Scenario, definition: dict[str, Any], by: str, now: float | None = None) -> tuple[ManagedScenario, bool]: ...
    async def delete(self, name: str) -> bool: ...


class InMemoryScenarios:
    def __init__(self) -> None:
        self.items: dict[str, ManagedScenario] = {}

    async def list(self) -> list[ManagedScenario]:
        return sorted(self.items.values(), key=lambda m: m.name)

    async def get(self, name) -> ManagedScenario | None:
        return self.items.get(name)

    async def put(self, scenario, definition, by, now=None):
        now = time.time() if now is None else now
        cur = self.items.get(scenario.name)
        m = ManagedScenario(scenario.name, scenario.agent, scenario.required, definition, cur.created_by if cur else by, by,
                            cur.created_at if cur else now, now, (cur.revision + 1) if cur else 1)
        self.items[scenario.name] = m
        return m, cur is None

    async def delete(self, name) -> bool:
        return self.items.pop(name, None) is not None


def parse_definition(source: str | dict[str, Any]) -> tuple[dict[str, Any], Scenario]:
    """Accept YAML/JSON text or a mapping and return (definition, validated scenario). Raises ScenarioError with the reason."""
    if isinstance(source, str):
        if len(source) > 100_000:
            raise ScenarioError("the scenario is larger than 100,000 characters")
        try:
            data = yaml.safe_load(source)
        except yaml.YAMLError as e:
            raise ScenarioError(f"not valid YAML or JSON: {e}") from e
    else:
        data = source
    if not isinstance(data, dict):
        raise ScenarioError("a scenario must be a mapping")
    data = {k: v for k, v in data.items() if k != "source"}
    return data, parse_scenario(data, "scenario")


def as_scenario(m: ManagedScenario) -> Scenario:
    sc = parse_scenario(m.definition, f"managed:{m.name}")
    sc.source = f"managed:{m.name}"
    return sc
