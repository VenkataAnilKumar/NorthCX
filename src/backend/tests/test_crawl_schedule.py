"""Scheduled re-crawls: validated like a crawl, run once per interval, never overlapping, claimed atomically."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.crawl_schedule import MAX_SCHEDULES, CrawlScheduler, InMemorySchedules
from northcx.crawler import CrawlConfig, CrawlRefused, Crawler
from northcx.knowledge import InMemoryKnowledge, Source
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from tests.test_ingest_crawl import HOST, KEY, H, html, public, site

PAGES = {"/": html("Home", "Welcome to help"), "/a": html("A", "page a")}
HOUR = 3600.0


@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        return InMemorySchedules()
    from northcx.db import PgSchedules
    return PgSchedules(request.getfixturevalue("engine"))


async def setup(repo, pages=PAGES):
    store = InMemoryKnowledge() if isinstance(repo, InMemorySchedules) else None
    if store is None:
        from northcx.db import PgKnowledge
        store = PgKnowledge(repo._sm.kw["bind"] if hasattr(repo._sm, "kw") else repo.engine)
    await store.create_source(Source("web", "Web"))
    c = Crawler(store, {HOST}, False, httpx.AsyncClient(transport=httpx.MockTransport(site(pages)), follow_redirects=False), public, lambda s: asyncio.sleep(0))
    return CrawlScheduler(c, repo), c, store


CFG = lambda: CrawlConfig(f"https://{HOST}/", use_sitemap=False, delay=0.25, max_depth=0)  # noqa: E731


async def test_a_schedule_runs_when_due_then_waits_a_full_interval(repo):
    sch, c, store = await setup(repo)
    s = await sch.create("web", CFG(), 6, "alice", now=1000.0)
    assert s.next_run == 1000.0 + 6 * HOUR
    assert await sch.tick(now=1000.0 + HOUR) == 0  # not due yet
    assert await sch.tick(now=1000.0 + 6 * HOUR) == 1
    await c.wait()
    assert [d.external_id for d, _ in await store.documents("web")] == [f"web:{HOST}/"]
    got = (await repo.list())[0]
    assert got.last_result == "started" and got.last_job_id and got.next_run == 1000.0 + 12 * HOUR
    assert await sch.tick(now=1000.0 + 6 * HOUR + 60) == 0  # the run was claimed: it does not run twice


async def test_a_run_that_cannot_start_is_recorded_and_tried_next_interval(repo):
    sch, c, store = await setup(repo)
    await sch.create("web", CFG(), 1, "alice", now=0.0)
    c.active["web"] = "other-job"  # a crawl of the source is still running
    assert await sch.tick(now=HOUR) == 0
    got = (await repo.list())[0]
    assert "already running" in got.last_result and got.next_run == 2 * HOUR
    c.active.clear()
    assert await sch.tick(now=2 * HOUR) == 1


async def test_a_host_that_is_no_longer_allowed_stops_the_runs(repo):
    sch, c, store = await setup(repo)
    await sch.create("web", CFG(), 1, "alice", now=0.0)
    c.allowed = {"elsewhere.example.net"}
    assert await sch.tick(now=HOUR) == 0
    assert "not in NORTHCX_CRAWL_HOSTS" in (await repo.list())[0].last_result


async def test_creation_is_validated_like_a_crawl(repo):
    sch, c, store = await setup(repo)
    with pytest.raises(CrawlRefused, match="every 1 hours"):
        await sch.create("web", CFG(), 0.5, "a")
    with pytest.raises(CrawlRefused, match="every 1 hours"):
        await sch.create("web", CFG(), 24 * 31, "a")
    with pytest.raises(CrawlRefused, match="not in NORTHCX_CRAWL_HOSTS"):
        await sch.create("web", CrawlConfig("https://evil.example.net/"), 2, "a")
    with pytest.raises(CrawlRefused, match="Unknown source"):
        await sch.create("nope", CFG(), 2, "a")
    with pytest.raises(CrawlRefused, match="max_pages"):
        await sch.create("web", CrawlConfig(f"https://{HOST}/", max_pages=100000), 2, "a")
    await sch.create("web", CFG(), 2, "a")
    with pytest.raises(CrawlRefused, match="already has"):
        await sch.create("web", CFG(), 3, "a")
    assert len(await repo.list()) == 1


async def test_pausing_stops_runs_and_resuming_does_not_fire_a_backlog(repo):
    sch, c, store = await setup(repo)
    s = await sch.create("web", CFG(), 1, "alice", now=0.0)
    assert await repo.set_enabled(s.id, False, 10.0)
    assert await sch.tick(now=5 * HOUR) == 0
    assert await repo.set_enabled(s.id, True, 5 * HOUR)
    assert await sch.tick(now=5 * HOUR) == 1 and await sch.tick(now=5 * HOUR + 60) == 0
    assert not await repo.set_enabled("cs-nope", True, 0.0) and await repo.delete(s.id) and not await repo.delete(s.id)


async def test_the_number_of_schedules_is_limited():
    repo = InMemorySchedules()
    sch, c, store = await setup(repo)
    for i in range(MAX_SCHEDULES):
        await sch.create("web", CrawlConfig(f"https://{HOST}/p{i}", delay=0.25), 2, "a")
    with pytest.raises(CrawlRefused, match="already"):
        await sch.create("web", CrawlConfig(f"https://{HOST}/last", delay=0.25), 2, "a")


# ---- API ----
def api(with_crawling=True):
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    kb = InMemoryKnowledge()
    crawler = Crawler(kb, {HOST}, False, httpx.AsyncClient(transport=httpx.MockTransport(site(PAGES)), follow_redirects=False), public)
    sched = CrawlScheduler(crawler, InMemorySchedules()) if with_crawling else None
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), knowledge=kb, crawler=crawler, crawl_scheduler=sched)), kb


def test_the_api_creates_lists_pauses_and_deletes_schedules_with_audit():
    c, kb = api()
    c.post("/v1/knowledge/sources", headers=H, json={"id": "web", "name": "Web"})
    body = {"url": f"https://{HOST}/", "everyHours": 12, "maxPages": 10}
    r = c.post("/v1/knowledge/sources/web/schedule", headers=H, json=body)
    assert r.status_code == 201 and r.json()["everyHours"] == 12 and r.json()["lastResult"] is None
    sid = r.json()["id"]
    assert c.post("/v1/knowledge/sources/web/schedule", headers=H, json=body).status_code == 409
    assert c.post("/v1/knowledge/sources/web/schedule", headers=H, json={**body, "url": "https://evil.example.net/", "everyHours": 2}).status_code == 400
    assert c.post("/v1/knowledge/sources/web/schedule", headers=H, json={**body, "everyHours": 0.1}).status_code == 400
    assert c.post("/v1/knowledge/sources/nope/schedule", headers=H, json=body).status_code == 404
    assert c.get("/v1/knowledge/schedules", headers=H).json()["schedules"][0]["id"] == sid
    assert c.post(f"/v1/knowledge/schedules/{sid}/enabled", headers=H, json={"enabled": False}).json() == {"enabled": False}
    assert c.delete(f"/v1/knowledge/schedules/{sid}", headers=H).json() == {"deleted": True} and c.delete(f"/v1/knowledge/schedules/{sid}", headers=H).status_code == 404
    actions = [e["action"] for e in c.get("/v1/audit?limit=20", headers=H).json()["entries"]]
    assert {"knowledge.schedule.create", "knowledge.schedule.pause", "knowledge.schedule.delete"} <= set(actions)
    assert c.get("/v1/knowledge/schedules").status_code == 401


def test_without_crawling_there_are_no_schedules():
    c, _ = api(with_crawling=False)
    assert c.get("/v1/knowledge/schedules", headers=H).json() == {"enabled": False, "schedules": []}
    assert c.post("/v1/knowledge/sources/web/schedule", headers=H, json={"url": f"https://{HOST}/", "everyHours": 2}).status_code == 501
