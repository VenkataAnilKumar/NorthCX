"""Postgres store for background-job leases. Expiry is judged on the database's clock, so servers with drifting clocks agree."""
from __future__ import annotations

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import JobLeaseRow
from northcx.db.stores._base import _Base


class PgLeases(_Base):
    @staticmethod
    def _now():
        return func.extract("epoch", func.clock_timestamp())

    async def acquire(self, name: str, holder: str, ttl: float) -> bool:
        ins = pg_insert(JobLeaseRow).values(name=name, holder=holder, expires_at=self._now() + ttl)
        stmt = ins.on_conflict_do_update(index_elements=[JobLeaseRow.name], set_={"holder": ins.excluded.holder, "expires_at": ins.excluded.expires_at},
                                         where=(JobLeaseRow.expires_at < self._now()) | (JobLeaseRow.holder == ins.excluded.holder)).returning(JobLeaseRow.holder)
        async with self._sm.begin() as s:
            return (await s.execute(stmt)).first() is not None

    async def release(self, name: str, holder: str) -> None:
        async with self._sm.begin() as s:
            await s.execute(update(JobLeaseRow).where(JobLeaseRow.name == name, JobLeaseRow.holder == holder).values(expires_at=0.0))

    async def forget_expired(self) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(JobLeaseRow).where(JobLeaseRow.expires_at < self._now() - 86400))).rowcount
