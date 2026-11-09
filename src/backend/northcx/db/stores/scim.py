"""Postgres store for people provisioned by SCIM."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import ScimUserRow
from northcx.db.stores._base import _Base
from northcx.scim import ScimUser


def _from(r: ScimUserRow) -> ScimUser:
    return ScimUser(r.id, r.user_name, r.display_name, r.external_id, r.active, r.created_at, r.updated_at)


class PgScimUsers(_Base):
    async def list(self) -> list[ScimUser]:
        async with self._ro() as s:
            rows = (await s.execute(select(ScimUserRow).order_by(ScimUserRow.created_at, ScimUserRow.id))).scalars().all()
        return [_from(r) for r in rows]

    async def get(self, user_id: str) -> ScimUser | None:
        async with self._ro() as s:
            r = (await s.execute(select(ScimUserRow).where(ScimUserRow.id == user_id))).scalar_one_or_none()
        return _from(r) if r else None

    async def by_name(self, user_name: str) -> ScimUser | None:
        async with self._ro() as s:
            r = (await s.execute(select(ScimUserRow).where(ScimUserRow.user_name == user_name))).scalar_one_or_none()
        return _from(r) if r else None

    async def save(self, u: ScimUser) -> None:
        vals = dict(id=u.id, user_name=u.user_name, display_name=u.display_name, external_id=u.external_id, active=u.active, created_at=u.created_at, updated_at=u.updated_at)
        stmt = pg_insert(ScimUserRow).values(**vals)
        stmt = stmt.on_conflict_do_update(index_elements=[ScimUserRow.id], set_={k: v for k, v in vals.items() if k not in ("id", "created_at")})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def delete(self, user_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(ScimUserRow).where(ScimUserRow.id == user_id))).rowcount > 0
