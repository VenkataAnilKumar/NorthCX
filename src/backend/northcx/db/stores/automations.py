"""Postgres store for routines, their runs and their schedule state."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.automations import CLAIM_SECONDS, Automation, Run
from northcx.db.models import AutomationRow, AutomationRunRow, AutomationStateRow
from northcx.db.stores._base import _Base, _jsonable

_FIELDS = ("data", "created_by", "proposed_by", "decided_by", "decision_note", "nonce")
_RUN = ("version", "trigger", "by", "ended_at", "steps", "outcome", "error")
CLAIM_SQL = text("update automation_state set next_run = :later where next_run is not null and next_run <= :now and not paused and "
                 "automation_id in (select automation_id from automation_state where next_run is not null and next_run <= :now and not paused order by next_run limit :n for update skip locked) "
                 "returning automation_id")


def _a(r: AutomationRow) -> Automation:
    return Automation(id=r.id, version=r.version, name=r.name, status=r.status, created_at=r.created_at, updated_at=r.updated_at, **{k: r.data.get(k) for k in _FIELDS})


def _run(r: AutomationRunRow) -> Run:
    return Run(automation_id=r.automation_id, id=r.id, status=r.status, started_at=r.started_at, **{k: r.data.get(k) for k in _RUN})


class PgAutomations(_Base):
    async def save(self, a: Automation) -> None:
        a.updated_at = time.time()
        data = _jsonable({k: getattr(a, k) for k in _FIELDS})
        stmt = pg_insert(AutomationRow).values(id=a.id, version=a.version, status=a.status, name=a.name, created_at=a.created_at, updated_at=a.updated_at, data=data)
        stmt = stmt.on_conflict_do_update(index_elements=[AutomationRow.tenant_id, AutomationRow.id, AutomationRow.version], set_={"status": a.status, "name": a.name, "updated_at": a.updated_at, "data": data})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def versions(self, automation_id: str) -> list[Automation]:
        async with self._ro() as s:
            rows = (await s.execute(select(AutomationRow).where(AutomationRow.id == automation_id).order_by(AutomationRow.version.desc()))).scalars().all()
        return [_a(r) for r in rows]

    async def list(self) -> list[Automation]:
        async with self._ro() as s:
            rows = (await s.execute(select(AutomationRow).order_by(AutomationRow.id, AutomationRow.version.desc()))).scalars().all()
        latest: dict[str, AutomationRow] = {}
        for r in rows:
            latest.setdefault(r.id, r)
        return sorted((_a(r) for r in latest.values()), key=lambda a: a.name.lower())

    async def published(self) -> list[Automation]:
        async with self._ro() as s:
            return [_a(r) for r in (await s.execute(select(AutomationRow).where(AutomationRow.status == "published"))).scalars().all()]

    async def save_run(self, r: Run) -> None:
        data = _jsonable({k: getattr(r, k) for k in _RUN})
        stmt = pg_insert(AutomationRunRow).values(id=r.id, automation_id=r.automation_id, status=r.status, started_at=r.started_at, data=data)
        stmt = stmt.on_conflict_do_update(index_elements=[AutomationRunRow.tenant_id, AutomationRunRow.id], set_={"status": r.status, "data": data})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def runs(self, automation_id: str | None, limit: int) -> list[Run]:
        q = select(AutomationRunRow).order_by(AutomationRunRow.started_at.desc()).limit(limit)
        if automation_id is not None:
            q = q.where(AutomationRunRow.automation_id == automation_id)
        async with self._ro() as s:
            return [_run(r) for r in (await s.execute(q)).scalars().all()]

    async def get_run(self, run_id: str) -> Run | None:
        async with self._ro() as s:
            r = (await s.execute(select(AutomationRunRow).where(AutomationRunRow.id == run_id))).scalar_one_or_none()
        return _run(r) if r else None

    async def running(self, automation_id: str | None, since: float) -> int:
        q = select(AutomationRunRow.id).where(AutomationRunRow.status == "running", AutomationRunRow.started_at >= since)
        if automation_id is not None:
            q = q.where(AutomationRunRow.automation_id == automation_id)
        async with self._ro() as s:
            return len((await s.execute(q)).all())

    async def fail_stale(self, before: float) -> int:
        async with self._sm.begin() as s:
            rows = (await s.execute(select(AutomationRunRow).where(AutomationRunRow.status == "running", AutomationRunRow.started_at < before))).scalars().all()
            for r in rows:
                r.status = "failed"
                r.data = {**r.data, "error": "The run was interrupted (the server stopped)", "ended_at": time.time()}
            return len(rows)

    async def state(self, automation_id: str) -> dict[str, Any]:
        async with self._ro() as s:
            r = (await s.execute(select(AutomationStateRow).where(AutomationStateRow.automation_id == automation_id))).scalar_one_or_none()
        return {"nextRun": r.next_run, "paused": r.paused} if r else {"nextRun": None, "paused": False}

    async def set_state(self, automation_id: str, next_run: Any = "keep", paused: bool | None = None) -> None:
        cur = await self.state(automation_id)
        nr = cur["nextRun"] if next_run == "keep" else next_run
        pz = cur["paused"] if paused is None else paused
        stmt = pg_insert(AutomationStateRow).values(automation_id=automation_id, next_run=nr, paused=pz)
        stmt = stmt.on_conflict_do_update(index_elements=[AutomationStateRow.tenant_id, AutomationStateRow.automation_id], set_={"next_run": nr, "paused": pz})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def claim_due(self, now: float, limit: int) -> list[str]:
        async with self._sm.begin() as s:
            return [r[0] for r in (await s.execute(CLAIM_SQL, {"now": now, "later": now + CLAIM_SECONDS, "n": limit})).all()]
