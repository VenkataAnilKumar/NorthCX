"""Customer data rights and retention: export everything held for a customer, erase it, and age out old conversations.

A *session index* records which conversations belong to which customer (and when each was last active). Export and
erasure walk that index and then collect or remove everything stored for each conversation: messages, traces, outbox
messages, approvals, hand-offs, monitoring findings, email threads and idempotent replies. The audit log is kept (it is
tamper-evident by design and holds no message text); erasures are recorded in it with a one-way hash of the customer id.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Protocol

ANON = ""  # customer id used in the index for conversations with no known customer


def customer_ref(customer_id: str) -> str:
    """A short one-way reference for logs and the audit trail (the id itself may be an email address)."""
    return "cust_" + hashlib.sha256(customer_id.encode()).hexdigest()[:16]


class PrivacyBackend(Protocol):
    async def link(self, session_id: str, customer_id: str | None, now: float | None = None) -> None: ...
    async def sessions_for_customer(self, customer_id: str) -> list[str]: ...
    async def sessions_idle_since(self, cutoff: float, limit: int = 1000) -> list[str]: ...
    async def export_session(self, session_id: str) -> dict[str, Any]: ...
    async def erase_session(self, session_id: str) -> dict[str, int]: ...
    async def export_facts(self, customer_id: str) -> dict[str, str]: ...
    async def erase_facts(self, customer_id: str) -> int: ...
    async def export_memories(self, customer_id: str) -> list[dict[str, Any]]: ...
    async def erase_memories(self, customer_id: str) -> int: ...


def _plain(v: Any) -> Any:
    return json.loads(json.dumps(v, default=lambda o: dataclasses.asdict(o) if dataclasses.is_dataclass(o) else str(o)))


class InMemoryPrivacy:
    """Works over the in-memory stores of a Runtime (development and tests)."""

    def __init__(self, runtime: Any) -> None:
        self.rt = runtime
        self.email: Any = None  # attach the email repository to include email threads
        self.sms: Any = None  # likewise for texts
        self.index: dict[tuple[str, str], list[float]] = {}  # (session, customer) -> [first_seen, last_seen]

    async def link(self, session_id, customer_id, now=None) -> None:
        now = time.time() if now is None else now
        row = self.index.setdefault((session_id, customer_id or ANON), [now, now])
        row[1] = now

    def _customer_sessions(self, customer_id: str) -> set[str]:
        out = {s for (s, c) in self.index if c == customer_id}
        out |= {a.session_id for a in getattr(self.rt.approvals, "_items", {}).values() if a.customer_id == customer_id}
        out |= {h.session_id for h in getattr(self.rt.handoffs, "_items", {}).values() if h.customer_id == customer_id}
        if self.email is not None:
            out |= {s.session_id for s in self.email.sessions.values() if s.customer_id == customer_id}
        return out

    async def sessions_for_customer(self, customer_id) -> list[str]:
        return sorted(self._customer_sessions(customer_id))

    async def sessions_idle_since(self, cutoff, limit=1000) -> list[str]:
        last: dict[str, float] = {}
        for (s, _), (_, seen) in self.index.items():
            last[s] = max(last.get(s, 0), seen)
        return sorted(s for s, t in last.items() if t < cutoff)[:limit]

    async def export_session(self, session_id) -> dict[str, Any]:
        rt = self.rt
        out: dict[str, Any] = {
            "sessionId": session_id,
            "messages": await rt.store.load_messages(session_id),
            "traces": [t.to_dict() for t in getattr(rt.traces, "_traces", {}).values() if t.session_id == session_id],
            "outbox": [{"id": m.id, "kind": m.kind, "payload": m.payload, "createdAt": m.created_at} for m in await rt.outbox.repo.list(session_id, 0, 100000)],
            "approvals": [_plain(a) for a in getattr(rt.approvals, "_items", {}).values() if a.session_id == session_id],
            "handoffs": [_plain(h) for h in getattr(rt.handoffs, "_items", {}).values() if h.session_id == session_id],
            "findings": [_plain(f) for f in await rt.monitor.repo.list(session_id=session_id, limit=100000)],
        }
        if self.email is not None:
            s = self.email.sessions.get(session_id)
            out["email"] = {"session": _plain(s), "messages": [{"messageId": k, **v} for k, v in self.email.messages.items() if v["session_id"] == session_id]} if s else None
        if self.sms is not None:
            s = self.sms.sessions.get(session_id)
            out["sms"] = {"session": _plain(s), "messages": [{"messageId": k, **v} for k, v in self.sms.messages.items() if v["session_id"] == session_id]} if s else None
        return _plain(out)

    async def erase_session(self, session_id) -> dict[str, int]:
        rt = self.rt
        n: dict[str, int] = {}
        msgs = getattr(rt.store, "_msgs", {})
        n["messages"] = len(msgs.pop(session_id, []))
        traces = getattr(rt.traces, "_traces", {})
        gone = [k for k, t in traces.items() if t.session_id == session_id]
        for k in gone:
            del traces[k]
        n["traces"] = len(gone)
        d = getattr(rt.traces, "_dir", None)
        if gone and d is not None and (d / "traces.jsonl").exists():  # the optional file mirror must not keep erased traces
            ids = set(gone)
            lines = [ln for ln in (d / "traces.jsonl").read_text().splitlines() if ln and json.loads(ln).get("id") not in ids]
            (d / "traces.jsonl").write_text("".join(ln + "\n" for ln in lines))
        items = rt.outbox.repo._items
        before = len(items)
        items[:] = [m for m in items if m.session_id != session_id]
        n["outbox"] = before - len(items)
        tg = getattr(self, "tags", None)
        if tg is not None:
            n["tags"] = await tg.erase_session(session_id)
        fb = getattr(self, "feedback", None)
        if fb is not None:
            n["feedback"] = await fb.erase_session(session_id)
        if getattr(rt, "exports", None) is not None:
            n["exports"] = await rt.exports.repo.erase_traces(gone)
        if getattr(rt, "inbox", None) is not None:
            ids = [h.id for h in getattr(rt.handoffs, "_items", {}).values() if h.session_id == session_id]
            n["inbox"] = await rt.inbox.repo.erase_handoffs(ids)
        for name, store in (("approvals", rt.approvals), ("handoffs", rt.handoffs)):
            d_ = getattr(store, "_items", {})
            ids_ = [k for k, v in d_.items() if v.session_id == session_id]
            for k in ids_:
                del d_[k]
            n[name] = len(ids_)
        f = rt.monitor.repo.items
        before = len(f)
        f[:] = [x for x in f if x.session_id != session_id]
        n["findings"] = before - len(f)
        if self.email is not None:
            had = session_id in self.email.sessions
            self.email.sessions.pop(session_id, None)
            mids = [k for k, v in self.email.messages.items() if v["session_id"] == session_id]
            for k in mids:
                del self.email.messages[k]
            n["email"] = len(mids) + (1 if had else 0)
        if self.sms is not None:
            had = session_id in self.sms.sessions
            self.sms.sessions.pop(session_id, None)
            mids = [k for k, v in self.sms.messages.items() if v["session_id"] == session_id]
            for k in mids:
                del self.sms.messages[k]
            n["sms"] = len(mids) + (1 if had else 0)
        idem = getattr(self, "idempotency", None)
        n["replies"] = await idem.forget_session(session_id) if idem is not None else 0
        for k in [k for k in self.index if k[0] == session_id]:
            del self.index[k]
        return n

    async def export_facts(self, customer_id) -> dict[str, str]:
        return await self.rt.store.get_facts(customer_id)

    async def erase_facts(self, customer_id) -> int:
        facts = getattr(self.rt.store, "_facts", {})
        return len(facts.pop(customer_id, {}))

    async def export_memories(self, customer_id) -> list[dict[str, Any]]:
        mem = self.rt.memories
        return [m.to_dict() for m in await mem.list(customer_id)] if mem is not None else []

    async def erase_memories(self, customer_id) -> int:
        mem = self.rt.memories
        return await mem.forget_all(customer_id) if mem is not None else 0


class PrivacyService:
    def __init__(self, backend: PrivacyBackend):
        self.backend = backend

    async def export_customer(self, customer_id: str, now: float | None = None) -> dict[str, Any]:
        sessions = await self.backend.sessions_for_customer(customer_id)
        return {"customerId": customer_id, "generatedAt": time.time() if now is None else now,
                "facts": await self.backend.export_facts(customer_id),
                "memories": await self.backend.export_memories(customer_id),
                "sessions": [await self.backend.export_session(s) for s in sessions]}

    async def erase_customer(self, customer_id: str) -> dict[str, Any]:
        total: dict[str, int] = {}
        sessions = await self.backend.sessions_for_customer(customer_id)
        for s in sessions:
            for k, v in (await self.backend.erase_session(s)).items():
                total[k] = total.get(k, 0) + v
        total["facts"] = await self.backend.erase_facts(customer_id)
        total["memories"] = await self.backend.erase_memories(customer_id)
        return {"sessions": len(sessions), "removed": total}

    async def erase_session(self, session_id: str) -> dict[str, int]:
        return await self.backend.erase_session(session_id)

    async def purge_idle(self, older_than_days: float, now: float | None = None, limit: int = 1000) -> dict[str, Any]:
        cutoff = (time.time() if now is None else now) - older_than_days * 86400
        sessions = await self.backend.sessions_idle_since(cutoff, limit)
        total: dict[str, int] = {}
        for s in sessions:
            for k, v in (await self.backend.erase_session(s)).items():
                total[k] = total.get(k, 0) + v
        return {"sessions": len(sessions), "removed": total}
