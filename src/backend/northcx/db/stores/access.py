"""Postgres stores for API keys and the tamper-evident audit log."""
from __future__ import annotations

import time

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.access import ApiKey
from northcx.audit import AuditEntry, entry_hash, GENESIS, Verification, verify_entries
from northcx.db.models import ApiKeyRow, AuditRow
from northcx.db.stores._base import _Base, _jsonable


class PgKeys(_Base):
    @staticmethod
    def _to_key(r: ApiKeyRow) -> ApiKey:
        return ApiKey(name=r.name, role=r.role, key_id=r.key_id, key_hash=r.key_hash, created_by=r.created_by, created_at=r.created_at,
                      expires_at=r.expires_at, revoked_at=r.revoked_at, revoked_by=r.revoked_by, last_used_at=r.last_used_at,
                      extra_roles=list(r.extra_roles) if r.extra_roles else None, groups=list(r.groups) if r.groups else None, tenant_id=r.tenant_id, agents=list(r.agents) if r.agents is not None else None, environments=list(r.environments) if r.environments is not None else None)

    async def create(self, key: ApiKey) -> ApiKey:
        async with self._sm.begin() as s:
            await s.execute(pg_insert(ApiKeyRow).values(
                key_id=key.key_id, name=key.name, role=key.role, key_hash=key.key_hash, created_by=key.created_by,
                created_at=key.created_at, expires_at=key.expires_at, extra_roles=key.extra_roles, groups=key.groups, tenant_id=key.tenant_id, agents=key.agents, environments=key.environments))
        return key

    async def get(self, key_id: str) -> ApiKey | None:
        async with self._ro() as s:
            r = (await s.execute(select(ApiKeyRow).where(ApiKeyRow.key_id == key_id))).scalar_one_or_none()
        return self._to_key(r) if r else None

    async def list(self) -> list[ApiKey]:
        async with self._ro() as s:
            rows = (await s.execute(select(ApiKeyRow).order_by(ApiKeyRow.created_at.desc()))).scalars().all()
        return [self._to_key(r) for r in rows]

    async def revoke(self, key_id: str, by: str) -> ApiKey:
        async with self._sm.begin() as s:
            row = (await s.execute(update(ApiKeyRow).where(ApiKeyRow.key_id == key_id, ApiKeyRow.revoked_at.is_(None))
                                   .values(revoked_at=time.time(), revoked_by=by).returning(ApiKeyRow))).scalar_one_or_none()
            if row is not None:
                return self._to_key(row)
            existing = (await s.execute(select(ApiKeyRow).where(ApiKeyRow.key_id == key_id))).scalar_one_or_none()
        if existing is None:
            raise KeyError(key_id)
        raise ValueError(f"Key {key_id} is already revoked")

    async def touch(self, key_id: str, at: float) -> None:
        async with self._sm.begin() as s:
            await s.execute(update(ApiKeyRow).where(ApiKeyRow.key_id == key_id).values(last_used_at=at))


class PgAudit(_Base):
    @staticmethod
    def _to_entry(r: AuditRow) -> AuditEntry:
        return AuditEntry(actor=r.actor, role=r.role, action=r.action, target=r.target, outcome=r.outcome, detail=r.detail,
                          key_id=r.key_id, at=r.at, id=r.id, prev_hash=r.prev_hash, hash=r.hash, tenant_id=r.tenant_id)

    async def append(self, entry: AuditEntry) -> AuditEntry:
        """Appends are serialised by an advisory lock so each entry chains onto the true previous one."""
        entry.detail = _jsonable(entry.detail)
        async with self._sm.begin() as s:
            await s.execute(text("select pg_advisory_xact_lock(hashtext('audit_log'))"))
            last = (await s.execute(select(AuditRow).order_by(AuditRow.id.desc()).limit(1))).scalar_one_or_none()
            entry.id = (last.id + 1) if last else 1
            entry.prev_hash = last.hash if last else GENESIS
            entry.hash = entry_hash(entry)
            await s.execute(pg_insert(AuditRow).values(
                id=entry.id, at=entry.at, actor=entry.actor, role=entry.role, key_id=entry.key_id, action=entry.action,
                target=entry.target[:300], outcome=entry.outcome, detail=entry.detail, prev_hash=entry.prev_hash, hash=entry.hash, tenant_id=entry.tenant_id))
        return entry

    async def list(self, limit: int = 100, before_id: int | None = None, actor: str | None = None,
                   action: str | None = None, tenant_id: str | None = None) -> list[AuditEntry]:
        q = select(AuditRow).order_by(AuditRow.id.desc()).limit(limit)
        if before_id is not None:
            q = q.where(AuditRow.id < before_id)
        if actor:
            q = q.where(AuditRow.actor == actor)
        if action:
            q = q.where(AuditRow.action == action)
        if tenant_id is not None:
            q = q.where(AuditRow.tenant_id == tenant_id)
        async with self._ro() as s:
            return [self._to_entry(r) for r in (await s.execute(q)).scalars().all()]

    async def verify(self) -> Verification:
        async with self._ro() as s:
            rows = (await s.execute(select(AuditRow).order_by(AuditRow.id))).scalars().all()
        return verify_entries([self._to_entry(r) for r in rows])
