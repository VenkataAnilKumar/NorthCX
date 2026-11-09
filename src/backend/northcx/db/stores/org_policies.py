"""Postgres store for organization policy versions."""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.db.models import OrgPolicyRow
from northcx.db.stores._base import _Base, _jsonable
from northcx.org_policies import OrgPolicy

_FIELDS = ("policy", "config", "cases", "applies_to", "proof", "created_by", "proposed_by", "decided_by", "decision_note")


def _from(r: OrgPolicyRow) -> OrgPolicy:
    return OrgPolicy(id=r.id, version=r.version, name=r.name, status=r.status, created_at=r.created_at, updated_at=r.updated_at, **{k: r.data.get(k) for k in _FIELDS})


class PgOrgPolicies(_Base):
    async def save(self, p: OrgPolicy) -> None:
        p.updated_at = time.time()
        data = _jsonable({k: getattr(p, k) for k in _FIELDS})
        stmt = pg_insert(OrgPolicyRow).values(id=p.id, version=p.version, status=p.status, name=p.name, created_at=p.created_at, updated_at=p.updated_at, data=data)
        stmt = stmt.on_conflict_do_update(index_elements=[OrgPolicyRow.tenant_id, OrgPolicyRow.id, OrgPolicyRow.version],
                                          set_={"status": p.status, "updated_at": p.updated_at, "data": data, "name": p.name})
        async with self._sm.begin() as s:
            await s.execute(stmt)

    async def versions(self, policy_id: str) -> list[OrgPolicy]:
        async with self._ro() as s:
            rows = (await s.execute(select(OrgPolicyRow).where(OrgPolicyRow.id == policy_id).order_by(OrgPolicyRow.version.desc()))).scalars().all()
        return [_from(r) for r in rows]

    async def get(self, policy_id: str, version: int | None = None) -> OrgPolicy | None:
        vs = await self.versions(policy_id)
        return next((p for p in vs if version is None or p.version == version), None)

    async def list(self) -> list[OrgPolicy]:
        async with self._ro() as s:
            rows = (await s.execute(select(OrgPolicyRow).order_by(OrgPolicyRow.id, OrgPolicyRow.version.desc()))).scalars().all()
        latest: dict[str, OrgPolicyRow] = {}
        for r in rows:
            latest.setdefault(r.id, r)
        return sorted((_from(r) for r in latest.values()), key=lambda p: p.name.lower())

    async def active(self) -> list[OrgPolicy]:
        async with self._ro() as s:
            rows = (await s.execute(select(OrgPolicyRow).where(OrgPolicyRow.status == "active"))).scalars().all()
        return [_from(r) for r in rows]
