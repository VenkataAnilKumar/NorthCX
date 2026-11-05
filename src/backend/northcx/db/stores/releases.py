"""Postgres stores for agent versions, releases, staged rollouts, simulation runs and managed scenarios."""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from northcx.db.models import AgentVersionRow, ReleaseRow, SimRunRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.rollout import Rollout
from northcx.simulation.managed import ManagedScenario
from northcx.simulation.store import SimRun
from northcx.versions import AgentVersion, Conflict, Release


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
        async with self._ro() as s:
            r = (await s.execute(select(AgentVersionRow).where(AgentVersionRow.id == version_id))).scalar_one_or_none()
        return self._to_version(r) if r else None

    async def get_number(self, agent_id: str, number: int) -> AgentVersion | None:
        async with self._ro() as s:
            r = (await s.execute(select(AgentVersionRow).where(AgentVersionRow.agent_id == agent_id,
                                                               AgentVersionRow.number == number))).scalar_one_or_none()
        return self._to_version(r) if r else None

    async def list(self, agent_id: str) -> list[AgentVersion]:
        async with self._ro() as s:
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
        async with self._ro() as s:
            rows = (await s.execute(select(ReleaseRow).where(ReleaseRow.agent_id == agent_id, ReleaseRow.environment == environment)
                                    .order_by(ReleaseRow.seq.desc()).limit(limit))).scalars().all()
        return [self._to_release(r) for r in rows]

    async def current(self, agent_id: str, environment: str = "production") -> Release | None:
        rows = await self.list(agent_id, environment, 1)
        return rows[0] if rows else None

    async def agents_with_releases(self, environment: str = "production") -> list[str]:
        async with self._ro() as s:
            rows = (await s.execute(select(ReleaseRow.agent_id).where(ReleaseRow.environment == environment).distinct())).all()
        return sorted(r[0] for r in rows)


class PgRollouts(_Base):
    @staticmethod
    def _r(r: Any) -> Rollout:
        return Rollout(r.agent_id, r.environment, r.candidate_number, r.control_number, r.percent, r.started_by, r.note, r.state, r.ended_by, r.ended_at, r.id, r.started_at)

    @staticmethod
    def _p(r: Rollout) -> dict[str, Any]:
        return {"id": r.id, "a": r.agent_id, "e": r.environment, "cn": r.candidate_number, "ctl": r.control_number, "p": r.percent, "st": r.state,
                "by": r.started_by, "note": r.note, "eby": r.ended_by, "sa": r.started_at, "ea": r.ended_at}

    async def add(self, r: Rollout) -> None:
        try:
            async with self._sm.begin() as s:
                await s.execute(text("insert into rollouts (id, agent_id, environment, candidate_number, control_number, percent, state, started_by, note, ended_by, started_at, ended_at) "
                                     "values (:id, :a, :e, :cn, :ctl, :p, :st, :by, :note, :eby, :sa, :ea)"), self._p(r))
        except IntegrityError as e:
            raise Conflict(f"A rollout is already running for {r.agent_id} in {r.environment}") from e

    async def save(self, r: Rollout) -> None:
        async with self._sm.begin() as s:
            await s.execute(text("update rollouts set percent = :p, state = :st, ended_by = :eby, ended_at = :ea where id = :id"), self._p(r))

    async def _one(self, where: str, params: dict[str, Any]) -> Rollout | None:
        async with self._ro() as s:
            row = (await s.execute(text(f"select * from rollouts where {where}"), params)).first()
        return self._r(row) if row else None

    async def active(self, agent_id: str, environment: str) -> Rollout | None:
        return await self._one("agent_id = :a and environment = :e and state = 'active'", {"a": agent_id, "e": environment})

    async def get(self, rollout_id: str) -> Rollout | None:
        return await self._one("id = :id", {"id": rollout_id})

    async def history(self, agent_id: str, limit: int = 50) -> list[Rollout]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from rollouts where agent_id = :a order by started_at desc limit :n"), {"a": agent_id, "n": limit})).all()
        return [self._r(r) for r in rows]

    async def assign(self, rollout_id: str, session_id: str, arm: str) -> str:
        async with self._sm.begin() as s:
            await s.execute(text("insert into rollout_assignments (rollout_id, session_id, arm) values (:r, :s, :a) on conflict do nothing"), {"r": rollout_id, "s": session_id, "a": arm})
            return (await s.execute(text("select arm from rollout_assignments where rollout_id = :r and session_id = :s"), {"r": rollout_id, "s": session_id})).scalar_one()

    async def arm_sessions(self, rollout_id: str, limit: int = 5000) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {"control": [], "candidate": []}
        async with self._ro() as s:
            for arm in out:
                rows = (await s.execute(text("select session_id from rollout_assignments where rollout_id = :r and arm = :a limit :n"), {"r": rollout_id, "a": arm, "n": limit})).all()
                out[arm] = [r[0] for r in rows]
        return out

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from rollout_assignments where session_id = :s"), {"s": session_id})).rowcount


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
        async with self._ro() as s:
            r = (await s.execute(select(SimRunRow).where(SimRunRow.id == run_id))).scalar_one_or_none()
        return self._to_run(r) if r else None

    async def list(self, limit: int = 50) -> list[SimRun]:
        async with self._ro() as s:
            rows = (await s.execute(select(SimRunRow).order_by(SimRunRow.created_at.desc()).limit(limit))).scalars().all()
        return [self._to_run(r) for r in rows]


class PgScenarios(_Base):
    @staticmethod
    def _m(r: Any) -> ManagedScenario:
        return ManagedScenario(r.name, r.agent_id, r.required, r.definition, r.created_by, r.updated_by, r.created_at, r.updated_at, r.revision)

    async def list(self) -> list[ManagedScenario]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from managed_scenarios order by name"))).all()
        return [self._m(r) for r in rows]

    async def get(self, name: str) -> ManagedScenario | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from managed_scenarios where name = :n"), {"n": name})).first()
        return self._m(r) if r else None

    async def put(self, scenario: Any, definition: dict[str, Any], by: str, now: float | None = None) -> tuple[ManagedScenario, bool]:
        now = time.time() if now is None else now
        async with self._sm.begin() as s:
            r = (await s.execute(text(
                "insert into managed_scenarios (name, agent_id, required, definition, created_by, updated_by, created_at, updated_at, revision) "
                "values (:n, :a, :r, cast(:d as jsonb), :b, :b, :t, :t, 1) on conflict (name) do update set agent_id = excluded.agent_id, required = excluded.required, "
                "definition = excluded.definition, updated_by = excluded.updated_by, updated_at = excluded.updated_at, revision = managed_scenarios.revision + 1 "
                "returning *, (xmax = 0) as inserted"),
                {"n": scenario.name, "a": scenario.agent, "r": scenario.required, "d": json.dumps(_jsonable(definition)), "b": by, "t": now})).one()
        return self._m(r), bool(r.inserted)

    async def delete(self, name: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from managed_scenarios where name = :n returning name"), {"n": name})).first() is not None
