"""Routes for insights, conversation search, reviews, ratings, tags and transcripts."""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from northcx.access import Identity
from northcx.analytics_qa import ask as ask_insights
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import AskBody, FeedbackBody, ReviewBody
from northcx.api.responses import SessionTags, TagAdded, TagRemoved, Transcript
from northcx.handoffs import transcript
from northcx.insights import TAG
from northcx.privacy import customer_ref
from northcx.reviews import quality, queue as review_queue_rows, Review, review_json, ReviewError, validate as review_validate

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    actor = d.actor
    events = d.events
    fb = d.fb
    insight = d.insight
    provider = d.provider
    record = d.record
    review_repo = d.review_repo
    runtime = d.runtime
    tag_repo = d.tag_repo
    too_many = d.too_many
    traces = d.traces

    # ---- insights ----
    def window(from_: float | None, to: float | None) -> tuple[float, float] | JSONResponse:
        now = time.time()
        end = now if to is None else to
        start = end - 7 * 86400 if from_ is None else from_
        if start >= end or end - start > 366 * 86400:
            return _err(400, "bad_request", "'from' must be before 'to', and the period at most 366 days")
        return start, end

    @app.get("/v1/insights/overview")
    async def insights_overview(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        return w if isinstance(w, JSONResponse) else await insight.overview(w[0], w[1], agent, environment)

    @app.post("/v1/insights/ask")
    async def insights_ask(body: AskBody, request: Request) -> Any:
        """A question about performance in plain words. The model only plans the query (one known figure, a period, maybe an agent); the numbers
        and the sentence come from the same code as the Insights pages, and the plan is returned so the reading can be checked."""
        who: Identity = request.state.identity
        if not (await access.limiter.hit(f"insights-ask:{who.key_id or 'open'}", 15))[0]:
            return too_many(60, "questions")
        try:
            out = await ask_insights(runtime.llm, insight, body.question, [a.id for a in await provider.all()], body.environment, tags=tag_repo, can_list=who.can("traces:read"))
        except Exception:
            log.exception("insights question failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "insights.ask", "insights", answerable=out["answerable"], metric=(out.get("plan") or {}).get("metric"))
        return out

    @app.get("/v1/insights/timeseries")
    async def insights_series(from_: float | None = Query(None, alias="from"), to: float | None = None, bucket: str = "day", agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        if isinstance(w, JSONResponse):
            return w
        if bucket not in ("hour", "day"):
            return _err(400, "bad_request", "bucket must be hour or day")
        return {"bucket": bucket, "points": await insight.series(w[0], w[1], bucket, agent, environment)}

    @app.get("/v1/insights/failures")
    async def insights_failures(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        return w if isinstance(w, JSONResponse) else {"causes": await insight.failure_analysis(w[0], w[1], agent, environment)}

    @app.get("/v1/insights/gaps")
    async def insights_gaps(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        return w if isinstance(w, JSONResponse) else await insight.intent_gaps(w[0], w[1], agent, environment)

    @app.post("/v1/sessions/{session_id}/feedback", status_code=201)
    async def post_feedback(session_id: str, body: FeedbackBody, request: Request) -> Any:
        """A customer's rating of a conversation (1 to 5). A chat token can rate only its own conversation; a second rating replaces the first."""
        who: Identity = request.state.identity
        if who.session_id is not None and session_id != who.session_id:
            await record(request, "auth.denied", f"POST /v1/sessions/{session_id}/feedback", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot rate another conversation")
        if not await traces.summaries(session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        new = await fb.add(session_id, body.rating, body.comment.strip())
        if events is not None:
            await events.emit("conversation.rated", {"rating": body.rating, "replaced": not new}, session_id)
        return JSONResponse({"saved": True, "replaced": not new}, status_code=201)

    @app.get("/v1/reviews/queue")
    async def review_queue(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production",
                           includeReviewed: bool = False, sample: float = 0.05, limit: int = 50) -> Any:
        """Conversations most worth a human look: hand-offs, low ratings, failed or blocked turns, plus a small random sample."""
        end = time.time() if to is None else to
        start = end - 14 * 86400 if from_ is None else from_
        if start >= end or end - start > 366 * 86400 or not 0 <= sample <= 1:
            return _err(400, "bad_request", "'from' must be before 'to', the period at most 366 days, and sample between 0 and 1")
        turns, handoffs, feedback = await insight._load(start, end, agent, environment)
        reviewed = await review_repo.for_sessions(list({t.session_id for t in turns}))
        return {"queue": review_queue_rows(turns, handoffs, feedback, reviewed, includeReviewed, sample, max(1, min(limit, 200)))}

    @app.get("/v1/sessions/{session_id}/transcript", responses={200: {"model": Transcript}})
    async def session_transcript(session_id: str) -> Any:
        """Everything a reviewer needs to judge one conversation."""
        summaries = await traces.summaries(session_id, 200)
        if not summaries:
            return _err(404, "not_found", "Unknown conversation")
        msgs = await runtime.store.load_messages(session_id)
        hs = await runtime.handoffs.list(None, session_id, 20)
        rev = await review_repo.get(session_id)
        fbk = await fb.for_session(session_id)
        return {"sessionId": session_id, "transcript": transcript(msgs), "tags": await tag_repo.all_for(session_id),
                "traces": [{"id": t.id, "status": t.status, "tools": t.tools, "startedAt": t.started_at, "agentVersion": t.agent_version, "environment": t.environment}
                           for t in sorted(summaries, key=lambda t: t.started_at or 0)],
                "handoffs": [{"id": h.id, "trigger": h.trigger, "state": h.state, "queue": h.queue, "reason": h.reason} for h in hs],
                "rating": fbk.rating if fbk else None, "review": review_json(rev) if rev else None}

    @app.put("/v1/sessions/{session_id}/review")
    async def put_review(session_id: str, body: ReviewBody, request: Request) -> Any:
        if not await traces.summaries(session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        handed = bool(await runtime.handoffs.list(None, session_id, 1))
        try:
            verdict, handoff, failures, note = review_validate(body.verdict, body.handoff, body.failures, body.note, handed)
        except ReviewError as e:
            return _err(400, "bad_request", str(e))
        who = actor(request, None)
        new = await review_repo.put(Review(session_id, verdict, handoff, failures, note, who))
        await record(request, "conversation.review", customer_ref(session_id), verdict=verdict, handoff=handoff, failures=failures)
        return {"saved": True, "replaced": not new}

    @app.get("/v1/insights/review-quality")
    async def review_quality(from_: float | None = Query(None, alias="from"), to: float | None = None) -> Any:
        w = window(from_, to)
        if isinstance(w, JSONResponse):
            return w
        return {"period": {"from": w[0], "to": w[1]}, **quality(await review_repo.between(w[0], w[1]))}

    @app.get("/v1/conversations/search")
    async def conversation_search(q: str = "", status: str | None = None, tag: str | None = None, handedOff: bool | None = None, agent: str | None = None,
                                  environment: str = "production", from_: float | None = Query(None, alias="from"), to: float | None = None, limit: int = 50,
                                  language: str | None = None) -> Any:
        """Find conversations by what was said, outcome, hand-off, rating and tag. Text shown is masked."""
        end = time.time() if to is None else to
        start = end - 30 * 86400 if from_ is None else from_
        if start >= end or end - start > 366 * 86400 or len(q) > 200:
            return _err(400, "bad_request", "'from' must be before 'to', the period at most 366 days, and the search at most 200 characters")
        return {"conversations": await insight.search(start, end, tag_repo, q, status, tag, handedOff, agent, environment, max(1, min(limit, 200)), language)}

    @app.get("/v1/sessions/{session_id}/tags", responses={200: {"model": SessionTags}})
    async def get_tags(session_id: str) -> Any:
        return {"sessionId": session_id, "tags": await tag_repo.all_for(session_id)}

    @app.put("/v1/sessions/{session_id}/tags/{tag}", responses={200: {"model": TagAdded}})
    async def add_tag(session_id: str, tag: str, request: Request) -> Any:
        if not TAG.match(tag):
            return _err(400, "bad_request", "A tag is 1-40 lowercase letters, digits, - or _")
        if not await traces.summaries(session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        try:
            new = await tag_repo.add(session_id, tag, actor(request, None))
        except ValueError as e:
            return _err(409, "conflict", str(e))
        if new:
            await record(request, "conversation.tag", customer_ref(session_id), tag=tag)
        return {"sessionId": session_id, "tag": tag, "added": new, "tags": await tag_repo.all_for(session_id)}

    @app.delete("/v1/sessions/{session_id}/tags/{tag}", responses={200: {"model": TagRemoved}})
    async def remove_tag(session_id: str, tag: str, request: Request) -> Any:
        if not await tag_repo.remove(session_id, tag):
            return _err(404, "not_found", "That conversation does not have that tag")
        await record(request, "conversation.untag", customer_ref(session_id), tag=tag)
        return {"removed": True, "tags": await tag_repo.all_for(session_id)}
