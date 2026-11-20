"""Postgres store for privacy: export, erasure and retention across every kind of data."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import delete, select, text

from northcx.db.models import FactRow
from northcx.db.stores._base import _Base, _jsonable


class PgPrivacy(_Base):
    """Export and erasure across every table that holds conversation data."""

    async def link(self, session_id: str, customer_id: str | None, now: float | None = None) -> None:
        now = time.time() if now is None else now
        async with self._sm.begin() as s:
            await s.execute(text("insert into session_index (session_id, customer_id, first_seen, last_seen) values (:s, :c, :n, :n) "
                                 "on conflict (tenant_id, session_id, customer_id) do update set last_seen = excluded.last_seen"),
                            {"s": session_id, "c": customer_id or "", "n": now})

    async def sessions_for_customer(self, customer_id: str) -> list[str]:
        async with self._ro() as s:
            rows = (await s.execute(text(
                "select session_id from session_index where customer_id = :c union select session_id from approvals where customer_id = :c "
                "union select session_id from handoffs where customer_id = :c union select session_id from email_sessions where customer_id = :c "
                "order by 1"), {"c": customer_id})).all()
        return [r[0] for r in rows]

    async def customer_for_session(self, session_id: str) -> str | None:
        async with self._ro() as s:
            r = (await s.execute(text("select customer_id from session_index where session_id = :s and customer_id <> '' limit 1"), {"s": session_id})).first()
        return r[0] if r else None

    async def sessions_idle_since(self, cutoff: float, limit: int = 1000) -> list[str]:
        async with self._ro() as s:
            rows = (await s.execute(text("select session_id from session_index group by session_id having max(last_seen) < :c order by max(last_seen) limit :n"),
                                    {"c": cutoff, "n": limit})).all()
        return [r[0] for r in rows]

    async def _rows(self, s: Any, sql: str, **p: Any) -> list[dict[str, Any]]:
        return [_jsonable(dict(r._mapping)) for r in (await s.execute(text(sql), p)).all()]

    async def export_session(self, session_id: str) -> dict[str, Any]:
        async with self._ro() as s:
            q = lambda sql: self._rows(s, sql, s_=session_id)  # noqa: E731
            traces = []
            for t in await q("select * from traces where session_id = :s_ order by started_at"):
                t["events"] = await self._rows(s, "select seq, type, t, data from trace_events where trace_id = :i order by seq", i=t["id"])
                traces.append(t)
            email_s = await q("select * from email_sessions where session_id = :s_")
            return {
                "sessionId": session_id,
                "messages": [{"role": m["role"], "content": m["content"]} for m in await q("select role, content from messages where session_id = :s_ order by seq")],
                "traces": traces,
                "outbox": await q("select id, kind, payload, created_at from outbox where session_id = :s_ order by id"),
                "approvals": await q("select * from approvals where session_id = :s_ order by created_at"),
                "shadow_drafts": await q("select * from shadow_drafts where session_id = :s_ order by created_at"),
                "handoffs": await q("select * from handoffs where session_id = :s_ order by created_at"),
                "findings": await q("select * from monitor_findings where session_id = :s_ order by created_at"),
                "email": {"session": email_s[0], "messages": await q("select * from email_messages where session_id = :s_")} if email_s else None,
                "sms": {"session": sms_s[0], "messages": await q("select * from sms_messages where session_id = :s_")} if (sms_s := await q("select * from sms_sessions where session_id = :s_")) else None,
            }

    async def erase_session(self, session_id: str) -> dict[str, int]:
        p = {"s": session_id}
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:s))"), p)  # not while the conversation is being saved
            out = {
                "messages": (await s.execute(text("select count(*) from messages where session_id = :s"), p)).scalar_one(),
                "traces": (await s.execute(text("delete from traces where session_id = :s"), p)).rowcount,  # events cascade
                "outbox": (await s.execute(text("delete from outbox where session_id = :s"), p)).rowcount,
                "approvals": (await s.execute(text("delete from approvals where session_id = :s"), p)).rowcount,
                "shadow_drafts": (await s.execute(text("delete from shadow_drafts where session_id = :s"), p)).rowcount,
                "handoffs": (await s.execute(text("delete from handoffs where session_id = :s"), p)).rowcount,
                "findings": (await s.execute(text("delete from monitor_findings where session_id = :s"), p)).rowcount,
                "replies": (await s.execute(text("delete from idempotency_keys where session_id = :s"), p)).rowcount,
            }
            out["calls"] = (await s.execute(text("delete from voice_calls where session_id = :s"), p)).rowcount
            out["attachments"] = (await s.execute(text("delete from attachments where session_id = :s"), p)).rowcount
            out["routes"] = (await s.execute(text("delete from session_routes where session_id = :s"), p)).rowcount
            out["rolloutAssignments"] = (await s.execute(text("delete from rollout_assignments where session_id = :s"), p)).rowcount
            out["reviews"] = (await s.execute(text("delete from conversation_reviews where session_id = :s"), p)).rowcount
            out["tags"] = (await s.execute(text("delete from conversation_tags where session_id = :s"), p)).rowcount
            out["judgements"] = (await s.execute(text("delete from qa_judgements where session_id = :s"), p)).rowcount
            out["coachingNotes"] = (await s.execute(text("delete from coaching_notes where session_id = :s"), p)).rowcount
            out["feedback"] = (await s.execute(text("delete from conversation_feedback where session_id = :s"), p)).rowcount
            out["exports"] = (await s.execute(text("delete from trace_exports where trace_id in (select id from traces where session_id = :s)"), p)).rowcount
            out["inbox"] = (await s.execute(text("delete from inbox_events where handoff_id in (select id from handoffs where session_id = :s)"), p)).rowcount
            out["email"] = ((await s.execute(text("delete from email_messages where session_id = :s"), p)).rowcount
                            + (await s.execute(text("delete from email_sessions where session_id = :s"), p)).rowcount)
            out["sms"] = ((await s.execute(text("delete from sms_messages where session_id = :s"), p)).rowcount
                          + (await s.execute(text("delete from sms_sessions where session_id = :s"), p)).rowcount)
            await s.execute(text("delete from sessions where id = :s"), p)  # messages cascade
            await s.execute(text("delete from session_index where session_id = :s"), p)
        return {k: int(v) for k, v in out.items()}

    async def export_facts(self, customer_id: str) -> dict[str, str]:
        async with self._ro() as s:
            rows = (await s.execute(select(FactRow.key, FactRow.value).where(FactRow.customer_id == customer_id))).all()
        return {r.key: r.value for r in rows}

    async def erase_facts(self, customer_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(FactRow).where(FactRow.customer_id == customer_id))).rowcount

    async def export_memories(self, customer_id: str) -> list[dict[str, Any]]:
        async with self._ro() as s:
            return await self._rows(s, "select id, text, source_session, created_at, updated_at from customer_memories where customer_id = :c order by updated_at desc", c=customer_id)

    async def erase_memories(self, customer_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from customer_memories where customer_id = :c"), {"c": customer_id})).rowcount
