from __future__ import annotations

import copy
from typing import Protocol

from .types import Message


class MemoryStore(Protocol):
    """Session history and per-customer facts. Swap for Postgres in production."""

    async def load_messages(self, session_id: str) -> list[Message]: ...
    async def save_messages(self, session_id: str, messages: list[Message]) -> None: ...
    async def get_facts(self, customer_id: str) -> dict[str, str]: ...
    async def set_fact(self, customer_id: str, key: str, value: str) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._msgs: dict[str, list[Message]] = {}
        self._facts: dict[str, dict[str, str]] = {}

    async def load_messages(self, session_id: str) -> list[Message]:
        return copy.deepcopy(self._msgs.get(session_id, []))

    async def save_messages(self, session_id: str, messages: list[Message]) -> None:
        self._msgs[session_id] = copy.deepcopy(messages)

    async def get_facts(self, customer_id: str) -> dict[str, str]:
        return dict(self._facts.get(customer_id, {}))

    async def set_fact(self, customer_id: str, key: str, value: str) -> None:
        self._facts.setdefault(customer_id, {})[key] = value
