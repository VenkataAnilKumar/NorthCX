"""Postgres-specific behaviour: migrations, persistence across restarts, and the server on Postgres."""
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import text

from examples.support_agent import support_agent
from sqlalchemy.pool import NullPool

from northcx.db import PgApprovalStore, PgHandoffs, PgMemoryStore, PgOutbox, PgTraceStore, create_engine
from northcx.outbox import Outbox
from northcx.db.engine import downgrade, migrate
from northcx.db.models import Base
from northcx.llm import ScriptedLLM, text as llm_text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app


def test_migrations_apply_roll_back_and_reapply_cleanly(db_url):
    import asyncio

    async def tables():
        eng = create_engine(db_url, poolclass=NullPool)
        async with eng.connect() as c:
            rows = (await c.execute(text("select tablename from pg_tables where schemaname='public'"))).all()
        await eng.dispose()
        return {r[0] for r in rows}

    downgrade(db_url)
    assert asyncio.run(tables()) <= {"alembic_version"}
    migrate(db_url)
    migrate(db_url)  # idempotent
    assert {"sessions", "messages", "customer_facts", "traces", "trace_events", "approvals", "outbox", "handoffs", "simulation_runs", "agent_versions", "releases", "api_keys", "audit_log", "email_sessions", "email_messages", "monitor_findings", "idempotency_keys", "knowledge_sources", "knowledge_documents", "knowledge_chunks", "session_index", "customer_memories", "sms_sessions", "sms_messages", "sms_opt_outs", "inbox_events", "trace_exports", "conversation_feedback", "conversation_tags", "managed_scenarios"} <= asyncio.run(tables())


async def test_migration_matches_the_models(engine):
    def diff(conn):
        return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)

    async with engine.connect() as c:
        assert await c.run_sync(diff) == []


def stores(engine):
    return PgMemoryStore(engine), PgTraceStore(engine), PgApprovalStore(engine)


async def test_conversation_and_approvals_survive_a_restart(db_url, engine):
    mem, traces, approvals = stores(engine)
    rt = Runtime(ScriptedLLM([tool_call("lookup_order", {"order_id": "1042"}, "t1"), llm_text("Delivered."),
                              tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t2")]), mem, traces, approvals)
    first = await rt.run(support_agent(), "sess", "where is order 1042?", "cust")
    held = await rt.run(support_agent(), "sess", "refund 240 for order 2077", "cust")
    assert (first.status, held.status) == ("completed", "needs_approval")

    # "Restart": brand-new engine, stores and runtime over the same database.
    engine2 = create_engine(db_url, poolclass=NullPool)
    try:
        mem2, traces2, approvals2 = stores(engine2)
        llm2 = ScriptedLLM([llm_text("Anything else?")])
        rt2 = Runtime(llm2, mem2, traces2, approvals2)
        again = await rt2.run(support_agent(), "sess", "thanks", "cust")
        assert again.status == "completed"
        sent = str(llm2.requests[0].messages)
        assert "where is order 1042?" in sent and "refund 240" in sent  # earlier turns were remembered
        pending = await approvals2.list("pending")
        assert len(pending) == 1 and pending[0].input["amount"] == 240
        assert (await traces2.get(first.trace_id)).tools_called() == ["lookup_order"]
        assert {s.id for s in await traces2.summaries("sess")} >= {first.trace_id, held.trace_id}
    finally:
        await engine2.dispose()


def test_server_runs_on_postgres(db_url):
    import asyncio

    async def prepare():
        eng = create_engine(db_url, poolclass=NullPool)
        async with eng.begin() as c:
            await c.execute(text("alter table audit_log disable trigger user"))
            await c.execute(text("truncate sessions, messages, customer_facts, traces, trace_events, approvals, outbox, handoffs, simulation_runs, releases, agent_versions, api_keys, audit_log, email_sessions, email_messages, monitor_findings, idempotency_keys, knowledge_sources, knowledge_documents, knowledge_chunks, session_index, customer_memories, sms_sessions, sms_messages, sms_opt_outs, inbox_events, trace_exports, conversation_feedback, conversation_tags, managed_scenarios restart identity cascade"))
            await c.execute(text("alter table audit_log enable trigger user"))
        await eng.dispose()

    asyncio.run(prepare())
    eng = create_engine(db_url, poolclass=NullPool)
    mem, traces, approvals = stores(eng)
    rt = Runtime(ScriptedLLM([tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t1"), llm_text("Refund sent.")]),
                 mem, traces, approvals, Outbox(PgOutbox(eng)))
    with TestClient(create_app(rt, traces, {"support": support_agent()})) as c:
        r = c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "refund"}).json()
        assert r["status"] == "needs_approval"
        assert c.get(f"/v1/traces/{r['traceId']}").json()["events"][0]["type"] == "user"
        listed = c.get("/v1/traces?sessionId=s").json()["traces"]
        assert listed[0]["status"] == "needs_approval" and listed[0]["tools"] == ["issue_refund"]
        aid = c.get("/v1/approvals?state=pending").json()["approvals"][0]["id"]
        done = c.post(f"/v1/approvals/{aid}/decision", json={"approved": True, "by": "rae"}).json()
        assert done["state"] == "executed" and done["resume"]["reply"] == "Refund sent."
        assert c.get("/v1/sessions/s/outbox").json()["messages"][0]["reply"] == "Refund sent."
        assert c.post(f"/v1/approvals/{aid}/decision", json={"approved": False, "by": "x"}).status_code == 409
        assert c.get("/v1/approvals?state=pending").json()["approvals"] == []


async def test_handoffs_and_forced_topics_survive_a_restart(db_url, engine):
    mem, traces, approvals = stores(engine)
    rt = Runtime(ScriptedLLM([tool_call("lookup_order", {"order_id": "1042"}, "t1"), llm_text("Delivered.")]),
                 mem, traces, approvals, handoffs=PgHandoffs(engine))
    await rt.run(support_agent(), "sess", "where is order 1042?", "cust")
    r = await rt.run(support_agent(), "sess", "I am going to call my lawyer", "cust")
    assert r.status == "escalated" and r.handoff_id
    engine2 = create_engine(db_url, poolclass=NullPool)
    try:
        h = await PgHandoffs(engine2).get(r.handoff_id)
        assert (h.trigger, h.topics, h.state) == ("forced_topic", ["legal"], "open")
        assert [(a["tool"], a["outcome"]) for a in h.package["actions"]] == [("lookup_order", "succeeded")]
        assert h.package["transcript"][-1]["from"] == "agent"
        assert (await PgHandoffs(engine2).resolve(h.id, "jo")).state == "resolved"
    finally:
        await engine2.dispose()
