"""Postgres store for staff notes about customers."""
from __future__ import annotations

from sqlalchemy import delete, select

from northcx.customers import CustomerNote
from northcx.db.models import CustomerNoteRow
from northcx.db.stores._base import _Base


class PgCustomerNotes(_Base):
    async def add(self, n: CustomerNote) -> None:
        async with self._sm.begin() as s:
            s.add(CustomerNoteRow(id=n.id, customer_id=n.customer_id, note=n.note, author=n.author, created_at=n.created_at))

    async def list(self, customer_id: str) -> list[CustomerNote]:
        async with self._ro() as s:
            rows = (await s.execute(select(CustomerNoteRow).where(CustomerNoteRow.customer_id == customer_id).order_by(CustomerNoteRow.created_at.desc()))).scalars().all()
        return [CustomerNote(r.customer_id, r.note, r.author, r.id, r.created_at) for r in rows]

    async def delete(self, customer_id: str, note_id: str) -> bool:
        async with self._sm.begin() as s:
            return (await s.execute(delete(CustomerNoteRow).where(CustomerNoteRow.id == note_id, CustomerNoteRow.customer_id == customer_id))).rowcount > 0

    async def erase_customer(self, customer_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(delete(CustomerNoteRow).where(CustomerNoteRow.customer_id == customer_id))).rowcount
