"""Postgres stores for conversations: history and facts, traces, which agent a conversation is with, and customer memories."""
from __future__ import annotations

import time
from typing import Any
import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import FactRow, MessageRow, SessionRow, TraceEventRow, TraceRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.knowledge import tokens
from northcx.tenancy import current_tenant
from northcx.memory import check_note, MAX_PER_CUSTOMER, Memory, text_hash
from northcx.trace import Trace, TraceEvent, TraceSummary
from northcx.types import Message


class PgMemoryStore(_Base):
    """Session history and per-customer facts."""

    async def load_messages(self, session_id: str) -> list[Message]:
        async with self._ro() as s:
            rows = (await s.execute(
                select(MessageRow.role, MessageRow.content).where(MessageRow.session_id == session_id).order_by(MessageRow.seq)
            )).all()
        return [{"role": r.role, "content": r.content} for r in rows]

    async def save_messages(self, session_id: str, messages: list[Message]) -> None:
        """Replace the session's history atomically. Saves for one session are serialised by an advisory lock."""
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:id))"), {"id": session_id})
            await s.execute(pg_insert(SessionRow).values(id=session_id, tenant_id=current_tenant()).on_conflict_do_update(
                index_elements=[SessionRow.tenant_id, SessionRow.id], set_={"updated_at": func.now()}))
            # Only what changed is written: a normal turn appends a few messages, so the (growing) earlier history is left alone.
            existing = (await s.execute(select(MessageRow.role, MessageRow.content).where(MessageRow.session_id == session_id).order_by(MessageRow.seq))).all()
            new = [{"session_id": session_id, "seq": i, "role": m["role"], "content": _jsonable(m["content"])} for i, m in enumerate(messages)]
            same = 0
            while same < len(existing) and same < len(new) and existing[same].role == new[same]["role"] and existing[same].content == new[same]["content"]:
                same += 1
            if same < len(existing):
                await s.execute(delete(MessageRow).where(MessageRow.session_id == session_id, MessageRow.seq >= same))
            if same < len(new):
                await s.execute(pg_insert(MessageRow).values(new[same:]))

    async def get_facts(self, customer_id: str) -> dict[str, str]:
        async with self._ro() as s:
            rows = (await s.execute(select(FactRow.key, FactRow.value).where(FactRow.customer_id == customer_id))).all()
        return {r.key: r.value for r in rows}

    async def set_fact(self, customer_id: str, key: str, value: str) -> None:
        async with self._sm.begin() as s:
            await s.execute(pg_insert(FactRow).values(customer_id=customer_id, key=key, value=value, tenant_id=current_tenant()).on_conflict_do_update(
                index_elements=[FactRow.tenant_id, FactRow.customer_id, FactRow.key], set_={"value": value, "updated_at": func.now()}))


class PgTraceStore(_Base):
    async def save(self, trace: Trace) -> None:
        summary = TraceSummary(trace.id, trace.agent_id, trace.session_id, len(trace.events), trace.status(),
                               trace.events[0].t if trace.events else None, trace.tools_called(), trace.agent_version, trace.environment)
        async with self._sm.begin() as s:
            values = dict(id=trace.id, session_id=trace.session_id, agent_id=trace.agent_id, status=summary.status,
                          started_at=summary.started_at, tools=summary.tools, event_count=summary.events,
                          agent_version=summary.agent_version, environment=trace.environment)
            await s.execute(pg_insert(TraceRow).values(**values).on_conflict_do_update(
                index_elements=[TraceRow.id], set_={k: v for k, v in values.items() if k != "id"}))
            await s.execute(delete(TraceEventRow).where(TraceEventRow.trace_id == trace.id))
            if trace.events:  # one statement for all the events
                await s.execute(pg_insert(TraceEventRow).values([
                    {"trace_id": trace.id, "seq": i, "type": e.type, "t": e.t, "data": _jsonable(e.data)}
                    for i, e in enumerate(trace.events)
                ]))

    async def get(self, trace_id: str) -> Trace | None:
        async with self._ro() as s:
            row = (await s.execute(select(TraceRow).where(TraceRow.id == trace_id))).scalar_one_or_none()
            if row is None:
                return None
            events = (await s.execute(
                select(TraceEventRow).where(TraceEventRow.trace_id == trace_id).order_by(TraceEventRow.seq))).scalars().all()
        t = Trace(agent_id=row.agent_id, session_id=row.session_id, id=row.id, agent_version=row.agent_version, environment=row.environment)
        t.events = [TraceEvent(e.t, e.type, e.data) for e in events]
        return t

    async def summaries(self, session_id: str | None = None, limit: int = 200) -> list[TraceSummary]:
        q = select(TraceRow).order_by(TraceRow.started_at.desc().nulls_last()).limit(limit)
        if session_id:
            q = q.where(TraceRow.session_id == session_id)
        async with self._ro() as s:
            rows = (await s.execute(q)).scalars().all()
        return [TraceSummary(r.id, r.agent_id, r.session_id, r.event_count, r.status, r.started_at, list(r.tools), r.agent_version, r.environment)
                for r in rows]


class PgSessionRoutes(_Base):
    async def get(self, session_id: str) -> str | None:
        async with self._ro() as s:
            return (await s.execute(text("select agent_id from session_routes where session_id = :s"), {"s": session_id})).scalar_one_or_none()

    async def set(self, session_id: str, agent_id: str) -> None:
        async with self._sm.begin() as s:
            await s.execute(text("insert into session_routes (session_id, agent_id, updated_at) values (:s, :a, :t) "
                                 "on conflict (tenant_id, session_id) do update set agent_id = excluded.agent_id, updated_at = excluded.updated_at"),
                            {"s": session_id, "a": agent_id, "t": time.time()})

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from session_routes where session_id = :s"), {"s": session_id})).rowcount


class PgMemories(_Base):
    @staticmethod
    def _m(r: Any) -> Memory:
        return Memory(r.customer_id, r.text, r.source_session, r.created_at, r.updated_at, r.id)

    async def remember(self, customer_id: str, text_: str, session_id: str | None = None, now: float | None = None) -> tuple[Memory, bool]:
        note = check_note(text_)
        now = time.time() if now is None else now
        h = text_hash(note)
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"mem:{customer_id}"})
            row = (await s.execute(text("update customer_memories set updated_at = :n where customer_id = :c and text_hash = :h returning *"),
                                   {"n": now, "c": customer_id, "h": h})).first()
            if row is not None:
                return self._m(row), False
            mid = uuid.uuid4().hex
            await s.execute(text("insert into customer_memories (id, customer_id, text, text_hash, source_session, created_at, updated_at) "
                                 "values (:i, :c, :t, :h, :s, :n, :n)"), {"i": mid, "c": customer_id, "t": note, "h": h, "s": session_id, "n": now})
            await s.execute(text("delete from customer_memories where customer_id = :c and id in "
                                 "(select id from customer_memories where customer_id = :c order by updated_at desc offset :k)"),
                            {"c": customer_id, "k": MAX_PER_CUSTOMER})
        return Memory(customer_id, note, session_id, now, now, mid), True

    async def list(self, customer_id: str, limit: int = 200) -> list[Memory]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from customer_memories where customer_id = :c order by updated_at desc limit :n"),
                                    {"c": customer_id, "n": limit})).all()
        return [self._m(r) for r in rows]

    async def recall(self, customer_id: str, query: str, limit: int = 5) -> list[Memory]:
        terms = list(dict.fromkeys(tokens(query)))
        if not terms:
            return []
        async with self._ro() as s:
            rows = (await s.execute(text(
                "select *, ts_rank_cd(tsv, to_tsquery('english', :q)) as rank from customer_memories "
                "where customer_id = :c and tsv @@ to_tsquery('english', :q) order by rank desc, updated_at desc limit :n"),
                {"q": " | ".join(terms), "c": customer_id, "n": limit})).all()
        return [self._m(r) for r in rows]

    async def forget(self, customer_id: str, memory_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from customer_memories where customer_id = :c and id = :i returning id"),
                                    {"c": customer_id, "i": memory_id})).first() is not None

    async def forget_all(self, customer_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from customer_memories where customer_id = :c"), {"c": customer_id})).rowcount
