"""Postgres store for shadow-mode drafts. Rows are tenant-scoped like every other table."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import ShadowDraftRow
from northcx.db.stores._base import _Base
from northcx.shadow import PENDING, EXPIRED, ShadowDraft

_FIELDS = ("session_id", "agent_id", "agent_version", "customer_id", "trace_id", "customer_message", "draft", "state", "final_text", "note", "decided_by", "decided_at", "created_at")


def _from(r: ShadowDraftRow) -> ShadowDraft:
    return ShadowDraft(id=r.id, reasons=list(r.reasons), **{k: getattr(r, k) for k in _FIELDS})


class PgShadowDrafts(_Base):
    async def add(self, **kw: Any) -> ShadowDraft:
        d = ShadowDraft(**kw)
        async with self._sm.begin() as s:
            await s.execute(pg_insert(ShadowDraftRow).values(id=d.id, reasons=list(d.reasons), **{k: getattr(d, k) for k in _FIELDS}))
        return d

    async def get(self, draft_id: str) -> ShadowDraft | None:
        async with self._ro() as s:
            r = (await s.execute(select(ShadowDraftRow).where(ShadowDraftRow.id == draft_id))).scalar_one_or_none()
        return _from(r) if r else None

    async def list(self, state: str | None = None, since: float | None = None, session_id: str | None = None, limit: int = 500) -> list[ShadowDraft]:
        q = select(ShadowDraftRow).order_by(ShadowDraftRow.created_at).limit(limit)
        if state:
            q = q.where(ShadowDraftRow.state == state)
        if since is not None:
            q = q.where(ShadowDraftRow.created_at >= since)
        if session_id:
            q = q.where(ShadowDraftRow.session_id == session_id)
        async with self._ro() as s:
            return [_from(r) for r in (await s.execute(q)).scalars().all()]

    async def decide(self, draft_id: str, state: str, by: str, final_text: str | None, reasons: list[str], note: str | None) -> ShadowDraft:
        """Atomically move one pending draft to its decided state. KeyError if unknown, ValueError if it was no longer pending."""
        async with self._sm.begin() as s:
            row = (await s.execute(update(ShadowDraftRow).where(ShadowDraftRow.id == draft_id, ShadowDraftRow.state == PENDING)
                                   .values(state=state, decided_by=by, decided_at=time.time(), final_text=final_text, reasons=list(reasons), note=note).returning(ShadowDraftRow))).scalar_one_or_none()
            if row is not None:
                return _from(row)
            existing = (await s.execute(select(ShadowDraftRow).where(ShadowDraftRow.id == draft_id))).scalar_one_or_none()
        if existing is None:
            raise KeyError(draft_id)
        raise ValueError(f"Draft {draft_id} is already {existing.state}")

    async def expire(self, draft_id: str) -> ShadowDraft | None:
        async with self._sm.begin() as s:
            row = (await s.execute(update(ShadowDraftRow).where(ShadowDraftRow.id == draft_id, ShadowDraftRow.state == PENDING)
                                   .values(state=EXPIRED, decided_at=time.time()).returning(ShadowDraftRow))).scalar_one_or_none()
        return _from(row) if row else None

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(ShadowDraftRow).where(ShadowDraftRow.session_id == session_id))).rowcount
