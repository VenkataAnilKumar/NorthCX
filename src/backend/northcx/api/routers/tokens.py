"""Route that mints customer chat tokens."""
from __future__ import annotations

from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import TokenBody
from northcx.tokens import MAX_TTL, MIN_TTL


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access

    # ---------------- chat tokens ----------------
    @app.post("/v1/chat-tokens", status_code=201)
    async def mint_chat_token(body: TokenBody, request: Request) -> Any:
        """Called by the company's server (holding a channel key), never by the customer's browser. Returns a token that
        lets one browser talk in one conversation as one customer until it expires."""
        who: Identity = request.state.identity
        if access.signer is None:
            return _err(501, "not_configured", "Chat tokens are not configured: set NORTHCX_TOKEN_SECRET or NORTHCX_API_KEY")
        if not MIN_TTL <= body.ttl_seconds <= MAX_TTL:
            return _err(400, "bad_request", f"ttlSeconds must be between {MIN_TTL} and {MAX_TTL}")
        sid = body.session_id or f"web-{uuid.uuid4().hex}"
        token, claims = access.signer.mint(sid=sid, kid=who.key_id or "open", cid=body.customer_id, agent=body.agent, ttl=body.ttl_seconds)
        return JSONResponse({"token": token, "sessionId": sid, "customerId": body.customer_id, "agent": body.agent,
                             "expiresAt": claims.exp, "ttlSeconds": body.ttl_seconds}, status_code=201)
