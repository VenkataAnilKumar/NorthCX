"""Postgres implementations of the memory, trace and approval repositories."""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ..access import ApiKey
from ..approvals import Approval
from ..channels.email import EmailSession
from ..audit import GENESIS, AuditEntry, Verification, entry_hash, verify_entries
from ..handoffs import Handoff
from ..simulation.store import SimRun
from ..versions import AgentVersion, Release
from ..outbox import OutboxMessage
from ..trace import Trace, TraceEvent, TraceSummary
from ..types import Message
from .models import ApprovalRow, FactRow, HandoffRow, AgentVersionRow, ApiKeyRow, AuditRow, EmailMessageRow, EmailSessionRow, MessageRow, OutboxRow, ReleaseRow, SimRunRow, SessionRow, TraceEventRow, TraceRow


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
                               trace.events[0].t if trace.events else None, trace.tools_called(), trace.agent_version)
        async with self._sm.begin() as s:
            values = dict(id=trace.id, session_id=trace.session_id, agent_id=trace.agent_id, status=summary.status,
                          started_at=summary.started_at, tools=summary.tools, event_count=summary.events,
                          agent_version=summary.agent_version)
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
        t = Trace(agent_id=row.agent_id, session_id=row.session_id, id=row.id, agent_version=row.agent_version)
        t.events = [TraceEvent(e.t, e.type, e.data) for e in events]
        return t

    async def summaries(self, session_id: str | None = None, limit: int = 200) -> list[TraceSummary]:
        q = select(TraceRow).order_by(TraceRow.started_at.desc().nulls_last()).limit(limit)
        if session_id:
            q = q.where(TraceRow.session_id == session_id)
        async with self._sm() as s:
            rows = (await s.execute(q)).scalars().all()
        return [TraceSummary(r.id, r.agent_id, r.session_id, r.event_count, r.status, r.started_at, list(r.tools), r.agent_version)
                for r in rows]


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
                             delivered_at=r.delivered_at, attempts=r.attempts, last_attempt_at=r.last_attempt_at)

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

    async def undelivered(self, limit: int = 100, max_attempts: int | None = None) -> list[OutboxMessage]:
        q = select(OutboxRow).where(OutboxRow.delivered_at.is_(None)).order_by(OutboxRow.id).limit(limit)
        if max_attempts is not None:
            q = q.where(OutboxRow.attempts < max_attempts)
        async with self._sm() as s:
            rows = (await s.execute(q)).scalars().all()
        return [self._to_msg(r) for r in rows]

    async def record_attempt(self, message_id: int, delivered: bool, at: float | None = None) -> None:
        at = at if at is not None else time.time()
        values: dict[str, Any] = {"attempts": OutboxRow.attempts + 1, "last_attempt_at": at}
        if delivered:
            values["delivered_at"] = at
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


class PgVersions(_Base):
    @staticmethod
    def _to_version(r: AgentVersionRow) -> AgentVersion:
        return AgentVersion(agent_id=r.agent_id, number=r.number, spec=r.spec, digest=r.digest, author=r.author, note=r.note,
                            id=r.id, created_at=r.created_at)

    async def create(self, agent_id: str, spec: dict[str, Any], digest: str, author: str, note: str | None) -> AgentVersion:
        """Numbers are assigned inside one transaction under a per-agent lock, so they are gapless and unique."""
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"agent_versions:{agent_id}"})
            last = (await s.execute(select(func.max(AgentVersionRow.number)).where(AgentVersionRow.agent_id == agent_id))).scalar()
            v = AgentVersion(agent_id, (last or 0) + 1, spec, digest, author, note)
            await s.execute(pg_insert(AgentVersionRow).values(
                id=v.id, agent_id=agent_id, number=v.number, spec=_jsonable(spec), digest=digest, author=author, note=note,
                created_at=v.created_at))
            return v

    async def get(self, version_id: str) -> AgentVersion | None:
        async with self._sm() as s:
            r = (await s.execute(select(AgentVersionRow).where(AgentVersionRow.id == version_id))).scalar_one_or_none()
        return self._to_version(r) if r else None

    async def get_number(self, agent_id: str, number: int) -> AgentVersion | None:
        async with self._sm() as s:
            r = (await s.execute(select(AgentVersionRow).where(AgentVersionRow.agent_id == agent_id,
                                                               AgentVersionRow.number == number))).scalar_one_or_none()
        return self._to_version(r) if r else None

    async def list(self, agent_id: str) -> list[AgentVersion]:
        async with self._sm() as s:
            rows = (await s.execute(select(AgentVersionRow).where(AgentVersionRow.agent_id == agent_id)
                                    .order_by(AgentVersionRow.number.desc()))).scalars().all()
        return [self._to_version(r) for r in rows]


class PgReleases(_Base):
    @staticmethod
    def _to_release(r: ReleaseRow) -> Release:
        return Release(agent_id=r.agent_id, action=r.action, by=r.by, version_id=r.version_id, number=r.number, gate=r.gate,
                       note=r.note, previous_number=r.previous_number, environment=r.environment, id=r.id,
                       created_at=r.created_at, seq=r.seq)

    async def add(self, release: Release) -> Release:
        async with self._sm.begin() as s:
            row = (await s.execute(pg_insert(ReleaseRow).values(
                id=release.id, agent_id=release.agent_id, environment=release.environment, action=release.action,
                version_id=release.version_id, number=release.number, previous_number=release.previous_number, by=release.by,
                note=release.note, gate=_jsonable(release.gate), created_at=release.created_at).returning(ReleaseRow))).scalar_one()
            return self._to_release(row)

    async def list(self, agent_id: str, environment: str = "production", limit: int = 100) -> list[Release]:
        async with self._sm() as s:
            rows = (await s.execute(select(ReleaseRow).where(ReleaseRow.agent_id == agent_id, ReleaseRow.environment == environment)
                                    .order_by(ReleaseRow.seq.desc()).limit(limit))).scalars().all()
        return [self._to_release(r) for r in rows]

    async def current(self, agent_id: str, environment: str = "production") -> Release | None:
        rows = await self.list(agent_id, environment, 1)
        return rows[0] if rows else None

    async def agents_with_releases(self, environment: str = "production") -> list[str]:
        async with self._sm() as s:
            rows = (await s.execute(select(ReleaseRow.agent_id).where(ReleaseRow.environment == environment).distinct())).all()
        return sorted(r[0] for r in rows)


class PgKeys(_Base):
    @staticmethod
    def _to_key(r: ApiKeyRow) -> ApiKey:
        return ApiKey(name=r.name, role=r.role, key_id=r.key_id, key_hash=r.key_hash, created_by=r.created_by, created_at=r.created_at,
                      expires_at=r.expires_at, revoked_at=r.revoked_at, revoked_by=r.revoked_by, last_used_at=r.last_used_at)

    async def create(self, key: ApiKey) -> ApiKey:
        async with self._sm.begin() as s:
            await s.execute(pg_insert(ApiKeyRow).values(
                key_id=key.key_id, name=key.name, role=key.role, key_hash=key.key_hash, created_by=key.created_by,
                created_at=key.created_at, expires_at=key.expires_at))
        return key

    async def get(self, key_id: str) -> ApiKey | None:
        async with self._sm() as s:
            r = (await s.execute(select(ApiKeyRow).where(ApiKeyRow.key_id == key_id))).scalar_one_or_none()
        return self._to_key(r) if r else None

    async def list(self) -> list[ApiKey]:
        async with self._sm() as s:
            rows = (await s.execute(select(ApiKeyRow).order_by(ApiKeyRow.created_at.desc()))).scalars().all()
        return [self._to_key(r) for r in rows]

    async def revoke(self, key_id: str, by: str) -> ApiKey:
        async with self._sm.begin() as s:
            row = (await s.execute(update(ApiKeyRow).where(ApiKeyRow.key_id == key_id, ApiKeyRow.revoked_at.is_(None))
                                   .values(revoked_at=time.time(), revoked_by=by).returning(ApiKeyRow))).scalar_one_or_none()
            if row is not None:
                return self._to_key(row)
            existing = (await s.execute(select(ApiKeyRow).where(ApiKeyRow.key_id == key_id))).scalar_one_or_none()
        if existing is None:
            raise KeyError(key_id)
        raise ValueError(f"Key {key_id} is already revoked")

    async def touch(self, key_id: str, at: float) -> None:
        async with self._sm.begin() as s:
            await s.execute(update(ApiKeyRow).where(ApiKeyRow.key_id == key_id).values(last_used_at=at))


class PgAudit(_Base):
    @staticmethod
    def _to_entry(r: AuditRow) -> AuditEntry:
        return AuditEntry(actor=r.actor, role=r.role, action=r.action, target=r.target, outcome=r.outcome, detail=r.detail,
                          key_id=r.key_id, at=r.at, id=r.id, prev_hash=r.prev_hash, hash=r.hash)

    async def append(self, entry: AuditEntry) -> AuditEntry:
        """Appends are serialised by an advisory lock so each entry chains onto the true previous one."""
        entry.detail = _jsonable(entry.detail)
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext('audit_log'))"))
            last = (await s.execute(select(AuditRow).order_by(AuditRow.id.desc()).limit(1))).scalar_one_or_none()
            entry.id = (last.id + 1) if last else 1
            entry.prev_hash = last.hash if last else GENESIS
            entry.hash = entry_hash(entry)
            await s.execute(pg_insert(AuditRow).values(
                id=entry.id, at=entry.at, actor=entry.actor, role=entry.role, key_id=entry.key_id, action=entry.action,
                target=entry.target[:300], outcome=entry.outcome, detail=entry.detail, prev_hash=entry.prev_hash, hash=entry.hash))
        return entry

    async def list(self, limit: int = 100, before_id: int | None = None, actor: str | None = None,
                   action: str | None = None) -> list[AuditEntry]:
        q = select(AuditRow).order_by(AuditRow.id.desc()).limit(limit)
        if before_id is not None:
            q = q.where(AuditRow.id < before_id)
        if actor:
            q = q.where(AuditRow.actor == actor)
        if action:
            q = q.where(AuditRow.action == action)
        async with self._sm() as s:
            return [self._to_entry(r) for r in (await s.execute(q)).scalars().all()]

    async def verify(self) -> Verification:
        async with self._sm() as s:
            rows = (await s.execute(select(AuditRow).order_by(AuditRow.id))).scalars().all()
        return verify_entries([self._to_entry(r) for r in rows])


class PgEmailRepo(_Base):
    @staticmethod
    def _to_session(r: EmailSessionRow) -> EmailSession:
        return EmailSession(session_id=r.session_id, sender=r.sender, subject=r.subject, last_message_id=r.last_message_id,
                            customer_id=r.customer_id, verified=r.verified, references=list(r.references), created_at=r.created_at)

    async def get_session(self, session_id: str) -> EmailSession | None:
        async with self._sm() as s:
            r = (await s.execute(select(EmailSessionRow).where(EmailSessionRow.session_id == session_id))).scalar_one_or_none()
        return self._to_session(r) if r else None

    async def find_session(self, message_ids: list[str]) -> EmailSession | None:
        if not message_ids:
            return None
        async with self._sm() as s:
            rows = (await s.execute(select(EmailMessageRow.message_id, EmailMessageRow.session_id)
                                    .where(EmailMessageRow.message_id.in_(message_ids)))).all()
            by_id = {r.message_id: r.session_id for r in rows}
            for mid in message_ids:  # nearest first
                sid = by_id.get(mid)
                if sid:
                    r = (await s.execute(select(EmailSessionRow).where(EmailSessionRow.session_id == sid))).scalar_one_or_none()
                    if r:
                        return self._to_session(r)
        return None

    async def save_session(self, session: EmailSession) -> None:
        values = dict(session_id=session.session_id, sender=session.sender, subject=session.subject[:500],
                      customer_id=session.customer_id, verified=session.verified, last_message_id=session.last_message_id,
                      references=session.references, created_at=session.created_at)
        async with self._sm.begin() as s:
            await s.execute(pg_insert(EmailSessionRow).values(**values).on_conflict_do_update(
                index_elements=[EmailSessionRow.session_id], set_={k: v for k, v in values.items() if k != "session_id"}))

    async def has_message(self, message_id: str) -> bool:
        async with self._sm() as s:
            return (await s.execute(select(EmailMessageRow.message_id).where(EmailMessageRow.message_id == message_id))).first() is not None

    async def record_message(self, message_id: str, session_id: str, direction: str, outcome: str, peer: str) -> bool:
        async with self._sm.begin() as s:
            res = await s.execute(pg_insert(EmailMessageRow).values(
                message_id=message_id[:998], session_id=session_id, direction=direction, outcome=outcome, peer=peer, created_at=time.time()
            ).on_conflict_do_nothing(index_elements=[EmailMessageRow.message_id]))
            return res.rowcount == 1

    async def recent_count(self, peer: str, direction: str, since: float) -> int:
        async with self._sm() as s:
            return (await s.execute(select(func.count()).select_from(EmailMessageRow).where(
                EmailMessageRow.peer == peer, EmailMessageRow.direction == direction, EmailMessageRow.created_at >= since))).scalar_one()
