"""The load gate (WP2.9). The benchmark always runs briefly so it cannot rot; the limit is enforced when NORTHCX_LOAD_GATE=1 (timing on a shared machine is too noisy to fail a build on)."""
import os

import pytest
from sqlalchemy.pool import NullPool

from northcx.db import create_engine
from tenancy_load import run_benchmark

LIMIT = float(os.environ.get("NORTHCX_LOAD_GATE_MAX", "0.15"))


async def test_the_benchmark_runs_and_reports_numbers(engine, app_engine):
    out = await run_benchmark(engine, app_engine, reads=20, trials=2, sessions=5)
    assert out["baseline_ms"] > 0 and out["secured_ms"] > 0 and -1 < out["overhead"] < 50


@pytest.mark.skipif(os.environ.get("NORTHCX_LOAD_GATE") != "1", reason="set NORTHCX_LOAD_GATE=1 to enforce the limit")
async def test_reads_with_row_level_security_stay_within_the_agreed_overhead(db_url, app_engine):
    owner = create_engine(db_url)               # pooled, like the server
    from urllib.parse import urlsplit, urlunsplit
    host = urlsplit(db_url).netloc.rsplit("@", 1)[-1]
    pooled_app = create_engine(urlunsplit((urlsplit(db_url).scheme, f"northcx_app_test:app-test-pw@{host}", urlsplit(db_url).path, "", "")))
    try:
        out = await run_benchmark(owner, pooled_app, reads=400, trials=7)
        print("load gate:", out)
        assert out["overhead"] <= LIMIT, out
    finally:
        await owner.dispose()
        await pooled_app.dispose()
