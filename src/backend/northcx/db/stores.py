"""Postgres implementations of the memory, trace and approval repositories."""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ..approvals import Approval
from ..handoffs import Handoff
from ..simulation.store import SimRun
from ..outbox import OutboxMessage
from ..trace import Trace, TraceEvent, TraceSummary
from ..types import Message
from .models import ApprovalRow, FactRow, HandoffRow, MessageRow, OutboxRow, SimRunRow, SessionRow, TraceEventRow, TraceRow


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
                        state=r.state, created_at=r.created_at, decided_by=r.decided_by, decided_at=r.decided_at,
                        agent_id=r.agent_id, customer_id=r.customer_id, note=r.note, result=r.result)

    async def add(self, **kw: Any) -> Approval:
        a = Approval(**kw)
        async with self._sm.begin() as s:
            await s.execute(pg_insert(ApprovalRow).values(
                id=a.id, trace_id=a.trace_id, session_id=a.session_id, tool=a.tool, input=_jsonable(a.input),
                reason=a.reason, state=a.state, created_at=a.created_at, agent_id=a.agent_id, customer_id=a.customer_id))
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

    async def _transition(self, approval_id: str, from_state: str, values: dict[str, Any]) -> tuple[ApprovalRow | None, str]:
        """Atomically move one approval out of `from_state`. Returns (updated row, its state); the row is None when the
        approval was in another state (that state is returned). Raises KeyError if it does not exist."""
        async with self._sm.begin() as s:
            row = (await s.execute(update(ApprovalRow).where(ApprovalRow.id == approval_id, ApprovalRow.state == from_state)
                                   .values(**values).returning(ApprovalRow))).scalar_one_or_none()
            if row is not None:
                return row, values["state"]
            existing = (await s.execute(select(ApprovalRow).where(ApprovalRow.id == approval_id))).scalar_one_or_none()
            if existing is None:
                raise KeyError(f"Unknown approval {approval_id}")
            return None, existing.state

    async def decide(self, approval_id: str, approved: bool, by: str, note: str | None = None) -> Approval:
        row, current = await self._transition(approval_id, "pending", dict(
            state="approved" if approved else "rejected", decided_by=by, decided_at=time.time(), note=note))
        if row is None:
            raise ValueError(f"Approval {approval_id} already {current}")
        return self._to_approval(row)

    async def claim_execution(self, approval_id: str) -> Approval:
        row, current = await self._transition(approval_id, "approved", dict(state="executing"))
        if row is None:
            raise ValueError(f"Approval {approval_id} is {current}, not approved")
        return self._to_approval(row)

    async def complete(self, approval_id: str, ok: bool, result: Any) -> Approval:
        row, current = await self._transition(approval_id, "executing", dict(
            state="executed" if ok else "failed", result=_jsonable(result)))
        if row is None:
            raise ValueError(f"Approval {approval_id} is {current}, not executing")
        return self._to_approval(row)

    async def expire(self, approval_id: str) -> Approval | None:
        row, _ = await self._transition(approval_id, "pending", dict(state="expired", decided_at=time.time()))
        return self._to_approval(row) if row else None


class PgOutbox(_Base):
    @staticmethod
    def _to_msg(r: OutboxRow) -> OutboxMessage:
        return OutboxMessage(r.session_id, r.kind, r.payload, id=r.id, created_at=r.created_at,
                             delivered_at=r.delivered_at, attempts=r.attempts)

    async def add(self, session_id: str, kind: str, payload: dict[str, Any]) -> OutboxMessage:
        async with self._sm.begin() as s:
            row = (await s.execute(pg_insert(OutboxRow).values(
                session_id=session_id, kind=kind, payload=_jsonable(payload), created_at=time.time()).returning(OutboxRow))).scalar_one()
            return self._to_msg(row)

    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]:
        async with self._sm() as s:
            rows = (await s.execute(select(OutboxRow).where(OutboxRow.session_id == session_id, OutboxRow.id > after_id)
                                    .order_by(OutboxRow.id).limit(limit))).scalars().all()
        return [self._to_msg(r) for r in rows]

    async def undelivered(self, limit: int = 100) -> list[OutboxMessage]:
        async with self._sm() as s:
            rows = (await s.execute(select(OutboxRow).where(OutboxRow.delivered_at.is_(None)).order_by(OutboxRow.id).limit(limit))).scalars().all()
        return [self._to_msg(r) for r in rows]

    async def record_attempt(self, message_id: int, delivered: bool) -> None:
        values: dict[str, Any] = {"attempts": OutboxRow.attempts + 1}
        if delivered:
            values["delivered_at"] = time.time()
        async with self._sm.begin() as s:
            await s.execute(update(OutboxRow).where(OutboxRow.id == message_id).values(**values))


class PgHandoffs(_Base):
    @staticmethod
    def _to_handoff(r: HandoffRow) -> Handoff:
        return Handoff(session_id=r.session_id, trace_id=r.trace_id, agent_id=r.agent_id, customer_id=r.customer_id,
                       trigger=r.trigger, reason=r.reason, topics=list(r.topics), package=r.package, id=r.id, state=r.state,
                       created_at=r.created_at, resolved_by=r.resolved_by, resolved_at=r.resolved_at, note=r.note)

    async def add(self, handoff: Handoff) -> Handoff:
        async with self._sm.begin() as s:
            await s.execute(pg_insert(HandoffRow).values(
                id=handoff.id, session_id=handoff.session_id, trace_id=handoff.trace_id, agent_id=handoff.agent_id,
                customer_id=handoff.customer_id, trigger=handoff.trigger, reason=handoff.reason, topics=handoff.topics,
                package=_jsonable(handoff.package), state=handoff.state, created_at=handoff.created_at))
        return handoff

    async def get(self, handoff_id: str) -> Handoff | None:
        async with self._sm() as s:
            r = (await s.execute(select(HandoffRow).where(HandoffRow.id == handoff_id))).scalar_one_or_none()
        return self._to_handoff(r) if r else None

    async def list(self, state: str | None = None, session_id: str | None = None, limit: int = 200) -> list[Handoff]:
        q = select(HandoffRow).order_by(HandoffRow.created_at.desc()).limit(limit)
        if state:
            q = q.where(HandoffRow.state == state)
        if session_id:
            q = q.where(HandoffRow.session_id == session_id)
        async with self._sm() as s:
            return [self._to_handoff(r) for r in (await s.execute(q)).scalars().all()]

    async def resolve(self, handoff_id: str, by: str, note: str | None = None) -> Handoff:
        """Atomic: only an open handoff can be resolved, once."""
        async with self._sm.begin() as s:
            row = (await s.execute(update(HandoffRow).where(HandoffRow.id == handoff_id, HandoffRow.state == "open")
                                   .values(state="resolved", resolved_by=by, resolved_at=time.time(), note=note)
                                   .returning(HandoffRow))).scalar_one_or_none()
            if row is not None:
                return self._to_handoff(row)
            existing = (await s.execute(select(HandoffRow).where(HandoffRow.id == handoff_id))).scalar_one_or_none()
        if existing is None:
            raise KeyError(f"Unknown handoff {handoff_id}")
        raise ValueError(f"Handoff {handoff_id} already {existing.state}")


class PgSimRuns(_Base):
    @staticmethod
    def _to_run(r: SimRunRow) -> SimRun:
        return SimRun(mode=r.mode, passed=r.passed, counts=r.counts, agent_digests=r.agent_digests, results=r.results,
                      seconds=r.seconds, source=r.source, meta=r.meta, id=r.id, created_at=r.created_at)

    async def add(self, run: SimRun) -> SimRun:
        async with self._sm.begin() as s:
            await s.execute(pg_insert(SimRunRow).values(
                id=run.id, created_at=run.created_at, mode=run.mode, source=run.source, passed=run.passed,
                seconds=run.seconds, counts=run.counts, agent_digests=run.agent_digests, meta=_jsonable(run.meta),
                results=_jsonable(run.results)))
        return run

    async def get(self, run_id: str) -> SimRun | None:
        async with self._sm() as s:
            r = (await s.execute(select(SimRunRow).where(SimRunRow.id == run_id))).scalar_one_or_none()
        return self._to_run(r) if r else None

    async def list(self, limit: int = 50) -> list[SimRun]:
        async with self._sm() as s:
            rows = (await s.execute(select(SimRunRow).order_by(SimRunRow.created_at.desc()).limit(limit))).scalars().all()
        return [self._to_run(r) for r in rows]
