"""Messages the platform sends to a customer outside a request/response cycle (for example after an approval).

Each message is stored first, so channels can poll for it, and optionally pushed to a signed webhook."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class OutboxMessage:
    session_id: str
    kind: str  # approval_result | approval_expired
    payload: dict[str, Any]
    id: int = 0
    created_at: float = field(default_factory=time.time)
    delivered_at: float | None = None
    attempts: int = 0


class OutboxRepo(Protocol):
    async def add(self, session_id: str, kind: str, payload: dict[str, Any]) -> OutboxMessage: ...
    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]: ...
    async def undelivered(self, limit: int = 100) -> list[OutboxMessage]: ...
    async def record_attempt(self, message_id: int, delivered: bool) -> None: ...


class InMemoryOutbox:
    def __init__(self) -> None:
        self._items: list[OutboxMessage] = []

    async def add(self, session_id: str, kind: str, payload: dict[str, Any]) -> OutboxMessage:
        m = OutboxMessage(session_id, kind, payload, id=len(self._items) + 1)
        self._items.append(m)
        return m

    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]:
        return [m for m in self._items if m.session_id == session_id and m.id > after_id][:limit]

    async def undelivered(self, limit: int = 100) -> list[OutboxMessage]:
        return [m for m in self._items if m.delivered_at is None][:limit]

    async def record_attempt(self, message_id: int, delivered: bool) -> None:
        m = self._items[message_id - 1]
        m.attempts += 1
        if delivered:
            m.delivered_at = time.time()


class Notifier(Protocol):
    async def deliver(self, message: OutboxMessage) -> None:
        """Raise on failure."""


class Outbox:
    """Stores a message, then tries to push it. A failed push leaves it undelivered for `flush` to retry."""

    def __init__(self, repo: OutboxRepo | None = None, notifier: Notifier | None = None):
        self.repo = repo or InMemoryOutbox()
        self.notifier = notifier

    async def publish(self, session_id: str, kind: str, payload: dict[str, Any]) -> OutboxMessage:
        m = await self.repo.add(session_id, kind, payload)
        if self.notifier:
            await self._push(m)
        return m

    async def _push(self, m: OutboxMessage) -> bool:
        try:
            await self.notifier.deliver(m)  # type: ignore[union-attr]
        except Exception:
            await self.repo.record_attempt(m.id, False)
            return False
        await self.repo.record_attempt(m.id, True)
        return True

    async def flush(self) -> int:
        """Retry every undelivered message; returns how many were delivered."""
        if not self.notifier:
            return 0
        return sum([await self._push(m) for m in await self.repo.undelivered()])

    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]:
        return await self.repo.list(session_id, after_id, limit)
