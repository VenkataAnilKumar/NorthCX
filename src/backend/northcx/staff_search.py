"""One search across what the person may see (WP5.6, W7): company knowledge, conversations and hand-offs, merged by reciprocal rank fusion.

Each source is a `SearchProvider`. A provider runs only for a person who holds its permission; one that cannot prove access returns nothing, and
nothing is counted for it, so a result the person may not see never appears in the list or in the totals. Each result says why the person can see it.
A provider that is slow or fails is named in `skipped` and the rest still answer."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .safety.pii import PIIDetection

RRF_K = 60  # the usual constant for reciprocal rank fusion
_MASK = PIIDetection()


def _mask(text: str, n: int = 240) -> str:
    return _MASK.mask(text[:n])[0]


@dataclass
class Result:
    kind: str          # knowledge | conversation | handoff
    id: str
    title: str
    snippet: str
    why: str           # why this person can see it
    provider: str
    url: str | None = None
    meta: dict[str, Any] | None = None
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "title": self.title, "snippet": self.snippet, "why": self.why, "provider": self.provider, "url": self.url,
                "meta": self.meta or {}, "score": round(self.score, 5)}


class SearchProvider(Protocol):
    name: str
    permission: str

    async def search(self, query: str, identity: Any, limit: int) -> list[Result]: ...


class KnowledgeProvider:
    name, permission = "knowledge", "knowledge:read"

    def __init__(self, kb: Any):
        self.kb = kb

    async def search(self, query: str, identity: Any, limit: int) -> list[Result]:
        out = []
        for p in await self.kb.search(query, limit):
            out.append(Result("knowledge", f"{p.source_id}/{p.document_id}", p.title, _mask(p.text), "Company knowledge: you have access to the Library", "knowledge", p.url,
                              {"source": p.source_id, "section": p.heading, "stale": p.stale}))
        return out


class ConversationProvider:
    name, permission = "conversations", "traces:read"

    def __init__(self, insight: Any, tags: Any):
        self.insight, self.tags = insight, tags

    async def search(self, query: str, identity: Any, limit: int) -> list[Result]:
        now = time.time()
        rows = await self.insight.search(now - 30 * 86400, now, self.tags, query, None, None, None, None, "production", limit, None)
        return [Result("conversation", str(r.get("sessionId", "")), f"Conversation {str(r.get('sessionId', ''))[:12]}", _mask(str(r.get("firstMessage") or r.get("lastReply") or "")),
                       "Conversation: your role may read conversations (customer details are masked)", "conversations", None,
                       {"status": r.get("lastStatus"), "handedOff": r.get("handedOff")}) for r in rows]


class HandoffProvider:
    name, permission = "handoffs", "handoffs:read"

    def __init__(self, handoffs: Any):
        self.handoffs = handoffs

    async def search(self, query: str, identity: Any, limit: int) -> list[Result]:
        q = query.lower()
        out = []
        for h in await self.handoffs.list(None, None, 200):
            hay = f"{h.reason} {h.trigger} {h.agent_id}".lower()
            if all(w in hay for w in q.split()):
                out.append(Result("handoff", h.id, f"Hand-off: {h.trigger}", _mask(h.reason), "Hand-off: your role may see the Inbox", "handoffs", None,
                                  {"state": h.state, "sessionId": h.session_id}))
            if len(out) >= limit:
                break
        return out


class SearchService:
    def __init__(self, providers: list[SearchProvider], timeout: float = 3.0):
        self.providers, self.timeout = providers, timeout

    async def search(self, identity: Any, query: str, limit: int = 20) -> dict[str, Any]:
        query = query.strip()
        if len(query) < 2:
            return {"results": [], "skipped": []}
        allowed = [p for p in self.providers if identity.can(p.permission)]    # a provider the person cannot use is not even asked

        async def one(p: SearchProvider) -> tuple[str, list[Result] | str]:
            try:
                return p.name, await asyncio.wait_for(p.search(query, identity, limit), self.timeout)
            except asyncio.TimeoutError:
                return p.name, "timed out"
            except Exception as e:  # noqa: BLE001 - one source failing must not take the others down
                return p.name, f"failed ({type(e).__name__})"
        done = await asyncio.gather(*(one(p) for p in allowed))
        scores: dict[tuple[str, str], Result] = {}
        skipped = []
        for name, res in done:
            if isinstance(res, str):
                skipped.append({"source": name, "reason": res})
                continue
            for rank, r in enumerate(res, start=1):
                key = (r.kind, r.id)
                r.score = 1.0 / (RRF_K + rank)
                if key in scores:
                    scores[key].score += r.score
                else:
                    scores[key] = r
        merged = sorted(scores.values(), key=lambda r: (-r.score, r.kind, r.id))[:limit]
        return {"results": [r.to_dict() for r in merged], "skipped": skipped, "searched": [p.name for p in allowed]}
