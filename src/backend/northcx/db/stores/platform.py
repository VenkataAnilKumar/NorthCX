"""Postgres store for idempotency keys."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import IdempotencyRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.idempotency import Outcome, STALE_AFTER, TTL_SECONDS


class PgIdempotency(_Base):
    async def begin(self, scope: str, req_hash: str, now: float | None = None, session_id: str | None = None) -> Outcome:
        now = time.time() if now is None else now
        async with self._sm.begin() as s:
            await s.execute(delete(IdempotencyRow).where(IdempotencyRow.created_at < now - TTL_SECONDS))
            ins = await s.execute(pg_insert(IdempotencyRow).values(scope=scope, req_hash=req_hash, response=None, created_at=now, session_id=session_id)
                                  .on_conflict_do_nothing().returning(IdempotencyRow.scope))
            if ins.first() is not None:
                return Outcome("new")
            row = (await s.execute(select(IdempotencyRow).where(IdempotencyRow.scope == scope).with_for_update())).scalar_one_or_none()
            if row is None:  # removed between statements: treat as new
                await s.execute(pg_insert(IdempotencyRow).values(scope=scope, req_hash=req_hash, response=None, created_at=now).on_conflict_do_nothing())
                return Outcome("new")
            if row.response is None and row.created_at < now - STALE_AFTER:
                row.req_hash, row.created_at, row.session_id = req_hash, now, session_id  # the earlier attempt never finished: take over
                return Outcome("new")
            if row.req_hash != req_hash:
                return Outcome("conflict")
            return Outcome("replay", row.response) if row.response is not None else Outcome("in_progress")

    async def complete(self, scope: str, response: dict[str, Any]) -> None:
        async with self._sm.begin() as s:
            await s.execute(update(IdempotencyRow).where(IdempotencyRow.scope == scope).values(response=_jsonable(response)))

    async def forget_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(IdempotencyRow).where(IdempotencyRow.session_id == session_id))).rowcount

    async def abandon(self, scope: str) -> None:
        async with self._sm.begin() as s:
            await s.execute(delete(IdempotencyRow).where(IdempotencyRow.scope == scope, IdempotencyRow.response.is_(None)))
