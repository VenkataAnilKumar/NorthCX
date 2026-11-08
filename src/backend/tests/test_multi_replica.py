"""WP0.5: several server processes (API replicas and workers) share one database without repeating or losing work."""
import asyncio
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from sqlalchemy.pool import NullPool

from northcx.alerts import AlertManager, AlertRule
from northcx.api.background import start_background
from northcx.crawler import CrawlRefused, Crawler
from northcx.db import PgAlertState, PgCrawlJobs, PgLeases, PgOutbox, create_engine
from northcx.knowledge import InMemoryKnowledge
from northcx.leases import InMemoryLeases, run_leased
from northcx.monitor import InMemoryMonitor
from northcx.outbox import Outbox

from tests.test_alerts import FakeInsights, no_wait

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def second_engine(db_url):
    e = create_engine(db_url, poolclass=NullPool)
    yield e
    asyncio.run(e.dispose())


# ---------- leases ----------
async def test_only_one_process_holds_a_lease_and_it_passes_on_when_released_or_expired(engine, second_engine):
    a, b = PgLeases(engine), PgLeases(second_engine)
    assert await a.acquire("outbox", "worker-a", 60)
    assert not await b.acquire("outbox", "worker-b", 60)  # taken
    assert await a.acquire("outbox", "worker-a", 60)  # the holder may renew
    await a.release("outbox", "worker-a")
    assert await b.acquire("outbox", "worker-b", 0.3)  # now free
    assert not await a.acquire("outbox", "worker-a", 60)
    await asyncio.sleep(0.5)  # worker-b is killed mid-pass and never renews: the lease runs out
    assert await a.acquire("outbox", "worker-a", 60)
    assert await b.acquire("other-job", "worker-b", 60)  # leases are per job name


async def test_a_job_pass_runs_once_when_two_workers_try_at_the_same_moment(engine, second_engine):
    ran: list[str] = []

    async def slow_job():
        ran.append("x")
        await asyncio.sleep(0.3)

    a, b = PgLeases(engine), PgLeases(second_engine)
    results = await asyncio.gather(run_leased(a, "job", 60, slow_job, "a"), run_leased(b, "job", 60, slow_job, "b"))
    assert sorted(results) == [False, True] and ran == ["x"]
    assert await run_leased(b, "job", 60, slow_job, "b")  # released after the pass, so the next pass can run anywhere
    assert await run_leased(None, "job", 60, slow_job)  # no leases (one process): always runs


async def test_in_memory_leases_follow_the_same_rules():
    now = [100.0]
    leases = InMemoryLeases(clock=lambda: now[0])
    assert await leases.acquire("j", "a", 10) and not await leases.acquire("j", "b", 10)
    now[0] = 111.0
    assert await leases.acquire("j", "b", 10)


# ---------- queues: each message is sent exactly once ----------
async def test_each_outbox_message_is_sent_once_with_two_workers(engine, second_engine):
    sent: list[int] = []

    class Slow:
        async def deliver(self, message):
            await asyncio.sleep(0.05)
            sent.append(message.id)

    writer = Outbox(PgOutbox(engine))  # no notifier: messages are only stored
    for i in range(8):
        await writer.publish(f"s{i}", "approval_result", {"n": i})
    w1, w2 = Outbox(PgOutbox(engine), Slow()), Outbox(PgOutbox(second_engine), Slow())
    l1, l2 = PgLeases(engine), PgLeases(second_engine)
    await asyncio.gather(run_leased(l1, "outbox", 60, w1.flush, "w1"), run_leased(l2, "outbox", 60, w2.flush, "w2"))
    assert sorted(sent) == sorted(set(sent)) and len(sent) == 8  # none twice, none lost
    assert await w1.repo.undelivered() == []


# ---------- alerts: state is shared ----------
def alert_manager(engine, ins):
    return AlertManager(ins, InMemoryMonitor(), [AlertRule("errors", "error_rate", 0.1, min_samples=5, cooldown_minutes=30)], None,
                        clock=time.time, sleep=no_wait, state=PgAlertState(engine))


async def test_an_alert_fires_once_even_when_a_different_worker_evaluates_next(engine, second_engine):
    ins = FakeInsights()
    ins.err = (0.5, 100)
    first, second = alert_manager(engine, ins), alert_manager(second_engine, ins)
    assert len(await first.evaluate()) == 1  # fires
    assert await second.evaluate() == []  # the other worker sees it is already firing: no second page
    assert await first.evaluate() == []
    await second.refresh()
    assert [a["rule"] for a in second.status()["active"]] == ["errors"]
    assert [e["event"] for e in second.status()["recent"]] == ["alert.fired"]  # one event, visible from either worker
    ins.err = (0.0, 100)
    await second.evaluate()  # recovers, seen by the other worker
    await first.refresh()
    assert first.status()["active"] == [] and [e["event"] for e in first.status()["recent"]] == ["alert.cleared", "alert.fired"]


# ---------- crawls: visible from every process ----------
async def test_a_crawl_started_on_one_process_is_visible_and_blocks_a_second_start_on_another(engine, second_engine):
    kb = InMemoryKnowledge()
    src = await kb.add_source("Help", "docs") if hasattr(kb, "add_source") else None
    sid = getattr(src, "id", "web")
    a = Crawler(kb, {"localhost"}, jobs_repo=PgCrawlJobs(engine))
    b = Crawler(kb, {"localhost"}, jobs_repo=PgCrawlJobs(second_engine))
    from northcx.crawler import CrawlJob
    job = CrawlJob(sid, "localhost")
    a.jobs[job.id] = job
    job.fetched = 3
    await a._save(job, force=True)
    seen = await b.all_jobs()
    assert [j["jobId"] for j in seen] == [job.id] and seen[0]["fetched"] == 3 and seen[0]["state"] == "running"
    assert (await b.job_status(job.id))["fetched"] == 3 and await b.job_status("nope") is None
    assert await PgCrawlJobs(second_engine).running(sid, time.time() - 300)
    assert not await PgCrawlJobs(second_engine).running(sid, time.time() + 5)  # a crawl whose heartbeat stopped is treated as dead
    job.state = "done"
    await a._save(job, force=True)
    assert not await PgCrawlJobs(second_engine).running(sid, time.time() - 300)


# ---------- roles ----------
async def test_an_api_only_process_starts_no_background_jobs_and_a_worker_does():
    from northcx.runtime import Runtime
    from northcx.store import InMemoryStore
    from northcx.trace import TraceStore

    class Notifier:
        async def deliver(self, message):
            pass

    rt = Runtime(None, InMemoryStore(), TraceStore(), outbox=Outbox(None, Notifier())) if "outbox" in Runtime.__init__.__code__.co_varnames else None
    if rt is None:
        rt = Runtime(None, InMemoryStore(), TraceStore())
        rt.outbox = Outbox(None, Notifier())
    kw = dict(runtime=rt, traces=None, flow=None, agents=None, approval_ttl_seconds=None, alerts=None, privacy=None, audit=None, retention_days=None, kb=None, crawl_scheduler=None)
    before = len(asyncio.all_tasks())
    stop_api = start_background("api", None, **kw)
    assert len(asyncio.all_tasks()) == before  # nothing started
    await stop_api()
    stop_worker = start_background("worker", None, **kw)
    assert len(asyncio.all_tasks()) > before
    await stop_worker()
    stop_all = start_background("all", None, **kw)
    assert len(asyncio.all_tasks()) > before
    await stop_all()


def _env(port: int, role: str, db_url: str, extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("NORTHCX_")}
    env.update({"NORTHCX_DEMO": "1", "NORTHCX_API_KEY": "k" * 32, "PORT": str(port), "PYTHONPATH": str(BACKEND), "NORTHCX_ROLE": role,
                "NORTHCX_DATABASE_URL": db_url, "NORTHCX_LIMITS_BACKEND": "postgres"})
    env.update(extra or {})
    return env


def _free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_and_exit(role: str, db_url: str, extra: dict | None = None) -> str:
    p = subprocess.run([sys.executable, "-m", "northcx"], env=_env(_free_port(), role, db_url, extra), cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert p.returncode != 0
    return p.stdout + p.stderr


def test_roles_are_validated_at_start_up():
    assert "NORTHCX_ROLE must be all, api or worker" in _run_and_exit("boss", "")
    assert "needs NORTHCX_DATABASE_URL" in _run_and_exit("api", "")


def _get(port: int, path: str, method: str = "GET", body: bytes | None = None) -> bytes:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method,
                                 headers={"authorization": "Bearer " + "k" * 32, "content-type": "application/json"})
    return urllib.request.urlopen(req, timeout=10).read()


def test_two_api_replicas_and_two_workers_against_one_database(db_url, engine):
    sync_url = db_url.replace("+asyncpg", "")
    roles = ["api", "api", "worker", "worker"]
    ports = [_free_port() for _ in roles]
    procs = [subprocess.Popen([sys.executable, "-m", "northcx"], env=_env(p, r, sync_url), cwd=BACKEND, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
             for p, r in zip(ports, roles)]
    try:
        for port, proc in zip(ports, procs):
            deadline = time.time() + 90
            while True:
                assert proc.poll() is None, proc.stdout.read()
                try:
                    if urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1).status == 200:
                        break
                except Exception:
                    pass
                assert time.time() < deadline, "did not become ready"
                time.sleep(0.4)
        # a conversation handled by one API replica is there on the other
        out = _get(ports[0], "/v1/agents/support/chat", "POST", b'{"sessionId":"mr-1","message":"where is order 1042?"}')
        assert b"1042" in out or b"order" in out.lower()
        seen = _get(ports[1], "/v1/sessions/mr-1/transcript")
        assert b"mr-1" in seen
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
