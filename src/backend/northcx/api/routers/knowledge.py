"""Routes for the knowledge base: sources, documents, file import, crawls and schedules, search and the meaning-search index."""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import CrawlBody, DocumentBody, EnabledBody, ScheduleBody, SourceBody
from northcx.crawler import CrawlConfig, CrawlRefused
from northcx.ingest import extract as extract_file, IngestError
from northcx.knowledge import KnowledgeError, Source


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    crawl_scheduler = d.crawl_scheduler
    crawler = d.crawler
    kb = d.kb
    record = d.record
    regression = d.regression
    too_many = d.too_many

    # ---- knowledge ----
    @app.get("/v1/knowledge/sources")
    async def kb_sources() -> Any:
        return {"sources": [{"id": s.id, "name": s.name, "staleAfterDays": s.stale_after_days, "createdAt": s.created_at} for s in await kb.list_sources()]}

    @app.post("/v1/knowledge/sources", status_code=201)
    async def kb_create_source(body: SourceBody, request: Request) -> Any:
        try:
            s = await kb.create_source(Source(body.id, body.name, body.stale_after_days))
        except KnowledgeError as e:
            return _err(400 if "already exists" not in str(e) else 409, "bad_request" if "already exists" not in str(e) else "conflict", str(e))
        await record(request, "knowledge.source.create", s.id, name=s.name)
        return {"id": s.id, "name": s.name, "staleAfterDays": s.stale_after_days}

    @app.delete("/v1/knowledge/sources/{source_id}")
    async def kb_delete_source(source_id: str, request: Request) -> Any:
        if await kb.get_source(source_id) is None:
            return _err(404, "not_found", "Unknown source")
        n = await kb.delete_source(source_id)
        await record(request, "knowledge.source.delete", source_id, documents=n)
        if regression is not None:
            regression.trigger(f"source {source_id} deleted")
        return {"deleted": True, "documents": n}

    @app.post("/v1/knowledge/sources/{source_id}/import", status_code=201)
    async def kb_import(source_id: str, request: Request, filename: str = "upload", externalId: str | None = None, url: str | None = None) -> Any:
        """Add a PDF, HTML, Markdown or text file to a source (the request body is the file)."""
        if await kb.get_source(source_id) is None:
            return _err(404, "not_found", "Unknown source")
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > 11 * 1024 * 1024:
                return _err(413, "too_large", "The file is too large")
        try:
            ex = await extract_file(data, filename, request.headers.get("x-file-type", ""))
        except IngestError as e:
            return _err(400, "bad_request", str(e))
        ext = externalId or "file:" + (re.sub(r"[^A-Za-z0-9._-]", "_", filename.rsplit("/", 1)[-1])[:120] or "upload")
        try:
            r = await kb.upsert(source_id, ext, ex.title, url, ex.text, None)
        except KnowledgeError as e:
            return _err(400, "bad_request", str(e))
        if r.status != "unchanged":
            await record(request, "knowledge.import", f"{source_id}/{ext}", kind=ex.kind, size=len(data), status=r.status, chunks=r.document.chunks)
            if regression is not None:
                regression.trigger(f"document {source_id}/{ext} {r.status}")
        return {"status": r.status, "kind": ex.kind, "document": r.document.to_dict()}

    @app.post("/v1/knowledge/sources/{source_id}/crawl", status_code=202)
    async def kb_crawl(source_id: str, body: CrawlBody, request: Request) -> Any:
        """Read a site's public pages into this source in the background. Only hosts the operator allowed can be crawled."""
        if crawler is None:
            return _err(501, "not_configured", "Crawling is switched off: the operator must list the sites that may be crawled in NORTHCX_CRAWL_HOSTS")
        who: Identity = request.state.identity
        if not (await access.limiter.hit(f"crawl:{who.key_id or 'open'}", 5))[0]:
            return too_many(60, "crawl requests")
        cfg = CrawlConfig(body.url, body.max_pages, body.max_depth, body.delay_seconds, body.include_paths, body.exclude_paths, body.use_sitemap, body.prune)
        try:
            job = await crawler.start(source_id, cfg)
        except CrawlRefused as e:
            code = 404 if str(e) == "Unknown source" else 409 if "already running" in str(e) else 400
            return _err(code, "not_found" if code == 404 else "conflict" if code == 409 else "bad_request", str(e))
        await record(request, "knowledge.crawl.start", f"{source_id}", host=job.host, maxPages=cfg.max_pages, prune=cfg.prune)
        return job.to_dict()

    @app.post("/v1/knowledge/sources/{source_id}/schedule", status_code=201)
    async def kb_schedule(source_id: str, body: ScheduleBody, request: Request) -> Any:
        """Repeat a crawl every so many hours (at least one). It is checked exactly like a crawl started now, and again on every run."""
        if crawl_scheduler is None:
            return _err(501, "not_configured", "Crawling is switched off: the operator must list the sites that may be crawled in NORTHCX_CRAWL_HOSTS")
        who: Identity = request.state.identity
        cfg = CrawlConfig(body.url, body.max_pages, body.max_depth, body.delay_seconds, body.include_paths, body.exclude_paths, body.use_sitemap, body.prune)
        try:
            s = await crawl_scheduler.create(source_id, cfg, body.every_hours, who.name if hasattr(who, "name") else "unknown")
        except CrawlRefused as e:
            code = 404 if str(e) == "Unknown source" else 409 if "already has" in str(e) else 400
            return _err(code, "not_found" if code == 404 else "conflict" if code == 409 else "bad_request", str(e))
        await record(request, "knowledge.schedule.create", source_id, host=urlsplit(body.url).netloc.lower(), everyHours=body.every_hours)
        return s.to_dict()

    @app.get("/v1/knowledge/schedules")
    async def kb_schedules() -> Any:
        return {"enabled": crawl_scheduler is not None, "schedules": [s.to_dict() for s in await crawl_scheduler.repo.list()] if crawl_scheduler is not None else []}

    @app.delete("/v1/knowledge/schedules/{schedule_id}")
    async def kb_schedule_delete(schedule_id: str, request: Request) -> Any:
        if crawl_scheduler is None or not await crawl_scheduler.repo.delete(schedule_id):
            return _err(404, "not_found", "Unknown schedule")
        await record(request, "knowledge.schedule.delete", schedule_id)
        return {"deleted": True}

    @app.post("/v1/knowledge/schedules/{schedule_id}/enabled")
    async def kb_schedule_enabled(schedule_id: str, body: EnabledBody, request: Request) -> Any:
        if crawl_scheduler is None or not await crawl_scheduler.repo.set_enabled(schedule_id, body.enabled, time.time()):
            return _err(404, "not_found", "Unknown schedule")
        await record(request, "knowledge.schedule.enable" if body.enabled else "knowledge.schedule.pause", schedule_id)
        return {"enabled": body.enabled}

    @app.get("/v1/knowledge/crawls")
    async def kb_crawls() -> Any:
        return {"enabled": crawler is not None, "crawls": crawler.jobs_list() if crawler is not None else []}

    @app.get("/v1/knowledge/crawls/{job_id}")
    async def kb_crawl_status(job_id: str) -> Any:
        job = crawler.jobs.get(job_id) if crawler is not None else None
        return job.to_dict() if job is not None else _err(404, "not_found", "Unknown crawl")

    @app.get("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_get_document(source_id: str, external_id: str) -> Any:
        found = await kb.get_document(source_id, external_id)
        if found is None:
            return _err(404, "not_found", "Unknown document")
        doc, body, rebuilt = found
        src = await kb.get_source(source_id)
        return {**doc.to_dict(src.stale_after_days if src else None), "text": body, "textRebuilt": rebuilt}

    @app.put("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_put_document(source_id: str, external_id: str, body: DocumentBody, request: Request) -> Any:
        try:
            r = await kb.upsert(source_id, external_id, body.title, body.url, body.text, body.source_updated_at)
        except KnowledgeError as e:
            return _err(404 if str(e).startswith("Unknown source") else 400, "not_found" if str(e).startswith("Unknown source") else "bad_request", str(e))
        if r.status != "unchanged":
            await record(request, "knowledge.document.put", f"{source_id}/{external_id}", status=r.status, chunks=r.document.chunks)
            if regression is not None:
                regression.trigger(f"document {source_id}/{external_id} {r.status}")
        return {"status": r.status, "document": r.document.to_dict()}

    @app.delete("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_delete_document(source_id: str, external_id: str, request: Request) -> Any:
        if not await kb.delete(source_id, external_id):
            return _err(404, "not_found", "Unknown document")
        await record(request, "knowledge.document.delete", f"{source_id}/{external_id}")
        if regression is not None:
            regression.trigger(f"document {source_id}/{external_id} deleted")
        return {"deleted": True}

    @app.get("/v1/knowledge/documents")
    async def kb_documents(source: str | None = None, stale: bool = False, limit: int = 200) -> Any:
        rows = await kb.documents(source, stale, max(1, min(limit, 1000)))
        return {"documents": [d.to_dict(days) for d, days in rows]}

    @app.get("/v1/knowledge/search")
    async def kb_search(q: str, source: str | None = None, limit: int = 5) -> Any:
        found = await kb.search(q, max(1, min(limit, 20)), source)
        return {"passages": [{"documentId": p.document_id, "sourceId": p.source_id, "title": p.title, "url": p.url, "section": p.heading,
                              "text": p.text, "score": p.score, "updatedAt": p.updated_at, "stale": p.stale, "via": p.via} for p in found]}

    @app.get("/v1/knowledge/index")
    async def kb_index() -> Any:
        idx = getattr(kb, "indexer", None)
        return await idx.status() if idx is not None else {"enabled": False}

    @app.post("/v1/knowledge/index/rebuild", status_code=202)
    async def kb_index_rebuild(request: Request) -> Any:
        """Throws away every stored embedding and re-embeds all passages in the background (use after changing the embedding model)."""
        idx = getattr(kb, "indexer", None)
        if idx is None:
            return _err(501, "not_configured", "Meaning-based search is not configured: set NORTHCX_EMBEDDINGS_URL and NORTHCX_EMBEDDINGS_MODEL")
        n = await idx.rebuild()
        await record(request, "knowledge.index.rebuild", "knowledge", cleared=n)
        return {"cleared": n}
