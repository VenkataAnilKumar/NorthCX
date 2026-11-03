"""Load test (Q12): many simulated customers chatting at once.

    python -m northcx.loadtest --users 100 --conversations 400                      # in this process, with a pretend model
    python -m northcx.loadtest --url http://localhost:3000 --key <channel key> ...  # against a running server

Each simulated customer gets a chat token, then talks for a few turns (order questions, small talk, a request for a person), pausing between
messages like a person. The report gives throughput, errors by status, and reply-time percentiles overall and per kind of request, plus how far
the server's event loop fell behind (a sign it is saturated). In-process mode uses the offline demo model with an optional added delay standing
in for model latency, so it measures what the PLATFORM costs per turn, not what any model costs. Against a server you run, results include your
database, your model and your network.

`--max-p95-ms` and `--max-error-rate` make it exit 1 when the run misses its targets, so it can gate a release.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import resource
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import httpx

QUESTIONS = ["where is order 1042?", "hello", "do you wrap gifts?", "refund 20 for order 1042", "thanks, that helps", "I want a person please", "what is the status of order 1042"]


@dataclass
class Profile:
    users: int = 50                 # customers talking at the same time
    conversations: int = 200        # total conversations to run
    turns: int = 4                  # messages per conversation
    think_ms: int = 300             # average pause between a customer's messages
    ramp_s: float = 2.0             # time over which the users are started
    agent: str = "support"
    seed: int = 1


@dataclass
class Report:
    profile: Profile
    seconds: float = 0.0
    latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    statuses: Counter = field(default_factory=Counter)
    failures: Counter = field(default_factory=Counter)
    loop_lag_ms: list[float] = field(default_factory=list)
    rss_mb: tuple[float, float] | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def requests(self) -> int:
        return sum(len(v) for v in self.latencies.values())

    @property
    def error_rate(self) -> float:
        bad = sum(n for s, n in self.statuses.items() if s == "network" or (isinstance(s, int) and s >= 500))
        return bad / self.requests if self.requests else 0.0

    def pct(self, op: str | None, q: float) -> float | None:
        xs = sorted(x for k, v in self.latencies.items() if op in (None, k) for x in v)
        return round(xs[min(len(xs) - 1, int(q * len(xs)))] * 1000, 1) if xs else None

    def summary(self) -> dict[str, Any]:
        lag = sorted(self.loop_lag_ms)
        return {"seconds": round(self.seconds, 2), "requests": self.requests, "requestsPerSecond": round(self.requests / self.seconds, 1) if self.seconds else None,
                "errorRate": round(self.error_rate, 4), "statuses": {str(k): v for k, v in sorted(self.statuses.items(), key=lambda kv: str(kv[0]))}, "failures": dict(self.failures),
                "latencyMs": {op or "all": {"p50": self.pct(op, .5), "p90": self.pct(op, .9), "p95": self.pct(op, .95), "p99": self.pct(op, .99), "max": self.pct(op, 1.0), "n": len(self.latencies[op]) if op else self.requests}
                              for op in [None, *sorted(self.latencies)]},
                "eventLoopLagMs": {"p95": round(lag[int(len(lag) * .95)], 1), "max": round(lag[-1], 1)} if lag else None,
                "memoryMb": {"before": self.rss_mb[0], "after": self.rss_mb[1]} if self.rss_mb else None, "users": self.profile.users, "conversations": self.profile.conversations, "turns": self.profile.turns}


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # kilobytes on Linux


async def lag_sampler(report: Report, stop: asyncio.Event, every: float = 0.05) -> None:
    """How late the event loop wakes up: close to zero when idle, large when the process is the bottleneck."""
    while not stop.is_set():
        t = time.perf_counter()
        await asyncio.sleep(every)
        report.loop_lag_ms.append(max(0.0, (time.perf_counter() - t - every) * 1000))


async def timed(client: httpx.AsyncClient, report: Report, op: str, method: str, url: str, **kw: Any) -> httpx.Response | None:
    t = time.perf_counter()
    try:
        r = await client.request(method, url, **kw)
    except httpx.HTTPError as e:
        report.latencies[op].append(time.perf_counter() - t)
        report.statuses["network"] += 1
        report.failures[type(e).__name__] += 1
        return None
    report.latencies[op].append(time.perf_counter() - t)
    report.statuses[r.status_code] += 1
    return r


async def one_conversation(client: httpx.AsyncClient, report: Report, p: Profile, rnd: random.Random, mint_key: str, n: int) -> None:
    r = await timed(client, report, "mint-token", "POST", "/v1/chat-tokens", headers={"authorization": f"Bearer {mint_key}"}, json={"customerId": f"load-{n}", "agent": p.agent})
    if r is None or r.status_code != 201:
        return
    grant = r.json()
    h = {"authorization": f"Bearer {grant['token']}"}
    for t in range(p.turns):
        await asyncio.sleep(rnd.expovariate(1000 / max(p.think_ms, 1)) if p.think_ms else 0)
        q = rnd.choice(QUESTIONS)
        r = await timed(client, report, "chat", "POST", f"/v1/agents/{p.agent}/chat", headers=h, json={"sessionId": grant["sessionId"], "message": q})
        if r is not None and r.status_code == 200 and r.json().get("status") == "escalated":
            await timed(client, report, "outbox", "GET", f"/v1/sessions/{grant['sessionId']}/outbox", headers=h)
            break
    if rnd.random() < 0.3:
        await timed(client, report, "feedback", "POST", f"/v1/sessions/{grant['sessionId']}/feedback", headers=h, json={"rating": rnd.randint(3, 5)})


async def run(client: httpx.AsyncClient, p: Profile, mint_key: str, in_process: bool = False) -> Report:
    report = Report(p)
    rnd = random.Random(p.seed)
    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(p.conversations):
        queue.put_nowait(i)
    stop = asyncio.Event()
    lag = asyncio.create_task(lag_sampler(report, stop))
    before = rss_mb() if in_process else None

    async def worker(w: int) -> None:
        await asyncio.sleep(p.ramp_s * w / max(p.users, 1))
        local = random.Random(rnd.random())
        while True:
            try:
                n = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            await one_conversation(client, report, p, local, mint_key, n)

    started = time.perf_counter()
    await asyncio.gather(*(worker(w) for w in range(p.users)))
    report.seconds = time.perf_counter() - started
    stop.set()
    await lag
    if in_process:
        report.rss_mb = (before, rss_mb())  # type: ignore[assignment]
    return report


class SlowModel:
    """The offline demo model plus a delay standing in for a real model's latency."""

    def __init__(self, latency_ms: float, jitter: float = 0.3):
        from .demo import DemoLLM
        self.inner, self.latency, self.jitter = DemoLLM(), latency_ms / 1000, jitter

    async def complete(self, req: Any) -> Any:
        if self.latency:
            await asyncio.sleep(self.latency * (1 + random.uniform(-self.jitter, self.jitter)))
        return await self.inner.complete(req)


def format_summary(s: dict[str, Any]) -> str:
    lines = [f"{s['users']} users, {s['conversations']} conversations of up to {s['turns']} turns: {s['requests']} requests in {s['seconds']} s = {s['requestsPerSecond']} requests/s, error rate {s['errorRate'] * 100:.2f}%",
             f"statuses: {s['statuses']}" + (f"   failures: {s['failures']}" if s['failures'] else ""), f"{'':12} {'p50':>8} {'p90':>8} {'p95':>8} {'p99':>8} {'max':>8} {'n':>6}   (ms)"]
    for op, v in s["latencyMs"].items():
        lines.append(f"{op:12} {v['p50']!s:>8} {v['p90']!s:>8} {v['p95']!s:>8} {v['p99']!s:>8} {v['max']!s:>8} {v['n']:>6}")
    if s["eventLoopLagMs"]:
        lines.append(f"event loop lag: p95 {s['eventLoopLagMs']['p95']} ms, max {s['eventLoopLagMs']['max']} ms (over ~50 ms means the process is saturated)")
    if s["memoryMb"]:
        lines.append(f"memory: {s['memoryMb']['before']} MB -> {s['memoryMb']['after']} MB")
    return "\n".join(lines)


async def in_process(p: Profile, model_ms: float) -> Report:
    from examples.support_agent import support_agent
    from .access import AccessControl, LimitConfig
    from .runtime import Runtime
    from .server import create_app
    from .store import InMemoryStore
    from .trace import TraceStore
    key = "load" * 10
    rt = Runtime(SlowModel(model_ms), InMemoryStore(), TraceStore())
    limits = LimitConfig(per_key_per_minute=10 ** 9, chat_per_session_per_minute=10 ** 9, auth_failures_per_minute=10 ** 9)
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=key, limits=limits))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://load", timeout=60, follow_redirects=False) as client:
        return await run(client, p, key, in_process=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="northcx.loadtest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="a running server; without it the test runs in this process")
    ap.add_argument("--key", help="a channel or admin key that may mint chat tokens (with --url)")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--conversations", type=int, default=200)
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--think-ms", type=int, default=300)
    ap.add_argument("--ramp-s", type=float, default=2.0)
    ap.add_argument("--model-ms", type=float, default=0.0, help="in-process only: added delay per model call, standing in for model latency")
    ap.add_argument("--agent", default="support")
    ap.add_argument("--max-p95-ms", type=float, help="fail if the chat reply time p95 is above this")
    ap.add_argument("--max-error-rate", type=float, default=0.01, help="fail if more than this share of requests fail with 5xx or network errors")
    ap.add_argument("--json", dest="json_out")
    a = ap.parse_args(argv)
    p = Profile(a.users, a.conversations, a.turns, a.think_ms, a.ramp_s, a.agent)
    if a.url:
        if not a.key:
            print("error: --url needs --key", file=sys.stderr)
            return 2

        async def remote() -> Report:
            async with httpx.AsyncClient(base_url=a.url.rstrip("/"), timeout=60, follow_redirects=False, limits=httpx.Limits(max_connections=max(a.users * 2, 20))) as c:
                return await run(c, p, a.key)
        report = asyncio.run(remote())
    else:
        report = asyncio.run(in_process(p, a.model_ms))
    s = report.summary()
    print(format_summary(s))
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump(s, f, indent=1)
    bad = []
    chat_p95 = s["latencyMs"].get("chat", {}).get("p95")
    if a.max_p95_ms is not None and (chat_p95 is None or chat_p95 > a.max_p95_ms):
        bad.append(f"chat p95 {chat_p95} ms is above {a.max_p95_ms} ms")
    if s["errorRate"] > a.max_error_rate:
        bad.append(f"error rate {s['errorRate'] * 100:.2f}% is above {a.max_error_rate * 100:.2f}%")
    for line in bad:
        print("MISSED TARGET:", line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
