"""Insights (O5, O6, O7): numbers about how the agents are doing, computed from what the platform already records.

Every figure comes with its numerator, denominator and period, as the success-metrics rules require. Nothing here calls a model.
A *turn* is one customer message and the agent's handling of it (one trace); a *conversation* is a session.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from .safety.pii import PIIDetection
from .trace import Trace

MAX_TURNS = 20000
_PII = PIIDetection(mask_pii=True)
BUCKETS = {"hour": 3600, "day": 86400}


@dataclass
class TurnFacts:
    trace_id: str
    session_id: str
    agent_id: str
    environment: str
    started_at: float
    duration: float
    status: str
    tokens: int = 0
    llm_calls: int = 0
    fallback_calls: int = 0
    tools: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    empty_searches: list[str] = field(default_factory=list)  # knowledge searches that found nothing
    first_message: str = ""
    errored: bool = False  # any error event, including model failures
    text: str = ""  # what was said (customer and agent), lower-cased and capped, for conversation search
    last_reply: str = ""


@dataclass
class HandoffFacts:
    session_id: str
    trace_id: str
    trigger: str
    topics: list[str]
    queue: str | None
    created_at: float


@dataclass
class FeedbackFacts:
    session_id: str
    rating: int
    created_at: float
    comment: str = ""


def facts_from_trace(t: Trace) -> TurnFacts:
    ev = t.events
    start = ev[0].t if ev else 0.0
    f = TurnFacts(t.id, t.session_id, t.agent_id, t.environment, start, (ev[-1].t - start) if ev else 0.0, t.status())
    pending_search: str | None = None
    said: list[str] = []
    for e in ev:
        d = e.data
        if e.type == "user":
            said.append(str(d.get("message", "")))
            if not f.first_message:
                f.first_message = str(d.get("message", ""))
        elif e.type == "reply":
            f.last_reply = str(d.get("reply", ""))
            said.append(f.last_reply)
        elif e.type == "llm":
            f.llm_calls += 1
            f.tokens += int(d.get("tokens", 0) or 0)
            f.fallback_calls += 1 if d.get("fallback") else 0
        elif e.type == "tool_call":
            f.tools.append(str(d.get("name")))
            pending_search = str((d.get("input") or {}).get("query", "")) if d.get("name") == "search_knowledge" else None
        elif e.type == "tool_result":
            out = d.get("output")
            if pending_search is not None and isinstance(out, dict) and out.get("results") == []:
                f.empty_searches.append(pending_search)
            pending_search = None
        elif e.type == "error":
            f.errored = True
            if d.get("tool"):
                f.tool_errors.append(str(d["tool"]))
        elif e.type == "guardrail" and d.get("reason") and "masked" not in str(d["reason"]).lower():
            f.guardrails.append(str(d.get("guardrail", "guardrail")))
    f.text = " ".join(said).lower()[:4000]
    return f


class InsightsSource(Protocol):
    async def turns(self, since: float, until: float, agent: str | None, environment: str, limit: int) -> list[TurnFacts]: ...
    async def handoffs(self, since: float, until: float) -> list[HandoffFacts]: ...
    async def feedback(self, since: float, until: float) -> list[FeedbackFacts]: ...


def ratio(num: float, den: float, digits: int = 4) -> dict[str, Any]:
    return {"value": round(num / den, digits) if den else None, "numerator": num, "denominator": den}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


def mask(text: str, limit: int = 160) -> str:
    return _PII.mask(text)[0][:limit]


def compute(turns: list[TurnFacts], handoffs: list[HandoffFacts], feedback: list[FeedbackFacts], since: float, until: float,
            price_per_million_tokens: float | None = None) -> dict[str, Any]:
    sessions = {t.session_id for t in turns}
    handed = {h.session_id for h in handoffs if h.session_id in sessions}
    with_tools = [t for t in turns if t.tools]
    llm_calls = sum(t.llm_calls for t in turns)
    tokens = sum(t.tokens for t in turns)
    rated = [f for f in feedback if f.session_id in sessions] if sessions else []
    dist = Counter(f.rating for f in rated)
    tool_use, tool_err = Counter(), Counter()
    for t in turns:
        tool_use.update(t.tools)
        tool_err.update(t.tool_errors)
    out: dict[str, Any] = {
        "period": {"from": since, "to": until},
        "conversations": len(sessions), "turns": len(turns),
        "containmentRate": ratio(len(sessions) - len(handed), len(sessions)),
        "escalationRate": ratio(sum(t.status == "escalated" for t in turns), len(turns)),
        "approvalRate": ratio(sum(t.status == "needs_approval" for t in turns), len(turns)),
        "guardrailBlockRate": ratio(sum(bool(t.guardrails) for t in turns), len(turns)),
        "toolErrorRate": ratio(sum(bool(t.tool_errors) for t in with_tools), len(with_tools)),
        "errorRate": ratio(sum(t.errored for t in turns), len(turns)),
        "fallbackModelRate": ratio(sum(t.fallback_calls for t in turns), llm_calls),
        "latencySeconds": {"p50": percentile([t.duration for t in turns], 0.5), "p95": percentile([t.duration for t in turns], 0.95), "samples": len(turns)},
        "tokens": {"total": tokens, "perConversation": round(tokens / len(sessions)) if sessions else None, "modelCalls": llm_calls},
        "handoffs": {"total": len(handoffs), "byTrigger": dict(Counter(h.trigger for h in handoffs).most_common()),
                     "byQueue": dict(Counter(h.queue or "general" for h in handoffs).most_common()),
                     "byTopic": dict(Counter(x for h in handoffs for x in h.topics).most_common(10))},
        "tools": {"used": dict(tool_use.most_common(15)), "errors": dict(tool_err.most_common(15))},
        "guardrails": dict(Counter(g for t in turns for g in t.guardrails).most_common(15)),
        "satisfaction": {"average": round(sum(f.rating for f in rated) / len(rated), 2) if rated else None, "responses": len(rated),
                         "responseRate": ratio(len({f.session_id for f in rated}), len(sessions)), "distribution": {str(i): dist.get(i, 0) for i in range(1, 6)}},
        "note": "Containment is the share of conversations that did not reach a person; it is not a resolution rate, which needs an agreed definition of "
                "'resolved' per intent. Figures cover only the turns recorded in this period and environment.",
    }
    if price_per_million_tokens:
        out["estimatedCost"] = {"amount": round(tokens / 1e6 * price_per_million_tokens, 4), "perConversation": round(tokens / 1e6 * price_per_million_tokens / len(sessions), 5) if sessions else None,
                                "basis": f"{price_per_million_tokens} per million tokens (blended)"}
    return out


def timeseries(turns: list[TurnFacts], since: float, until: float, bucket: str = "day") -> list[dict[str, Any]]:
    step = BUCKETS[bucket]
    first = int(since // step) * step
    rows: dict[int, list[TurnFacts]] = {}
    for t in turns:
        rows.setdefault(int(t.started_at // step) * step, []).append(t)
    out = []
    for start in range(first, int(until) + 1, step):
        ts = rows.get(start, [])
        out.append({"start": start, "turns": len(ts), "conversations": len({t.session_id for t in ts}), "escalated": sum(t.status == "escalated" for t in ts),
                    "guardrailBlocks": sum(bool(t.guardrails) for t in ts), "errors": sum(t.errored for t in ts), "tokens": sum(t.tokens for t in ts),
                    "p95Latency": percentile([t.duration for t in ts], 0.95)})
    return out[-500:]


def failures(turns: list[TurnFacts], handoffs: list[HandoffFacts], limit: int = 15) -> list[dict[str, Any]]:
    """Why conversations went wrong, most common first, with a few example traces to open. Causes are the hand-off trigger, a tool that
    failed, or a guardrail that blocked."""
    by_trace = {h.trace_id: h for h in handoffs}
    causes: dict[str, list[str]] = {}
    for t in turns:
        h = by_trace.get(t.trace_id)
        if h is not None:
            causes.setdefault(f"hand-off: {h.trigger}", []).append(t.trace_id)
        for tool in dict.fromkeys(t.tool_errors):
            causes.setdefault(f"tool failed: {tool}", []).append(t.trace_id)
        for g in dict.fromkeys(t.guardrails):
            causes.setdefault(f"blocked by: {g}", []).append(t.trace_id)
    ranked = sorted(causes.items(), key=lambda kv: -len(kv[1]))[:limit]
    return [{"cause": c, "count": len(ids), "share": ratio(len(ids), len(turns)), "exampleTraceIds": ids[:3]} for c, ids in ranked]


def gaps(turns: list[TurnFacts], handoffs: list[HandoffFacts], limit: int = 15) -> dict[str, Any]:
    """Things customers asked that the agent could not handle: knowledge searches that found nothing, and what customers said just before
    the agent handed them to a person (masked)."""
    searches = Counter(q.strip().lower() for t in turns for q in t.empty_searches if q.strip())
    by_trace = {h.trace_id for h in handoffs if h.trigger in ("agent_handoff", "step_limit", "supervisor_rejections")}
    said = Counter(mask(t.first_message.strip().lower()) for t in turns if t.trace_id in by_trace and t.first_message.strip())
    return {"unansweredSearches": [{"query": q, "count": n} for q, n in searches.most_common(limit)],
            "messagesBeforeHandoff": [{"message": m, "count": n} for m, n in said.most_common(limit)]}


TAG = __import__("re").compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_TAGS = 20


def search_conversations(turns: list[TurnFacts], handoffs: list[HandoffFacts], feedback: list[FeedbackFacts], tags: dict[str, list[str]],
                         q: str = "", status: str | None = None, tag: str | None = None, handed_off: bool | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Conversations (sessions) matching a word or phrase and filters, newest first. Text is masked before it is shown."""
    needle = " ".join(q.lower().split())
    by_session: dict[str, list[TurnFacts]] = {}
    for t in turns:
        by_session.setdefault(t.session_id, []).append(t)
    h_by_session: dict[str, list[HandoffFacts]] = {}
    for h in handoffs:
        h_by_session.setdefault(h.session_id, []).append(h)
    rated = {f.session_id: f.rating for f in feedback}
    out = []
    for sid, ts in by_session.items():
        ts.sort(key=lambda t: t.started_at)
        last = ts[-1]
        if needle and not any(needle in t.text for t in ts):
            continue
        if status and last.status != status:
            continue
        if tag and tag not in tags.get(sid, []):
            continue
        hs = h_by_session.get(sid, [])
        if handed_off is not None and bool(hs) != handed_off:
            continue
        out.append({"sessionId": sid, "agentId": ts[0].agent_id, "environment": ts[0].environment, "turns": len(ts), "startedAt": ts[0].started_at,
                    "endedAt": last.started_at + last.duration, "lastStatus": last.status, "firstMessage": mask(ts[0].first_message, 200), "lastReply": mask(last.last_reply, 200),
                    "handedOff": bool(hs), "handoffTriggers": sorted({h.trigger for h in hs}), "rating": rated.get(sid), "tags": tags.get(sid, []), "traceIds": [t.trace_id for t in ts][-5:]})
    out.sort(key=lambda r: -r["endedAt"])
    return out[:limit]


class TagRepo(Protocol):
    async def add(self, session_id: str, tag: str, by: str) -> bool: ...
    async def remove(self, session_id: str, tag: str) -> bool: ...
    async def for_sessions(self, session_ids: list[str]) -> dict[str, list[str]]: ...
    async def all_for(self, session_id: str) -> list[str]: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryTags:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, str]] = {}

    async def add(self, session_id, tag, by) -> bool:
        cur = self.items.setdefault(session_id, {})
        if tag in cur:
            return False
        if len(cur) >= MAX_TAGS:
            raise ValueError(f"a conversation can have at most {MAX_TAGS} tags")
        cur[tag] = by
        return True

    async def remove(self, session_id, tag) -> bool:
        return self.items.get(session_id, {}).pop(tag, None) is not None

    async def for_sessions(self, session_ids) -> dict[str, list[str]]:
        return {s: sorted(self.items[s]) for s in session_ids if self.items.get(s)}

    async def all_for(self, session_id) -> list[str]:
        return sorted(self.items.get(session_id, {}))

    async def erase_session(self, session_id) -> int:
        return len(self.items.pop(session_id, {}))


class FeedbackRepo(Protocol):
    async def add(self, session_id: str, rating: int, comment: str, at: float | None = None) -> bool: ...
    async def for_session(self, session_id: str) -> FeedbackFacts | None: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryFeedback:
    def __init__(self) -> None:
        self.items: dict[str, FeedbackFacts] = {}

    async def add(self, session_id, rating, comment, at=None) -> bool:
        """One rating per conversation; a second submission replaces the first. Returns True if it was new."""
        new = session_id not in self.items
        self.items[session_id] = FeedbackFacts(session_id, rating, time.time() if at is None else at, comment)
        return new

    async def for_session(self, session_id) -> FeedbackFacts | None:
        return self.items.get(session_id)

    async def erase_session(self, session_id) -> int:
        return 1 if self.items.pop(session_id, None) else 0


class InMemoryInsightsSource:
    def __init__(self, runtime: Any, feedback: InMemoryFeedback):
        self.rt, self.fb = runtime, feedback

    async def turns(self, since, until, agent, environment, limit) -> list[TurnFacts]:
        out = []
        for t in getattr(self.rt.traces, "_traces", {}).values():
            if not t.events or not (since <= t.events[0].t <= until) or t.environment != environment or (agent and t.agent_id != agent):
                continue
            out.append(facts_from_trace(t))
        return sorted(out, key=lambda f: -f.started_at)[:limit]

    async def handoffs(self, since, until) -> list[HandoffFacts]:
        return [HandoffFacts(h.session_id, h.trace_id, h.trigger, list(h.topics), h.queue, h.created_at)
                for h in getattr(self.rt.handoffs, "_items", {}).values() if since <= h.created_at <= until]

    async def feedback(self, since, until) -> list[FeedbackFacts]:
        return [f for f in self.fb.items.values() if since <= f.created_at <= until]


class InsightsService:
    def __init__(self, source: InsightsSource, price_per_million_tokens: float | None = None):
        self.source, self.price = source, price_per_million_tokens

    async def _load(self, since: float, until: float, agent: str | None, environment: str):
        turns = await self.source.turns(since, until, agent, environment, MAX_TURNS)
        return turns, await self.source.handoffs(since, until), await self.source.feedback(since, until)

    async def overview(self, since: float, until: float, agent: str | None = None, environment: str = "production") -> dict[str, Any]:
        turns, handoffs, feedback = await self._load(since, until, agent, environment)
        out = compute(turns, handoffs, feedback, since, until, self.price)
        out.update({"agent": agent, "environment": environment, "truncated": len(turns) >= MAX_TURNS})
        return out

    async def series(self, since: float, until: float, bucket: str, agent: str | None = None, environment: str = "production") -> list[dict[str, Any]]:
        turns = await self.source.turns(since, until, agent, environment, MAX_TURNS)
        return timeseries(turns, since, until, bucket)

    async def failure_analysis(self, since: float, until: float, agent: str | None = None, environment: str = "production") -> list[dict[str, Any]]:
        turns, handoffs, _ = await self._load(since, until, agent, environment)
        return failures(turns, handoffs)

    async def search(self, since: float, until: float, tags: TagRepo, q: str = "", status: str | None = None, tag: str | None = None,
                     handed_off: bool | None = None, agent: str | None = None, environment: str = "production", limit: int = 50) -> list[dict[str, Any]]:
        turns, handoffs, feedback = await self._load(since, until, agent, environment)
        sessions = list({t.session_id for t in turns})
        return search_conversations(turns, handoffs, feedback, await tags.for_sessions(sessions), q, status, tag, handed_off, limit)

    async def intent_gaps(self, since: float, until: float, agent: str | None = None, environment: str = "production") -> dict[str, Any]:
        turns, handoffs, _ = await self._load(since, until, agent, environment)
        return gaps(turns, handoffs)
