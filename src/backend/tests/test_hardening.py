"""Protections that apply everywhere: request size caps, safe response headers, voice stream flood limits."""
import json

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.hardening import DEFAULT_LIMIT, limit_for
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.voice import VoiceConfig

KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def app(**kw):
    rt = Runtime(ScriptedLLM([text("hi")] * 5), InMemoryStore(), TraceStore())
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), **kw), raise_server_exceptions=False)


def test_limits_by_endpoint():
    assert limit_for("POST", "/v1/agents/support/chat") == DEFAULT_LIMIT
    assert limit_for("PUT", "/v1/sessions/s1/attachments") > 10 * 1024 * 1024 and limit_for("POST", "/v1/sessions/s1/feedback") == DEFAULT_LIMIT
    assert limit_for("PUT", "/v1/knowledge/sources/a/documents/b") > DEFAULT_LIMIT and limit_for("GET", "/v1/me") < DEFAULT_LIMIT
    assert limit_for("POST", "/v1/channels/email/inbound") > DEFAULT_LIMIT


def test_a_request_bigger_than_its_endpoint_allows_is_refused_before_it_is_read():
    c = app()
    big = json.dumps({"sessionId": "s", "message": "x" * (DEFAULT_LIMIT + 10)})
    r = c.post("/v1/agents/support/chat", content=big, headers={**H, "content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
    assert c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "hello"}, headers=H).status_code == 200      # normal requests are unaffected
    assert c.get("/v1/me", headers={**H, "content-length": "999999"}).status_code in (413, 400)                              # a GET has no business sending a large body


def test_a_body_without_a_declared_length_is_cut_off_as_it_arrives():
    c = app()

    def chunks():
        for _ in range(40):
            yield b"x" * (64 * 1024)
    r = c.post("/v1/agents/support/chat", content=chunks(), headers={**H, "content-type": "application/json"})
    assert r.status_code == 413


def test_uploads_may_be_larger_but_not_unlimited():
    c = app()
    assert c.put("/v1/sessions/s1/attachments", content=b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024), headers=H).status_code == 400   # over the picture limit: refused by the file rules
    assert c.put("/v1/sessions/s1/attachments", content=b"\x00" * (12 * 1024 * 1024), headers=H).status_code == 413                            # over the absolute cap: refused outright


def test_every_response_carries_safe_headers_and_api_answers_are_never_cached():
    c = app()
    r = c.get("/v1/me", headers=H)
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store" and "camera=()" in r.headers["permissions-policy"]
    assert c.get("/v1/me").headers["cache-control"] == "no-store"                                                                              # even a refusal
    h = c.get("/health")
    assert h.headers["x-content-type-options"] == "nosniff" and "cache-control" not in h.headers
    sdk = c.get("/sdk/northcx-widget.js")
    assert "max-age" in sdk.headers["cache-control"]                                                                                           # a route's own choice is kept


def test_a_bridge_that_floods_the_stream_is_cut_off():
    from starlette.websockets import WebSocketDisconnect
    c = app(voice=VoiceConfig("support"))
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect("/v1/voice/stream", headers=H) as ws:
            ws.send_json({"type": "start", "callId": "flood"})
            for _ in range(2000):
                ws.send_json({"type": "transcript", "text": "hello", "final": False})
            for _ in range(2000):
                ws.receive_json()
    assert e.value.code == 4429
