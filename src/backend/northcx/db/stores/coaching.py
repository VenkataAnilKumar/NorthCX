"""Postgres store for coaching notes."""
from __future__ import annotations

from sqlalchemy import delete, select

from northcx.db.models import CoachingNoteRow
from northcx.db.stores._base import _Base
from northcx.qa import CoachingNote


def _from(r: CoachingNoteRow) -> CoachingNote:
    return CoachingNote(r.session_id, r.about, r.note, r.author, r.id, r.created_at)


class PgCoaching(_Base):
    async def add(self, n: CoachingNote) -> None:
        async with self._sm.begin() as s:
            s.add(CoachingNoteRow(id=n.id, session_id=n.session_id, about=n.about, note=n.note, author=n.author, created_at=n.created_at))

    async def list(self, session_id: str | None = None, about: str | None = None, limit: int = 100) -> list[CoachingNote]:
        q = select(CoachingNoteRow).order_by(CoachingNoteRow.created_at.desc()).limit(limit)
        if session_id is not None:
            q = q.where(CoachingNoteRow.session_id == session_id)
        if about is not None:
            q = q.where(CoachingNoteRow.about == about)
        async with self._ro() as s:
            return [_from(r) for r in (await s.execute(q)).scalars().all()]

    async def delete(self, note_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(CoachingNoteRow).where(CoachingNoteRow.id == note_id))).rowcount > 0

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(CoachingNoteRow).where(CoachingNoteRow.session_id == session_id))).rowcount
