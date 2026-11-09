"""Routes for staged rollouts of an agent version."""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import PercentBody, PromoteBody, RolloutBody
from northcx.rollout import CANDIDATE, compare as compare_arms, CONTROL, rollout_json, RolloutService
from northcx.versions import Conflict, GateBlocked, NotFound


def register(app: FastAPI, d: AppDeps) -> None:
    actor = d.actor
    insight = d.insight
    need_env = d.need_env
    record = d.record
    rel_error = d.rel_error
    review_repo = d.review_repo
    rollouts = d.rollouts

    def need_rollouts() -> RolloutService | JSONResponse:
        return rollouts or _err(501, "not_configured", "Staged rollouts are not configured on this server")

    def held_by_two_person_rule(environment: str) -> JSONResponse | None:
        """A staged rollout puts a candidate in front of real customers, which is a release; with the two-person rule on for this environment it cannot skip the second person."""
        appr = getattr(d.releases, "approvals", None)
        if appr is not None and appr.needs_approval(environment):
            return _err(409, "conflict", f"{environment} needs a second person for every release, so staged rollouts are not available there; publish the version and have another person approve it")
        return None

    def rollout_error(e: Exception) -> JSONResponse:
        if isinstance(e, ValueError) and not isinstance(e, (Conflict, GateBlocked)):
            return _err(400, "bad_request", str(e))
        return rel_error(e)

    @app.post("/v1/agents/{agent_id}/rollouts", status_code=201)
    async def start_rollout(agent_id: str, body: RolloutBody, request: Request) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.environment, "releases:publish")) is not None:
            return denied
        if (held := held_by_two_person_rule(body.environment)) is not None:
            return held
        try:
            r = await svc.start(agent_id, body.version, body.percent, actor(request, body.by), body.environment, body.note)
        except GateBlocked as e:
            await record(request, "rollout.start", f"{agent_id}@{body.version}", "blocked", reasons=e.reasons[:10], environment=body.environment)
            return rel_error(e)
        except (NotFound, Conflict, ValueError) as e:
            return rollout_error(e)
        await record(request, "rollout.start", f"{agent_id}@{r.candidate_number}", percent=r.percent, environment=r.environment, control=r.control_number)
        return rollout_json(r)

    @app.get("/v1/agents/{agent_id}/rollouts")
    async def list_rollouts(agent_id: str) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        return {"rollouts": [rollout_json(r) for r in await svc.repo.history(agent_id)]}

    async def rollout_for(svc: RolloutService, agent_id: str, rollout_id: str) -> Any:
        r = await svc.repo.get(rollout_id)
        return r if r is not None and r.agent_id == agent_id else None

    @app.put("/v1/agents/{agent_id}/rollouts/{rollout_id}/percent")
    async def rollout_percent(agent_id: str, rollout_id: str, body: PercentBody, request: Request) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        cur = await rollout_for(svc, agent_id, rollout_id)
        if cur is None:
            return _err(404, "not_found", "Unknown rollout")
        if (denied := await need_env(request, cur.environment, "releases:publish")) is not None:
            return denied
        try:
            r = await svc.set_percent(agent_id, rollout_id, body.percent)
        except (NotFound, Conflict, ValueError) as e:
            return rollout_error(e)
        await record(request, "rollout.percent", f"{agent_id}@{r.candidate_number}", percent=r.percent, environment=r.environment)
        return rollout_json(r)

    @app.post("/v1/agents/{agent_id}/rollouts/{rollout_id}/promote")
    async def rollout_promote(agent_id: str, rollout_id: str, request: Request, body: PromoteBody | None = None) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        cur = await rollout_for(svc, agent_id, rollout_id)
        if cur is None:
            return _err(404, "not_found", "Unknown rollout")
        if (denied := await need_env(request, cur.environment, "releases:publish")) is not None:
            return denied
        if (held := held_by_two_person_rule(cur.environment)) is not None:
            return held
        try:
            r = await svc.promote(agent_id, rollout_id, actor(request, body.by if body else None), body.note if body else None)
        except GateBlocked as e:
            await record(request, "rollout.promote", f"{agent_id}@{cur.candidate_number}", "blocked", reasons=e.reasons[:10], environment=cur.environment)
            return rel_error(e)
        except (NotFound, Conflict, ValueError) as e:
            return rollout_error(e)
        await record(request, "rollout.promote", f"{agent_id}@{r.candidate_number}", environment=r.environment, percent=r.percent)
        return rollout_json(r)

    @app.post("/v1/agents/{agent_id}/rollouts/{rollout_id}/abort")
    async def rollout_abort(agent_id: str, rollout_id: str, request: Request) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        cur = await rollout_for(svc, agent_id, rollout_id)
        if cur is None:
            return _err(404, "not_found", "Unknown rollout")
        if (denied := await need_env(request, cur.environment, "releases:rollback")) is not None:
            return denied
        try:
            r = await svc.abort(agent_id, rollout_id, actor(request, None))
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "rollout.abort", f"{agent_id}@{r.candidate_number}", environment=r.environment)
        return rollout_json(r)

    @app.get("/v1/agents/{agent_id}/rollouts/{rollout_id}/comparison")
    async def rollout_comparison(agent_id: str, rollout_id: str) -> Any:
        """Control and candidate measured the same way, over the conversations assigned to each."""
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        r = await rollout_for(svc, agent_id, rollout_id)
        if r is None:
            return _err(404, "not_found", "Unknown rollout")
        arms = await svc.repo.arm_sessions(r.id)
        end = r.ended_at or time.time()
        turns, handoffs, feedback = await insight._load(r.started_at, end + 1, agent_id, r.environment)
        revs = await review_repo.for_sessions(arms[CONTROL] + arms[CANDIDATE])
        return {"rollout": rollout_json(r), **compare_arms(arms, turns, handoffs, feedback, revs, r.started_at, end),
                "versions": {CONTROL: r.control_number, CANDIDATE: r.candidate_number}}
