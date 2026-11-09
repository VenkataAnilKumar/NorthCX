"""Append-only, hash-chained audit log: who did what, when, with what outcome.

Each entry's hash covers its own content and the previous entry's hash, so deleting or editing an entry breaks the chain
and `verify` reports where. (In Postgres a trigger also refuses UPDATE and DELETE.) Entries hold identifiers and reasons,
never conversation text or personal data."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .tenancy import DEFAULT_TENANT, current_tenant

GENESIS = "0" * 64


@dataclass
class AuditEntry:
    actor: str
    role: str
    action: str  # for example release.publish, key.create, approval.decide, auth.denied
    target: str = ""
    outcome: str = "success"  # success | denied | blocked | failed
    detail: dict[str, Any] = field(default_factory=dict)
    key_id: str | None = None
    at: float = field(default_factory=time.time)
    id: int = 0
    prev_hash: str = GENESIS
    hash: str = ""
    tenant_id: str = field(default_factory=current_tenant)  # whose entry this is (the request's tenant)


def entry_hash(e: AuditEntry) -> str:
    body = {"id": e.id, "at": round(e.at, 6), "actor": e.actor, "role": e.role, "key_id": e.key_id, "action": e.action,
            "target": e.target, "outcome": e.outcome, "detail": json.loads(json.dumps(e.detail, default=str, sort_keys=True))}
    if e.tenant_id != DEFAULT_TENANT:
        body["tenant"] = e.tenant_id  # the default tenant's entries hash exactly as before, so an existing chain still verifies
    return hashlib.sha256((e.prev_hash + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


@dataclass
class Verification:
    ok: bool
    checked: int
    broken_at: int | None = None
    reason: str | None = None
    head: str | None = None  # hash of the newest entry; keep a copy elsewhere to detect removal of the newest entries


def verify_entries(entries: list[AuditEntry]) -> Verification:
    """`entries` oldest first."""
    prev = GENESIS
    for n, e in enumerate(entries):
        if e.prev_hash != prev:
            return Verification(False, n, e.id, "the chain is broken: an earlier entry was removed or changed")
        if entry_hash(e) != e.hash:
            return Verification(False, n, e.id, "this entry was changed after it was written")
        prev = e.hash
    return Verification(True, len(entries), head=entries[-1].hash if entries else None)


class AuditRepo(Protocol):
    async def append(self, entry: AuditEntry) -> AuditEntry: ...
    async def list(self, limit: int = 100, before_id: int | None = None, actor: str | None = None,
                   action: str | None = None, tenant_id: str | None = None) -> list[AuditEntry]: ...
    async def verify(self) -> Verification: ...


class InMemoryAudit:
    def __init__(self) -> None:
        self._items: list[AuditEntry] = []
        self._lock = asyncio.Lock()

    async def append(self, entry: AuditEntry) -> AuditEntry:
        async with self._lock:
            entry.id = len(self._items) + 1
            entry.prev_hash = self._items[-1].hash if self._items else GENESIS
            entry.hash = entry_hash(entry)
            self._items.append(entry)
            return entry

    async def list(self, limit: int = 100, before_id: int | None = None, actor: str | None = None,
                   action: str | None = None, tenant_id: str | None = None) -> list[AuditEntry]:
        rows = [e for e in reversed(self._items) if (before_id is None or e.id < before_id)
                and (actor is None or e.actor == actor) and (action is None or e.action == action)
                and (tenant_id is None or e.tenant_id == tenant_id)]
        return rows[:limit]

    async def verify(self) -> Verification:
        return verify_entries(list(self._items))
