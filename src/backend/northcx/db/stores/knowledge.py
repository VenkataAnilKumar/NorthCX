"""Postgres stores for the knowledge base (documents, passages, meaning-search vectors) and scheduled crawls."""
from __future__ import annotations

import json
import time
from typing import Any
import uuid

from sqlalchemy import text

from northcx.db.stores._base import _Base
from northcx.knowledge import _prepare, chunk_text, content_hash, Document, is_stale, KnowledgeError, Passage, Source, tokens, UpsertResult, valid_id


def _hnsw_ddl(dim: int) -> str:
    """DDL cannot take bound values; the only value in it is an integer checked to be a plausible vector size."""
    dim = int(dim)
    if not 2 <= dim <= 2000:
        raise ValueError("unsupported vector size")
    return "create index if not exists ix_ke_hnsw_%d on knowledge_embeddings using hnsw ((embedding::vector(%d)) vector_cosine_ops) where vector_dims(embedding) = %d" % (dim, dim, dim)


class PgKnowledge(_Base):
    async def create_source(self, source: Source) -> Source:
        if not valid_id(source.id):
            raise KnowledgeError("source id must be 1-200 characters: letters, digits and . _ : / -")
        if not source.name.strip() or len(source.name) > 200:
            raise KnowledgeError("name must be 1-200 characters")
        if source.stale_after_days is not None and not 1 <= source.stale_after_days <= 3650:
            raise KnowledgeError("stale_after_days must be between 1 and 3650")
        async with self._sm.begin() as s:
            r = await s.execute(text("insert into knowledge_sources (id, name, stale_after_days, created_at) values (:i, :n, :d, :c) on conflict do nothing returning id"),
                                {"i": source.id, "n": source.name, "d": source.stale_after_days, "c": source.created_at})
            if r.first() is None:
                raise KnowledgeError(f"Source '{source.id}' already exists")
        return source

    @staticmethod
    def _src(r: Any) -> Source:
        return Source(r.id, r.name, r.stale_after_days, r.created_at)

    async def get_source(self, source_id: str) -> Source | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from knowledge_sources where id = :i"), {"i": source_id})).first()
        return self._src(r) if r else None

    async def list_sources(self) -> list[Source]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from knowledge_sources order by created_at"))).all()
        return [self._src(r) for r in rows]

    async def upsert(self, source_id, external_id, title, url, text_, source_updated_at, now=None) -> UpsertResult:
        src = await self.get_source(source_id)
        _prepare(src, source_id, external_id, title, text_)
        now = time.time() if now is None else now
        h = content_hash(title, url, text_)
        parts = chunk_text(text_)
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"kn:{source_id}:{external_id}"})
            old = (await s.execute(text("select * from knowledge_documents where source_id = :s and external_id = :e"),
                                   {"s": source_id, "e": external_id})).first()
            if old and old.content_hash == h:
                await s.execute(text("update knowledge_documents set body = coalesce(body, :b) where id = :i"), {"b": text_, "i": old.id})  # keep the text once we have it
                if source_updated_at is not None:
                    await s.execute(text("update knowledge_documents set source_updated_at = :u where id = :i"), {"u": source_updated_at, "i": old.id})
                    old = (await s.execute(text("select * from knowledge_documents where id = :i"), {"i": old.id})).first()
                return UpsertResult(self._doc(old), "unchanged")
            doc_id = old.id if old else uuid.uuid4().hex
            if old:
                await s.execute(text("delete from knowledge_chunks where document_id = :i"), {"i": doc_id})
                await s.execute(text("update knowledge_documents set title=:t, url=:u, content_hash=:h, chunks=:c, source_updated_at=:su, ingested_at=:n, body=:b where id=:i"),
                                {"t": title.strip(), "u": url, "h": h, "c": len(parts), "su": source_updated_at, "n": now, "i": doc_id, "b": text_})
            else:
                await s.execute(text("insert into knowledge_documents (id, source_id, external_id, title, url, content_hash, chunks, source_updated_at, ingested_at, body) "
                                     "values (:i,:s,:e,:t,:u,:h,:c,:su,:n,:b)"),
                                {"i": doc_id, "s": source_id, "e": external_id, "t": title.strip(), "u": url, "h": h, "c": len(parts), "su": source_updated_at, "n": now, "b": text_})
            if parts:
                await s.execute(text("insert into knowledge_chunks (document_id, seq, heading, body, search_text) values (:d,:q,:h,:b,:x)"),
                                [{"d": doc_id, "q": i, "h": hd, "b": tx, "x": f"{title} {hd} {tx}"} for i, (hd, tx) in enumerate(parts)])
            row = (await s.execute(text("select * from knowledge_documents where id = :i"), {"i": doc_id})).first()
        return UpsertResult(self._doc(row), "updated" if old else "created")

    @staticmethod
    def _doc(r: Any) -> Document:
        return Document(r.source_id, r.external_id, r.title, r.url, r.content_hash, r.chunks, r.source_updated_at, r.ingested_at, id=r.id)

    async def get_document(self, source_id: str, external_id: str):
        async with self._ro() as s:
            r = (await s.execute(text("select * from knowledge_documents where source_id = :s and external_id = :e"), {"s": source_id, "e": external_id})).first()
            if r is None:
                return None
            if r.body is not None:
                return self._doc(r), r.body, False
            chunks = (await s.execute(text("select heading, body from knowledge_chunks where document_id = :i order by seq"), {"i": r.id})).all()
        rebuilt, last = [], ""
        for c in chunks:  # documents saved before the text was kept: put the passages back together, restoring each new heading
            if c.heading and c.heading != last:
                rebuilt.append("#" * min(6, c.heading.count(" > ") + 1) + " " + c.heading.split(" > ")[-1])
            last = c.heading
            rebuilt.append(c.body)
        return self._doc(r), "\n\n".join(rebuilt), True

    async def delete(self, source_id: str, external_id: str) -> bool:
        async with self._sm.begin() as s:
            r = await s.execute(text("delete from knowledge_documents where source_id = :s and external_id = :e returning id"), {"s": source_id, "e": external_id})
            return r.first() is not None

    async def delete_source(self, source_id: str) -> int:
        async with self._sm.begin() as s:
            n = (await s.execute(text("select count(*) from knowledge_documents where source_id = :s"), {"s": source_id})).scalar_one()
            await s.execute(text("delete from knowledge_sources where id = :s"), {"s": source_id})
        return int(n)

    async def documents(self, source_id=None, stale_only=False, limit=200, now=None):
        q = "select d.*, s.stale_after_days from knowledge_documents d join knowledge_sources s on s.id = d.source_id"
        params: dict[str, Any] = {}
        if source_id:
            q += " where d.source_id = :s"
            params["s"] = source_id
        q += " order by d.ingested_at desc"
        async with self._ro() as s:
            rows = (await s.execute(text(q), params)).all()
        out = []
        for r in rows:
            d = self._doc(r)
            if stale_only and not is_stale(d, r.stale_after_days, now):
                continue
            out.append((d, r.stale_after_days))
        return out[:limit]

    async def search(self, query, limit=5, source_id=None, now=None) -> list[Passage]:
        terms = list(dict.fromkeys(tokens(query)))
        if not terms:
            return []
        q = ("select c.heading, c.body, d.id as doc_id, d.source_id, d.title, d.url, d.source_updated_at, d.ingested_at, d.content_hash, "
             "d.external_id, d.chunks, s.stale_after_days, ts_rank_cd(c.tsv, to_tsquery('english', :q)) as rank "
             "from knowledge_chunks c join knowledge_documents d on d.id = c.document_id join knowledge_sources s on s.id = d.source_id "
             "where c.tsv @@ to_tsquery('english', :q)")
        params: dict[str, Any] = {"q": " | ".join(terms), "n": limit}  # any word may match; ranking puts the best passages first
        if source_id:
            q += " and d.source_id = :s"
            params["s"] = source_id
        q += " order by rank desc, c.id limit :n"
        async with self._ro() as s:
            rows = (await s.execute(text(q), params)).all()
        out = []
        for r in rows:
            d = Document(r.source_id, r.external_id, r.title, r.url, r.content_hash, r.chunks, r.source_updated_at, r.ingested_at, id=r.doc_id)
            out.append(Passage(r.doc_id, r.source_id, r.title, r.url, r.heading, r.body, round(float(r.rank), 4),
                               r.source_updated_at or r.ingested_at, is_stale(d, r.stale_after_days, now)))
        return out

    # ---- meaning-based search (pgvector); see embeddings.py. Created on demand, so deployments without it never need the extension ----
    async def ensure_semantic(self) -> None:
        async with self._sm.begin() as s:
            try:
                await s.execute(text("create extension if not exists vector"))
            except Exception as e:
                raise KnowledgeError("meaning-based search needs the pgvector extension; use a Postgres image that includes it (see the Deployment Guide) "
                                     "or ask a database administrator to run: CREATE EXTENSION vector") from e
            await s.execute(text("create table if not exists knowledge_embeddings (chunk_id bigint primary key references knowledge_chunks(id) on delete cascade, "
                                 "model text not null, embedding vector not null, created_at double precision not null)"))
            await s.execute(text("create index if not exists ix_knowledge_embeddings_model on knowledge_embeddings (model)"))

    @staticmethod
    def _scope(include: list[str] | None, exclude: list[str] | None, params: dict[str, Any], col: str = "d.source_id") -> str:
        sql = ""
        if include is not None:
            sql += f" and {col} = any(:inc)"
            params["inc"] = list(include)
        if exclude:
            sql += f" and not ({col} = any(:exc))"
            params["exc"] = list(exclude)
        return sql

    async def pending_chunks(self, model: str, limit: int, include: list[str] | None = None, exclude: list[str] | None = None) -> list[tuple[Any, str]]:
        params: dict[str, Any] = {"m": model, "n": limit}
        scope = self._scope(include, exclude, params)
        async with self._ro() as s:
            rows = (await s.execute(text(
                "select c.id, d.title, c.heading, c.body from knowledge_chunks c join knowledge_documents d on d.id = c.document_id "
                "left join knowledge_embeddings e on e.chunk_id = c.id and e.model = :m where e.chunk_id is null" + scope + " order by c.id limit :n"), params)).all()
        return [(r.id, f"{r.title}\n{r.heading}\n{r.body}".strip()) for r in rows]

    async def save_embeddings(self, model: str, items: list[tuple[Any, list[float]]]) -> int:
        now = time.time()
        async with self._sm.begin() as s:
            for ref, vec in items:
                await s.execute(text(
                    "insert into knowledge_embeddings (chunk_id, model, embedding, created_at) select :c, :m, cast(:v as vector), :t where exists (select 1 from knowledge_chunks where id = :c) "
                    "on conflict (chunk_id) do update set model = excluded.model, embedding = excluded.embedding, created_at = excluded.created_at"),
                    {"c": ref, "m": model, "v": "[" + ",".join(repr(float(x)) for x in vec) + "]", "t": now})
        return len(items)

    async def embedding_counts(self, model: str, include: list[str] | None = None, exclude: list[str] | None = None) -> tuple[int, int]:
        params: dict[str, Any] = {"m": model}
        scope = self._scope(include, exclude, params)
        async with self._ro() as s:
            r = (await s.execute(text(
                "select count(*) filter (where e.model = :m) as done, count(*) as total from knowledge_chunks c join knowledge_documents d on d.id = c.document_id "
                "left join knowledge_embeddings e on e.chunk_id = c.id where true" + scope), params)).one()
        return int(r.done), int(r.total)

    async def clear_embeddings(self) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from knowledge_embeddings"))).rowcount

    ann_threshold = 5000  # passages with a vector of one size before an approximate index is worth building
    _ann_dims: set[int] | None = None

    async def _existing_ann(self) -> set[int]:
        async with self._ro() as s:
            rows = (await s.execute(text("select indexname from pg_indexes where tablename = 'knowledge_embeddings' and indexname like 'ix_ke_hnsw_%'"))).all()
        return {int(r.indexname.rsplit("_", 1)[1]) for r in rows}

    async def maybe_build_ann(self, model: str) -> int | None:
        """Builds a cosine HNSW index for the vector size in use once there are enough vectors. Returns the size indexed, or None."""
        async with self._ro() as s:
            r = (await s.execute(text("select vector_dims(embedding) as d, count(*) as n from knowledge_embeddings where model = :m group by 1 order by 2 desc limit 1"), {"m": model})).first()
        if r is None or r.n < self.ann_threshold or not 2 <= int(r.d) <= 2000:  # HNSW indexes at most 2000 dimensions
            return None
        dim = int(r.d)
        if dim in await self._existing_ann():
            self._ann_dims = await self._existing_ann()
            return dim
        async with self._sm.begin() as s:
            await s.execute(text(_hnsw_ddl(dim)))
        self._ann_dims = await self._existing_ann()
        return dim

    async def ann_status(self) -> dict[str, Any]:
        return {"indexedSizes": sorted(await self._existing_ann()), "threshold": self.ann_threshold}

    async def semantic_search(self, vec: list[float], model: str, limit: int, source_id: str | None = None, now: float | None = None,
                              include: list[str] | None = None, exclude: list[str] | None = None) -> list[Passage]:
        dim = len(vec)
        if self._ann_dims is None:
            self._ann_dims = await self._existing_ann()
        use_index = dim in self._ann_dims  # the index is on the vector cast to a fixed size, so the query must use the same expression
        col, lit = (f"(e.embedding::vector({dim}))", f"cast(:v as vector({dim}))") if use_index else ("e.embedding", "cast(:v as vector)")
        q = ("select c.heading, c.body, d.id as doc_id, d.source_id, d.title, d.url, d.source_updated_at, d.ingested_at, d.content_hash, d.external_id, d.chunks, "
             f"s.stale_after_days, 1 - ({col} <=> {lit}) as sim from knowledge_embeddings e join knowledge_chunks c on c.id = e.chunk_id "
             "join knowledge_documents d on d.id = c.document_id join knowledge_sources s on s.id = d.source_id where e.model = :m and vector_dims(e.embedding) = :dim")
        params: dict[str, Any] = {"v": "[" + ",".join(repr(float(x)) for x in vec) + "]", "m": model, "dim": dim, "n": limit}
        if source_id:
            q += " and d.source_id = :s"
            params["s"] = source_id
        q += self._scope(include, exclude, params)
        q += f" order by {col} <=> {lit}, c.id limit :n"
        async with self._ro() as s:
            rows = (await s.execute(text(q), params)).all()
        out = []
        for r in rows:
            d = Document(r.source_id, r.external_id, r.title, r.url, r.content_hash, r.chunks, r.source_updated_at, r.ingested_at, id=r.doc_id)
            out.append(Passage(r.doc_id, r.source_id, r.title, r.url, r.heading, r.body, round(float(r.sim), 4), r.source_updated_at or r.ingested_at,
                               is_stale(d, r.stale_after_days, now), "meaning"))
        return out


class PgSchedules(_Base):
    @staticmethod
    def _s(r: Any) -> Any:
        from northcx.crawl_schedule import Schedule
        return Schedule(r.source_id, r.config, r.every_hours, r.next_run, r.created_by, id=r.id, last_run=r.last_run, last_job_id=r.last_job_id,
                        last_result=r.last_result, enabled=r.enabled, created_at=r.created_at)

    async def list(self) -> list[Any]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from crawl_schedules order by created_at"))).all()
        return [self._s(r) for r in rows]

    async def add(self, sc: Any) -> bool:
        from northcx.crawl_schedule import MAX_SCHEDULES
        async with self._sm.begin() as s:
            if (await s.execute(text("select count(*) from crawl_schedules"))).scalar_one() >= MAX_SCHEDULES:
                return False
            if (await s.execute(text("select 1 from crawl_schedules where source_id = :s and config->>'start_url' = :u"), {"s": sc.source_id, "u": sc.config["start_url"]})).first():
                return False
            await s.execute(text("insert into crawl_schedules (id, source_id, config, every_hours, next_run, enabled, created_by, created_at) "
                                 "values (:i, :s, cast(:c as jsonb), :h, :n, true, :b, :t)"),
                            {"i": sc.id, "s": sc.source_id, "c": json.dumps(sc.config), "h": sc.every_hours, "n": sc.next_run, "b": sc.created_by, "t": sc.created_at})
        return True

    async def delete(self, schedule_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from crawl_schedules where id = :i returning id"), {"i": schedule_id})).first() is not None

    async def set_enabled(self, schedule_id: str, enabled: bool, now: float) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(text("update crawl_schedules set enabled = :e, next_run = case when :e then greatest(next_run, :n) else next_run end where id = :i returning id"),
                                    {"i": schedule_id, "e": enabled, "n": now})).first() is not None

    async def claim_due(self, now: float, limit: int = 5) -> list[Any]:
        """Atomically moves each due schedule's next run forward, so only one server process starts it."""
        async with self._sm.begin() as s:
            rows = (await s.execute(text(
                "update crawl_schedules set next_run = :now + every_hours * 3600 where id in "
                "(select id from crawl_schedules where enabled and next_run <= :now order by next_run limit :n for update skip locked) returning *"), {"now": now, "n": limit})).all()
        return [self._s(r) for r in rows]

    async def record(self, schedule_id: str, at: float, job_id: str | None, result: str) -> None:
        async with self._sm.begin() as s:
            await s.execute(text("update crawl_schedules set last_run = :t, last_job_id = :j, last_result = :r where id = :i"), {"t": at, "j": job_id, "r": result[:300], "i": schedule_id})
