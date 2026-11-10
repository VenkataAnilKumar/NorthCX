"""Postgres store for sealed per-tenant secrets. The platform API works across tenants, so each call names the tenant it acts for."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import TenantSecretRow
from northcx.db.stores._base import _Base
from northcx.tenancy import TENANT
from northcx.vault import Stored


class PgSecrets(_Base):
    @staticmethod
    def _as(tenant: str):
        return TENANT.set(tenant)

    async def put(self, tenant: str, s: Stored) -> None:
        token = self._as(tenant)
        try:
            vals = dict(sealed=s.sealed, updated_by=s.updated_by, updated_at=s.updated_at)
            stmt = pg_insert(TenantSecretRow).values(name=s.name, **vals)
            stmt = stmt.on_conflict_do_update(index_elements=[TenantSecretRow.tenant_id, TenantSecretRow.name], set_=vals)
            async with self._sm.begin() as sess:
                await sess.execute(stmt)
        finally:
            TENANT.reset(token)

    async def get(self, tenant: str, name: str) -> Stored | None:
        token = self._as(tenant)
        try:
            async with self._ro() as sess:
                r = (await sess.execute(select(TenantSecretRow).where(TenantSecretRow.name == name))).scalar_one_or_none()
            return Stored(r.name, r.sealed, r.updated_by, r.updated_at) if r else None
        finally:
            TENANT.reset(token)

    async def names(self, tenant: str) -> list[Stored]:
        token = self._as(tenant)
        try:
            async with self._ro() as sess:
                rows = (await sess.execute(select(TenantSecretRow).order_by(TenantSecretRow.name))).scalars().all()
            return [Stored(r.name, r.sealed, r.updated_by, r.updated_at) for r in rows]
        finally:
            TENANT.reset(token)

    async def delete(self, tenant: str, name: str) -> bool:
        token = self._as(tenant)
        try:
            async with self._sm.begin() as sess:
                return (await sess.execute(delete(TenantSecretRow).where(TenantSecretRow.name == name))).rowcount > 0
        finally:
            TENANT.reset(token)
