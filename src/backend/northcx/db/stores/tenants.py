"""Postgres store for tenants and channel bindings."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import ChannelBindingRow, TenantRow
from northcx.db.stores._base import _Base
from northcx.tenancy import Binding, Tenant


class PgTenants(_Base):
    async def list(self) -> list[Tenant]:
        async with self._ro() as s:
            rows = (await s.execute(select(TenantRow).order_by(TenantRow.created_at, TenantRow.id))).scalars().all()
        return [Tenant(r.id, r.name, r.status, r.created_at) for r in rows]

    async def get(self, tenant_id: str) -> Tenant | None:
        async with self._ro() as s:
            r = (await s.execute(select(TenantRow).where(TenantRow.id == tenant_id))).scalar_one_or_none()
        return Tenant(r.id, r.name, r.status, r.created_at) if r else None

    async def save(self, t: Tenant) -> None:
        stmt = pg_insert(TenantRow).values(id=t.id, name=t.name, status=t.status, created_at=t.created_at)
        stmt = stmt.on_conflict_do_update(index_elements=[TenantRow.id], set_={"name": t.name, "status": t.status})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def bind(self, b: Binding) -> bool:
        stmt = pg_insert(ChannelBindingRow).values(kind=b.kind, address=b.address, tenant_id=b.tenant_id, created_at=b.created_at).on_conflict_do_nothing()
        async with self._sm.begin() as s:
            return (await s.execute(stmt)).rowcount == 1

    async def unbind(self, kind: str, address: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(ChannelBindingRow).where(ChannelBindingRow.kind == kind, ChannelBindingRow.address == address))).rowcount > 0

    async def resolve(self, kind: str, address: str) -> str | None:
        async with self._ro() as s:
            return (await s.execute(select(ChannelBindingRow.tenant_id).where(ChannelBindingRow.kind == kind, ChannelBindingRow.address == address))).scalar_one_or_none()

    async def any_bindings(self) -> bool:
        async with self._ro() as s:
            return (await s.execute(select(ChannelBindingRow.kind).limit(1))).first() is not None

    async def bindings(self, tenant_id: str) -> list[Binding]:
        async with self._ro() as s:
            rows = (await s.execute(select(ChannelBindingRow).where(ChannelBindingRow.tenant_id == tenant_id))).scalars().all()
        return [Binding(r.kind, r.address, r.tenant_id, r.created_at) for r in rows]
