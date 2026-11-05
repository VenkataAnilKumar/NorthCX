"""Shared pieces of the Postgres stores."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _jsonable(value: Any) -> Any:
    """Make arbitrary tool output safe for a JSONB column."""
    return json.loads(json.dumps(value, default=str))


class _Base:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sm = async_sessionmaker(engine, expire_on_commit=False)
        # Reads need no transaction: autocommit saves a BEGIN and a ROLLBACK round trip on every one of the dozens of lookups a conversation turn makes.
        self._ro = async_sessionmaker(engine.execution_options(isolation_level="AUTOCOMMIT"), expire_on_commit=False)
