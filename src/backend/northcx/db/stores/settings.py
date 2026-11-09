"""Postgres store for per-tenant settings changed from the Admin app."""
from __future__ import annotations

import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import TenantSettingRow
from northcx.db.stores._base import _Base


class PgSettings(_Base):
    async def get(self, key: str) -> dict | None:
        async with self._ro() as s:
            r = (await s.execute(select(TenantSettingRow).where(TenantSettingRow.key == key))).scalar_one_or_none()
        return dict(r.data) if r else None

    async def put(self, key: str, data: dict, by: str) -> None:
        stmt = pg_insert(TenantSettingRow).values(key=key, data=data, updated_by=by[:200], updated_at=time.time())
        stmt = stmt.on_conflict_do_update(index_elements=[TenantSettingRow.tenant_id, TenantSettingRow.key], set_={"data": data, "updated_by": by[:200], "updated_at": time.time()})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def delete(self, key: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(TenantSettingRow).where(TenantSettingRow.key == key))).rowcount > 0
