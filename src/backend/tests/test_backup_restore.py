"""WP 6.3 (O4, O5): back up the whole database to one file and restore it, with a drill that compares every table."""
import asyncio
import os
import subprocess
import sys
import tarfile
import json
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.pool import NullPool

from examples.support_agent import support_agent
from northcx.db import PgApprovalStore, PgMemoryStore, PgTraceStore, create_engine
from northcx.db.engine import migrate
from northcx.llm import ScriptedLLM, text as llm_text, tool_call
from northcx.ops.backup import OpsError, backup, newest_revision, read_manifest, restore
from northcx.runtime import Runtime

BASE = os.environ.get("NORTHCX_TEST_DATABASE_URL", "postgresql+asyncpg://northcx:northcx@localhost:5432/northcx_test")


def url_for(name: str) -> str:
    return BASE.rsplit("/", 1)[0] + "/" + name


async def admin(sql: str) -> None:
    conn = await asyncpg.connect(url_for("postgres").replace("+asyncpg", ""))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture()
def drill(db_url):
    """Two empty databases of their own, so the shared test database is never touched."""
    names = ["northcx_drill_src", "northcx_drill_dst"]
    for n in names:
        asyncio.run(admin(f'drop database if exists {n} with (force)'))
        asyncio.run(admin(f"create database {n}"))
    yield [url_for(n) for n in names]
    for n in names:
        asyncio.run(admin(f'drop database if exists {n} with (force)'))


async def conversation(url: str, session: str, script: list, message: str) -> object:
    eng = create_engine(url, poolclass=NullPool)
    try:
        rt = Runtime(ScriptedLLM(script), PgMemoryStore(eng), PgTraceStore(eng), PgApprovalStore(eng))
        return await rt.run(support_agent(), session, message, "cust-1")
    finally:
        await eng.dispose()


async def counts(url: str) -> dict[str, int]:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        names = [r["tablename"] for r in await conn.fetch("select tablename from pg_tables where schemaname='public' and tablename <> 'knowledge_embeddings' order by 1")]
        return {n: await conn.fetchval(f'select count(*) from "{n}"') for n in names}
    finally:
        await conn.close()


async def audit_chain(url: str) -> tuple[bool, int]:
    from northcx.audit import AuditEntry
    from northcx.db.stores.access import PgAudit
    eng = create_engine(url, poolclass=NullPool)
    try:
        repo = PgAudit(eng)
        await repo.append(AuditEntry(actor="drill", role="admin", action="drill.check"))
        v = await repo.verify()
        return v.ok, v.checked
    finally:
        await eng.dispose()


def seed(src: str) -> None:
    migrate(src)
    asyncio.run(conversation(src, "s1", [tool_call("lookup_order", {"order_id": "1042"}, "t1"), llm_text("Delivered.")], "where is order 1042?"))
    asyncio.run(conversation(src, "s2", [tool_call("issue_refund", {"order_id": "2077", "amount": 240}, "t2")], "refund 240 for order 2077"))
    for _ in range(3):
        asyncio.run(audit_chain(src))


def test_the_restore_drill_every_table_comes_back_with_the_same_rows_and_the_conversation_reads_and_continues(drill, tmp_path):
    src, dst = drill
    seed(src)
    out = tmp_path / "northcx.backup"
    manifest = backup(src, out)
    assert manifest["revision"] == newest_revision() and manifest["excluded"] == ["knowledge_embeddings"] and sum(t["rows"] for t in manifest["tables"].values()) > 10
    restored = restore(dst, out)
    assert restored["revision"] == manifest["revision"]
    before, after = asyncio.run(counts(src)), asyncio.run(counts(dst))
    assert before == after and before["messages"] >= 4 and before["approvals"] == 1
    assert asyncio.run(audit_chain(dst)) == (True, 4)                      # the 3 restored entries and one new one: the tamper-evident chain still verifies
    # the conversation reads back, and new work can be added (the counters were reset past the restored rows)
    follow = asyncio.run(conversation(dst, "s1", [llm_text("Anything else?")], "thanks"))
    assert follow.status == "completed"
    eng = create_engine(dst, poolclass=NullPool)

    async def pending():
        try:
            return await PgApprovalStore(eng).list("pending")
        finally:
            await eng.dispose()
    assert [a.input["amount"] for a in asyncio.run(pending())] == [240]


def test_a_backup_is_a_snapshot_with_a_checksum_per_table_and_is_never_overwritten(drill, tmp_path):
    src, _ = drill
    seed(src)
    out = tmp_path / "a.backup"
    backup(src, out)
    m = read_manifest(out)
    assert m["format"] == 1 and all(len(t["sha256"]) == 64 for t in m["tables"].values())
    with tarfile.open(out) as tar:
        assert {"manifest.json", "tables/messages.bin"} <= set(tar.getnames())
    with pytest.raises(OpsError, match="already exists"):
        backup(src, out)
    assert not list(tmp_path.glob("*.partial"))


def test_a_database_with_no_schema_cannot_be_backed_up(drill, tmp_path):
    with pytest.raises(OpsError, match="no NorthCX schema|Could not connect"):
        backup(drill[0], tmp_path / "x.backup")


def test_restore_refuses_a_database_that_holds_data_unless_told_to_replace_it(drill, tmp_path):
    src, dst = drill
    seed(src)
    seed(dst)
    out = tmp_path / "a.backup"
    backup(src, out)
    with pytest.raises(OpsError, match="already holds data .* --replace"):
        restore(dst, out)
    asyncio.run(conversation(dst, "extra", [llm_text("hi")], "an extra conversation"))
    restore(dst, out, replace=True)
    assert asyncio.run(counts(src)) == asyncio.run(counts(dst))


def _rewrite(path: Path, out: Path, change) -> None:
    with tarfile.open(path) as tar, tarfile.open(out, "w") as new:
        for m in tar.getmembers():
            data = tar.extractfile(m).read()
            data = change(m.name, data)
            m.size = len(data)
            import io
            new.addfile(m, io.BytesIO(data))


def test_restore_refuses_a_damaged_file_a_foreign_file_and_a_backup_from_a_newer_version(drill, tmp_path):
    src, dst = drill
    seed(src)
    good = tmp_path / "good.backup"
    backup(src, good)
    damaged = tmp_path / "damaged.backup"
    _rewrite(good, damaged, lambda n, d: d[:-1] + bytes([d[-1] ^ 1]) if n == "tables/messages.bin" else d)
    with pytest.raises(OpsError, match="damaged: the data for 'messages'"):
        restore(dst, damaged)
    assert asyncio.run(counts(dst)) == {} or sum(asyncio.run(counts(dst)).values()) == 0          # nothing was loaded
    foreign = tmp_path / "foreign.backup"
    foreign.write_bytes(b"not a backup")
    with pytest.raises(OpsError, match="not a NorthCX backup"):
        restore(dst, foreign)
    newer = tmp_path / "newer.backup"
    _rewrite(good, newer, lambda n, d: json.dumps({**json.loads(d), "revision": "9999_from_the_future"}).encode() if n == "manifest.json" else d)
    with pytest.raises(OpsError, match="newer version of NorthCX"):
        restore(dst, newer)


def test_the_command_line_backs_up_and_restores_and_never_prints_the_password(drill, tmp_path):
    src, dst = drill
    seed(src)
    env = {**os.environ, "NORTHCX_DATABASE_URL": src.replace("+asyncpg", "")}
    out = tmp_path / "cli.backup"
    run = subprocess.run([sys.executable, "-m", "northcx", "backup", "--out", str(out)], env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and "Backed up" in run.stdout and "personal data" in run.stdout
    env["NORTHCX_DATABASE_URL"] = dst.replace("+asyncpg", "")
    run = subprocess.run([sys.executable, "-m", "northcx", "restore", str(out)], env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and "Restored" in run.stdout and "knowledge_embeddings" in run.stdout
    assert "northcx:northcx@" not in run.stdout + run.stderr
    assert asyncio.run(counts(src)) == asyncio.run(counts(dst))
    bad = subprocess.run([sys.executable, "-m", "northcx", "restore", str(tmp_path / "missing.backup")], env=env, capture_output=True, text=True, timeout=60)
    assert bad.returncode != 0 and "Error:" in bad.stderr
