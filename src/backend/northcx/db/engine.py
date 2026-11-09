from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

MIGRATIONS = Path(__file__).with_name("migrations")


def database_url_from_env(url: str | None = None) -> str | None:
    """`NORTHCX_DATABASE_URL` (or the value given, for example read from a secret file), accepting plain `postgresql://`
    and `postgres://` forms."""
    url = url or os.environ.get("NORTHCX_DATABASE_URL")
    if not url:
        return None
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def create_engine(url: str, **kwargs) -> AsyncEngine:
    kwargs.setdefault("pool_pre_ping", True)  # a connection that went away (database restarted) is replaced instead of failing a request
    # Everything the application does ends its own transaction before a connection goes back to the pool, so the pool's extra rollback on return is
    # pure overhead (with asyncpg it costs a BEGIN and a ROLLBACK round trip for every one of the dozens of checkouts a conversation turn makes).
    if "poolclass" not in kwargs:  # (tests and one-off tools pass their own pool)
        kwargs.setdefault("pool_reset_on_return", None)
        kwargs.setdefault("pool_size", int(os.environ.get("NORTHCX_DB_POOL_SIZE") or 20))
        kwargs.setdefault("max_overflow", 10)
    from northcx.db.tenant_sql import install_session_hooks
    install_session_hooks()  # once per process: every session says which tenant it is for
    return create_async_engine(url, **kwargs)


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def migrate(url: str, revision: str = "head") -> None:
    """Apply migrations. Call from synchronous code (before the event loop starts)."""
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    if revision == "base":  # the meaning-search table is created on demand (not by a migration), so a full teardown must remove it first
        import asyncio
        from sqlalchemy import text

        async def drop() -> None:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy.pool import NullPool
            eng = create_async_engine(url if "+asyncpg" in url else url.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool)
            async with eng.begin() as c:
                await c.execute(text("drop table if exists knowledge_embeddings"))
            await eng.dispose()
        try:
            asyncio.run(drop())
        except Exception:
            pass
    command.downgrade(alembic_config(url), revision)
