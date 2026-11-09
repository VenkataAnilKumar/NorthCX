"""Postgres store for which team answered."""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import DecisionTeamRow
from northcx.db.stores._base import _Base


class PgTeams(_Base):
    async def record(self, kind: str, item_id: str, team: str) -> None:
        stmt = pg_insert(DecisionTeamRow).values(kind=kind, item_id=item_id, team=team, at=time.time())
        stmt = stmt.on_conflict_do_update(index_elements=[DecisionTeamRow.tenant_id, DecisionTeamRow.kind, DecisionTeamRow.item_id], set_={"team": team, "at": time.time()})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def for_ids(self, kind: str, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        async with self._ro() as s:
            rows = (await s.execute(select(DecisionTeamRow.item_id, DecisionTeamRow.team).where(DecisionTeamRow.kind == kind, DecisionTeamRow.item_id.in_(ids)))).all()
        return {r[0]: r[1] for r in rows}
