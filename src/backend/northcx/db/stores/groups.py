"""Postgres store for groups."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import GroupRow
from northcx.db.stores._base import _Base
from northcx.groups import Group


def _from(r: GroupRow) -> Group:
    return Group(r.id, r.name, list(r.roles), list(r.members), r.external_name, r.description, r.created_by, r.created_at)


class PgGroups(_Base):
    async def list(self) -> list[Group]:
        async with self._ro() as s:
            rows = (await s.execute(select(GroupRow).order_by(GroupRow.name))).scalars().all()
        return [_from(r) for r in rows]

    async def get(self, group_id: str) -> Group | None:
        async with self._ro() as s:
            r = (await s.execute(select(GroupRow).where(GroupRow.id == group_id))).scalar_one_or_none()
        return _from(r) if r else None

    async def save(self, g: Group) -> None:
        vals = dict(id=g.id, name=g.name, external_name=g.external_name, description=g.description, roles=g.roles, members=g.members,
                    created_by=g.created_by, created_at=g.created_at)
        stmt = pg_insert(GroupRow).values(**vals)
        stmt = stmt.on_conflict_do_update(index_elements=[GroupRow.id], set_={k: v for k, v in vals.items() if k not in ("id", "created_by", "created_at")})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def delete(self, group_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(GroupRow).where(GroupRow.id == group_id))).rowcount > 0
