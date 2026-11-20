"""The browser SDK: served by the backend, kept in step with its source, and callable from allowed websites only."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = ROOT.parent / "sdk" / "src"
KEY = "boot" * 10


def app(**kw):
    rt = Runtime(ScriptedLLM([text("hi")] * 3), InMemoryStore(), TraceStore())
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), **kw))


def test_the_widget_and_client_are_served_without_a_key_and_cacheable():
    c = app()
    for name, marker in (("northcx-widget.js", "northcx-chat"), ("northcx-client.js", "NorthCXClient")):
        r = c.get(f"/sdk/{name}")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript") and marker in r.text
        assert r.headers["x-content-type-options"] == "nosniff" and "max-age" in r.headers["cache-control"]
    assert c.get("/sdk/secrets.txt").status_code == 404 and c.get("/sdk/..%2Fserver.py").status_code in (404, 400)
    assert c.get("/v1/agents").status_code == 401   # only the two scripts are public


@pytest.mark.skipif(not SDK_SRC.exists(), reason="the SDK source is not in this checkout")
def test_the_committed_bundle_matches_the_sdk_source():
    h = hashlib.sha256()
    for f in sorted(p.name for p in SDK_SRC.iterdir()):
        h.update(f.encode())
        h.update((SDK_SRC / f).read_bytes())
    stamp = h.hexdigest()[:16]
    first = (ROOT / "northcx" / "static" / "northcx-widget.js").read_text().splitlines()[0]
    assert first == f"/* northcx-widget source:{stamp} */", "src/sdk changed: run `npm run build` in src/sdk and commit the bundle"


def test_without_a_setting_no_website_may_call_the_api_from_a_browser():
    r = app().options("/v1/agents/support/chat", headers={"origin": "https://shop.example.com", "access-control-request-method": "POST", "access-control-request-headers": "authorization"})
    assert "access-control-allow-origin" not in r.headers


def test_listed_websites_can_call_the_chat_api_and_others_cannot():
    c = app(cors_origins=["https://shop.example.com"])
    ask = lambda origin: c.options("/v1/agents/support/chat", headers={"origin": origin, "access-control-request-method": "POST",  # noqa: E731
                                                                         "access-control-request-headers": "authorization,content-type,idempotency-key"})
    ok = ask("https://shop.example.com")
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "https://shop.example.com" and "authorization" in ok.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in ok.headers                       # tokens travel in a header, never cookies
    assert "access-control-allow-origin" not in ask("https://evil.example.net").headers
    real = c.get("/health", headers={"origin": "https://shop.example.com"})
    assert real.headers["access-control-allow-origin"] == "https://shop.example.com"
    unauth = c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "x"}, headers={"origin": "https://shop.example.com"})
    assert unauth.status_code == 401                                                  # CORS opens the door for the browser, not the lock


@pytest.mark.parametrize("bad", ["*", "http://shop.example.com", "https://shop.example.com/path", "shop.example.com", "https://a.example.com, *"])
def test_unsafe_cors_settings_stop_the_server_from_starting(bad):
    env = {k: v for k, v in os.environ.items() if not k.startswith("NORTHCX_")}
    env.update({"NORTHCX_DEMO": "1", "NORTHCX_API_KEY": "k" * 32, "NORTHCX_CORS_ORIGINS": bad, "PYTHONPATH": str(ROOT)})
    r = subprocess.run([sys.executable, "-m", "northcx"], env=env, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode != 0 and "NORTHCX_CORS_ORIGINS" in (r.stdout + r.stderr)


def test_the_widget_stays_within_its_size_budget():
    """The widget is loaded on customers' pages. Its budget is 16,384 bytes as served (13,294 on 2026-11-20, 5,199 gzipped); to grow past it, change the number here and in docs/01-chat/NorthCX_Choices-and-Media.md on purpose."""
    served = (Path(__file__).parent.parent / "northcx" / "static" / "northcx-widget.js").stat().st_size
    assert served <= 16_384, f"the widget is {served} bytes; the budget is 16,384"
