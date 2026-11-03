"""Meaning-based search for the knowledge base (K4): embeddings, an indexer, and hybrid ranking.

NorthCX does not ship an embedding model. The operator points it at any service that speaks the common embeddings API (`POST <url>/embeddings` with
`{"model": ..., "input": [...]}` answering `{"data": [{"index": 0, "embedding": [...]}]}`): a hosted service, or a server run inside the company's own
network. Knowledge text, and each search query, is sent to that endpoint and nowhere else; with a self-hosted endpoint nothing leaves the network.

Passages are embedded in the background (never while a document is being saved, so an embedding outage cannot block editing). A search combines the
keyword ranking with the meaning-based one using reciprocal rank fusion, so exact terms such as order numbers and product codes still win when they
should; if the embedding service cannot answer in time the search quietly falls back to keywords only.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import OrderedDict
from typing import Any, Protocol

import httpx

from .knowledge import Passage

log = logging.getLogger("northcx.embeddings")
BATCH = 32
MAX_TEXT = 8000
RRF_K = 60


class EmbeddingError(RuntimeError):
    """The embedding service failed or answered badly. The message is safe to show: no address, key or response text."""


class Embedder(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, query: str) -> list[float]: ...


class HttpEmbedder:
    def __init__(self, url: str, model: str, api_key: str | None = None, dimensions: int | None = None, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        u = httpx.URL(url)
        local = u.host in ("localhost", "127.0.0.1", "::1")
        if u.scheme not in ("https", "http") or not u.host or u.userinfo or u.query or u.fragment or (u.scheme == "http" and not local):
            raise ValueError("NORTHCX_EMBEDDINGS_URL must be an https address such as https://embeddings.example.com/v1 (http is allowed for localhost only)")
        if not model or len(model) > 200:
            raise ValueError("NORTHCX_EMBEDDINGS_MODEL is required")
        if dimensions is not None and not 8 <= dimensions <= 8192:
            raise ValueError("NORTHCX_EMBEDDINGS_DIMENSIONS must be between 8 and 8192")
        path = u.path.rstrip("/")
        self.url = str(u.copy_with(path=path if path.endswith("/embeddings") else path + "/embeddings"))
        self.model, self.dimensions, self._key = model, dimensions, api_key
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            out += await self._batch([t[:MAX_TEXT] or " " for t in texts[i:i + BATCH]])
        return out

    async def _batch(self, texts: list[str]) -> list[list[float]]:
        headers = {"content-type": "application/json", "accept": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"
        body: dict[str, Any] = {"model": self.model, "input": texts}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        try:
            r = await self._client.post(self.url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise EmbeddingError(f"the embedding service could not be reached ({type(e).__name__})") from e
        if r.status_code != 200:
            raise EmbeddingError(f"the embedding service returned {r.status_code}")
        try:
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            vecs = [[float(x) for x in d["embedding"]] for d in data]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise EmbeddingError("the embedding service answered in an unexpected form") from None
        if len(vecs) != len(texts) or not vecs[0]:
            raise EmbeddingError("the embedding service returned the wrong number of vectors")
        dim = len(vecs[0])
        if any(len(v) != dim or not all(math.isfinite(x) for x in v) for v in vecs) or (self.dimensions and dim != self.dimensions):
            raise EmbeddingError("the embedding service returned vectors of the wrong size or with invalid numbers")
        return vecs

    async def embed_query(self, query: str) -> list[float]:
        q = query.strip()[:1000]
        if q in self._cache:
            self._cache.move_to_end(q)
            return self._cache[q]
        vec = (await self.embed([q]))[0]
        self._cache[q] = vec
        if len(self._cache) > 256:
            self._cache.popitem(last=False)
        return vec


def passage_key(p: Passage) -> tuple[str, str, str]:
    return (p.document_id, p.heading, p.text[:200])


def fuse(keyword: list[Passage], meaning: list[Passage], limit: int) -> list[Passage]:
    """Reciprocal rank fusion: a passage ranked well by either method, and better by both, comes first."""
    scores: dict[tuple[str, str, str], float] = {}
    best: dict[tuple[str, str, str], Passage] = {}
    seen_by: dict[tuple[str, str, str], set[str]] = {}
    for name, lst in (("keyword", keyword), ("meaning", meaning)):
        for rank, p in enumerate(lst, 1):
            k = passage_key(p)
            scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank)
            best.setdefault(k, p)
            seen_by.setdefault(k, set()).add(name)
    out = []
    for k in sorted(scores, key=lambda k: -scores[k])[:limit]:
        p = best[k]
        out.append(Passage(p.document_id, p.source_id, p.title, p.url, p.heading, p.text, round(scores[k] * 100, 4), p.updated_at, p.stale,
                           "both" if len(seen_by[k]) == 2 else next(iter(seen_by[k]))))
    return out


class HybridKnowledge:
    """A knowledge store whose search also understands meaning. Everything else is the underlying store's."""

    hybrid = True

    def __init__(self, store: Any, embedder: Embedder, min_similarity: float = 0.25, query_timeout: float = 4.0):
        self.store, self.embedder, self.min_similarity, self.query_timeout = store, embedder, min_similarity, query_timeout
        self.indexer: EmbeddingIndexer | None = None
        self.last_fallback: str | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.store, name)

    async def upsert(self, *a: Any, **kw: Any) -> Any:
        r = await self.store.upsert(*a, **kw)
        if self.indexer is not None and r.status != "unchanged":
            self.indexer.kick()
        return r

    async def keyword_search(self, query: str, limit: int = 5, source_id: str | None = None, now: float | None = None) -> list[Passage]:
        return await self.store.search(query, limit, source_id, now)

    async def search(self, query: str, limit: int = 5, source_id: str | None = None, now: float | None = None) -> list[Passage]:
        wide = max(limit * 4, 20)
        kw_task = asyncio.ensure_future(self.store.search(query, wide, source_id, now))
        try:
            vec = await asyncio.wait_for(self.embedder.embed_query(query), self.query_timeout)
            meaning = [p for p in await self.store.semantic_search(vec, self.embedder.model, wide, source_id, now) if p.score >= self.min_similarity]
            self.last_fallback = None
        except Exception as e:  # any failure here means keywords only; the conversation must never notice
            meaning = []
            self.last_fallback = type(e).__name__
        keyword = await kw_task
        if not meaning:
            return [Passage(p.document_id, p.source_id, p.title, p.url, p.heading, p.text, p.score, p.updated_at, p.stale, "keyword") for p in keyword[:limit]]
        return fuse(keyword, meaning, limit)


class EmbeddingIndexer:
    """Keeps every passage's embedding up to date in the background."""

    def __init__(self, store: Any, embedder: Embedder, interval: float = 30.0, sleep: Any = asyncio.sleep):
        self.store, self.embedder, self.interval, self.sleep = store, embedder, interval, sleep
        self.last_error: str | None = None
        self.last_run: float | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._failures = 0
        self._ready = False
        self._stop = False

    def kick(self) -> None:
        self._wake.set()

    async def run_once(self) -> int:
        """Embeds everything that is waiting; returns how many passages were done. Stops at the first failure and remembers why."""
        done = 0
        self.last_run = time.time()
        if not self._ready:
            prepare = getattr(self.store, "ensure_semantic", None)
            try:
                if prepare is not None:
                    await prepare()
                self._ready = True
            except Exception as e:
                self.last_error = str(e)
                self._failures += 1
                return 0
        while True:
            pending = await self.store.pending_chunks(self.embedder.model, BATCH * 2)
            if not pending:
                self.last_error, self._failures = None, 0
                return done
            try:
                vecs = await self.embedder.embed([t for _, t in pending])
                await self.store.save_embeddings(self.embedder.model, [(ref, v) for (ref, _), v in zip(pending, vecs)])
            except Exception as e:
                self.last_error = str(e) if isinstance(e, EmbeddingError) else type(e).__name__
                self._failures += 1
                log.warning("embedding indexing failed: %s", self.last_error)
                return done
            done += len(pending)

    async def status(self) -> dict[str, Any]:
        indexed, total = await self.store.embedding_counts(self.embedder.model)
        return {"enabled": True, "model": self.embedder.model, "indexed": indexed, "passages": total, "pending": max(0, total - indexed),
                "lastRun": self.last_run, "lastError": self.last_error}

    async def rebuild(self) -> int:
        n = await self.store.clear_embeddings()
        self.kick()
        return n

    async def _loop(self) -> None:
        while not self._stop:
            try:
                await self.run_once()
            except Exception:
                log.exception("embedding indexer error")
            wait = min(self.interval * 2 ** min(self._failures, 5), 600.0)
            try:
                await asyncio.wait_for(self._wake.wait(), wait)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
