"""Postgres stores for insights: the trace-derived source, ratings, reviews, tags, monitoring findings and the trace-export queue."""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import MonitorFindingRow
from northcx.db.stores._base import _Base
from northcx.insights import facts_from_trace, FeedbackFacts, HandoffFacts, MAX_TAGS, TurnFacts
from northcx.monitor import Finding
from northcx.reviews import Review
from northcx.trace import Trace, TraceEvent
from northcx.trace_export import ExportJob, MAX_ATTEMPTS as EXPORT_MAX_ATTEMPTS


class PgInsightsSource(_Base):
    async def turns(self, since: float, until: float, agent: str | None, environment: str, limit: int) -> list[TurnFacts]:
        q = ("select t.id, t.session_id, t.agent_id, t.environment, t.agent_version, e.type, e.t as ts, e.data from "
             "(select * from traces where started_at between :a and :b and environment = :env" + (" and agent_id = :ag" if agent else "") +
             " order by started_at desc limit :n) t join trace_events e on e.trace_id = t.id order by t.started_at desc, t.id, e.seq")
        params: dict[str, Any] = {"a": since, "b": until, "env": environment, "n": limit}
        if agent:
            params["ag"] = agent
        async with self._ro() as s:
            rows = (await s.execute(text(q), params)).all()
        out: list[TurnFacts] = []
        cur: Trace | None = None
        for r in rows:
            if cur is None or cur.id != r.id:
                if cur is not None:
                    out.append(facts_from_trace(cur))
                cur = Trace(agent_id=r.agent_id, session_id=r.session_id, id=r.id, agent_version=r.agent_version, environment=r.environment)
            cur.events.append(TraceEvent(r.ts, r.type, r.data))
        if cur is not None:
            out.append(facts_from_trace(cur))
        return out

    async def handoffs(self, since: float, until: float) -> list[HandoffFacts]:
        async with self._ro() as s:
            rows = (await s.execute(text("select session_id, trace_id, trigger, topics, queue, created_at from handoffs where created_at between :a and :b"),
                                    {"a": since, "b": until})).all()
        return [HandoffFacts(r.session_id, r.trace_id, r.trigger, list(r.topics), r.queue, r.created_at) for r in rows]

    async def feedback(self, since: float, until: float) -> list[FeedbackFacts]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from conversation_feedback where created_at between :a and :b"), {"a": since, "b": until})).all()
        return [FeedbackFacts(r.session_id, r.rating, r.created_at, r.comment) for r in rows]


class PgFeedback(_Base):
    async def add(self, session_id: str, rating: int, comment: str, at: float | None = None) -> bool:
        async with self._sm.begin() as s:
            r = await s.execute(text("insert into conversation_feedback (session_id, rating, comment, created_at) values (:s, :r, :c, :t) "
                                     "on conflict (session_id) do update set rating = excluded.rating, comment = excluded.comment, created_at = excluded.created_at "
                                     "returning (xmax = 0) as inserted"), {"s": session_id, "r": rating, "c": comment[:1000], "t": time.time() if at is None else at})
            return bool(r.scalar_one())

    async def for_session(self, session_id: str) -> FeedbackFacts | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from conversation_feedback where session_id = :s"), {"s": session_id})).first()
        return FeedbackFacts(r.session_id, r.rating, r.created_at, r.comment) if r else None

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from conversation_feedback where session_id = :s"), {"s": session_id})).rowcount


class PgReviews(_Base):
    @staticmethod
    def _r(r: Any) -> Review:
        return Review(r.session_id, r.verdict, r.handoff, list(r.failures), r.note, r.reviewer, r.reviewed_at)

    async def put(self, review: Review) -> bool:
        async with self._sm.begin() as s:
            r = await s.execute(text(
                "insert into conversation_reviews (session_id, verdict, handoff, failures, note, reviewer, reviewed_at) values (:s, :v, :h, cast(:f as jsonb), :n, :r, :t) "
                "on conflict (session_id) do update set verdict = excluded.verdict, handoff = excluded.handoff, failures = excluded.failures, note = excluded.note, "
                "reviewer = excluded.reviewer, reviewed_at = excluded.reviewed_at returning (xmax = 0) as inserted"),
                {"s": review.session_id, "v": review.verdict, "h": review.handoff, "f": json.dumps(review.failures), "n": review.note, "r": review.reviewer, "t": review.reviewed_at})
            return bool(r.scalar_one())

    async def get(self, session_id: str) -> Review | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from conversation_reviews where session_id = :s"), {"s": session_id})).first()
        return self._r(r) if r else None

    async def between(self, since: float, until: float) -> list[Review]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from conversation_reviews where reviewed_at between :a and :b"), {"a": since, "b": until})).all()
        return [self._r(r) for r in rows]

    async def for_sessions(self, session_ids: list[str]) -> dict[str, Review]:
        if not session_ids:
            return {}
        async with self._ro() as s:
            rows = (await s.execute(text("select * from conversation_reviews where session_id = any(:ids)"), {"ids": session_ids})).all()
        return {r.session_id: self._r(r) for r in rows}

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from conversation_reviews where session_id = :s"), {"s": session_id})).rowcount


class PgTags(_Base):
    async def add(self, session_id: str, tag: str, by: str) -> bool:
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"tags:{session_id}"})
            n = (await s.execute(text("select count(*) from conversation_tags where session_id = :s"), {"s": session_id})).scalar_one()
            r = await s.execute(text("insert into conversation_tags (session_id, tag, by, created_at) values (:s, :t, :b, :c) on conflict do nothing returning tag"),
                                {"s": session_id, "t": tag, "b": by[:200], "c": time.time()}) if n < MAX_TAGS else None
            if r is None:
                if (await s.execute(text("select 1 from conversation_tags where session_id = :s and tag = :t"), {"s": session_id, "t": tag})).first():
                    return False
                raise ValueError(f"a conversation can have at most {MAX_TAGS} tags")
            return r.first() is not None

    async def remove(self, session_id: str, tag: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from conversation_tags where session_id = :s and tag = :t returning tag"), {"s": session_id, "t": tag})).first() is not None

    async def for_sessions(self, session_ids: list[str]) -> dict[str, list[str]]:
        if not session_ids:
            return {}
        async with self._ro() as s:
            rows = (await s.execute(text("select session_id, tag from conversation_tags where session_id = any(:ids) order by tag"), {"ids": session_ids})).all()
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r.session_id, []).append(r.tag)
        return out

    async def all_for(self, session_id: str) -> list[str]:
        return (await self.for_sessions([session_id])).get(session_id, [])

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from conversation_tags where session_id = :s"), {"s": session_id})).rowcount


class PgMonitor(_Base):
    async def add(self, findings: list[Finding]) -> None:
        if not findings:
            return
        async with self._sm.begin() as s:
            await s.execute(pg_insert(MonitorFindingRow).values([
                dict(id=f.id, rule=f.rule, severity=f.severity, detail=f.detail[:400], trace_id=f.trace_id, session_id=f.session_id,
                     agent_id=f.agent_id, agent_version=f.agent_version, created_at=f.created_at) for f in findings]))

    async def list(self, *, rule=None, severity=None, agent_id=None, session_id=None, since=None, limit=100) -> list[Finding]:
        q = select(MonitorFindingRow).order_by(MonitorFindingRow.created_at.desc()).limit(limit)
        for col, v in ((MonitorFindingRow.rule, rule), (MonitorFindingRow.severity, severity), (MonitorFindingRow.agent_id, agent_id),
                       (MonitorFindingRow.session_id, session_id)):
            if v:
                q = q.where(col == v)
        if since is not None:
            q = q.where(MonitorFindingRow.created_at >= since)
        async with self._ro() as s:
            rows = (await s.execute(q)).scalars().all()
        return [Finding(r.rule, r.severity, r.detail, r.trace_id, r.session_id, r.agent_id, r.agent_version, r.created_at, r.id) for r in rows]

    async def counts(self, since: float | None = None) -> dict[str, dict[str, int]]:
        q = select(MonitorFindingRow.rule, MonitorFindingRow.severity, func.count()).group_by(MonitorFindingRow.rule, MonitorFindingRow.severity)
        if since is not None:
            q = q.where(MonitorFindingRow.created_at >= since)
        async with self._ro() as s:
            rows = (await s.execute(q)).all()
        out: dict[str, dict[str, int]] = {}
        for rule, sev, n in rows:
            out.setdefault(rule, {})[sev] = n
        return out


class PgExports(_Base):
    @staticmethod
    def _j(r: Any) -> ExportJob:
        return ExportJob(r.trace_id, r.exporter, r.id, r.created_at, r.attempts, r.last_attempt_at, r.delivered_at, r.error)

    async def enqueue(self, jobs: list[ExportJob]) -> None:
        if not jobs:
            return
        async with self._sm.begin() as s:
            await s.execute(text("insert into trace_exports (id, trace_id, exporter, created_at) values (:id, :t, :e, :c)"),
                            [{"id": j.id, "t": j.trace_id, "e": j.exporter, "c": j.created_at} for j in jobs])

    async def pending(self, limit: int = 100) -> list[ExportJob]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from trace_exports where delivered_at is null and attempts < :m order by created_at, id limit :n"),
                                    {"m": EXPORT_MAX_ATTEMPTS, "n": limit})).all()
        return [self._j(r) for r in rows]

    async def record(self, job_id: str, delivered: bool, error: str | None, at: float) -> None:
        async with self._sm.begin() as s:
            await s.execute(text("update trace_exports set attempts = attempts + 1, last_attempt_at = :t, error = :err, "
                                 "delivered_at = case when :d then :t else delivered_at end where id = :i"),
                            {"t": at, "err": None if delivered else error, "d": delivered, "i": job_id})

    async def for_trace(self, trace_id: str) -> list[ExportJob]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from trace_exports where trace_id = :t order by created_at, id"), {"t": trace_id})).all()
        return [self._j(r) for r in rows]

    async def erase_traces(self, trace_ids: list[str]) -> int:
        if not trace_ids:
            return 0
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from trace_exports where trace_id = any(:ids)"), {"ids": trace_ids})).rowcount

    async def counts(self) -> dict[str, int]:
        async with self._ro() as s:
            r = (await s.execute(text("select count(*) filter (where delivered_at is null and attempts < :m) as pending, count(*) filter (where delivered_at is not null) as delivered, "
                                      "count(*) filter (where delivered_at is null and attempts >= :m) as failed from trace_exports"), {"m": EXPORT_MAX_ATTEMPTS})).one()
        return {"pending": int(r.pending), "delivered": int(r.delivered), "failed": int(r.failed)}
