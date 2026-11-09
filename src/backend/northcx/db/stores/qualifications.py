"""Postgres store for model qualifications."""
from __future__ import annotations

from sqlalchemy import select

from northcx.db.models import ModelQualificationRow
from northcx.db.stores._base import _Base
from northcx.providers.qualification import Qualification


def _from(r: ModelQualificationRow) -> Qualification:
    d = r.result
    return Qualification(r.agent_id, r.model, d["agentDigest"], d["qualified"], d["required"]["total"], d["required"]["passed"],
                         d["other"]["total"], d["other"]["passed"], d["runId"], r.created_at, list(d.get("reasons", [])))


class PgQualifications(_Base):
    async def save(self, q: Qualification) -> None:
        async with self._sm.begin() as s:
            s.add(ModelQualificationRow(agent_id=q.agent_id, model=q.model, created_at=q.created_at, result=q.to_dict()))

    async def latest(self, agent_id: str, model: str) -> Qualification | None:
        async with self._ro() as s:
            r = (await s.execute(select(ModelQualificationRow).where(ModelQualificationRow.agent_id == agent_id, ModelQualificationRow.model == model)
                                 .order_by(ModelQualificationRow.id.desc()).limit(1))).scalar_one_or_none()
        return _from(r) if r else None

    async def list(self, agent_id: str) -> list[Qualification]:
        async with self._ro() as s:
            rows = (await s.execute(select(ModelQualificationRow).where(ModelQualificationRow.agent_id == agent_id)
                                    .order_by(ModelQualificationRow.id.desc()).limit(200))).scalars().all()
        return [_from(r) for r in rows]
