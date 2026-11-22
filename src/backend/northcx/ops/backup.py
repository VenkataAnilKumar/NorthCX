"""Backup and restore of the whole NorthCX database as one file.

Everything the product stores (conversations, approvals, versions, keys, outputs, files, sealed secrets) is in the one Postgres database, so one file is a
complete backup. The file is a tar archive of a manifest and one binary dump per table, read in one consistent snapshot. It needs only what the server
already has (the database driver); no Postgres client tools. Restore builds the schema at the backup's revision, loads the tables in foreign-key order,
fixes the counters and then upgrades to the current revision.

The meaning-search index (`knowledge_embeddings`) is derived from the knowledge chunks and is made on demand, so it is not saved; the manifest says so.
The backup holds personal data and is not encrypted: keep it where the database's own protections apply.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

import asyncpg

from northcx.db.engine import database_url_from_env, downgrade, migrate

FORMAT = 1
EXCLUDED = ("knowledge_embeddings",)
CHUNK = 1 << 20


class OpsError(Exception):
    """A problem the operator can fix; the message says how."""


def plain_url(url: str) -> str:
    """The URL in the plain form the driver takes (the server's own settings may name the async dialect)."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1).replace("postgres://", "postgresql://", 1)


def newest_revision() -> str:
    from alembic.script import ScriptDirectory

    from northcx.db.engine import alembic_config
    return ScriptDirectory.from_config(alembic_config("postgresql://x")).get_current_head() or ""


def revision_order() -> list[str]:
    """Every revision, oldest first."""
    from alembic.script import ScriptDirectory

    from northcx.db.engine import alembic_config
    return [s.revision for s in reversed(list(ScriptDirectory.from_config(alembic_config("postgresql://x")).walk_revisions()))]


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def _tables(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch("select tablename from pg_tables where schemaname = 'public' order by tablename")
    return [r["tablename"] for r in rows if r["tablename"] not in EXCLUDED and r["tablename"] != "alembic_version"]        # the revision is in the manifest and is set by the migration


async def _order(conn: asyncpg.Connection, tables: list[str]) -> list[str]:
    """Tables so that every table comes after the ones its foreign keys point to. A cycle is an error: restore cannot load it safely."""
    deps = {t: set() for t in tables}
    for r in await conn.fetch("select c.conrelid::regclass::text as child, c.confrelid::regclass::text as parent from pg_constraint c where c.contype = 'f' and c.connamespace = 'public'::regnamespace"):
        child, parent = r["child"].strip('"'), r["parent"].strip('"')
        if child in deps and parent in deps and child != parent:
            deps[child].add(parent)
    out: list[str] = []
    while deps:
        ready = sorted(t for t, d in deps.items() if not d)
        if not ready:
            raise OpsError(f"Tables point at each other ({', '.join(sorted(deps))}); this backup tool cannot order them. Report it.")
        out += ready
        for t in ready:
            del deps[t]
        for d in deps.values():
            d.difference_update(ready)
    return out


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


async def _backup(url: str, out: Path) -> dict[str, Any]:
    conn = await asyncpg.connect(plain_url(url))
    try:
        has = await conn.fetchval("select to_regclass('public.alembic_version') is not null")
        revision = await conn.fetchval("select version_num from alembic_version") if has else None
        if revision is None:
            raise OpsError("This database has no NorthCX schema (no migration has run), so there is nothing to back up.")
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            tables: dict[str, dict[str, Any]] = {}
            async with conn.transaction(isolation="repeatable_read", readonly=True):            # one snapshot: every table is from the same moment
                names = await _tables(conn)
                for name in names:
                    path = tmpdir / f"{name}.bin"
                    await conn.copy_from_query(f"select * from {_q(name)}", output=str(path), format="binary")
                    rows = await conn.fetchval(f"select count(*) from {_q(name)}")
                    tables[name] = {"rows": rows, "sha256": _sha(path), "bytes": path.stat().st_size}
            manifest = {"format": FORMAT, "createdAt": time.time(), "revision": revision, "newestRevision": newest_revision(), "tables": tables, "excluded": list(EXCLUDED)}
            (tmpdir / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
            out.parent.mkdir(parents=True, exist_ok=True)
            partial = out.with_name(out.name + ".partial")
            with tarfile.open(partial, "w") as tar:
                tar.add(tmpdir / "manifest.json", arcname="manifest.json")
                for name in tables:
                    tar.add(tmpdir / f"{name}.bin", arcname=f"tables/{name}.bin")
            partial.replace(out)                                                                 # a half-written file never has the final name
            return manifest
    finally:
        await conn.close()


def backup(url: str, out: str | Path) -> dict[str, Any]:
    """Write the whole database to `out`. Returns the manifest."""
    path = Path(out)
    if path.exists():
        raise OpsError(f"{path} already exists. Choose another name; a backup is never overwritten.")
    try:
        return asyncio.run(_backup(url, path))
    except (OSError, asyncpg.PostgresError) as e:
        raise OpsError(f"The database could not be used: {str(e).splitlines()[0] if str(e) else type(e).__name__}. Check NORTHCX_DATABASE_URL.") from e


def read_manifest(path: str | Path) -> dict[str, Any]:
    try:
        with tarfile.open(path) as tar:
            member = tar.extractfile("manifest.json")
            if member is None:
                raise OpsError("This file is not a NorthCX backup (no manifest).")
            manifest = json.loads(member.read())
    except (tarfile.TarError, KeyError, ValueError) as e:
        raise OpsError("This file is not a NorthCX backup, or it is damaged.") from e
    if manifest.get("format") != FORMAT:
        raise OpsError(f"This backup has format {manifest.get('format')}; this version reads format {FORMAT}.")
    return manifest


async def _data_rows(conn: asyncpg.Connection) -> int:
    total = 0
    for name in await _tables(conn):
        # a freshly migrated database already holds the default organization; that is not data
        total += await conn.fetchval("select count(*) from tenants where id <> 'default'" if name == "tenants" else f"select count(*) from {_q(name)}")
    return total


async def _load(url: str, manifest: dict[str, Any], tmpdir: Path) -> None:
    conn = await asyncpg.connect(plain_url(url))
    try:
        order = await _order(conn, [t for t in await _tables(conn) if t in manifest["tables"]])
        missing = sorted(set(manifest["tables"]) - set(order))
        if missing:
            raise OpsError(f"The backup has tables this database does not have: {', '.join(missing)}. The schema is not at the backup's revision.")
        async with conn.transaction():
            # The audit log refuses edits and truncation (a trigger). Restoring it is the one time that is right: the rows come back exactly as they were, hash chain
            # included, and the trigger is switched back on before the transaction ends (so a failure leaves nothing half-restored and the trigger on).
            guarded = "audit_log" in order
            if guarded:
                await conn.execute("alter table audit_log disable trigger user")
            await conn.execute("truncate " + ", ".join(_q(t) for t in order) + " restart identity cascade")      # what the migrations seeded (the default organization) comes from the backup instead
            for name in order:
                await conn.copy_to_table(name, source=str(tmpdir / f"{name}.bin"), format="binary", schema_name="public")
            if guarded:
                await conn.execute("alter table audit_log enable trigger user")
            for r in await conn.fetch("""select c.relname as t, a.attname as col, pg_get_serial_sequence(quote_ident(c.relname), a.attname) as seq
                                         from pg_attribute a join pg_class c on c.oid = a.attrelid
                                         where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' and not a.attisdropped
                                           and (a.attidentity <> '' or pg_get_serial_sequence(quote_ident(c.relname), a.attname) is not null)"""):
                if r["seq"]:
                    await conn.execute(f"select setval($1, coalesce((select max({_q(r['col'])}) from {_q(r['t'])}), 0) + 1, false)", r["seq"])
    finally:
        await conn.close()


async def _target_state(url: str) -> tuple[int, str | None]:
    conn = await asyncpg.connect(plain_url(url))
    try:
        has = await conn.fetchval("select to_regclass('public.alembic_version') is not null")
        if not has:
            return 0, None
        return await _data_rows(conn), await conn.fetchval("select version_num from alembic_version")
    finally:
        await conn.close()


def restore(url: str, source: str | Path, replace: bool = False) -> dict[str, Any]:
    """Load a backup into the database at `url`. The database must have no data unless `replace` is set (which empties it first)."""
    source = Path(source)
    manifest = read_manifest(source)
    order = revision_order()
    if manifest["revision"] not in order:
        raise OpsError(f"This backup is from a newer version of NorthCX (schema revision {manifest['revision']}). Upgrade NorthCX first, then restore.")
    try:
        rows, current = asyncio.run(_target_state(url))
    except (OSError, asyncpg.PostgresError) as e:
        raise OpsError(f"The database could not be used: {str(e).splitlines()[0] if str(e) else type(e).__name__}. Check NORTHCX_DATABASE_URL.") from e
    if rows and not replace:
        raise OpsError(f"The target database already holds data ({rows} rows). Restore into an empty database, or add --replace to empty it first.")
    migration_url = database_url_from_env(url) or url
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        with tarfile.open(source) as tar:
            for name, info in manifest["tables"].items():
                member = tar.getmember(f"tables/{name}.bin")
                member.name = f"{name}.bin"
                tar.extract(member, tmpdir, filter="data")
                if _sha(tmpdir / f"{name}.bin") != info["sha256"]:
                    raise OpsError(f"The backup is damaged: the data for '{name}' does not match its checksum. Nothing was restored.")
        if current is not None:
            downgrade(migration_url)                                                             # an empty schema, or --replace: start from nothing
        migrate(migration_url, manifest["revision"])
        asyncio.run(_load(url, manifest, tmpdir))
    migrate(migration_url)                                                                                # then up to what this version of NorthCX expects
    return manifest
