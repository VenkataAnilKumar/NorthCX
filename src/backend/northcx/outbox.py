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
    last_attempt_at: float | None = None


class OutboxRepo(Protocol):
    async def add(self, session_id: str, kind: str, payload: dict[str, Any]) -> OutboxMessage: ...
    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]: ...
    async def undelivered(self, limit: int = 100, max_attempts: int | None = None) -> list[OutboxMessage]: ...
    async def record_attempt(self, message_id: int, delivered: bool, at: float | None = None) -> None: ...


class InMemoryOutbox:
    def __init__(self) -> None:
        self._items: list[OutboxMessage] = []

    async def add(self, session_id: str, kind: str, payload: dict[str, Any]) -> OutboxMessage:
        m = OutboxMessage(session_id, kind, payload, id=len(self._items) + 1)
        self._items.append(m)
        return m

    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]:
        return [m for m in self._items if m.session_id == session_id and m.id > after_id][:limit]

    async def undelivered(self, limit: int = 100, max_attempts: int | None = None) -> list[OutboxMessage]:
        return [m for m in self._items if m.delivered_at is None and (max_attempts is None or m.attempts < max_attempts)][:limit]

    async def record_attempt(self, message_id: int, delivered: bool, at: float | None = None) -> None:
        at = at if at is not None else time.time()
        m = self._items[message_id - 1]
        m.attempts += 1
        m.last_attempt_at = at
        if delivered:
            m.delivered_at = at


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

    async def _push(self, m: OutboxMessage, now: float | None = None) -> bool:
        try:
            await self.notifier.deliver(m)  # type: ignore[union-attr]
        except Exception:
            await self.repo.record_attempt(m.id, False, now)
            return False
        await self.repo.record_attempt(m.id, True, now)
        return True

    async def flush(self, now: float | None = None, max_attempts: int = 12) -> int:
        """Retry undelivered messages whose back-off has passed (30 s, doubling to an hour, between attempts), giving up
        after `max_attempts` (the message stays stored and visible). Returns how many were delivered."""
        if not self.notifier:
            return 0
        now = now if now is not None else time.time()
        due = [m for m in await self.repo.undelivered(200, max_attempts)
               if m.last_attempt_at is None or now - m.last_attempt_at >= min(30 * 2 ** max(m.attempts - 1, 0), 3600)]
        return sum([await self._push(m, now) for m in due])

    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]:
        return await self.repo.list(session_id, after_id, limit)
