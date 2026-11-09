"""Postgres store for Pilot tasks."""
from __future__ import annotations

import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import WorkspaceTaskRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.tasks import Task

_FIELDS = ("style", "prompt", "questions", "answers", "plan", "steps", "results", "tokens", "note")


def _from(r: WorkspaceTaskRow) -> Task:
    return Task(id=r.id, owner=r.owner, status=r.status, created_at=r.created_at, updated_at=r.updated_at, **{k: r.data[k] for k in _FIELDS})


class PgTasks(_Base):
    async def save(self, t: Task) -> None:
        t.updated_at = time.time()
        data = _jsonable({k: getattr(t, k) for k in _FIELDS})
        stmt = pg_insert(WorkspaceTaskRow).values(id=t.id, owner=t.owner, status=t.status, created_at=t.created_at, updated_at=t.updated_at, data=data)
        stmt = stmt.on_conflict_do_update(index_elements=[WorkspaceTaskRow.id], set_={"status": t.status, "updated_at": t.updated_at, "data": data})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get(self, task_id: str) -> Task | None:
        async with self._ro() as s:
            r = (await s.execute(select(WorkspaceTaskRow).where(WorkspaceTaskRow.id == task_id))).scalar_one_or_none()
        return _from(r) if r else None

    async def list(self, owner: str, limit: int) -> list[Task]:
        async with self._ro() as s:
            rows = (await s.execute(select(WorkspaceTaskRow).where(WorkspaceTaskRow.owner == owner).order_by(WorkspaceTaskRow.created_at.desc()).limit(limit))).scalars().all()
        return [_from(r) for r in rows]

    async def delete(self, task_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(WorkspaceTaskRow).where(WorkspaceTaskRow.id == task_id))).rowcount > 0
