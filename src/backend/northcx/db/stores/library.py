"""Postgres store for Library items."""
from __future__ import annotations

import time

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import LibraryItemRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.library_items import Item


def _i(r: LibraryItemRow) -> Item:
    return Item(r.owner, r.title, r.kind, r.visibility, list(r.data["versions"]), list(r.data.get("tags", [])), r.uses, r.id, r.created_at, r.updated_at, r.data.get("team", ""))


class PgLibrary(_Base):
    async def put(self, i: Item) -> None:
        i.updated_at = time.time()
        vals = dict(owner=i.owner, title=i.title, kind=i.kind, visibility=i.visibility, created_at=i.created_at, updated_at=i.updated_at, data=_jsonable({"versions": i.versions, "tags": i.tags, "team": i.team}))
        stmt = pg_insert(LibraryItemRow).values(id=i.id, uses=i.uses, **vals)
        stmt = stmt.on_conflict_do_update(index_elements=[LibraryItemRow.tenant_id, LibraryItemRow.id], set_=vals)      # uses is changed only by bump, never overwritten by an edit
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get(self, item_id: str) -> Item | None:
        async with self._ro() as s:
            r = (await s.execute(select(LibraryItemRow).where(LibraryItemRow.id == item_id))).scalar_one_or_none()
        return _i(r) if r else None

    async def list(self) -> list[Item]:
        async with self._ro() as s:
            return [_i(r) for r in (await s.execute(select(LibraryItemRow).order_by(LibraryItemRow.title).limit(1100))).scalars().all()]

    async def delete(self, item_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(LibraryItemRow).where(LibraryItemRow.id == item_id))).rowcount > 0

    async def bump(self, item_id: str) -> int:
        async with self._sm.begin() as s:
            r = (await s.execute(update(LibraryItemRow).where(LibraryItemRow.id == item_id).values(uses=LibraryItemRow.uses + 1).returning(LibraryItemRow.uses))).first()
        return int(r[0]) if r else 0
