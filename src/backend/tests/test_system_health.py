"""WP 6.4 (O6): the operator's health page."""
import asyncio
import os

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.alerts import AlertManager, WebhookAlerts
from northcx.db import PgApprovalStore, PgMemoryStore, PgTraceStore, create_engine
from northcx.db.engine import migrate
from northcx.llm import ScriptedLLM
from northcx.monitor import InMemoryMonitor
from northcx.ops.backup import newest_revision
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}
BASE = os.environ.get("NORTHCX_TEST_DATABASE_URL", "postgresql+asyncpg://northcx:northcx@localhost:5432/northcx_test")


def health(app, headers=H):
    return TestClient(app).get("/v1/system/health", headers=headers)


def by_name(resp):
    return {c["name"]: c for c in resp.json()["checks"]}


class Insights:
    pass


def memory_app(**kw):
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    return create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), **kw), rt


def test_a_server_with_no_database_says_so_and_what_to_set():
    app, _ = memory_app()
    r = health(app)
    assert r.status_code == 200 and r.json()["status"] == "ok"                      # not set up is not failing
    c = by_name(r)
    assert c["Database"]["status"] == "not_set_up" and "NORTHCX_DATABASE_URL" in c["Database"]["action"]
    assert c["Database schema"]["status"] == "not_set_up" and c["Models"]["status"] == "not_set_up"
    assert {n for n in c if n.startswith("Channel:")} == {f"Channel: {x}" for x in ("Email", "SMS", "WhatsApp", "Telegram", "Voice")}
    assert all(set(x) == {"name", "status", "detail", "action"} for x in c.values())
    assert c["Alert delivery"]["status"] == "not_set_up"


def test_a_database_that_does_not_answer_is_failing_and_the_page_says_what_to_check():
    app, rt = memory_app()

    async def broken(_):
        raise ConnectionError("password authentication failed for user northcx-secret-user")
    rt.store.load_messages = broken
    r = health(app)
    assert r.json()["status"] == "failing"
    db = by_name(r)["Database"]
    assert db["status"] == "failing" and "Postgres is running" in db["action"]
    assert "secret-user" not in r.text and "password" not in r.text.lower().replace("password authentication", "")      # the driver's message (which can name a user or host) is not repeated


@pytest.mark.parametrize("webhook,failed,status", [(False, 0, "not_set_up"), (True, 0, "ok"), (True, 2, "failing")])
def test_alert_delivery_is_not_set_up_ok_or_failing(webhook, failed, status):
    mgr = AlertManager(Insights(), InMemoryMonitor(), [], WebhookAlerts("https://alerts.example/hook", "s" * 20) if webhook else None)
    mgr.events = [{"event": "alert.fired", "delivery": {"status": "failed"}} for _ in range(failed)]
    app, _ = memory_app(alerts=mgr)
    c = by_name(health(app))["Alert delivery"]
    assert c["status"] == status and (status == "ok" or c["action"])


def test_only_an_operator_may_see_it_and_nothing_secret_is_in_it():
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    control = AccessControl(bootstrap_key=KEY)
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=control)
    viewer = {"authorization": "Bearer " + asyncio.new_event_loop().run_until_complete(control.issue("v", "viewer", "t"))[1]}
    assert TestClient(app).get("/v1/system/health").status_code == 401
    assert health(app, viewer).status_code == 403
    assert KEY not in health(app).text


def url_for(name):
    return BASE.rsplit("/", 1)[0] + "/" + name


async def admin(sql):
    conn = await asyncpg.connect(url_for("postgres").replace("+asyncpg", ""))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture()
def drill_db(db_url):
    asyncio.run(admin("drop database if exists northcx_health_drill with (force)"))
    asyncio.run(admin("create database northcx_health_drill"))
    yield url_for("northcx_health_drill")
    asyncio.run(admin("drop database if exists northcx_health_drill with (force)"))


def pg_app(url):
    eng = create_engine(url, poolclass=NullPool)
    rt = Runtime(ScriptedLLM([]), PgMemoryStore(eng), PgTraceStore(eng), PgApprovalStore(eng))
    return create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY))


def test_on_postgres_the_schema_is_ok_at_the_newest_revision_and_failing_when_behind(drill_db):
    migrate(drill_db)
    c = by_name(health(pg_app(drill_db)))
    assert c["Database"]["status"] == "ok" and c["Database schema"]["status"] == "ok" and newest_revision() in c["Database schema"]["detail"]
    asyncio.run(admin("drop database northcx_health_drill with (force)"))
    asyncio.run(admin("create database northcx_health_drill"))
    migrate(drill_db, "0057")
    r = health(pg_app(drill_db))
    c = by_name(r)
    assert r.json()["status"] == "failing" and c["Database schema"]["status"] == "failing"
    assert "0057" in c["Database schema"]["detail"] and newest_revision() in c["Database schema"]["detail"] and "Restart the server" in c["Database schema"]["action"]
