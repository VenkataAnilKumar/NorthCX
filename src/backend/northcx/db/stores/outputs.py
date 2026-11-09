"""Postgres store for Workspace outputs and spaces."""
from __future__ import annotations

import time

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import WorkspaceOutputRow, WorkspaceSpaceRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.outputs import Output, Space


def _o(r: WorkspaceOutputRow) -> Output:
    return Output(r.owner, r.title, r.kind, r.visibility, list(r.data["versions"]), r.space_id, r.source, r.id, r.created_at, r.updated_at, r.expires_at)


def _s(r: WorkspaceSpaceRow) -> Space:
    return Space(r.owner, r.name, r.visibility, r.data.get("description", ""), r.data.get("instructions", ""), r.id, r.created_at, r.updated_at)


class PgContent(_Base):
    async def put_output(self, o: Output) -> None:
        o.updated_at = time.time()
        vals = dict(owner=o.owner, title=o.title, kind=o.kind, visibility=o.visibility, space_id=o.space_id, source=o.source, created_at=o.created_at, updated_at=o.updated_at,
                    expires_at=o.expires_at, data=_jsonable({"versions": o.versions}))
        stmt = pg_insert(WorkspaceOutputRow).values(id=o.id, **vals)
        stmt = stmt.on_conflict_do_update(index_elements=[WorkspaceOutputRow.tenant_id, WorkspaceOutputRow.id], set_=vals)
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get_output(self, output_id: str) -> Output | None:
        async with self._ro() as s:
            r = (await s.execute(select(WorkspaceOutputRow).where(WorkspaceOutputRow.id == output_id))).scalar_one_or_none()
        return _o(r) if r else None

    async def list_outputs(self, space_id: str | None, kind: str | None, now: float) -> list[Output]:
        q = select(WorkspaceOutputRow).where(WorkspaceOutputRow.expires_at > now).order_by(WorkspaceOutputRow.updated_at.desc()).limit(1000)
        if space_id is not None:
            q = q.where(WorkspaceOutputRow.space_id == space_id)
        if kind is not None:
            q = q.where(WorkspaceOutputRow.kind == kind)
        async with self._ro() as s:
            return [_o(r) for r in (await s.execute(q)).scalars().all()]

    async def delete_output(self, output_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(WorkspaceOutputRow).where(WorkspaceOutputRow.id == output_id))).rowcount > 0

    async def purge_expired(self, now: float) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(WorkspaceOutputRow).where(WorkspaceOutputRow.expires_at <= now))).rowcount

    async def count_outputs(self, owner: str | None) -> int:
        q = select(func.count()).select_from(WorkspaceOutputRow)
        if owner is not None:
            q = q.where(WorkspaceOutputRow.owner == owner)
        async with self._ro() as s:
            return int((await s.execute(q)).scalar_one())

    async def put_space(self, sp: Space) -> None:
        sp.updated_at = time.time()
        vals = dict(owner=sp.owner, name=sp.name, visibility=sp.visibility, created_at=sp.created_at, updated_at=sp.updated_at,
                    data={"description": sp.description, "instructions": sp.instructions})
        stmt = pg_insert(WorkspaceSpaceRow).values(id=sp.id, **vals)
        stmt = stmt.on_conflict_do_update(index_elements=[WorkspaceSpaceRow.tenant_id, WorkspaceSpaceRow.id], set_=vals)
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get_space(self, space_id: str) -> Space | None:
        async with self._ro() as s:
            r = (await s.execute(select(WorkspaceSpaceRow).where(WorkspaceSpaceRow.id == space_id))).scalar_one_or_none()
        return _s(r) if r else None

    async def list_spaces(self) -> list[Space]:
        async with self._ro() as s:
            return [_s(r) for r in (await s.execute(select(WorkspaceSpaceRow).order_by(WorkspaceSpaceRow.name).limit(1000))).scalars().all()]

    async def delete_space(self, space_id: str) -> bool:
        async with self._sm.begin() as s:
            await s.execute(update(WorkspaceOutputRow).where(WorkspaceOutputRow.space_id == space_id).values(space_id=None))     # outputs outlive their space
            return (await s.execute(delete(WorkspaceSpaceRow).where(WorkspaceSpaceRow.id == space_id))).rowcount > 0
