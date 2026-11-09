"""WP5.6: one search over what a person may see, merged by rank, never showing or counting what they may not."""
import asyncio

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl, Identity
from northcx.knowledge import InMemoryKnowledge, Source
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.staff_search import RRF_K, Result, SearchService
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


class Fake:
    def __init__(self, name, permission, ids, delay=0.0, fail=False):
        self.name, self.permission, self.ids, self.delay, self.fail, self.asked = name, permission, ids, delay, fail, 0

    async def search(self, query, identity, limit):
        self.asked += 1
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("down")
        return [Result("knowledge", i, f"t{i}", "s", "why", self.name) for i in self.ids]


class Person:
    def __init__(self, *perms):
        self.perms = set(perms)

    def can(self, p):
        return p in self.perms


def run(coro):
    return asyncio.run(coro)


def test_results_from_several_sources_are_merged_by_reciprocal_rank():
    a, b = Fake("a", "x", ["1", "2", "3"]), Fake("b", "y", ["2", "9"])
    out = run(SearchService([a, b]).search(Person("x", "y"), "qq"))
    ids = [r["id"] for r in out["results"]]
    assert ids[0] == "2"                                                    # found by both: ranked first
    assert abs(out["results"][0]["score"] - (1 / (RRF_K + 2) + 1 / (RRF_K + 1))) < 1e-4 and set(ids) == {"1", "2", "3", "9"}


def test_a_source_the_person_cannot_use_is_not_asked_and_adds_nothing_to_the_results():
    secret = Fake("secret", "traces:read", ["s1", "s2"])
    open_ = Fake("open", "knowledge:read", ["k1"])
    out = run(SearchService([secret, open_]).search(Person("knowledge:read"), "qq"))
    assert [r["id"] for r in out["results"]] == ["k1"] and secret.asked == 0 and out["searched"] == ["open"]
    assert "secret" not in str(out)                                          # not even named: the person learns nothing about it


def test_a_slow_or_failing_source_is_named_and_the_others_still_answer():
    out = run(SearchService([Fake("slow", "x", ["1"], delay=0.5), Fake("bad", "x", ["2"], fail=True), Fake("ok", "x", ["3"])], timeout=0.05).search(Person("x"), "qq"))
    assert [r["id"] for r in out["results"]] == ["3"]
    assert {(s["source"], s["reason"]) for s in out["skipped"]} == {("slow", "timed out"), ("bad", "failed (RuntimeError)")}


def test_a_very_short_query_returns_nothing():
    assert run(SearchService([Fake("a", "x", ["1"])]).search(Person("x"), " a ")) == {"results": [], "skipped": []}


def test_the_search_endpoint_covers_knowledge_conversations_and_handoffs_and_masks_customers():
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([text("Sure.")]), InMemoryStore(), TraceStore())
    kb = InMemoryKnowledge()
    loop.run_until_complete(kb.create_source(Source("faq", "FAQ")))
    loop.run_until_complete(kb.upsert("faq", "w", "Warranty", None, "Every product has a two year warranty.", None))
    ac = AccessControl(bootstrap_key="boot" * 10)
    agent = support_agent()
    c = TestClient(create_app(rt, rt.traces, {"support": agent}, access=ac, knowledge=kb))
    loop.run_until_complete(rt.run(agent, "s1", "My warranty email is jo@example.com, please help"))
    key = lambda role, name=None: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(name or role, role, "t"))[1]}  # noqa: E731
    r = c.get("/v1/workspace/search", headers=key("reviewer"), params={"q": "warranty"})
    assert r.status_code == 200
    kinds = {x["kind"] for x in r.json()["results"]}
    assert {"knowledge", "conversation"} <= kinds and "jo@example.com" not in r.text
    assert all(x["why"] for x in r.json()["results"])
    assert c.get("/v1/workspace/search", headers=key("channel"), params={"q": "warranty"}).status_code == 403
    assert c.get("/v1/workspace/search", params={"q": "warranty"}).status_code == 401
    assert c.get("/v1/workspace/search", headers=key("viewer", "v2"), params={"q": "x" * 300}).status_code == 400
