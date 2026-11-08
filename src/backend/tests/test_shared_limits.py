"""WP0.4: several server processes share one rate limit, abuse burst count and daily token budget through Postgres."""
import asyncio
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.pool import NullPool

from northcx.access import RateLimiter
from northcx.db import PgLimiter, PgUsageLedger, create_engine
from northcx.db.models import RateCounterRow
from northcx.safety.abuse import AbuseDetection

BACKEND = Path(__file__).resolve().parents[1]


async def window_with_room(seconds: float = 15.0) -> None:
    """Fixed one-minute windows: start a test early enough in a minute that it cannot straddle two windows."""
    left = 60 - (time.time() % 60)
    if left < seconds:
        await asyncio.sleep(left + 0.2)


@pytest.fixture
def second_engine(db_url):
    """A second, independent connection pool: stands in for a second server process."""
    e = create_engine(db_url, poolclass=NullPool)
    yield e
    asyncio.run(e.dispose())


async def test_two_limiters_on_one_database_share_one_limit(engine, second_engine):
    await window_with_room()
    a, b = PgLimiter(engine), PgLimiter(second_engine)
    results = [(await a.hit("key:k1", 5))[0] for _ in range(3)] + [(await b.hit("key:k1", 5))[0] for _ in range(3)]
    assert results == [True] * 5 + [False]  # the sixth in the minute is refused, whichever process it reaches
    assert (await b.hit("key:other", 5))[0]  # other keys are unaffected
    ok, retry = await a.hit("key:k1", 5)
    assert not ok and 1 <= retry <= 60


async def test_the_database_going_away_degrades_to_this_process_never_to_no_limit(engine, caplog):
    lim = PgLimiter(engine, fallback=RateLimiter())

    async def broken(*a, **k):
        raise ConnectionError("database is down")

    lim._bump = broken
    with caplog.at_level(logging.WARNING, logger="northcx.limits"):
        out = [(await lim.hit("key:x", 2))[0] for _ in range(4)]
        assert await lim.count("burst:s", 60) == 1 and await lim.count("burst:s", 60) == 2
    assert out == [True, True, False, False]
    assert len([r for r in caplog.records if "database unreachable" in r.message]) == 1  # warned once, not on every request


async def test_the_abuse_burst_check_counts_across_processes(engine, second_engine):
    await window_with_room()
    first, second = AbuseDetection(burst_limit=3), AbuseDetection(burst_limit=3)
    first.limiter, second.limiter = PgLimiter(engine), PgLimiter(second_engine)
    kinds = []
    for guard in (first, second, first, second):  # one conversation whose messages land on two servers
        kinds.append((await guard.check_input_ctx("where is my order", "sess-1", [])).kinds)
    assert kinds == [[], [], [], ["burst"]]
    other = await second.check_input_ctx("where is my order", "sess-2", [])
    assert other.kinds == []


async def test_the_daily_token_budget_is_one_number_across_processes(engine, second_engine):
    a, b = PgUsageLedger(engine, 100), PgUsageLedger(second_engine, 100)
    await a.charge("support", 60)
    await b.charge("support", 30)
    await b.charge("other", 5)
    assert await a.spent() == 95 and await a.spent("support") == 90 and await a.spent("other") == 5
    assert not await a.over_budget()
    await b.charge("support", 10)
    a._read_at = -1e9  # a looks again (it re-reads every few seconds)
    assert await a.over_budget()
    assert not await PgUsageLedger(engine, None).over_budget()  # no budget set


async def test_the_budget_falls_back_to_this_process_when_the_database_is_down(engine, caplog):
    led = PgUsageLedger(engine, 50)

    def broken(*a, **k):
        raise ConnectionError("down")

    led._ro = led._sm = broken  # every database access now fails
    with caplog.at_level(logging.WARNING, logger="northcx.limits"):
        await led.charge("support", 30)
        assert not await led.over_budget()
        await led.charge("support", 30)
        led._read_at = -1e9
        assert await led.over_budget()  # this process's own count (60) is over the 50 budget: degraded, not unlimited
    assert any("database unreachable" in r.message for r in caplog.records)


async def test_old_windows_are_cleaned_up(engine):
    async with PgLimiter(engine)._sm.begin() as s:
        await s.execute(text("insert into rate_counters(key, window_start, count) values ('old|60', 1000, 3)"))
    lim = PgLimiter(engine, cleanup_every=0)
    await lim.hit("key:z", 10)
    async with lim._ro() as s:
        assert (await s.execute(select(func.count()).select_from(RateCounterRow).where(RateCounterRow.key == "old|60"))).scalar_one() == 0


def free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start(port: int, db_url: str) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items() if not k.startswith("NORTHCX_")}
    env.update({"NORTHCX_DEMO": "1", "NORTHCX_API_KEY": "k" * 32, "PORT": str(port), "PYTHONPATH": str(BACKEND),
                "NORTHCX_DATABASE_URL": db_url, "NORTHCX_LIMITS_BACKEND": "postgres", "NORTHCX_RATE_LIMIT_PER_MINUTE": "10"})
    return subprocess.Popen([sys.executable, "-m", "northcx"], env=env, cwd=BACKEND, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _wait(port: int, p: subprocess.Popen) -> None:
    deadline = time.time() + 60
    while time.time() < deadline and p.poll() is None:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1).status == 200:
                return
        except Exception:
            time.sleep(0.3)
    raise AssertionError(p.stdout.read() if p.poll() is not None else "server did not become ready")


def _status(port: int) -> int:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/agents", headers={"authorization": "Bearer " + "k" * 32})
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def test_two_real_server_processes_enforce_one_limit(db_url, engine):
    ports = [free_port(), free_port()]
    procs = [_start(p, db_url.replace("+asyncpg", "")) for p in ports]
    try:
        for port, proc in zip(ports, procs):
            _wait(port, proc)
        time.sleep(max(0, 60 - (time.time() % 60) + 0.5) if (60 - time.time() % 60) < 20 else 0)
        codes = [_status(ports[i % 2]) for i in range(16)]  # alternate between the two servers
    finally:
        for proc in procs:
            proc.terminate()
            try:
                proc.wait(8)
            except subprocess.TimeoutExpired:
                proc.kill()
    assert codes.count(200) == 10 and codes.count(429) == 6, codes
