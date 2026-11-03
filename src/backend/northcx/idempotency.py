"""Idempotency keys for API writes: a retried request with the same key gets the first answer, never a second action."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

TTL_SECONDS = 24 * 3600
STALE_AFTER = 300  # a request that never finished (crash) can be retried after this long
_KEY = re.compile(r"^[\x21-\x7e]{1,200}$")


def valid_key(key: str) -> bool:
    return bool(_KEY.match(key))


def scope_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def request_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass
class Outcome:
    state: str  # new | replay | conflict | in_progress
    response: dict[str, Any] | None = None


class IdempotencyStore(Protocol):
    async def begin(self, scope: str, req_hash: str, now: float | None = None, session_id: str | None = None) -> Outcome: ...
    async def complete(self, scope: str, response: dict[str, Any]) -> None: ...
    async def abandon(self, scope: str) -> None: ...
    async def forget_session(self, session_id: str) -> int: ...


class InMemoryIdempotency:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def begin(self, scope: str, req_hash: str, now: float | None = None, session_id: str | None = None) -> Outcome:
        now = time.time() if now is None else now
        async with self._lock:
            for k in [k for k, r in self._rows.items() if r["at"] < now - TTL_SECONDS]:
                del self._rows[k]
            row = self._rows.get(scope)
            if row is None or (row["response"] is None and row["at"] < now - STALE_AFTER):
                self._rows[scope] = {"hash": req_hash, "response": None, "at": now, "session": session_id}
                return Outcome("new")
            if row["hash"] != req_hash:
                return Outcome("conflict")
            return Outcome("replay", row["response"]) if row["response"] is not None else Outcome("in_progress")

    async def complete(self, scope: str, response: dict[str, Any]) -> None:
        if scope in self._rows:
            self._rows[scope]["response"] = response

    async def forget_session(self, session_id: str) -> int:
        gone = [k for k, r in self._rows.items() if r.get("session") == session_id]
        for k in gone:
            del self._rows[k]
        return len(gone)

    async def abandon(self, scope: str) -> None:
        row = self._rows.get(scope)
        if row is not None and row["response"] is None:
            del self._rows[scope]
