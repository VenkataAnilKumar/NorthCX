"""Postgres implementations of the memory, trace and approval repositories."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ..approvals import Approval
from ..trace import Trace, TraceEvent, TraceSummary
from ..types import Message
from .models import ApprovalRow, FactRow, MessageRow, SessionRow, TraceEventRow, TraceRow


def _jsonable(value: Any) -> Any:
    """Make arbitrary tool output safe for a JSONB column."""
    return json.loads(json.dumps(value, default=str))


class _Base:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sm = async_sessionmaker(engine, expire_on_commit=False)


class PgMemoryStore(_Base):
    """Session history and per-customer facts."""

    async def load_messages(self, session_id: str) -> list[Message]:
        async with self._sm() as s:
            rows = (await s.execute(
                select(MessageRow.role, MessageRow.content).where(MessageRow.session_id == session_id).order_by(MessageRow.seq)
            )).all()
        return [{"role": r.role, "content": r.content} for r in rows]

    async def save_messages(self, session_id: str, messages: list[Message]) -> None:
        """Replace the session's history atomically. Saves for one session are serialised by an advisory lock."""
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:id))"), {"id": session_id})
            await s.execute(pg_insert(SessionRow).values(id=session_id).on_conflict_do_update(
                index_elements=[SessionRow.id], set_={"updated_at": func.now()}))
            await s.execute(delete(MessageRow).where(MessageRow.session_id == session_id))
            if messages:
                await s.execute(pg_insert(MessageRow), [
                    {"session_id": session_id, "seq": i, "role": m["role"], "content": _jsonable(m["content"])}
                    for i, m in enumerate(messages)
                ])

    async def get_facts(self, customer_id: str) -> dict[str, str]:
        async with self._sm() as s:
            rows = (await s.execute(select(FactRow.key, FactRow.value).where(FactRow.customer_id == customer_id))).all()
        return {r.key: r.value for r in rows}

    async def set_fact(self, customer_id: str, key: str, value: str) -> None:
        async with self._sm.begin() as s:
            await s.execute(pg_insert(FactRow).values(customer_id=customer_id, key=key, value=value).on_conflict_do_update(
                index_elements=[FactRow.customer_id, FactRow.key], set_={"value": value, "updated_at": func.now()}))


class PgTraceStore(_Base):
    async def save(self, trace: Trace) -> None:
        summary = TraceSummary(trace.id, trace.agent_id, trace.session_id, len(trace.events), trace.status(),
                               trace.events[0].t if trace.events else None, trace.tools_called())
        async with self._sm.begin() as s:
            values = dict(id=trace.id, session_id=trace.session_id, agent_id=trace.agent_id, status=summary.status,
                          started_at=summary.started_at, tools=summary.tools, event_count=summary.events)
            await s.execute(pg_insert(TraceRow).values(**values).on_conflict_do_update(
                index_elements=[TraceRow.id], set_={k: v for k, v in values.items() if k != "id"}))
            await s.execute(delete(TraceEventRow).where(TraceEventRow.trace_id == trace.id))
            if trace.events:
                await s.execute(pg_insert(TraceEventRow), [
                    {"trace_id": trace.id, "seq": i, "type": e.type, "t": e.t, "data": _jsonable(e.data)}
                    for i, e in enumerate(trace.events)
                ])

    async def get(self, trace_id: str) -> Trace | None:
        async with self._sm() as s:
            row = (await s.execute(select(TraceRow).where(TraceRow.id == trace_id))).scalar_one_or_none()
            if row is None:
                return None
            events = (await s.execute(
                select(TraceEventRow).where(TraceEventRow.trace_id == trace_id).order_by(TraceEventRow.seq))).scalars().all()
        t = Trace(agent_id=row.agent_id, session_id=row.session_id, id=row.id)
        t.events = [TraceEvent(e.t, e.type, e.data) for e in events]
        return t

    async def summaries(self, session_id: str | None = None, limit: int = 200) -> list[TraceSummary]:
        q = select(TraceRow).order_by(TraceRow.started_at.desc().nulls_last()).limit(limit)
        if session_id:
            q = q.where(TraceRow.session_id == session_id)
        async with self._sm() as s:
            rows = (await s.execute(q)).scalars().all()
        return [TraceSummary(r.id, r.agent_id, r.session_id, r.event_count, r.status, r.started_at, list(r.tools)) for r in rows]


class PgApprovalStore(_Base):
    @staticmethod
    def _to_approval(r: ApprovalRow) -> Approval:
        return Approval(trace_id=r.trace_id, session_id=r.session_id, tool=r.tool, input=r.input, reason=r.reason, id=r.id,
                        state=r.state, created_at=r.created_at, decided_by=r.decided_by, decided_at=r.decided_at)

    async def add(self, **kw: Any) -> Approval:
        a = Approval(**kw)
        async with self._sm.begin() as s:
            await s.execute(pg_insert(ApprovalRow).values(
                id=a.id, trace_id=a.trace_id, session_id=a.session_id, tool=a.tool, input=_jsonable(a.input),
                reason=a.reason, state=a.state, created_at=a.created_at))
        return a

    async def get(self, approval_id: str) -> Approval | None:
        async with self._sm() as s:
            r = (await s.execute(select(ApprovalRow).where(ApprovalRow.id == approval_id))).scalar_one_or_none()
        return self._to_approval(r) if r else None

    async def list(self, state: str | None = None) -> list[Approval]:
        q = select(ApprovalRow).order_by(ApprovalRow.created_at)
        if state:
            q = q.where(ApprovalRow.state == state)
        async with self._sm() as s:
            return [self._to_approval(r) for r in (await s.execute(q)).scalars().all()]

    async def decide(self, approval_id: str, approved: bool, by: str) -> Approval:
        """Atomic: only a pending approval can be decided, so concurrent decisions cannot both win."""
        import time

        state = "approved" if approved else "rejected"
        async with self._sm.begin() as s:
            res = await s.execute(update(ApprovalRow).where(ApprovalRow.id == approval_id, ApprovalRow.state == "pending")
                                  .values(state=state, decided_by=by, decided_at=time.time()).returning(ApprovalRow))
            row = res.scalar_one_or_none()
            if row is None:
                existing = (await s.execute(select(ApprovalRow).where(ApprovalRow.id == approval_id))).scalar_one_or_none()
                if existing is None:
                    raise KeyError(f"Unknown approval {approval_id}")
                raise ValueError(f"Approval {approval_id} already {existing.state}")
            return self._to_approval(row)
