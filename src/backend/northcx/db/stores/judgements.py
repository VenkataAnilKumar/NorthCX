"""Postgres store for model verdicts on conversations."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import QaJudgementRow
from northcx.db.stores._base import _Base
from northcx.qa import Judgement


def _j(r: QaJudgementRow) -> Judgement:
    return Judgement(r.session_id, r.verdict, r.reason, r.rubric_version, r.judged_by, r.created_at)


class PgJudgements(_Base):
    async def put(self, j: Judgement) -> None:
        vals = dict(verdict=j.verdict, reason=j.reason, rubric_version=j.rubric_version, judged_by=j.judged_by, created_at=j.created_at)
        stmt = pg_insert(QaJudgementRow).values(session_id=j.session_id, **vals)
        stmt = stmt.on_conflict_do_update(index_elements=[QaJudgementRow.tenant_id, QaJudgementRow.session_id], set_=vals)
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get(self, session_id: str) -> Judgement | None:
        async with self._ro() as s:
            r = (await s.execute(select(QaJudgementRow).where(QaJudgementRow.session_id == session_id))).scalar_one_or_none()
        return _j(r) if r else None

    async def for_sessions(self, session_ids: list[str]) -> dict[str, Judgement]:
        if not session_ids:
            return {}
        async with self._ro() as s:
            rows = (await s.execute(select(QaJudgementRow).where(QaJudgementRow.session_id.in_(session_ids)))).scalars().all()
        return {r.session_id: _j(r) for r in rows}

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(QaJudgementRow).where(QaJudgementRow.session_id == session_id))).rowcount
