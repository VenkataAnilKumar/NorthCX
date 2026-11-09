"""Meaning-based search for the knowledge base (K4): embeddings, an indexer, and hybrid ranking.

NorthCX does not ship an embedding model. The operator points it at any service that speaks the common embeddings API (`POST <url>/embeddings` with
`{"model": ..., "input": [...]}` answering `{"data": [{"index": 0, "embedding": [...]}]}`): a hosted service, or a server run inside the company's own
network. Knowledge text, and each search query, is sent to that endpoint and nowhere else; with a self-hosted endpoint nothing leaves the network.

Passages are embedded in the background (never while a document is being saved, so an embedding outage cannot block editing). A search combines the
keyword ranking with the meaning-based one using reciprocal rank fusion, so exact terms such as order numbers and product codes still win when they
should; if the embedding service cannot answer in time the search quietly falls back to keywords only.
"""
from __future__ import annotations

from northcx.tenancy import for_each_tenant

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

    def for_model(self, model: str) -> "HttpEmbedder":
        """The same service with a different model name (shares the connection)."""
        if model == self.model:
            return self
        return HttpEmbedder(self.url, model, self._key, self.dimensions, client=self._client)

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


def model_groups(default: str, source_models: dict[str, str]) -> list[tuple[str, list[str] | None, list[str] | None]]:
    by_model: dict[str, list[str]] = {}
    for src, m in sorted(source_models.items()):
        if m != default:
            by_model.setdefault(m, []).append(src)
    others = sorted(s for ss in by_model.values() for s in ss)
    return [(default, None, others or None)] + [(m, ss, None) for m, ss in sorted(by_model.items())]


def parse_source_models(text: str) -> dict[str, str]:
    """'help=model-a,docs=model-b' -> {'help': 'model-a', 'docs': 'model-b'}"""
    out: dict[str, str] = {}
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        src, sep, model = part.partition("=")
        if not sep or not src.strip() or not model.strip() or len(model) > 200 or src.strip() in out:
            raise ValueError("NORTHCX_EMBEDDINGS_SOURCE_MODELS must look like source=model,source2=model2 with each source once")
        out[src.strip()] = model.strip()
    return out


class HybridKnowledge:
    """A knowledge store whose search also understands meaning. Everything else is the underlying store's."""

    hybrid = True

    def __init__(self, store: Any, embedder: Embedder, min_similarity: float = 0.25, query_timeout: float = 4.0, source_models: dict[str, str] | None = None):
        self.store, self.embedder, self.min_similarity, self.query_timeout = store, embedder, min_similarity, query_timeout
        self.source_models = dict(source_models or {})
        if self.source_models and not hasattr(embedder, "for_model"):
            raise ValueError("this embedder cannot use a different model per source")
        self.indexer: EmbeddingIndexer | None = None
        self.last_fallback: str | None = None

    def groups(self) -> list[tuple[str, list[str] | None, list[str] | None]]:
        """(model, only these sources, all but these sources): the sources that use another model, and everything else with the default."""
        return model_groups(self.embedder.model, self.source_models)

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
            meaning = []
            for model, inc, exc in self.groups():
                if source_id and not ((inc is None or source_id in inc) and not (exc and source_id in exc)):
                    continue
                emb = self.embedder.for_model(model) if hasattr(self.embedder, "for_model") else self.embedder
                vec = await asyncio.wait_for(emb.embed_query(query), self.query_timeout)
                meaning += [p for p in await self.store.semantic_search(vec, model, wide, source_id, now, include=inc, exclude=exc) if p.score >= self.min_similarity]
            meaning.sort(key=lambda p: -p.score)
            meaning = meaning[:wide]
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

    def __init__(self, store: Any, embedder: Embedder, interval: float = 30.0, sleep: Any = asyncio.sleep, source_models: dict[str, str] | None = None):
        self.store, self.embedder, self.interval, self.sleep = store, embedder, interval, sleep
        self.source_models = dict(source_models or {})
        self.last_error: str | None = None
        self.last_run: float | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._failures = 0
        self._ready = False
        self._stop = False

    def kick(self) -> None:
        self._wake.set()

    def _groups(self) -> list[tuple[str, list[str] | None, list[str] | None]]:
        return model_groups(self.embedder.model, self.source_models)

    def _embedder_for(self, model: str) -> Any:
        return self.embedder.for_model(model) if hasattr(self.embedder, "for_model") else self.embedder

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
        for model, inc, exc in self._groups():
            emb = self._embedder_for(model)
            while True:
                pending = await self.store.pending_chunks(model, BATCH * 2, include=inc, exclude=exc)
                if not pending:
                    break
                try:
                    vecs = await emb.embed([t for _, t in pending])
                    await self.store.save_embeddings(model, [(ref, v) for (ref, _), v in zip(pending, vecs)])
                except Exception as e:
                    self.last_error = str(e) if isinstance(e, EmbeddingError) else type(e).__name__
                    self._failures += 1
                    log.warning("embedding indexing failed: %s", self.last_error)
                    return done
                done += len(pending)
            ann = getattr(self.store, "maybe_build_ann", None)
            if ann is not None:
                try:
                    await ann(model)
                except Exception as ex:  # an index is an optimisation: search still works without it
                    log.warning("approximate index not built: %s", type(ex).__name__)
        self.last_error, self._failures = None, 0
        return done

    async def status(self) -> dict[str, Any]:
        models, indexed, total = [], 0, 0
        for model, inc, exc in self._groups():
            i, t = await self.store.embedding_counts(model, include=inc, exclude=exc)
            indexed, total = indexed + i, total + t
            models.append({"model": model, "sources": inc if inc is not None else "all others", "indexed": i, "passages": t})
        ann = getattr(self.store, "ann_status", None)
        return {"enabled": True, "model": self.embedder.model, "models": models, "indexed": indexed, "passages": total, "pending": max(0, total - indexed),
                "lastRun": self.last_run, "lastError": self.last_error, "approximateIndex": await ann() if ann is not None else None}

    async def rebuild(self) -> int:
        n = await self.store.clear_embeddings()
        self.kick()
        return n

    tenants: Any = None  # northcx.tenancy.TenantService, set by the server

    async def _loop(self) -> None:
        while not self._stop:
            try:
                await for_each_tenant(self.tenants, self.run_once, log)  # once per tenant, as that tenant
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
