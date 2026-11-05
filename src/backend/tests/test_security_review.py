"""Standing checks from the Phase 6 security review: things that must stay true as the code changes."""
import ast
import json
from pathlib import Path

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

ROOT = Path(__file__).resolve().parents[1] / "northcx"
KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def sources():
    for p in ROOT.rglob("*.py"):
        if "migrations" not in p.parts:
            yield p, ast.parse(p.read_text())


def test_sql_values_are_always_bound_never_pasted_in():
    """Every raw SQL string is a constant, apart from one helper whose only callers pass constants."""
    pasted = []
    for p, tree in sources():
        if "db" not in p.parts:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "text" and n.args and isinstance(n.args[0], ast.JoinedStr):
                pasted.append((p.name, n.lineno))
    assert pasted == [("releases.py", pasted[0][1])] and len(pasted) == 1, pasted      # the single allowed helper: PgRollouts._one(where, params), in db/stores/releases.py
    tree = ast.parse((ROOT / "db" / "stores" / "releases.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "_one"]
    assert calls and all(isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str) for c in calls)


def test_no_dangerous_python_constructs():
    bad = []
    for p, tree in sources():
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            owner = getattr(getattr(n.func, "value", None), "id", None)
            if name in ("eval", "exec", "compile") and isinstance(n.func, ast.Name):
                bad.append((p.name, n.lineno, name))
            if owner == "pickle" or (owner == "os" and name in ("system", "popen")) or (owner == "yaml" and name in ("load", "unsafe_load")):
                bad.append((p.name, n.lineno, f"{owner}.{name}"))
            if owner == "subprocess" or any(k.arg == "shell" and getattr(k.value, "value", False) for k in n.keywords) or any(k.arg == "verify" and getattr(k.value, "value", True) is False for k in n.keywords):
                bad.append((p.name, n.lineno, "subprocess/shell/verify=False"))
    assert bad == [], bad


def test_every_outgoing_http_client_refuses_redirects_or_is_the_model_sdk():
    """A redirect from an operator-configured URL must not be followed to somewhere else (private addresses, other hosts)."""
    loose = []
    for p, tree in sources():
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "AsyncClient" and getattr(getattr(n.func, "value", None), "id", None) == "httpx":
                follows = [k for k in n.keywords if k.arg == "follow_redirects"]
                if not follows or getattr(follows[0].value, "value", None) is not False:
                    loose.append((p.name, n.lineno))
    assert loose == [], loose


def make(**kw):
    rt = Runtime(ScriptedLLM([text("hi")] * 3), InMemoryStore(), TraceStore())
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY), **kw)), rt


def test_cors_never_echoes_null_or_unlisted_origins():
    c, _ = make(cors_origins=["https://shop.example.com"])
    for origin in ("null", "https://shop.example.com.evil.net", "http://shop.example.com", "https://evil.example.net"):
        r = c.options("/v1/agents/support/chat", headers={"origin": origin, "access-control-request-method": "POST"})
        assert r.headers.get("access-control-allow-origin") is None, origin
    assert c.options("/v1/agents/support/chat", headers={"origin": "https://shop.example.com", "access-control-request-method": "POST"}).headers["access-control-allow-origin"] == "https://shop.example.com"


def test_secrets_never_reach_the_audit_log_or_error_bodies():
    c, rt = make()
    made = c.post("/v1/keys", headers=H, json={"name": "ci-bot", "role": "developer"}).json()
    token = c.post("/v1/chat-tokens", headers=H, json={"sessionId": "w1"}).json()["token"]
    c.post("/v1/agents/support/chat", headers={"authorization": f"Bearer {token}"}, json={"sessionId": "w1", "message": "hello"})
    audit = json.dumps(c.get("/v1/audit?limit=100", headers=H).json())
    assert made["key"] not in audit and token not in audit and KEY not in audit
    for bad in (c.get("/v1/agents/nobody/live", headers=H), c.post("/v1/agents/support/chat", headers=H, json={}), c.get("/v1/keys", headers={"authorization": "Bearer wrong"})):
        assert KEY not in bad.text and "Traceback" not in bad.text and "File \"" not in bad.text


def test_keys_are_stored_hashed_and_compared_in_constant_time():
    src = (ROOT / "access.py").read_text()
    assert "hmac.compare_digest" in src and "hash_secret" in src
    c, rt = make()
    made = c.post("/v1/keys", headers=H, json={"name": "ci-bot", "role": "developer"}).json()
    listing = json.dumps(c.get("/v1/keys", headers=H).json())
    assert made["key"] not in listing and "key_hash" not in listing and "hash" not in listing.lower().replace("last", "")


def test_a_customers_token_cannot_reach_staff_features():
    c, rt = make()
    token = c.post("/v1/chat-tokens", headers=H, json={"sessionId": "w1"}).json()["token"]
    mine = {"authorization": f"Bearer {token}"}
    for method, path in [("GET", "/v1/traces"), ("GET", "/v1/handoffs"), ("GET", "/v1/keys"), ("GET", "/v1/audit"), ("GET", "/v1/sessions/w1/attachments"), ("GET", "/v1/voice/calls"),
                         ("POST", "/v1/handoffs/x/reply"), ("DELETE", "/v1/privacy/sessions/w1"), ("POST", "/v1/chat-tokens"), ("GET", "/v1/insights/overview")]:
        r = c.request(method, path, headers=mine, json={} if method != "GET" else None)
        assert r.status_code == 403, (method, path, r.status_code)


def test_parsers_of_untrusted_input_only_fail_in_their_own_way():
    """Random and hostile input to every parser of outside data either works or raises that parser's documented error, never something else."""
    import base64
    import random

    from northcx.assist import AssistError, parse as parse_assist
    from northcx.attachments import AttachmentError, sniff
    from northcx.journeys import DraftError, parse_draft
    from northcx.language import detect
    from northcx.sso import SsoConfig, SsoError, verify_id_token
    from northcx.voice import consent_answer, speakable

    rnd = random.Random(1234)
    cfg = SsoConfig("https://idp.example.com", "client", "secret", "https://app.example.com/cb", role_map={"g": "viewer"})
    jwks = {"keys": [{"kty": "RSA", "kid": "k", "n": "AQAB", "e": "AQAB"}, {"kty": "EC", "crv": "P-256", "x": "AA", "y": "AA"}, {"kty": "oct"}]}
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    for _ in range(400):
        blob = bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 200)))
        try:
            sniff(blob)
        except AttachmentError:
            pass
        s = blob.decode("latin-1")
        for fn, err in ((parse_assist, AssistError), (lambda x: parse_draft(x, {"a"}), DraftError)):
            try:
                fn(s)
                fn("{" + s + "}")
            except err:
                pass
        speakable(s), detect(s), consent_answer(s)
        head = b64(rnd.choice([b'{"alg":"RS256","kid":"k"}', b'{"alg":"ES256"}', b'{"alg":"none"}', blob[:20], b"[]", b"1"]))
        body = b64(rnd.choice([b'{"iss":"https://idp.example.com","aud":"client","sub":"u","exp":9999999999,"nonce":"n"}', blob[:30], b"[]", b'{"aud":[1,2],"exp":"x"}']))
        try:
            verify_id_token(f"{head}.{body}.{b64(blob[:64])}", jwks, cfg, "n")
        except SsoError:
            pass
