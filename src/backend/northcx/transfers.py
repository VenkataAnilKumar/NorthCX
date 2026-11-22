"""Multi-agent routing (R8): a conversation can be passed from one agent to a specialist.

An agent lists the specialists it may pass a conversation to and when (`routes`). It gets a `transfer_to_agent` tool limited to exactly those.
When the model uses it, the conversation continues in the same turn with the specialist's instructions, tools and checks, and later messages in
that conversation go to the specialist. Every transfer is on the trace. A turn can pass the conversation on at most a few times, so two agents
cannot hand it back and forth forever.
"""
from __future__ import annotations

import re
import time
from typing import Any, Protocol

from pydantic import BaseModel, Field

TRANSFER = "transfer_to_agent"
MAX_TRANSFERS_PER_TURN = 3
AGENT_ID = r"^[A-Za-z0-9_.-]+$"


class RouteSpec(BaseModel):
    agent: str = Field(pattern=AGENT_ID, max_length=100)
    when: str = Field(min_length=1, max_length=300)  # plain-language description of the conversations this specialist takes
    model_config = {"extra": "forbid"}


def transfer_spec(routes: list[RouteSpec]) -> dict[str, Any]:
    listing = "; ".join(f"{r.agent}: {r.when}" for r in routes)
    return {
        "name": TRANSFER,
        "description": f"Pass the conversation to a specialist agent who is better placed to help. Only use it when one of these clearly applies. {listing}",
        "input_schema": {"type": "object", "properties": {"agent": {"type": "string", "enum": [r.agent for r in routes]}, "reason": {"type": "string"}},
                         "required": ["agent", "reason"]},
    }


def handover_note(source: str, reason: str) -> str:
    return (f"\n\nThis conversation was passed to you from the '{source}' agent. Reason: {reason.strip()[:300] or 'not given'}. "
            "Carry on helping the customer from where it stands; do not greet them again or ask for what they already told you.")


class SessionRoutes(Protocol):
    async def get(self, session_id: str) -> str | None: ...
    async def set(self, session_id: str, agent_id: str) -> None: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemorySessionRoutes:
    def __init__(self) -> None:
        self.items: dict[str, tuple[str, float]] = {}

    async def get(self, session_id: str) -> str | None:
        found = self.items.get(session_id)
        return found[0] if found else None

    async def set(self, session_id: str, agent_id: str) -> None:
        self.items[session_id] = (agent_id, time.time())

    async def erase_session(self, session_id: str) -> int:
        return 1 if self.items.pop(session_id, None) else 0


def check_routes(own_id: str, routes: list[RouteSpec]) -> list[str]:
    problems = []
    seen = [r.agent for r in routes]
    if len(set(seen)) != len(seen):
        problems.append("The same specialist is listed more than once. Remove the repeats so each specialist appears once.")
    if own_id in seen:
        problems.append("An agent cannot hand a conversation to itself. Remove this agent from its own list of specialists.")
    return problems


def valid_id(value: str) -> bool:
    return bool(re.fullmatch(AGENT_ID, value))
