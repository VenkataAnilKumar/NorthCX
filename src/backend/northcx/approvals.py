from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Approval:
    trace_id: str
    session_id: str
    tool: str
    input: Any
    reason: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: str = "pending"  # pending|approved|rejected
    created_at: float = field(default_factory=time.time)
    decided_by: str | None = None
    decided_at: float | None = None


class ApprovalRepo(Protocol):
    async def add(self, **kw: Any) -> Approval: ...
    async def get(self, approval_id: str) -> Approval | None: ...
    async def list(self, state: str | None = None) -> list[Approval]: ...
    async def decide(self, approval_id: str, approved: bool, by: str) -> Approval: ...


class ApprovalStore:
    """In-memory approvals. Resuming a run after a decision is not implemented yet (Phase 2, sprint 6)."""

    def __init__(self) -> None:
        self._items: dict[str, Approval] = {}

    async def add(self, **kw: Any) -> Approval:
        a = Approval(**kw)
        self._items[a.id] = a
        return a

    async def get(self, approval_id: str) -> Approval | None:
        return self._items.get(approval_id)

    async def list(self, state: str | None = None) -> list[Approval]:
        return sorted((a for a in self._items.values() if not state or a.state == state), key=lambda a: a.created_at)

    async def decide(self, approval_id: str, approved: bool, by: str) -> Approval:
        a = self._items.get(approval_id)
        if a is None:
            raise KeyError(f"Unknown approval {approval_id}")
        if a.state != "pending":
            raise ValueError(f"Approval {approval_id} already {a.state}")
        a.state = "approved" if approved else "rejected"
        a.decided_by, a.decided_at = by, time.time()
        return a
