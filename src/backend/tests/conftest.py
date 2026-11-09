import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_URL = "postgresql+asyncpg://northcx:northcx@localhost:5432/northcx_test"


def _reachable(url: str) -> bool:
    import asyncpg

    async def ping() -> None:
        conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"), timeout=3)
        await conn.close()

    try:
        asyncio.run(ping())
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_url():
    """A migrated, empty Postgres database. Set NORTHCX_TEST_DATABASE_URL; tests skip if it is unreachable
    unless NORTHCX_REQUIRE_DB=1 (CI), in which case they fail."""
    from northcx.db import migrate
    from northcx.db.engine import downgrade

    url = os.environ.get("NORTHCX_TEST_DATABASE_URL", DEFAULT_URL)
    if not _reachable(url):
        if os.environ.get("NORTHCX_REQUIRE_DB") == "1":
            pytest.fail(f"Postgres required but unreachable: {url}")
        pytest.skip("Postgres not reachable; set NORTHCX_TEST_DATABASE_URL to run database tests")
    downgrade(url)
    migrate(url)
    return url


@pytest.fixture
def engine(db_url):
    """A fresh engine over an emptied database. Sync fixture so it can be used from any fixture or test."""
    from sqlalchemy import text
    from sqlalchemy.pool import NullPool

    from northcx.db import create_engine

    async def clean() -> None:
        eng = create_engine(db_url, poolclass=NullPool)
        async with eng.begin() as c:
            await c.execute(text("alter table audit_log disable trigger user"))  # the log refuses truncation; tests reset it
            await c.execute(text(
                "truncate sessions, messages, customer_facts, traces, trace_events, approvals, outbox, handoffs, simulation_runs, "
                "releases, agent_versions, api_keys, audit_log, email_sessions, email_messages, monitor_findings, idempotency_keys, knowledge_sources, knowledge_documents, knowledge_chunks, session_index, customer_memories, sms_sessions, sms_messages, sms_opt_outs, inbox_events, trace_exports, conversation_feedback, conversation_tags, managed_scenarios, conversation_reviews, rollouts, rollout_assignments, session_routes, attachments, voice_calls, verification_codes, crawl_schedules, rate_counters, usage_ledger, job_leases, alert_state, alert_events, crawl_jobs, model_qualifications, groups, scim_users, release_requests, channel_bindings, workspace_tasks, template_installs, usage_dims, tenant_settings, org_policies, org_templates restart identity cascade"))
            await c.execute(text("alter table audit_log enable trigger user"))
        await eng.dispose()

    asyncio.run(clean())
    return create_engine(db_url, poolclass=NullPool)  # NullPool: no connections outlive a test's event loop


@pytest.fixture
def app_engine(engine, db_url):
    """An engine that connects as an ordinary database role (not the owner, not a superuser), the way a tenant-aware deployment must run the
    server: row-level security applies to it. Skips if the test database user cannot create roles."""
    from urllib.parse import urlsplit, urlunsplit

    from sqlalchemy import text
    from sqlalchemy.pool import NullPool

    from northcx.db import create_engine

    async def prepare() -> bool:
        eng = create_engine(db_url, poolclass=NullPool)
        try:
            async with eng.begin() as c:
                await c.execute(text("do $$ begin if not exists (select 1 from pg_roles where rolname = 'northcx_app_test') then "
                                     "create role northcx_app_test login password 'app-test-pw' nosuperuser nobypassrls; end if; end $$"))
                await c.execute(text("grant all on all tables in schema public to northcx_app_test"))
                await c.execute(text("grant all on all sequences in schema public to northcx_app_test"))
            return True
        except Exception:
            return False
        finally:
            await eng.dispose()

    if not asyncio.run(prepare()):
        pytest.skip("the test database user cannot create roles")
    u = urlsplit(db_url)
    host = u.netloc.rsplit("@", 1)[-1]
    return create_engine(urlunsplit((u.scheme, f"northcx_app_test:app-test-pw@{host}", u.path, "", "")), poolclass=NullPool)
