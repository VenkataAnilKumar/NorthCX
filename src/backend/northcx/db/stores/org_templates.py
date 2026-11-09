"""Postgres store for organization template versions."""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import OrgTemplateRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.org_templates import OrgTemplate

_FIELDS = ("data", "check", "created_by", "proposed_by", "decided_by", "decision_note")


def _from(r: OrgTemplateRow) -> OrgTemplate:
    return OrgTemplate(id=r.id, version=r.version, title=r.name, status=r.status, created_at=r.created_at, updated_at=r.updated_at, **{k: r.data.get(k) for k in _FIELDS})


class PgOrgTemplates(_Base):
    async def save(self, p: OrgTemplate) -> None:
        p.updated_at = time.time()
        data = _jsonable({k: getattr(p, k) for k in _FIELDS})
        stmt = pg_insert(OrgTemplateRow).values(id=p.id, version=p.version, status=p.status, name=p.title, created_at=p.created_at, updated_at=p.updated_at, data=data)
        stmt = stmt.on_conflict_do_update(index_elements=[OrgTemplateRow.tenant_id, OrgTemplateRow.id, OrgTemplateRow.version],
                                          set_={"status": p.status, "updated_at": p.updated_at, "data": data, "name": p.title})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def versions(self, template_id: str) -> list[OrgTemplate]:
        async with self._ro() as s:
            rows = (await s.execute(select(OrgTemplateRow).where(OrgTemplateRow.id == template_id).order_by(OrgTemplateRow.version.desc()))).scalars().all()
        return [_from(r) for r in rows]

    async def get(self, template_id: str, version: int | None = None) -> OrgTemplate | None:
        vs = await self.versions(template_id)
        return next((p for p in vs if version is None or p.version == version), None)

    async def list(self) -> list[OrgTemplate]:
        async with self._ro() as s:
            rows = (await s.execute(select(OrgTemplateRow).order_by(OrgTemplateRow.id, OrgTemplateRow.version.desc()))).scalars().all()
        latest: dict[str, OrgTemplateRow] = {}
        for r in rows:
            latest.setdefault(r.id, r)
        return sorted((_from(r) for r in latest.values()), key=lambda p: p.title.lower())

    async def published(self) -> list[OrgTemplate]:
        async with self._ro() as s:
            rows = (await s.execute(select(OrgTemplateRow).where(OrgTemplateRow.status == "published"))).scalars().all()
        return [_from(r) for r in rows]
