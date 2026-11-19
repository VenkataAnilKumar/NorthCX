"""Postgres store for MCP connections. Rows are tenant-scoped like every other table."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import McpConnectionRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.mcp_connections import McpConnection

_FIELDS = ("name", "url", "trusted", "secret", "enabled", "created_by", "created_at", "updated_by", "updated_at")


def _from(r: McpConnectionRow) -> McpConnection:
    return McpConnection(id=r.id, approved=list(r.approved), **{k: getattr(r, k) for k in _FIELDS})


class PgMcpConnections(_Base):
    async def save(self, c: McpConnection) -> None:
        vals = {k: getattr(c, k) for k in _FIELDS} | {"approved": _jsonable(c.approved)}
        stmt = pg_insert(McpConnectionRow).values(id=c.id, **vals)
        stmt = stmt.on_conflict_do_update(index_elements=[McpConnectionRow.tenant_id, McpConnectionRow.id], set_=vals)
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def get(self, connection_id: str) -> McpConnection | None:
        async with self._ro() as s:
            r = (await s.execute(select(McpConnectionRow).where(McpConnectionRow.id == connection_id))).scalar_one_or_none()
        return _from(r) if r else None

    async def get_by_name(self, name: str) -> McpConnection | None:
        async with self._ro() as s:
            r = (await s.execute(select(McpConnectionRow).where(McpConnectionRow.name == name))).scalar_one_or_none()
        return _from(r) if r else None

    async def list(self) -> list[McpConnection]:
        async with self._ro() as s:
            rows = (await s.execute(select(McpConnectionRow).order_by(McpConnectionRow.name))).scalars().all()
        return [_from(r) for r in rows]

    async def delete(self, connection_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(McpConnectionRow).where(McpConnectionRow.id == connection_id))).rowcount > 0
