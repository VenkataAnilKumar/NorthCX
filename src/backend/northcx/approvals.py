from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

# pending -> approved -> executing -> executed | failed
# pending -> rejected | expired
PENDING, APPROVED, REJECTED, EXPIRED, EXECUTING, EXECUTED, FAILED = (
    "pending", "approved", "rejected", "expired", "executing", "executed", "failed")


@dataclass
class Approval:
    trace_id: str
    session_id: str
    tool: str
    input: Any
    reason: str
    agent_id: str = ""
    customer_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: str = PENDING
    created_at: float = field(default_factory=time.time)
    decided_by: str | None = None
    decided_at: float | None = None
    note: str | None = None
    result: Any = None


class ApprovalRepo(Protocol):
    """Every transition is atomic, so concurrent callers cannot decide, claim or expire the same approval twice."""

    async def add(self, **kw: Any) -> Approval: ...
    async def get(self, approval_id: str) -> Approval | None: ...
    async def list(self, state: str | None = None) -> list[Approval]: ...
    async def decide(self, approval_id: str, approved: bool, by: str, note: str | None = None) -> Approval: ...
    async def claim_execution(self, approval_id: str) -> Approval: ...
    async def complete(self, approval_id: str, ok: bool, result: Any) -> Approval: ...
    async def expire(self, approval_id: str) -> Approval | None: ...


class ApprovalStore:
    """In-memory approvals."""

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

    def _need(self, approval_id: str) -> Approval:
        a = self._items.get(approval_id)
        if a is None:
            raise KeyError(f"Unknown approval {approval_id}")
        return a

    async def decide(self, approval_id: str, approved: bool, by: str, note: str | None = None) -> Approval:
        a = self._need(approval_id)
        if a.state != PENDING:
            raise ValueError(f"Approval {approval_id} already {a.state}")
        a.state = APPROVED if approved else REJECTED
        a.decided_by, a.decided_at, a.note = by, time.time(), note
        return a

    async def claim_execution(self, approval_id: str) -> Approval:
        a = self._need(approval_id)
        if a.state != APPROVED:
            raise ValueError(f"Approval {approval_id} is {a.state}, not approved")
        a.state = EXECUTING
        return a

    async def complete(self, approval_id: str, ok: bool, result: Any) -> Approval:
        a = self._need(approval_id)
        if a.state != EXECUTING:
            raise ValueError(f"Approval {approval_id} is {a.state}, not executing")
        a.state, a.result = (EXECUTED if ok else FAILED), result
        return a

    async def expire(self, approval_id: str) -> Approval | None:
        a = self._need(approval_id)
        if a.state != PENDING:
            return None
        a.state, a.decided_at = EXPIRED, time.time()
        return a
