"""The tenancy load gate (WP2.9): how much slower are reads with row-level security than without?

The same store code reads the same data twice: as the table owner (row-level security does not apply, the single-company baseline) and as an ordinary
role with a tenant set (the multi-tenant way). Each is timed over many reads of a conversation and of a list, and the median of several trials is compared."""
from __future__ import annotations

import statistics
import time

from northcx.db import PgMemoryStore, PgTraceStore
from northcx.tenancy import TENANT
from northcx.trace import Trace


async def seed(owner_engine, sessions: int = 40, messages: int = 12) -> None:
    store, traces = PgMemoryStore(owner_engine), PgTraceStore(owner_engine)
    for tenant in ("default", "other"):
        token = TENANT.set(tenant)
        try:
            for s in range(sessions):
                await store.save_messages(f"s{s}", [{"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i} of conversation {s} for {tenant}"} for i in range(messages)])
                t = Trace("support", f"s{s}")
                t.add("llm", tokens=10)
                await traces.save(t)
        finally:
            TENANT.reset(token)


async def timed(engine, tenant: str, reads: int, sessions: int) -> float:
    store, traces = PgMemoryStore(engine), PgTraceStore(engine)
    token = TENANT.set(tenant)
    try:
        for s in range(sessions):                              # warm up connections and caches before timing
            await store.load_messages(f"s{s}")
        start = time.perf_counter()
        for i in range(reads):
            await store.load_messages(f"s{i % sessions}")
            await traces.summaries(f"s{i % sessions}", 20)
        return (time.perf_counter() - start) / reads * 1000
    finally:
        TENANT.reset(token)


async def run_benchmark(owner_engine, app_engine, reads: int = 300, trials: int = 5, sessions: int = 40) -> dict[str, float]:
    await seed(owner_engine, sessions)
    baseline = [await timed(owner_engine, "default", reads, sessions) for _ in range(trials)]
    secured = [await timed(app_engine, "default", reads, sessions) for _ in range(trials)]
    b, s = statistics.median(baseline), statistics.median(secured)
    return {"baseline_ms": round(b, 3), "secured_ms": round(s, 3), "overhead": round((s - b) / b, 4), "reads": reads, "trials": trials}
