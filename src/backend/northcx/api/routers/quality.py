"""Routes for Quality: the rubric, scorecards, calibration against reviewers, and coaching notes (E7)."""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import CoachingBody, RubricBody
from northcx.insights import ratio
from northcx.qa import CoachingNote, InMemoryCoaching, QAError, RubricService, calibration, score
from northcx.reviews import sampled

MAX_SESSIONS = 2000


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime, insight, review_repo, traces = d.record, d.runtime, d.insight, d.review_repo, d.traces
    rubrics: RubricService = getattr(runtime, "rubrics", None) or RubricService()
    coaching = getattr(runtime, "coaching", None) or InMemoryCoaching()
    app.state.rubrics, app.state.coaching = rubrics, coaching
    if type(runtime.privacy).__name__ == "InMemoryPrivacy":      # the Postgres backend erases the table itself
        runtime.privacy.coaching = coaching

    async def scored(days: int, agent: str | None) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str], dict[str, Any]]:
        rubric = await rubrics.get()
        until = time.time()
        turns, handoffs, feedback = await insight._load(until - days * 86400.0, until, agent, "production")
        by: dict[str, list[Any]] = {}
        for t in turns:
            by.setdefault(t.session_id, []).append(t)
        hs: dict[str, list[Any]] = {}
        for h in handoffs:
            hs.setdefault(h.session_id, []).append(h)
        rating = {f.session_id: f.rating for f in feedback}
        results = {}
        for sid in list(by)[:MAX_SESSIONS]:
            r = score(by[sid], hs.get(sid, []), rating.get(sid), rubric)
            results[sid] = {**r, "agentId": by[sid][0].agent_id, "turns": len(by[sid]), "startedAt": min(t.started_at for t in by[sid])}
        reviews = await review_repo.for_sessions(list(results))
        return rubric, results, {sid: r.verdict for sid, r in reviews.items()}, {"truncated": len(by) > MAX_SESSIONS}

    @app.get("/v1/quality/rubric")
    async def get_rubric() -> Any:
        return {**await rubrics.get(), "checks": {"kinds": list(__import__("northcx.qa", fromlist=["CHECKS"]).CHECKS)}}

    @app.put("/v1/quality/rubric")
    async def put_rubric(body: RubricBody, request: Request) -> Any:
        try:
            out = await rubrics.put(body.model_dump(), request.state.identity.name)
        except QAError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "quality.rubric", f"v{out['version']}", criteria=len(out["criteria"]), passMark=out["passMark"], sample=out["sample"])
        return out

    @app.delete("/v1/quality/rubric")
    async def reset_rubric(request: Request) -> Any:
        gone = await rubrics.reset()
        await record(request, "quality.rubric_reset", "default", had_custom=gone)
        return {"reset": gone}

    @app.get("/v1/quality/scorecards")
    async def scorecards(days: int = 7, agent: str | None = None) -> Any:
        """Score every conversation in the period against the rubric. Checks that did not apply to a conversation are left out of its score."""
        if not 1 <= days <= 90:
            return _err(400, "bad_request", "days must be between 1 and 90")
        rubric, results, verdicts, meta = await scored(days, agent)
        scores = [r["score"] for r in results.values() if r["score"] is not None]
        mark = rubric["passMark"]
        per_agent: dict[str, list[float]] = {}
        per_check: dict[str, dict[str, int]] = {}
        for r in results.values():
            if r["score"] is not None:
                per_agent.setdefault(r["agentId"], []).append(r["score"])
            for c in r["criteria"]:
                if c["result"] != "na":
                    s = per_check.setdefault(c["id"], {"pass": 0, "fail": 0})
                    s[c["result"]] += 1
        worst = sorted((s for s in results if results[s]["score"] is not None), key=lambda s: results[s]["score"])[:25]
        to_review = [s for s in results if s not in verdicts and sampled(s, rubric["sample"])][:50]
        return {"days": days, "rubricVersion": rubric["version"], "passMark": mark, "scored": len(scores), "conversations": len(results),
                "averageScore": round(sum(scores) / len(scores), 1) if scores else None, "passRate": ratio(sum(s >= mark for s in scores), len(scores)),
                "byAgent": [{"agent": a, "scored": len(v), "average": round(sum(v) / len(v), 1)} for a, v in sorted(per_agent.items())],
                "byCheck": [{"id": c["id"], "label": c["label"], "passed": per_check.get(c["id"], {}).get("pass", 0), "failed": per_check.get(c["id"], {}).get("fail", 0)} for c in rubric["criteria"]],
                "lowest": [{"sessionId": s, **results[s]} for s in worst], "sampleToReview": to_review, **meta,
                "note": "Scores come from recorded facts, not from reading the conversation; they point you at conversations to read, and calibration shows how far to trust them."}

    @app.get("/v1/quality/calibration")
    async def quality_calibration(days: int = 30) -> Any:
        if not 1 <= days <= 90:
            return _err(400, "bad_request", "days must be between 1 and 90")
        rubric, results, verdicts, _ = await scored(days, None)
        return {"rubricVersion": rubric["version"], "passMark": rubric["passMark"], **calibration({s: r["score"] for s, r in results.items()}, verdicts, rubric["passMark"])}

    @app.get("/v1/quality/coaching")
    async def list_coaching(sessionId: str | None = None, about: str | None = None) -> Any:
        return {"notes": [n.to_dict() for n in await coaching.list(sessionId, about, 100)]}

    @app.post("/v1/quality/coaching", status_code=201)
    async def add_coaching(body: CoachingBody, request: Request) -> Any:
        from northcx.memory import MemoryRejected
        from northcx.workspace import screen_staff_note
        if not await traces.summaries(body.session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        try:
            clean = screen_staff_note(body.note)       # no customer details, card numbers, secrets or instructions in a note
        except MemoryRejected as e:
            return _err(400, "bad_request", str(e))
        n = CoachingNote(body.session_id, body.about.strip(), clean, request.state.identity.name)
        await coaching.add(n)
        await record(request, "quality.coaching", n.id, about=n.about)
        return n.to_dict()

    @app.delete("/v1/quality/coaching/{note_id}")
    async def delete_coaching(note_id: str, request: Request) -> Any:
        who = request.state.identity
        mine = next((n for n in await coaching.list(None, None, 1000) if n.id == note_id), None)
        if mine is None:
            return _err(404, "not_found", "Unknown note")
        if mine.author != who.name and not who.can("keys:manage"):
            return _err(403, "forbidden", "Only the author or an administrator can delete a coaching note")
        await coaching.delete(note_id)
        await record(request, "quality.coaching_delete", note_id)
        return {"deleted": True}
