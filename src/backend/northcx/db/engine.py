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
    kwargs.setdefault("pool_pre_ping", True)
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
    command.downgrade(alembic_config(url), revision)
