"""Meaning-based knowledge search: the embeddings client, background indexing, hybrid ranking and the keyword fallback."""
import json

import httpx
import pytest

from northcx.embeddings import EmbeddingError, EmbeddingIndexer, HttpEmbedder, HybridKnowledge, fuse, model_groups, parse_source_models
from northcx.knowledge import InMemoryKnowledge, Passage, Source

CONCEPTS = [("refund", "money back", "reimburse", "return"), ("ship", "delivery", "courier", "parcel"), ("gift", "voucher", "present")]


class Fake:
    """Understands that 'money back' means 'refund' without sharing a word with it."""
    model = "fake-1"

    def __init__(self):
        self.down = False
        self.calls = 0

    def _v(self, t):
        t = t.lower()
        return [float(sum(w in t for w in group)) for group in CONCEPTS]

    async def embed(self, texts):
        self.calls += 1
        if self.down:
            raise EmbeddingError("the embedding service could not be reached (ConnectError)")
        return [self._v(t) for t in texts]

    async def embed_query(self, q):
        return (await self.embed([q]))[0]

    def for_model(self, model):
        other = Fake()
        other.model, other.down, other.calls = model, self.down, self.calls
        return other


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        return InMemoryKnowledge()
    from northcx.db import PgKnowledge
    return PgKnowledge(request.getfixturevalue("engine"))


async def build(store):
    await store.create_source(Source("help", "Help", None))
    await store.upsert("help", "a", "Refunds", None, "# Refunds\n\nWe reimburse the full price within thirty days.", None, 1.0)
    await store.upsert("help", "b", "Shipping", None, "# Shipping\n\nA courier brings your parcel in three days.", None, 1.0)
    emb = Fake()
    hy = HybridKnowledge(store, emb)
    hy.indexer = EmbeddingIndexer(store, emb)
    return hy, emb


async def test_a_question_in_different_words_finds_the_passage_by_meaning(store):
    hy, emb = await build(store)
    assert (await store.search("money back", 3)) == []  # no shared word: keywords alone find nothing
    assert await hy.indexer.run_once() == 2
    found = await hy.search("money back", 3)
    assert found and found[0].title == "Refunds" and found[0].via == "meaning"


async def test_exact_terms_still_win_and_agreeing_methods_are_marked_both(store):
    hy, _ = await build(store)
    await hy.indexer.run_once()
    found = await hy.search("refund", 3)
    assert found[0].title == "Refunds"
    found = await hy.search("courier", 3)
    assert found[0].title == "Shipping" and found[0].via == "both"


async def test_the_status_counts_and_a_rebuild_clears_and_redoes(store):
    hy, _ = await build(store)
    s = await hy.indexer.status()
    assert (s["indexed"], s["passages"], s["pending"]) == (0, 2, 2)
    await hy.indexer.run_once()
    assert (await hy.indexer.status())["pending"] == 0
    assert await hy.indexer.rebuild() == 2
    assert (await hy.indexer.status())["pending"] == 2
    await hy.indexer.run_once()
    assert (await hy.indexer.status())["indexed"] == 2


async def test_editing_a_document_reindexes_only_what_changed(store):
    hy, emb = await build(store)
    await hy.indexer.run_once()
    await store.upsert("help", "a", "Refunds", None, "# Refunds\n\nMoney back takes ten days.", None, 2.0)
    assert (await hy.indexer.status())["pending"] == 1
    await hy.indexer.run_once()
    assert (await hy.search("reimburse", 1))[0].text.startswith("Money back")


async def test_deleting_a_document_removes_its_vectors(store):
    hy, _ = await build(store)
    await hy.indexer.run_once()
    await store.delete("help", "a")
    assert all(p.title != "Refunds" for p in await hy.search("money back", 5))
    assert (await hy.indexer.status())["indexed"] == 1


async def test_when_the_embedding_service_is_down_search_falls_back_to_keywords(store):
    hy, emb = await build(store)
    await hy.indexer.run_once()
    emb.down = True
    found = await hy.search("courier", 3)
    assert found and found[0].title == "Shipping" and found[0].via == "keyword"
    assert hy.last_fallback == "EmbeddingError"
    assert await hy.search("money back", 3) == []  # nothing to match by words: empty, never an error


async def test_indexing_failures_are_remembered_without_raising(store):
    hy, emb = await build(store)
    emb.down = True
    assert await hy.indexer.run_once() == 0
    s = await hy.indexer.status()
    assert "could not be reached" in s["lastError"] and s["pending"] == 2
    emb.down = False
    await hy.indexer.run_once()
    assert (await hy.indexer.status())["lastError"] is None


def test_fusion_rewards_agreement():
    def p(i):
        return Passage(f"d{i}", "s", "t", None, "h", f"text{i}", 1.0, 0.0, False)
    out = fuse([p(1), p(2)], [p(2), p(3)], 3)
    assert [x.document_id for x in out] == ["d2", "d1", "d3"] and out[0].via == "both"


# ---- the HTTP client ----
def client(handler, **kw):
    return HttpEmbedder("https://emb.example.com/v1", "m", "secret", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


async def test_the_client_speaks_the_common_shape_and_keeps_order():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        n = len(seen["body"]["input"])
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [float(i), 1.0]} for i in reversed(range(n))]})
    e = client(handler)
    assert await e.embed(["a", "b"]) == [[0.0, 1.0], [1.0, 1.0]]
    assert seen["url"] == "https://emb.example.com/v1/embeddings" and seen["auth"] == "Bearer secret" and seen["body"]["model"] == "m"


async def test_bad_answers_become_safe_errors():
    for resp in (httpx.Response(500, text="secret internal detail"), httpx.Response(200, text="not json"),
                 httpx.Response(200, json={"data": []}), httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, "x"]}]}),
                 httpx.Response(200, text='{"data": [{"index": 0, "embedding": [1e999]}]}')):
        with pytest.raises(EmbeddingError) as ei:
            await client(lambda r, resp=resp: resp).embed(["a"])
        assert "secret" not in str(ei.value) and "emb.example.com" not in str(ei.value)


async def test_a_wrong_dimension_is_refused():
    with pytest.raises(EmbeddingError):
        await client(lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}), dimensions=8).embed(["a"])


async def test_queries_are_cached():
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})
    e = client(handler)
    await e.embed_query("hello")
    await e.embed_query("hello")
    assert n["c"] == 1


@pytest.mark.parametrize("url", ["ftp://x/v1", "http://emb.example.com/v1", "https://u:p@emb.example.com/v1", "https://emb.example.com/v1?k=1", "nonsense"])
def test_unsafe_addresses_are_refused(url):
    with pytest.raises(ValueError):
        HttpEmbedder(url, "m")


def test_plain_http_is_fine_for_localhost_and_model_is_required():
    assert HttpEmbedder("http://localhost:8080/v1", "m").url.endswith("/v1/embeddings")
    with pytest.raises(ValueError):
        HttpEmbedder("https://emb.example.com/v1", "")


# ---- the API ----
def test_the_index_endpoints_and_search_marks_how_each_passage_was_found():
    import asyncio
    from fastapi.testclient import TestClient
    from northcx.access import AccessControl
    from examples.support_agent import support_agent
    from northcx.llm import ScriptedLLM
    from northcx.runtime import Runtime
    from northcx.server import create_app
    from northcx.store import InMemoryStore
    from northcx.trace import TraceStore
    hy, _ = asyncio.run(build(InMemoryKnowledge()))
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    key = "boot" * 10
    h = {"authorization": f"Bearer {key}"}
    with TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=key), knowledge=hy)) as c:
        asyncio.run(hy.indexer.run_once())
        st = c.get("/v1/knowledge/index", headers=h).json()
        assert st["enabled"] and st["pending"] == 0 and st["model"] == "fake-1"
        got = c.get("/v1/knowledge/search", params={"q": "money back"}, headers=h).json()["passages"]
        assert got and got[0]["title"] == "Refunds" and got[0]["via"] == "meaning"
        assert c.post("/v1/knowledge/index/rebuild", headers=h).status_code == 202
    plain = AccessControl(bootstrap_key=key)
    rt2 = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    with TestClient(create_app(rt2, rt2.traces, {"support": support_agent()}, access=plain)) as c:
        assert c.get("/v1/knowledge/index", headers=h).json() == {"enabled": False}
        assert c.post("/v1/knowledge/index/rebuild", headers=h).status_code == 501


# ---- approximate index (Postgres only) ----
async def test_the_approximate_index_is_built_past_the_threshold_and_agrees_with_the_exact_scan(engine):
    from sqlalchemy import text as sql
    from northcx.db import PgKnowledge
    st = PgKnowledge(engine)
    st.ann_threshold = 4
    await st.create_source(Source("help", "Help", None))
    for i in range(6):
        await st.upsert("help", f"d{i}", f"Doc {i}", None, f"# Doc {i}\n\n" + ["refund money back", "courier parcel ship", "gift voucher present"][i % 3] + f" item{i}", None, 1.0)
    idx = EmbeddingIndexer(st, Fake())
    await st.ensure_semantic()
    st.ann_threshold = 10_000
    await idx.run_once()
    assert (await st.ann_status())["indexedSizes"] == []  # below the threshold: the exact scan is used
    exact = [(p.document_id, p.score) for p in await st.semantic_search([1.0, 0.0, 0.0], "fake-1", 6)]
    st.ann_threshold = 4
    assert await st.maybe_build_ann("fake-1") == 3 and (await st.ann_status())["indexedSizes"] == [3]
    st._ann_dims = None
    approx = [(p.document_id, p.score) for p in await st.semantic_search([1.0, 0.0, 0.0], "fake-1", 6)]
    assert {d for d, _ in approx} == {d for d, _ in exact} and sorted(s for _, s in approx) == sorted(s for _, s in exact)
    async with engine.begin() as c:
        await c.execute(sql("set local enable_seqscan = off"))
        plan = (await c.execute(sql("explain select chunk_id from knowledge_embeddings where vector_dims(embedding) = 3 order by (embedding::vector(3)) <=> '[1,0,0]'::vector(3) limit 3"))).all()
    assert any("ix_ke_hnsw_3" in str(r) for r in plan)
    assert (await idx.status())["approximateIndex"]["indexedSizes"] == [3]


# ---- a different model for some sources ----
def test_source_model_settings_are_parsed_strictly_and_grouped():
    assert parse_source_models("help=m2, docs = m3") == {"help": "m2", "docs": "m3"} and parse_source_models("") == {}
    for bad in ("help", "help=", "=m", "a=m,a=n"):
        with pytest.raises(ValueError):
            parse_source_models(bad)
    assert model_groups("m1", {"help": "m2", "docs": "m2", "faq": "m1"}) == [("m1", None, ["docs", "help"]), ("m2", ["docs", "help"], None)]
    assert model_groups("m1", {}) == [("m1", None, None)]


async def test_each_source_is_indexed_and_searched_with_its_own_model(store):
    await store.create_source(Source("help", "Help", None))
    await store.create_source(Source("docs", "Docs", None))
    await store.upsert("help", "a", "Refunds", None, "# Refunds\n\nWe reimburse the full price.", None, 1.0)
    await store.upsert("docs", "b", "Refund API", None, "# Refund API\n\nPOST a refund to reimburse an order.", None, 1.0)
    emb = Fake()
    hy = HybridKnowledge(store, emb, source_models={"docs": "fake-2"})
    hy.indexer = EmbeddingIndexer(store, emb, source_models={"docs": "fake-2"})
    assert await hy.indexer.run_once() == 2
    st = await hy.indexer.status()
    assert [(m["model"], m["indexed"], m["passages"]) for m in st["models"]] == [("fake-1", 1, 1), ("fake-2", 1, 1)] and st["pending"] == 0
    assert [p.source_id for p in await store.semantic_search([1.0, 0.0, 0.0], "fake-1", 5)] == ["help"]  # the default model only holds the help source
    assert [p.source_id for p in await store.semantic_search([1.0, 0.0, 0.0], "fake-2", 5)] == ["docs"]
    found = await hy.search("money back", 5)
    assert {p.source_id for p in found} == {"help", "docs"}
    assert [p.source_id for p in await hy.search("money back", 5, "docs")] == ["docs"]


async def test_changing_a_sources_model_makes_only_that_source_pending(store):
    await store.create_source(Source("help", "Help", None))
    await store.upsert("help", "a", "Refunds", None, "# Refunds\n\nWe reimburse the full price.", None, 1.0)
    emb = Fake()
    await EmbeddingIndexer(store, emb).run_once()
    idx = EmbeddingIndexer(store, emb, source_models={"help": "fake-3"})
    assert (await idx.status())["pending"] == 1
    await idx.run_once()
    assert (await idx.status())["pending"] == 0
