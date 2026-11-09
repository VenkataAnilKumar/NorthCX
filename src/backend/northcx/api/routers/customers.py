"""Routes for the Customers tab: look up one customer by the company's own identifier, with personal data masked and every open audited."""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import CustomerFindBody, CustomerLookupBody, CustomerNoteBody, CustomerRemoveBody, CustomerRevealBody, CustomerSettingsBody
from northcx.insights import mask
from northcx.customers import WINDOW_DAYS, CustomerNote, CustomerService, InMemoryNotes
from northcx.memory import MemoryRejected, check_note
from northcx.privacy import customer_ref


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime, insight, review_repo, privacy = d.record, d.runtime, d.insight, d.review_repo, d.privacy
    svc: CustomerService = getattr(runtime, "customers", None) or CustomerService(InMemoryNotes())
    app.state.customers = svc
    privacy.notes = svc.notes                      # an export includes the notes and an erasure removes them

    PRIVATE = {"Cache-Control": "no-store"}

    async def gate() -> JSONResponse | None:
        if not await svc.enabled():
            return _err(403, "disabled", "The Customers view is turned off for this organization")
        return None

    async def known(customer_id: str) -> tuple[list[str], list[Any]]:
        sessions = await privacy.backend.sessions_for_customer(customer_id)
        facts = await runtime.memories.list(customer_id) if runtime.memories is not None else []
        return sessions, facts

    async def who_is(body: Any) -> str | JSONResponse:
        """The customer a request is about: the identifier given, or the customer of the conversation named."""
        if body.customer_id and body.session_id or not (body.customer_id or body.session_id):
            return _err(400, "bad_request", "Give either customerId or sessionId")
        if body.customer_id:
            return body.customer_id.strip()
        cid = await privacy.backend.customer_for_session(body.session_id)
        return cid if cid else _err(404, "not_found", "No customer is linked to that conversation")

    @app.get("/v1/customers/settings")
    async def get_settings() -> Any:
        return {"enabled": await svc.enabled()}

    @app.put("/v1/customers/settings")
    async def put_settings(body: CustomerSettingsBody, request: Request) -> Any:
        await svc.set_enabled(body.enabled, request.state.identity.name)
        await record(request, "customers.settings", "enabled" if body.enabled else "disabled")
        return {"enabled": body.enabled}

    @app.post("/v1/customers/lookup")
    async def lookup(body: CustomerLookupBody, request: Request) -> Any:
        """The id goes in the body, never in a URL, so it does not end up in logs."""
        if (g := await gate()) is not None:
            return g
        cid = await who_is(body)
        if isinstance(cid, JSONResponse):
            return cid
        sessions, facts = await known(cid)
        if not sessions and not facts and not await svc.notes.list(cid):
            await record(request, "customers.lookup", customer_ref(cid), "not_found")
            return _err(404, "not_found", "No customer with that identifier")
        now = time.time()
        turns, handoffs, feedback = await insight.for_sessions(now - WINDOW_DAYS * 86400.0, now, sessions)
        reviews = await review_repo.for_sessions(sessions)
        out = await svc.profile(cid, sessions, turns, handoffs, feedback, reviews, facts)
        await record(request, "customers.open", out["ref"], sessions=len(sessions), facts=len(facts))
        return JSONResponse(out, headers=PRIVATE)

    @app.post("/v1/customers/find")
    async def find(body: CustomerFindBody, request: Request) -> Any:
        """Find conversations that mention an order number, exactly, and say which customer each belongs to (by reference only). Open one with its sessionId."""
        if (g := await gate()) is not None:
            return g
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(body.order_number.lower()) + r"(?![A-Za-z0-9])")
        now = time.time()
        turns, _, _ = await insight._load(now - WINDOW_DAYS * 86400.0, now, None, "production")
        seen: dict[str, Any] = {}
        for t in sorted(turns, key=lambda t: -t.started_at):
            if t.session_id not in seen and pattern.search(t.text):
                seen[t.session_id] = t
        matches = []
        for sid, t in list(seen.items())[:10]:
            cid = await privacy.backend.customer_for_session(sid)
            matches.append({"sessionId": sid, "customerRef": customer_ref(cid) if cid else None, "agentId": t.agent_id, "startedAt": t.started_at, "firstMessage": mask(t.first_message, 160)})
        await record(request, "customers.find", "order:" + hashlib.sha256(body.order_number.lower().encode()).hexdigest()[:12], matches=len(matches))
        return JSONResponse({"matches": matches, "windowDays": WINDOW_DAYS, "truncated": len(turns) >= 20000, "note": "Exact matches in conversations from the last %d days. The customer identifier is not shown; open a match to see the masked record." % WINDOW_DAYS},
                            headers=PRIVATE)

    @app.post("/v1/customers/reveal")
    async def reveal(body: CustomerRevealBody, request: Request) -> Any:
        """Show the identifier unmasked. A reason is required and kept in the audit log."""
        if (g := await gate()) is not None:
            return g
        cid = await who_is(body)
        if isinstance(cid, JSONResponse):
            return cid
        sessions, facts = await known(cid)
        if not sessions and not facts:
            return _err(404, "not_found", "No customer with that identifier")
        await record(request, "customers.reveal", customer_ref(cid), reason=body.reason.strip())
        return JSONResponse({"ref": customer_ref(cid), "id": cid}, headers=PRIVATE)

    @app.post("/v1/customers/notes", status_code=201)
    async def add_note(body: CustomerNoteBody, request: Request) -> Any:
        if (g := await gate()) is not None:
            return g
        cid = await who_is(body)
        if isinstance(cid, JSONResponse):
            return cid
        sessions, facts = await known(cid)
        if not sessions and not facts and not await svc.notes.list(cid):
            return _err(404, "not_found", "No customer with that identifier")
        try:
            clean = check_note(body.note)             # no card numbers, passwords or instructions-looking text
        except MemoryRejected as e:
            return _err(400, "bad_request", str(e))
        n = CustomerNote(cid, clean, request.state.identity.name)
        await svc.notes.add(n)
        await record(request, "customers.note_add", customer_ref(cid), note=n.id)
        return n.to_dict()

    @app.post("/v1/customers/notes/{note_id}/delete")
    async def delete_note(note_id: str, body: CustomerLookupBody, request: Request) -> Any:
        if (g := await gate()) is not None:
            return g
        cid = await who_is(body)
        if isinstance(cid, JSONResponse):
            return cid
        mine = next((n for n in await svc.notes.list(cid) if n.id == note_id), None)
        if mine is None:
            return _err(404, "not_found", "Unknown note")
        who = request.state.identity
        if mine.author != who.name and not who.can("keys:manage"):
            return _err(403, "forbidden", "Only the author or an administrator can delete a note")
        await svc.notes.delete(cid, note_id)
        await record(request, "customers.note_delete", customer_ref(cid), note=note_id)
        return {"deleted": True}

    @app.post("/v1/customers/facts/{fact_id}/remove")
    async def remove_fact(fact_id: str, body: CustomerRemoveBody, request: Request) -> Any:
        """Remove a fact the agents may use, usually because the customer asked. The reason is logged."""
        if (g := await gate()) is not None:
            return g
        if runtime.memories is None:
            return _err(501, "not_configured", "Memory is not enabled on this server")
        cid = await who_is(body)
        if isinstance(cid, JSONResponse):
            return cid
        if not await runtime.memories.forget(cid, fact_id):
            return _err(404, "not_found", "Unknown fact")
        await record(request, "customers.fact_remove", customer_ref(cid), fact=fact_id, reason=body.reason.strip())
        return {"removed": True}
