"""Postgres store for release requests (the two-person rule)."""
from __future__ import annotations

import time

from sqlalchemy import select, update

from northcx.db.models import ReleaseRequestRow
from northcx.db.stores._base import _Base
from northcx.release_requests import ReleaseRequest


def _from(r: ReleaseRequestRow) -> ReleaseRequest:
    return ReleaseRequest(r.id, r.agent_id, r.kind, r.environment, r.version, r.requested_by, r.note, r.status, r.decided_by, r.decision_note, r.created_at, r.decided_at)


class PgReleaseRequests(_Base):
    async def add(self, r: ReleaseRequest) -> None:
        async with self._sm.begin() as s:
            s.add(ReleaseRequestRow(id=r.id, agent_id=r.agent_id, kind=r.kind, environment=r.environment, version=r.version, requested_by=r.requested_by,
                                    note=r.note, status=r.status, created_at=r.created_at))

    async def get(self, request_id: str) -> ReleaseRequest | None:
        async with self._ro() as s:
            row = (await s.execute(select(ReleaseRequestRow).where(ReleaseRequestRow.id == request_id))).scalar_one_or_none()
        return _from(row) if row else None

    async def list(self, status: str | None, agent_id: str | None, limit: int) -> list[ReleaseRequest]:
        q = select(ReleaseRequestRow)
        if status:
            q = q.where(ReleaseRequestRow.status == status)
        if agent_id:
            q = q.where(ReleaseRequestRow.agent_id == agent_id)
        async with self._ro() as s:
            rows = (await s.execute(q.order_by(ReleaseRequestRow.created_at.desc()).limit(limit))).scalars().all()
        return [_from(r) for r in rows]

    async def mark(self, request_id: str, status: str, note: str | None) -> None:
        async with self._sm.begin() as s:
            await s.execute(update(ReleaseRequestRow).where(ReleaseRequestRow.id == request_id).values(status=status, decision_note=note))

    async def decide(self, request_id: str, status: str, by: str, note: str | None) -> ReleaseRequest | None:
        async with self._sm.begin() as s:  # one statement, only while pending: two people deciding at once cannot both win
            row = (await s.execute(update(ReleaseRequestRow).where(ReleaseRequestRow.id == request_id, ReleaseRequestRow.status == "pending")
                                   .values(status=status, decided_by=by, decision_note=note, decided_at=time.time()).returning(ReleaseRequestRow))).scalar_one_or_none()
        return _from(row) if row else None
