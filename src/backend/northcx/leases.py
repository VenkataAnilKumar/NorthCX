"""Leases: one server process at a time runs a background job, so several workers never do the same work twice.

A holder takes a named lease for a few minutes, runs one pass of the job and gives the lease back. A holder that dies
mid-pass simply stops renewing, and the lease expires on its own so another process takes the job over."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Protocol

log = logging.getLogger("northcx.leases")
HOLDER = f"{uuid.uuid4().hex[:12]}"  # this process


class Leases(Protocol):
    async def acquire(self, name: str, holder: str, ttl: float) -> bool: ...
    async def release(self, name: str, holder: str) -> None: ...


class InMemoryLeases:
    """For a single process (and tests): same rules, no database."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock, self._held = clock, {}

    async def acquire(self, name: str, holder: str, ttl: float) -> bool:
        cur = self._held.get(name)
        if cur is not None and cur[1] > self.clock() and cur[0] != holder:
            return False
        self._held[name] = (holder, self.clock() + ttl)
        return True

    async def release(self, name: str, holder: str) -> None:
        if self._held.get(name, (None,))[0] == holder:
            self._held[name] = (holder, 0.0)


async def run_leased(leases: Leases | None, name: str, ttl: float, job: Callable[[], Awaitable[Any]], holder: str = HOLDER) -> bool:
    """Run `job` once if this process can take the lease `name`. Returns whether it ran. With no leases it always runs."""
    if leases is None:
        await job()
        return True
    try:
        got = await leases.acquire(name, holder, ttl)
    except Exception:
        log.exception("could not take the lease for %s; skipping this pass", name)
        return False
    if not got:
        return False
    try:
        await job()
    finally:
        try:
            await leases.release(name, holder)
        except Exception:
            log.exception("could not release the lease for %s (it will expire by itself)", name)
    return True
