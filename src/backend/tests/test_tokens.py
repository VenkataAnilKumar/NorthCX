"""Per-conversation chat tokens for customers' browsers and apps."""
import base64
import json
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import ROLES, AccessControl, InMemoryKeys, LimitConfig
from northcx.audit import InMemoryAudit
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.tokens import MAX_TTL, MIN_TTL, TokenError, TokenSigner, derive_secret
from northcx.widget import WIDGET_HTML

SECRET = b"k" * 32


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ---------------- the signed token ----------------
def test_a_token_carries_exactly_what_the_server_put_in_it():
    clock = Clock()
    s = TokenSigner(SECRET, clock)
    token, c = s.mint(sid="web-1", kid="abcd1234", cid="cust-9", agent="support", ttl=600)
    assert token.startswith("ncxc_") and s.verify(token) == c
    assert (c.sid, c.cid, c.agent, c.kid, c.exp - c.iat) == ("web-1", "cust-9", "support", "abcd1234", 600)
    assert SECRET.decode() not in token and base64.urlsafe_b64decode(token[5:].split(".")[0] + "==")  # readable claims, no secret
    a, _ = s.mint(sid="web-1", kid="k", ttl=600)
    b, _ = s.mint(sid="web-1", kid="k", ttl=600)
    assert a != b  # every token has its own id


def test_tokens_expire_exactly_at_their_time():
    clock = Clock()
    s = TokenSigner(SECRET, clock)
    token, _ = s.mint(sid="s", kid="k", ttl=300)
    clock.t += 299
    s.verify(token)
    clock.t += 1
    with pytest.raises(TokenError) as e:
        s.verify(token)
    assert e.value.kind == "expired"


@pytest.mark.parametrize("ttl", [MIN_TTL - 1, MAX_TTL + 1, 0, -5])
def test_lifetimes_are_bounded(ttl):
    with pytest.raises(ValueError, match="ttlSeconds"):
        TokenSigner(SECRET).mint(sid="s", kid="k", ttl=ttl)


def test_forgeries_and_damage_are_rejected():
    s = TokenSigner(SECRET)
    token, _ = s.mint(sid="mine", kid="k", cid="me")
    payload, sig = token[5:].split(".")
    evil = json.loads(base64.urlsafe_b64decode(payload + "=="))
    evil["sid"], evil["cid"] = "someone-else", "other"
    cases = {
        "payload edited": "ncxc_" + b64(json.dumps(evil).encode()) + "." + sig,
        "signature cut": token[:-3],
        "signature swapped": "ncxc_" + payload + "." + b64(b"x" * 32),
        "another secret": TokenSigner(b"z" * 32).mint(sid="mine", kid="k")[0],
        "wrong prefix": token.replace("ncxc_", "ncxd_", 1),
        "no dot": "ncxc_" + payload,
        "two dots": token + ".x",
        "empty": "ncxc_",
        "huge": "ncxc_" + "A" * 5000 + ".AAAA",
    }
    for name, bad in cases.items():
        with pytest.raises(TokenError) as e:
            s.verify(bad)
        assert e.value.kind in ("malformed", "bad_signature"), name
    assert s.verify(token).sid == "mine"


def test_a_correctly_signed_but_nonsensical_payload_is_malformed_not_a_crash():
    s = TokenSigner(SECRET)
    for body in [{"v": 2}, {"v": 1}, {"v": 1, "sid": "s"}, ["not", "a", "dict"], {"v": 1, "sid": "s", "cid": None, "ag": None, "kid": "k", "jti": "j", "iat": "x", "exp": "y"}]:
        payload = b64(json.dumps(body).encode())
        with pytest.raises(TokenError) as e:
            s.verify(f"ncxc_{payload}.{s._sign(payload)}")
        assert e.value.kind in ("malformed", "unsupported")
    garbage = b64(b"\xff\xfe not json")
    with pytest.raises(TokenError):
        s.verify(f"ncxc_{garbage}.{s._sign(garbage)}")


def test_signing_secrets():
    assert derive_secret(None, None) is None
    a, b = derive_secret("explicit-secret-value", "boot-key"), derive_secret(None, "boot-key")
    assert a != b and derive_secret("explicit-secret-value", "other") == a  # an explicit secret wins and is stable
    assert derive_secret(None, "boot-key") == b != derive_secret(None, "another-key")
    assert b != b"boot-key" and len(b) == 32
    with pytest.raises(ValueError, match="too short"):
        TokenSigner(b"short")


# ---------------- authenticating a token ----------------
async def keys_and_signer(clock=None):
    ac = AccessControl(bootstrap_key="boot" * 10, signer=TokenSigner(SECRET, clock or time.time))
    return ac


async def test_a_token_is_good_while_its_minting_key_is_good():
    ac = await keys_and_signer()
    channel, _ = await ac.issue("shop-web", "channel", "root")
    token, _ = ac.signer.mint(sid="s1", kid=channel.key_id, cid="c1", agent="support")
    who, why = await ac.authenticate_detail(token)
    assert (who.role, who.session_id, who.customer_id, who.agent, why) == ("customer_session", "s1", "c1", "support", None)
    assert who.permissions == {"chat:send", "outbox:read", "feedback:send"} and not who.can("traces:read") and not who.can("chat:mint")
    boot, _ = ac.signer.mint(sid="s2", kid="bootstrap")
    assert (await ac.authenticate(boot)).session_id == "s2"
    await ac.revoke(channel.key_id, "root")
    assert await ac.authenticate_detail(token) == (None, "invalid")  # the minting key is gone, so is every token it minted
    assert (await ac.authenticate(boot)) is not None


async def test_tokens_from_keys_that_may_not_mint_are_refused():
    ac = await keys_and_signer()
    viewer, _ = await ac.issue("viewer-key", "viewer", "root")
    token, _ = ac.signer.mint(sid="s", kid=viewer.key_id)  # as if someone with the signing secret forged it
    assert await ac.authenticate(token) is None
    assert await ac.authenticate(ac.signer.mint(sid="s", kid="no-such-key")[0]) is None
    assert await AccessControl(keys=InMemoryKeys()).authenticate(token) is None  # no signer configured at all


async def test_an_expired_token_is_reported_as_expired_and_nothing_else_is():
    clock = Clock(time.time())
    ac = await keys_and_signer(clock)
    token, _ = ac.signer.mint(sid="s", kid="bootstrap", ttl=MIN_TTL)
    assert (await ac.authenticate_detail(token))[1] is None
    clock.t += MIN_TTL + 1
    assert await ac.authenticate_detail(token) == (None, "expired")
    assert await ac.authenticate_detail("ncxc_garbage.sig") == (None, "invalid")
    assert await ac.authenticate_detail("plain-key") == (None, "invalid")


async def test_tokens_and_keys_are_not_interchangeable():
    ac = await keys_and_signer()
    key, secret = await ac.issue("svc", "channel", "root")
    assert await ac.authenticate(secret) is not None
    token, _ = ac.signer.mint(sid="s", kid=key.key_id)
    assert (await ac.authenticate(token)).role == "customer_session"
    assert await ac.authenticate(token.replace("ncxc_", "ncx_", 1)) is None
    assert "customer_session" not in ROLES
    with pytest.raises(ValueError, match="Unknown role"):
        await ac.issue("sneaky", "customer_session", "root")


# ---------------- through the API ----------------
def build(access=None, api_key="boot" * 10, limits=None, scripted=None):
    traces_store = None
    from northcx.trace import TraceStore
    traces_store = TraceStore()
    llm = ScriptedLLM(scripted or [text("hello")] * 100)
    rt = Runtime(llm, InMemoryStore(), traces_store)
    audit = InMemoryAudit()
    access = access or AccessControl(bootstrap_key=api_key, limits=limits)
    app = create_app(rt, traces_store, {"support": support_agent()}, api_key if access is None else None, access=access, audit=audit)
    return TestClient(app), rt, audit, access, llm


def H(token):
    return {"authorization": f"Bearer {token}"}


async def channel_key(ac):
    return (await ac.issue("shop-web", "channel", "root"))[1]


def run(coro):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro)


def mint(c, key, **body):
    return c.post("/v1/chat-tokens", json=body, headers=H(key))


def test_a_server_mints_a_token_and_the_browser_chats_with_it():
    c, rt, audit, ac, llm = build()
    run(rt.store.set_fact("cust-9", "tier", "gold"))
    run(rt.store.set_fact("cust-evil", "tier", "STOLEN-DATA"))
    key = run(channel_key(ac))
    r = mint(c, key, sessionId="web-123", customerId="cust-9", agent="support", ttlSeconds=1800)
    assert r.status_code == 201
    m = r.json()
    assert m["token"].startswith("ncxc_") and m["sessionId"] == "web-123" and m["customerId"] == "cust-9"
    assert abs(m["expiresAt"] - (time.time() + 1800)) < 5 and key not in json.dumps(m)
    chat = c.post("/v1/agents/support/chat", headers=H(m["token"]),
                  json={"sessionId": "web-123", "message": "hi", "customerId": "cust-evil"})  # the browser tries to be someone else
    assert chat.status_code == 200 and chat.json()["status"] == "completed"
    system = llm.requests[0].system
    assert "gold" in system and "STOLEN-DATA" not in system  # the customer id came from the token
    assert c.get("/v1/sessions/web-123/outbox", headers=H(m["token"])).status_code == 200
    me = c.get("/v1/me", headers=H(m["token"])).json()
    assert me["role"] == "customer_session" and set(me["permissions"]) == {"chat:send", "outbox:read", "feedback:send"}


def test_a_token_works_only_for_its_own_conversation_and_agent():
    c, rt, audit, ac, _ = build()
    key = run(channel_key(ac))
    tok = mint(c, key, sessionId="mine", agent="support").json()["token"]
    other = c.post("/v1/agents/support/chat", headers=H(tok), json={"sessionId": "someone-elses", "message": "hi"})
    assert other.status_code == 403 and other.json()["error"]["code"] == "forbidden"
    assert c.get("/v1/sessions/someone-elses/outbox", headers=H(tok)).status_code == 403
    only_billing = mint(c, key, sessionId="mine", agent="billing").json()["token"]
    assert c.post("/v1/agents/support/chat", headers=H(only_billing), json={"sessionId": "mine", "message": "hi"}).status_code == 403
    any_agent = mint(c, key, sessionId="mine").json()["token"]
    assert c.post("/v1/agents/support/chat", headers=H(any_agent), json={"sessionId": "mine", "message": "hi"}).status_code == 200
    denials = run(audit.list(limit=50, action="auth.denied"))
    assert len([d for d in denials if d.detail.get("reason") == "outside the token's scope"]) == 3
    assert all(tok not in json.dumps(d.__dict__) for d in denials)


def test_a_token_can_do_nothing_else():
    c, rt, audit, ac, _ = build()
    tok = mint(c, run(channel_key(ac)), sessionId="s").json()["token"]
    for method, path in [("GET", "/v1/agents"), ("GET", "/v1/traces"), ("GET", "/v1/approvals"), ("GET", "/v1/handoffs"),
                         ("GET", "/v1/keys"), ("GET", "/v1/audit"), ("GET", "/v1/simulations/scenarios"),
                         ("POST", "/v1/chat-tokens"), ("POST", "/v1/keys"), ("POST", "/v1/agents/support/rollback")]:
        assert c.request(method, path, json={}, headers=H(tok)).status_code == 403, (method, path)


def test_only_the_right_roles_can_mint_and_the_request_is_validated():
    c, rt, audit, ac, _ = build()
    for role in ("viewer", "developer", "reviewer", "release_manager", "auditor"):
        k = run(ac.issue(f"{role}-key", role, "root"))[1]
        assert mint(c, k, sessionId="s").status_code == 403, role
    assert mint(c, "boot" * 10, sessionId="s").status_code == 201 and mint(c, run(channel_key(ac)), sessionId="s").status_code == 201
    key = run(channel_key(ac)) if False else "boot" * 10
    assert mint(c, key, ttlSeconds=MIN_TTL - 1).status_code == 400 and mint(c, key, ttlSeconds=MAX_TTL + 1).status_code == 400
    assert mint(c, key, sessionId="has spaces").status_code == 400 and mint(c, key, sessionId="x" * 201).status_code == 400
    assert mint(c, key, sessionId="a/b").status_code == 400
    generated = mint(c, key).json()
    assert generated["sessionId"].startswith("web-") and len(generated["sessionId"]) > 20
    assert c.post("/v1/agents/support/chat", headers=H(mint(c, key, sessionId=generated["sessionId"]).json()["token"]),
                  json={"sessionId": generated["sessionId"], "message": "hi"}).status_code == 200
    assert abs(mint(c, key, sessionId="d").json()["ttlSeconds"] - 3600) < 1  # default lifetime
    assert c.post("/v1/chat-tokens", json={}).status_code == 401


def test_expired_forged_and_orphaned_tokens_are_refused_distinctly():
    clock = Clock(time.time())
    ac = AccessControl(bootstrap_key="boot" * 10, signer=TokenSigner(SECRET, clock))
    c, rt, audit, _, _ = build(access=ac)
    key = run(channel_key(ac))
    tok = mint(c, key, sessionId="s", ttlSeconds=MIN_TTL).json()["token"]
    ok = lambda t: c.post("/v1/agents/support/chat", headers=H(t), json={"sessionId": "s", "message": "hi"})  # noqa: E731
    assert ok(tok).status_code == 200
    payload, sig = tok[5:].split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged["sid"] = "s2"
    assert ok("ncxc_" + b64(json.dumps(forged).encode()) + "." + sig).status_code == 401
    assert ok("ncxc_nonsense").json()["error"]["code"] == "unauthorized"
    clock.t += MIN_TTL + 5
    r = ok(tok)
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    fresh = mint(c, key, sessionId="s").json()["token"]
    assert ok(fresh).status_code == 200
    key_id = re.match(r"ncx_([0-9a-f]{8})_", key).group(1)
    run(ac.revoke(key_id, "root"))
    assert ok(fresh).status_code == 401 and mint(c, key, sessionId="s").status_code == 401  # revoking the key ends its tokens


def test_tokens_survive_a_restart_when_the_secret_is_stable():
    secret = derive_secret(None, "boot" * 10)
    one = AccessControl(bootstrap_key="boot" * 10, signer=TokenSigner(secret))
    c1, *_ = build(access=one)
    tok = mint(c1, "boot" * 10, sessionId="s").json()["token"]
    two = AccessControl(bootstrap_key="boot" * 10, signer=TokenSigner(derive_secret(None, "boot" * 10)))  # a restarted or second server
    c2, *_ = build(access=two)
    assert c2.post("/v1/agents/support/chat", headers=H(tok), json={"sessionId": "s", "message": "hi"}).status_code == 200
    other = AccessControl(bootstrap_key="different" * 5, signer=TokenSigner(derive_secret(None, "different" * 5)))
    c3, *_ = build(access=other)
    assert c3.post("/v1/agents/support/chat", headers=H(tok), json={"sessionId": "s", "message": "hi"}).status_code == 401


def test_a_conversation_is_still_rate_limited_when_the_browser_holds_the_token():
    ac = AccessControl(bootstrap_key="boot" * 10, limits=LimitConfig(per_key_per_minute=1000, chat_per_session_per_minute=3))
    c, *_ = build(access=ac)
    a = mint(c, "boot" * 10, sessionId="busy").json()["token"]
    b = mint(c, "boot" * 10, sessionId="quiet").json()["token"]
    send = lambda t, sid: c.post("/v1/agents/support/chat", headers=H(t), json={"sessionId": sid, "message": "hi"}).status_code  # noqa: E731
    assert [send(a, "busy") for _ in range(5)] == [200, 200, 200, 429, 429] and send(b, "quiet") == 200


def test_open_mode_needs_no_token_but_can_still_mint_one():
    c = TestClient(create_app(Runtime(ScriptedLLM([text("hi")] * 5), InMemoryStore(), __import__("northcx.trace", fromlist=["TraceStore"]).TraceStore()),
                              __import__("northcx.trace", fromlist=["TraceStore"]).TraceStore(), {"support": support_agent()}))
    assert c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "hi"}).status_code == 200
    assert c.post("/v1/chat-tokens", json={"sessionId": "s"}).status_code == 201


def test_the_demo_page_uses_a_fragment_token_and_not_a_key():
    assert "location.hash" in WIDGET_HTML and "token=" in WIDGET_HTML and "history.replaceState" in WIDGET_HTML
    assert "sessionStorage" in WIDGET_HTML and "type=\"password\"" not in WIDGET_HTML and "Channel key" not in WIDGET_HTML
    assert "token_expired" in WIDGET_HTML and "/outbox" in WIDGET_HTML
