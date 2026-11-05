"""Postgres stores for the channels: SMS and messaging apps, email, voice calls, identity-verification codes and attachments."""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from northcx.attachments import Attachment
from northcx.channels.email import EmailSession
from northcx.channels.sms import phone_hash, SmsSession
from northcx.db.models import EmailMessageRow, EmailSessionRow
from northcx.db.stores._base import _Base
from northcx.voice import CallRecord


class PgSmsRepo(_Base):
    @staticmethod
    def _s(r: Any) -> SmsSession:
        return SmsSession(r.session_id, r.phone, r.our_number, r.created_at, r.last_seen)

    async def latest_session(self, phone: str, our_number: str) -> SmsSession | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from sms_sessions where phone = :p and our_number = :o order by last_seen desc limit 1"),
                                 {"p": phone, "o": our_number})).first()
        return self._s(r) if r else None

    async def get_session(self, session_id: str) -> SmsSession | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from sms_sessions where session_id = :i"), {"i": session_id})).first()
        return self._s(r) if r else None

    async def save_session(self, session: SmsSession) -> None:
        async with self._sm.begin() as s:
            await s.execute(text("insert into sms_sessions (session_id, phone, our_number, created_at, last_seen) values (:i, :p, :o, :c, :l) "
                                 "on conflict (session_id) do update set last_seen = excluded.last_seen"),
                            {"i": session.session_id, "p": session.phone, "o": session.our_number, "c": session.created_at, "l": session.last_seen})

    async def has_message(self, message_id: str) -> bool:
        async with self._ro() as s:
            return (await s.execute(text("select 1 from sms_messages where message_id = :i"), {"i": message_id})).first() is not None

    async def record_message(self, message_id: str, session_id: str, direction: str, outcome: str, peer: str) -> bool:
        async with self._sm.begin() as s:
            r = await s.execute(text("insert into sms_messages (message_id, session_id, direction, outcome, peer, created_at) values (:i,:s,:d,:o,:p,:t) "
                                     "on conflict do nothing returning message_id"),
                                {"i": message_id[:400], "s": session_id, "d": direction, "o": outcome, "p": peer, "t": time.time()})
            return r.first() is not None

    async def recent_count(self, peer: str, direction: str, since: float) -> int:
        async with self._ro() as s:
            return int((await s.execute(text("select count(*) from sms_messages where peer = :p and direction = :d and created_at >= :t"),
                                        {"p": peer, "d": direction, "t": since})).scalar_one())

    async def set_opt_out(self, phone: str, opted_out: bool) -> None:
        async with self._sm.begin() as s:
            if opted_out:
                await s.execute(text("insert into sms_opt_outs (phone_hash, updated_at) values (:h, :t) on conflict (phone_hash) do update set updated_at = excluded.updated_at"),
                                {"h": phone_hash(phone), "t": time.time()})
            else:
                await s.execute(text("delete from sms_opt_outs where phone_hash = :h"), {"h": phone_hash(phone)})

    async def is_opted_out(self, phone: str) -> bool:
        async with self._ro() as s:
            return (await s.execute(text("select 1 from sms_opt_outs where phone_hash = :h"), {"h": phone_hash(phone)})).first() is not None


class PgEmailRepo(_Base):
    @staticmethod
    def _to_session(r: EmailSessionRow) -> EmailSession:
        return EmailSession(session_id=r.session_id, sender=r.sender, subject=r.subject, last_message_id=r.last_message_id,
                            customer_id=r.customer_id, verified=r.verified, references=list(r.references), created_at=r.created_at)

    async def get_session(self, session_id: str) -> EmailSession | None:
        async with self._ro() as s:
            r = (await s.execute(select(EmailSessionRow).where(EmailSessionRow.session_id == session_id))).scalar_one_or_none()
        return self._to_session(r) if r else None

    async def find_session(self, message_ids: list[str]) -> EmailSession | None:
        if not message_ids:
            return None
        async with self._ro() as s:
            rows = (await s.execute(select(EmailMessageRow.message_id, EmailMessageRow.session_id)
                                    .where(EmailMessageRow.message_id.in_(message_ids)))).all()
            by_id = {r.message_id: r.session_id for r in rows}
            for mid in message_ids:  # nearest first
                sid = by_id.get(mid)
                if sid:
                    r = (await s.execute(select(EmailSessionRow).where(EmailSessionRow.session_id == sid))).scalar_one_or_none()
                    if r:
                        return self._to_session(r)
        return None

    async def save_session(self, session: EmailSession) -> None:
        values = dict(session_id=session.session_id, sender=session.sender, subject=session.subject[:500],
                      customer_id=session.customer_id, verified=session.verified, last_message_id=session.last_message_id,
                      references=session.references, created_at=session.created_at)
        async with self._sm.begin() as s:
            await s.execute(pg_insert(EmailSessionRow).values(**values).on_conflict_do_update(
                index_elements=[EmailSessionRow.session_id], set_={k: v for k, v in values.items() if k != "session_id"}))

    async def has_message(self, message_id: str) -> bool:
        async with self._ro() as s:
            return (await s.execute(select(EmailMessageRow.message_id).where(EmailMessageRow.message_id == message_id))).first() is not None

    async def record_message(self, message_id: str, session_id: str, direction: str, outcome: str, peer: str) -> bool:
        async with self._sm.begin() as s:
            res = await s.execute(pg_insert(EmailMessageRow).values(
                message_id=message_id[:998], session_id=session_id, direction=direction, outcome=outcome, peer=peer, created_at=time.time()
            ).on_conflict_do_nothing(index_elements=[EmailMessageRow.message_id]))
            return res.rowcount == 1

    async def recent_count(self, peer: str, direction: str, since: float) -> int:
        async with self._ro() as s:
            return (await s.execute(select(func.count()).select_from(EmailMessageRow).where(
                EmailMessageRow.peer == peer, EmailMessageRow.direction == direction, EmailMessageRow.created_at >= since))).scalar_one()


class PgCalls(_Base):
    @staticmethod
    def _c(r: Any) -> CallRecord:
        return CallRecord(r.call_id, r.session_id, r.agent_id, r.caller_hash, r.started_at, r.ended_at, r.outcome, r.consent, r.recorded, r.turns, r.barge_ins,
                          list(r.languages), r.handoff_id, list(r.latency_ms))

    async def save(self, c: CallRecord) -> None:
        async with self._sm.begin() as s:
            await s.execute(text(
                "insert into voice_calls (call_id, session_id, agent_id, caller_hash, started_at, ended_at, outcome, consent, recorded, turns, barge_ins, languages, handoff_id, latency_ms) "
                "values (:id, :s, :a, :h, :st, :en, :o, :c, :r, :t, :b, cast(:l as jsonb), :ho, cast(:lat as jsonb)) "
                "on conflict (call_id) do update set ended_at = excluded.ended_at, outcome = excluded.outcome, consent = excluded.consent, recorded = excluded.recorded, "
                "turns = excluded.turns, barge_ins = excluded.barge_ins, languages = excluded.languages, handoff_id = excluded.handoff_id, latency_ms = excluded.latency_ms"),
                {"id": c.call_id, "s": c.session_id, "a": c.agent_id, "h": c.caller_hash, "st": c.started_at, "en": c.ended_at, "o": c.outcome, "c": c.consent, "r": c.recorded,
                 "t": c.turns, "b": c.barge_ins, "l": json.dumps(c.languages), "ho": c.handoff_id, "lat": json.dumps(c.latency_ms)})

    async def get(self, call_id: str) -> CallRecord | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from voice_calls where call_id = :id"), {"id": call_id})).first()
        return self._c(r) if r else None

    async def recent(self, limit: int = 50) -> list[CallRecord]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from voice_calls order by started_at desc limit :n"), {"n": limit})).all()
        return [self._c(r) for r in rows]

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from voice_calls where session_id = :s"), {"s": session_id})).rowcount


class PgVerify(_Base):
    async def get(self, session_id: str) -> Any:
        from northcx.verification import VerifyRecord
        async with self._ro() as s:
            r = (await s.execute(text("select * from verification_codes where session_id = :s"), {"s": session_id})).first()
        return VerifyRecord(r.session_id, r.customer_id, r.channel, r.dest_hash, r.code_hash, r.expires_at, r.attempts, list(r.sends), r.verified_until) if r else None

    async def save(self, r: Any) -> None:
        async with self._sm.begin() as s:
            await s.execute(text(
                "insert into verification_codes (session_id, customer_id, channel, dest_hash, code_hash, expires_at, attempts, sends, verified_until, updated_at) "
                "values (:s, :c, :ch, :d, :h, :e, :a, cast(:sn as jsonb), :v, :u) on conflict (session_id) do update set customer_id = excluded.customer_id, channel = excluded.channel, "
                "dest_hash = excluded.dest_hash, code_hash = excluded.code_hash, expires_at = excluded.expires_at, attempts = excluded.attempts, sends = excluded.sends, "
                "verified_until = excluded.verified_until, updated_at = excluded.updated_at"),
                {"s": r.session_id, "c": r.customer_id, "ch": r.channel, "d": r.dest_hash, "h": r.code_hash, "e": r.expires_at, "a": r.attempts, "sn": json.dumps(r.sends), "v": r.verified_until, "u": time.time()})

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from verification_codes where session_id = :s"), {"s": session_id})).rowcount


class PgAttachments(_Base):
    @staticmethod
    def _a(r: Any) -> Attachment:
        return Attachment(r.session_id, r.name, r.kind, r.media_type, r.size, r.sha256, bytes(r.data), r.uploaded_by, r.id, r.created_at)

    async def add(self, a: Attachment) -> Attachment:
        async with self._sm.begin() as s:
            await s.execute(text("insert into attachments (id, session_id, name, kind, media_type, size, sha256, data, uploaded_by, created_at) "
                                 "values (:id, :s, :n, :k, :m, :z, :h, :d, :u, :t)"),
                            {"id": a.id, "s": a.session_id, "n": a.name, "k": a.kind, "m": a.media_type, "z": a.size, "h": a.sha256, "d": a.data, "u": a.uploaded_by, "t": a.created_at})
        return a

    async def get(self, attachment_id: str) -> Attachment | None:
        async with self._ro() as s:
            r = (await s.execute(text("select * from attachments where id = :id"), {"id": attachment_id})).first()
        return self._a(r) if r else None

    async def for_session(self, session_id: str) -> list[Attachment]:
        async with self._ro() as s:
            rows = (await s.execute(text("select * from attachments where session_id = :s order by created_at"), {"s": session_id})).all()
        return [self._a(r) for r in rows]

    async def usage(self, session_id: str) -> tuple[int, int]:
        async with self._ro() as s:
            r = (await s.execute(text("select count(*), coalesce(sum(size), 0) from attachments where session_id = :s"), {"s": session_id})).one()
        return int(r[0]), int(r[1])

    async def erase_session(self, session_id: str) -> int:
        async with self._sm.begin() as s:
            return (await s.execute(text("delete from attachments where session_id = :s"), {"s": session_id})).rowcount
