"""Postgres store for the Pilot's proposed actions."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import PilotActionRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.pilot_actions import PilotAction


def _a(r: PilotActionRow) -> PilotAction:
    return PilotAction(r.owner, r.chat_id, r.tool, dict(r.data["input"]), r.data["summary"], r.id, r.state, r.data.get("result", ""), r.created_at)


class PgPilotActions(_Base):
    async def put(self, a: PilotAction) -> None:
        vals = dict(owner=a.owner, chat_id=a.chat_id, tool=a.tool, state=a.state, created_at=a.created_at, data=_jsonable({"input": a.input, "summary": a.summary, "result": a.result}))
        stmt = pg_insert(PilotActionRow).values(id=a.id, **vals)
        stmt = stmt.on_conflict_do_update(index_elements=[PilotActionRow.tenant_id, PilotActionRow.id], set_=vals)
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get(self, action_id: str) -> PilotAction | None:
        async with self._ro() as s:
            r = (await s.execute(select(PilotActionRow).where(PilotActionRow.id == action_id))).scalar_one_or_none()
        return _a(r) if r else None

    async def list(self, owner: str, chat_id: str | None, state: str | None) -> list[PilotAction]:
        q = select(PilotActionRow).where(PilotActionRow.owner == owner).order_by(PilotActionRow.created_at).limit(200)
        if chat_id is not None:
            q = q.where(PilotActionRow.chat_id == chat_id)
        if state is not None:
            q = q.where(PilotActionRow.state == state)
        async with self._ro() as s:
            return [_a(r) for r in (await s.execute(q)).scalars().all()]
