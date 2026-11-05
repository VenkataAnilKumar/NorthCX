"""Routes for the voice channel: the call-session WebSocket and the call records."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from northcx.access import OPEN_IDENTITY
from northcx.api.deps import AppDeps
from northcx.audit import AuditEntry
from northcx.voice import CallSession


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    audit = d.audit
    call_repo = d.call_repo
    provider = d.provider
    runtime = d.runtime
    voice = d.voice

    @app.get("/v1/voice/calls")
    async def voice_calls(limit: int = 50) -> Any:
        """Recent phone calls: outcome, consent, turns, barge-ins, languages and reply latency. No audio and no phone numbers."""
        return {"enabled": voice is not None, "calls": [c.summary() for c in await call_repo.recent(max(1, min(limit, 200)))]}

    @app.websocket("/v1/voice/stream")
    async def voice_stream(ws: WebSocket) -> None:
        """The telephony bridge's connection for one call (JSON messages both ways; see docs/05-technical/NorthCX_Voice.md). Authenticated with a
        channel key in the Authorization header, because the HTTP key check does not cover WebSockets."""
        if voice is None:
            await ws.close(code=4404)
            return
        ip = ws.client.host if ws.client else "unknown"
        if not access.limiter.allow(f"voice:{ip}", 60)[0]:
            await ws.close(code=4429)
            return
        if await access.enabled():
            header = ws.headers.get("authorization", "")
            ident, _ = await access.authenticate_detail(header[7:] if header.startswith("Bearer ") else None)
            if ident is None:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/v1/voice/stream", outcome="denied", detail={"client": ip}))
                await ws.close(code=4401)
                return
            if not ident.can("channel:inbound"):
                await audit.append(AuditEntry(actor=ident.name, role=ident.role, action="auth.denied", target="/v1/voice/stream", outcome="denied", detail={"permission": "channel:inbound"}))
                await ws.close(code=4403)
                return
        else:
            ident = OPEN_IDENTITY
        await ws.accept()

        async def send(msg: dict[str, Any]) -> None:
            try:
                await ws.send_json(msg)
            except Exception:  # the bridge went away; the call is ending anyway
                pass

        async def resolve(agent_id: str, session_id: str) -> Any:
            return await provider.get(agent_id, "production", session_id)
        call = CallSession(runtime, resolve, voice, call_repo, send)
        tokens, stamp = [300.0], [time.monotonic()]

        def bucket_allow() -> bool:
            now = time.monotonic()
            tokens[0] = min(300.0, tokens[0] + (now - stamp[0]) * 100)  # 100 messages a second sustained, bursts of 300
            stamp[0] = now
            tokens[0] -= 1
            return tokens[0] >= 0
        try:
            while True:
                raw = await ws.receive_text()
                if len(raw) > 65536:
                    await ws.close(code=1009)
                    break
                if not bucket_allow():
                    await ws.close(code=4429)  # a bridge that floods the stream is cut off
                    break
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "transcript" and msg.get("final", True) and not access.limiter.allow(f"voice-turns:{ident.key_id or ip}", 120)[0]:
                    continue  # at most 120 spoken turns a minute per key; the rest are ignored
                if msg.get("type") == "start" and call.rec is None:
                    await call.handle(msg)
                    await audit.append(AuditEntry(actor=ident.name, role=ident.role, action="voice.call", target=call.session_id, outcome="ok", detail={"callId": call.rec.call_id if call.rec else None}))
                else:
                    await call.handle(msg)
                if call.state == "ended":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            if call._turn is not None and not call._turn.done():
                try:
                    await asyncio.wait_for(asyncio.shield(call._turn), 20)  # an answer in progress is still saved to the conversation
                except Exception:
                    pass
            if call.state != "ended":
                await call.handle({"type": "end", "reason": "caller_hung_up"})
            try:
                await ws.close()
            except Exception:
                pass
