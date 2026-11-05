"""Postgres stores for held actions, hand-offs, and the queues that deliver them (outbox and helpdesk inbox)."""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.approvals import Approval
from northcx.db.models import ApprovalRow, HandoffRow, OutboxRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.handoffs import Handoff
from northcx.inbox import InboxEvent, MAX_ATTEMPTS
from northcx.outbox import OutboxMessage


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
        async with self._ro() as s:
            r = (await s.execute(select(ApprovalRow).where(ApprovalRow.id == approval_id))).scalar_one_or_none()
        return self._to_approval(r) if r else None

    async def list(self, state: str | None = None) -> list[Approval]:
        q = select(ApprovalRow).order_by(ApprovalRow.created_at)
        if state:
            q = q.where(ApprovalRow.state == state)
        async with self._ro() as s:
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


class PgHandoffs(_Base):
    @staticmethod
    def _to_handoff(r: HandoffRow) -> Handoff:
        return Handoff(session_id=r.session_id, trace_id=r.trace_id, agent_id=r.agent_id, customer_id=r.customer_id,
                       trigger=r.trigger, reason=r.reason, topics=list(r.topics), package=r.package, id=r.id, state=r.state,
                       created_at=r.created_at, resolved_by=r.resolved_by, resolved_at=r.resolved_at, note=r.note,
                       queue=r.queue, after_hours=r.after_hours)

    async def add(self, handoff: Handoff) -> Handoff:
        async with self._sm.begin() as s:
            await s.execute(pg_insert(HandoffRow).values(
                id=handoff.id, session_id=handoff.session_id, trace_id=handoff.trace_id, agent_id=handoff.agent_id,
                customer_id=handoff.customer_id, trigger=handoff.trigger, reason=handoff.reason, topics=handoff.topics,
                package=_jsonable(handoff.package), state=handoff.state, created_at=handoff.created_at,
                queue=handoff.queue, after_hours=handoff.after_hours))
        return handoff

    async def get(self, handoff_id: str) -> Handoff | None:
        async with self._ro() as s:
            r = (await s.execute(select(HandoffRow).where(HandoffRow.id == handoff_id))).scalar_one_or_none()
        return self._to_handoff(r) if r else None

    async def list(self, state: str | None = None, session_id: str | None = None, limit: int = 200, queue: str | None = None) -> list[Handoff]:
        q = select(HandoffRow).order_by(HandoffRow.created_at.desc()).limit(limit)
        if state:
            q = q.where(HandoffRow.state == state)
        if session_id:
            q = q.where(HandoffRow.session_id == session_id)
        if queue:
            q = q.where(HandoffRow.queue == queue)
        async with self._ro() as s:
            return [self._to_handoff(r) for r in (await s.execute(q)).scalars().all()]

    async def set_package_field(self, handoff_id: str, key: str, value: Any) -> bool:
        async with self._sm.begin() as s:
            r = await s.execute(text("update handoffs set package = jsonb_set(package, cast(:k as text[]), cast(:v as jsonb), true) where id = :id"),
                                {"k": [key], "v": json.dumps(_jsonable(value)), "id": handoff_id})
            return r.rowcount > 0

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


class PgOutbox(_Base):
    @staticmethod
    def _to_msg(r: OutboxRow) -> OutboxMessage:
        return OutboxMessage(r.session_id, r.kind, r.payload, id=r.id, created_at=r.created_at,
                             delivered_at=r.delivered_at, attempts=r.attempts, last_attempt_at=r.last_attempt_at)

    async def add(self, session_id: str, kind: str, payload: dict[str, Any]) -> OutboxMessage:
        async with self._sm.begin() as s:
            row = (await s.execute(pg_insert(OutboxRow).values(
                session_id=session_id, kind=kind, payload=_jsonable(payload), created_at=time.time()).returning(OutboxRow))).scalar_one()
            return self._to_msg(row)

    async def list(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[OutboxMessage]:
        async with self._ro() as s:
            rows = (await s.execute(select(OutboxRow).where(OutboxRow.session_id == session_id, OutboxRow.id > after_id)
                                    .order_by(OutboxRow.id).limit(limit))).scalars().all()
        return [self._to_msg(r) for r in rows]

    async def undelivered(self, limit: int = 100, max_attempts: int | None = None) -> list[OutboxMessage]:
        q = select(OutboxRow).where(OutboxRow.delivered_at.is_(None)).order_by(OutboxRow.id).limit(limit)
        if max_attempts is not None:
            q = q.where(OutboxRow.attempts < max_attempts)
        async with self._ro() as s:
            rows = (await s.execute(q)).scalars().all()
        return [self._to_msg(r) for r in rows]

    async def record_attempt(self, message_id: int, delivered: bool, at: float | None = None) -> None:
        at = at if at is not None else time.time()
        values: dict[str, Any] = {"attempts": OutboxRow.attempts + 1, "last_attempt_at": at}
        if delivered:
            values["delivered_at"] = at
        async with self._sm.begin() as s:
            await s.execute(update(OutboxRow).where(OutboxRow.id == message_id).values(**values))


class PgInbox(_Base):
    @staticmethod
    def _e(r: Any) -> InboxEvent:
        return InboxEvent(r.handoff_id, r.connector, r.event, r.id, r.created_at, r.attempts, r.last_attempt_at, r.delivered_at, r.external_ref, r.error)

    async def enqueue(self, events: list[InboxEvent]) -> None:
        if not events:
            return
        async with self._sm.begin() as s:
            await s.execute(text("insert into inbox_events (id, handoff_id, connector, event, created_at) values (:id, :h, :c, :e, :t)"),
                            [{"id": e.id, "h": e.handoff_id, "c": e.connector, "e": e.event, "t": e.created_at} for e in events])

    async def pending(self, limit: int = 100) -> list[InboxEvent]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from inbox_events where delivered_at is null and attempts < :m order by created_at, id limit :n"),
                                    {"m": MAX_ATTEMPTS, "n": limit})).all()
        return [self._e(r) for r in rows]

    async def record(self, event_id: str, delivered: bool, ref: str | None, error: str | None, at: float) -> None:
        async with self._sm.begin() as s:
            await s.execute(text("update inbox_events set attempts = attempts + 1, last_attempt_at = :t, error = :err, "
                                 "delivered_at = case when :d then :t else delivered_at end, external_ref = case when :d then :r else external_ref end where id = :i"),
                            {"t": at, "err": None if delivered else error, "d": delivered, "r": ref, "i": event_id})

    async def for_handoff(self, handoff_id: str) -> list[InboxEvent]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from inbox_events where handoff_id = :h order by created_at, id"), {"h": handoff_id})).all()
        return [self._e(r) for r in rows]

    async def erase_handoffs(self, handoff_ids: list[str]) -> int:
        if not handoff_ids:
            return 0
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from inbox_events where handoff_id = any(:ids)"), {"ids": handoff_ids})).rowcount
