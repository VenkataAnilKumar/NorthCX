"""WP 6.2 (O3): a database made by an earlier version, and holding data, upgrades to the current one without losing a row.

The previous release's exact schema revision cannot be read from this checkout (the tag is not here), so this proves upgrades from several earlier revisions;
add the release's revision to REVISIONS when it is known."""
import asyncio
import os

import asyncpg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.pool import NullPool

from examples.support_agent import support_agent
from northcx.db import PgApprovalStore, PgMemoryStore, PgTraceStore, create_engine
from northcx.db.engine import migrate
from northcx.db.models import Base
from northcx.llm import ScriptedLLM, text as llm_text
from northcx.ops.backup import newest_revision, revision_order
from northcx.runtime import Runtime

BASE = os.environ.get("NORTHCX_TEST_DATABASE_URL", "postgresql+asyncpg://northcx:northcx@localhost:5432/northcx_test")
NAME = "northcx_upgrade_drill"
REVISIONS = ["0001", "0010", "0020", "0030", "0041", "0050", "0057"]
VALUE = {"text": "'x'", "character varying": "'x'", "character": "'x'", "integer": "1", "bigint": "1", "smallint": "1", "boolean": "false", "double precision": "0",
         "real": "0", "numeric": "0", "jsonb": "'{}'::jsonb", "json": "'{}'::json", "timestamp with time zone": "now()", "timestamp without time zone": "now()", "date": "current_date",
         "bytea": "'\\x00'::bytea", "uuid": "gen_random_uuid()", "ARRAY": "'{}'"}


def url(name: str) -> str:
    return BASE.rsplit("/", 1)[0] + "/" + name


async def sql(db: str, text: str) -> None:
    conn = await asyncpg.connect(url(db).replace("+asyncpg", ""))
    try:
        await conn.execute(text)
    finally:
        await conn.close()


async def fill(db: str) -> dict[str, int]:
    """One row in every table the schema has right now, made from the column types alone (constraints between tables are switched off while it is made)."""
    conn = await asyncpg.connect(url(db).replace("+asyncpg", ""))
    filled: dict[str, int] = {}
    try:
        await conn.execute("set session_replication_role = replica")
        for t in [r["tablename"] for r in await conn.fetch("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version' order by 1")]:
            cols = await conn.fetch("select column_name, data_type, is_nullable, column_default, is_identity, is_generated from information_schema.columns where table_schema='public' and table_name=$1 order by ordinal_position", t)
            if await conn.fetchval(f'select count(*) from "{t}"'):
                filled[t] = await conn.fetchval(f'select count(*) from "{t}"')            # seeded by the migrations (the default organization)
                continue
            names, values = [], []
            for c in cols:
                if c["is_generated"] == "ALWAYS" or c["is_identity"] == "YES" or c["column_default"] is not None or c["is_nullable"] == "YES":
                    continue
                if c["data_type"] not in VALUE:
                    raise AssertionError(f"table {t}: no sample value for a column of type {c['data_type']} ({c['column_name']}); add one to VALUE")
                names.append(f'"{c["column_name"]}"')
                values.append(VALUE[c["data_type"]])
            await conn.execute(f'insert into "{t}" ({", ".join(names)}) values ({", ".join(values)})' if names else f'insert into "{t}" default values')
            filled[t] = 1
    finally:
        await conn.close()
    return filled


async def counts(db: str) -> dict[str, int]:
    conn = await asyncpg.connect(url(db).replace("+asyncpg", ""))
    try:
        return {r["tablename"]: await conn.fetchval(f'select count(*) from "{r["tablename"]}"') for r in await conn.fetch("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'")}
    finally:
        await conn.close()


async def drift(db: str) -> list:
    eng = create_engine(url(db), poolclass=NullPool)
    try:
        async with eng.connect() as c:
            return await c.run_sync(lambda conn: compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata))
    finally:
        await eng.dispose()


@pytest.fixture()
def fresh(db_url):
    asyncio.run(sql("postgres", f"drop database if exists {NAME} with (force)"))
    asyncio.run(sql("postgres", f"create database {NAME}"))
    yield url(NAME)
    asyncio.run(sql("postgres", f"drop database if exists {NAME} with (force)"))


def test_the_listed_revisions_exist_and_the_newest_is_not_one_of_them():
    order = revision_order()
    assert all(r in order for r in REVISIONS) and newest_revision() not in REVISIONS


@pytest.mark.parametrize("revision", REVISIONS)
def test_a_database_from_an_earlier_revision_upgrades_with_every_row_kept_and_the_schema_matching_the_code(fresh, revision):
    migrate(fresh, revision)
    before = asyncio.run(fill(NAME))
    assert len(before) >= 2
    migrate(fresh)
    after = asyncio.run(counts(NAME))
    lost = {t: (n, after.get(t)) for t, n in before.items() if after.get(t) is None or after[t] < n}
    assert not lost, f"rows lost or tables gone after upgrading from {revision}: {lost}"
    assert asyncio.run(drift(NAME)) == []                                    # the upgraded schema is the one the code expects, not just a schema that has the tables


def test_an_upgraded_old_database_still_takes_conversations_through_the_current_stores(fresh):
    migrate(fresh, REVISIONS[0])
    asyncio.run(fill(NAME))
    migrate(fresh)

    async def turn():
        eng = create_engine(fresh, poolclass=NullPool)
        try:
            rt = Runtime(ScriptedLLM([llm_text("Hello!")]), PgMemoryStore(eng), PgTraceStore(eng), PgApprovalStore(eng))
            return await rt.run(support_agent(), "after-upgrade", "hello", "cust")
        finally:
            await eng.dispose()
    assert asyncio.run(turn()).status == "completed"
