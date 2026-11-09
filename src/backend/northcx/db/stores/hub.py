"""Postgres store for Agent Hub install records."""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import TemplateInstallRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.hub import Install

_FIELDS = ("template_id", "template_version", "params", "version_number", "installed_by", "spec_snapshot", "scenario_names", "tests")


def _from(r: TemplateInstallRow) -> Install:
    return Install(agent_id=r.agent_id, installed_at=r.installed_at, updated_at=r.updated_at, **{k: r.data[k] for k in _FIELDS})


class PgInstalls(_Base):
    async def save(self, i: Install) -> None:
        i.updated_at = time.time()
        data = _jsonable({k: getattr(i, k) for k in _FIELDS})
        stmt = pg_insert(TemplateInstallRow).values(agent_id=i.agent_id, data=data, installed_at=i.installed_at, updated_at=i.updated_at)
        stmt = stmt.on_conflict_do_update(index_elements=[TemplateInstallRow.tenant_id, TemplateInstallRow.agent_id], set_={"data": data, "updated_at": i.updated_at})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get(self, agent_id: str) -> Install | None:
        async with self._ro() as s:
            r = (await s.execute(select(TemplateInstallRow).where(TemplateInstallRow.agent_id == agent_id))).scalar_one_or_none()
        return _from(r) if r else None

    async def list(self) -> list[Install]:
        async with self._ro() as s:
            rows = (await s.execute(select(TemplateInstallRow).order_by(TemplateInstallRow.agent_id))).scalars().all()
        return [_from(r) for r in rows]
