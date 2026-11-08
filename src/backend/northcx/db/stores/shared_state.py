"""Postgres stores for state that more than one server process must see: firing alerts, alert events, crawl jobs."""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import AlertEventRow, AlertStateRow, CrawlJobRow
from northcx.db.stores._base import _Base, _jsonable


class PgAlertState(_Base):
    async def load(self) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """(firing alerts by rule, recent events oldest first)."""
        async with self._ro() as s:
            active = {r.rule: r.payload for r in (await s.execute(select(AlertStateRow))).scalars()}
            rows = (await s.execute(select(AlertEventRow).order_by(AlertEventRow.id.desc()).limit(200))).scalars().all()
        return active, [dict(r.payload, _id=r.id) for r in reversed(rows)]

    async def set_active(self, rule: str, payload: dict[str, Any]) -> None:
        stmt = pg_insert(AlertStateRow).values(rule=rule, payload=_jsonable(payload))
        async with self._sm.begin() as s:
            await s.execute(stmt.on_conflict_do_update(index_elements=[AlertStateRow.rule], set_={"payload": stmt.excluded.payload}))

    async def clear_active(self, rule: str) -> None:
        async with self._sm.begin() as s:
            await s.execute(delete(AlertStateRow).where(AlertStateRow.rule == rule))

    async def add_event(self, event: dict[str, Any]) -> int:
        async with self._sm.begin() as s:
            row = (await s.execute(pg_insert(AlertEventRow).values(at=float(event.get("at", 0)), payload=_jsonable(event)).returning(AlertEventRow.id))).scalar_one()
            await s.execute(delete(AlertEventRow).where(AlertEventRow.id < row - 200))  # keep the last 200
        return int(row)

    async def update_event(self, event_id: int, event: dict[str, Any]) -> None:
        async with self._sm.begin() as s:
            row = await s.get(AlertEventRow, event_id)
            if row is not None:
                row.payload = _jsonable(event)


class PgCrawlJobs(_Base):
    async def save(self, job: dict[str, Any], updated_at: float) -> None:
        values = dict(id=job["jobId"], source_id=job["sourceId"], state=job["state"], started_at=job["startedAt"], updated_at=updated_at, payload=_jsonable(job))
        stmt = pg_insert(CrawlJobRow).values(**values)
        async with self._sm.begin() as s:
            await s.execute(stmt.on_conflict_do_update(index_elements=[CrawlJobRow.id], set_={k: getattr(stmt.excluded, k) for k in ("state", "updated_at", "payload")}))
            await s.execute(delete(CrawlJobRow).where(CrawlJobRow.started_at < select(CrawlJobRow.started_at).order_by(CrawlJobRow.started_at.desc()).offset(49).limit(1).scalar_subquery()))

    async def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self._ro() as s:
            rows = (await s.execute(select(CrawlJobRow).order_by(CrawlJobRow.started_at.desc()).limit(limit))).scalars().all()
        return [r.payload for r in rows]

    async def get(self, job_id: str) -> dict[str, Any] | None:
        async with self._ro() as s:
            row = await s.get(CrawlJobRow, job_id)
        return row.payload if row else None

    async def running(self, source_id: str, alive_since: float) -> bool:
        """Is a crawl of this source running somewhere (its heartbeat is newer than `alive_since`)?"""
        async with self._ro() as s:
            return (await s.execute(select(CrawlJobRow.id).where(CrawlJobRow.source_id == source_id, CrawlJobRow.state == "running",
                                                                 CrawlJobRow.updated_at >= alive_since).limit(1))).first() is not None
