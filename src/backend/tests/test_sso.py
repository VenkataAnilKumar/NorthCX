"""Single sign-on (P5): OpenID Connect with PKCE, ID token checks, role mapping, session keys, audit, logout."""
import asyncio
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.sso import Sso, SsoConfig, SsoError, config_from_env, login_from_claims, parse_role_map, role_for, verify_id_token
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

ISSUER, CLIENT = "https://idp.example.com", "northcx-studio"
REDIRECT = "https://studio.example.com/api/northcx/auth/sso/callback"
KEY = "boot" * 10
NOW = 1_800_000_000.0


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def num(n: int) -> str:
    return b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))


RSA_KEY, RSA2_KEY, EC_KEY = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048), ec.generate_private_key(ec.SECP256R1())


def jwk_rsa(key, kid):
    n = key.public_key().public_numbers()
    return {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": num(n.n), "e": num(n.e)}


def jwk_ec(key, kid):
    n = key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256", "kid": kid, "use": "sig", "x": b64(n.x.to_bytes(32, "big")), "y": b64(n.y.to_bytes(32, "big"))}


JWKS = {"keys": [jwk_rsa(RSA_KEY, "r1"), jwk_ec(EC_KEY, "e1")]}


def sign(claims, key=RSA_KEY, kid="r1", alg="RS256"):
    head = b64(json.dumps({"alg": alg, "kid": kid}).encode())
    body = b64(json.dumps(claims).encode())
    data = f"{head}.{body}".encode()
    if alg == "RS256":
        sig = key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    elif alg == "ES256":
        r, s = utils.decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
        sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    else:
        sig = b"x"
    return f"{head}.{body}.{b64(sig)}"


def claims(**kw):
    c = {"iss": ISSUER, "aud": CLIENT, "sub": "u-1", "email": "rae@corp.com", "email_verified": True, "name": "Rae", "groups": ["cx-editors"],
         "iat": NOW - 5, "exp": NOW + 300, "nonce": "n0"}
    c.update(kw)
    return c


def cfg(**kw):
    base = dict(issuer=ISSUER, client_id=CLIENT, client_secret="shh", redirect_uri=REDIRECT, role_map={"cx-admins": "admin", "cx-editors": "developer", "cx-readers": "viewer"})
    base.update(kw)
    return SsoConfig(**base)


def test_configuration_is_checked():
    assert cfg().landing == "/sso" and parse_role_map("a=admin, b = viewer") == {"a": "admin", "b": "viewer"}
    for kw, msg in [({"issuer": "http://idp.example.com"}, "https"), ({"redirect_uri": "http://studio.example.com/cb"}, "https"), ({"role_map": {"g": "channel"}}, "can give"),
                    ({"role_map": {"g": "root"}}, "can give"), ({"session_hours": 48}, "between"), ({"session_hours": 0}, "between"), ({"landing": "//evil.com"}, "path on this site"),
                    ({"landing": "https://evil.com"}, "path on this site"), ({"role_map": {}}, "otherwise nobody")]:
        with pytest.raises(ValueError, match=msg):
            cfg(**kw)
    assert cfg(issuer="http://localhost:8080", redirect_uri="http://localhost:3000/cb").issuer == "http://localhost:8080"
    with pytest.raises(ValueError, match="bad|Bad"):
        parse_role_map("novalue")
    assert config_from_env({}, "") is None
    with pytest.raises(ValueError, match="NORTHCX_SSO_CLIENT_ID"):
        config_from_env({"NORTHCX_SSO_ISSUER": ISSUER}, "s")
    c = config_from_env({"NORTHCX_SSO_ISSUER": ISSUER + "/", "NORTHCX_SSO_CLIENT_ID": CLIENT, "NORTHCX_SSO_REDIRECT_URI": REDIRECT, "NORTHCX_SSO_ROLE_MAP": "g=viewer",
                         "NORTHCX_SSO_ALLOWED_DOMAINS": "@Corp.com, other.org", "NORTHCX_SSO_SESSION_HOURS": "4"}, "s")
    assert c.issuer == ISSUER and c.allowed_domains == ["corp.com", "other.org"] and c.session_hours == 4 and c.role_claim == "groups"


def test_id_tokens_are_verified_completely():
    ok = verify_id_token(sign(claims()), JWKS, cfg(), "n0", NOW)
    assert ok["email"] == "rae@corp.com"
    assert verify_id_token(sign(claims(), EC_KEY, "e1", "ES256"), JWKS, cfg(), "n0", NOW)["sub"] == "u-1"
    assert verify_id_token(sign(claims(aud=[CLIENT, "other"], azp=CLIENT)), JWKS, cfg(), "n0", NOW)
    bad = {
        "signature": sign(claims(), RSA2_KEY, "r1"), "issuer": sign(claims(iss="https://evil.example.com")), "audience": sign(claims(aud="someone-else")),
        "azp": sign(claims(aud=[CLIENT, "other"])), "expired": sign(claims(exp=NOW - 120)), "future": sign(claims(iat=NOW + 600)), "nonce": sign(claims(nonce="other")),
        "no sub": sign({k: v for k, v in claims().items() if k != "sub"}), "none alg": sign(claims(), alg="none"), "hs256": sign(claims(), alg="HS256"),
        "unknown kid": sign(claims(), RSA_KEY, "nope"), "garbage": "a.b.c", "two parts": "a.b", "tampered": sign(claims()).rsplit(".", 1)[0] + "." + b64(b"0" * 256),
    }
    for name, tok in bad.items():
        with pytest.raises(SsoError):
            verify_id_token(tok, JWKS, cfg(), "n0", NOW)
        assert name
    # a key from a different algorithm family cannot verify the other family's signature
    with pytest.raises(SsoError):
        verify_id_token(sign(claims(), EC_KEY, "r1", "ES256"), JWKS, cfg(), "n0", NOW)
    assert verify_id_token(sign(claims(exp=NOW - 30)), JWKS, cfg(), "n0", NOW)  # a minute of clock difference is tolerated


def test_roles_come_from_groups_and_the_strongest_wins():
    c = cfg()
    assert role_for({"groups": ["cx-readers", "cx-admins"]}, c) == "admin" and role_for({"groups": ["cx-editors", "cx-readers"]}, c) == "developer"
    assert role_for({"groups": "cx-readers"}, c) == "viewer" and role_for({"groups": ["unknown"]}, c) is None and role_for({}, c) is None
    assert role_for({"groups": ["unknown"]}, cfg(default_role="viewer")) == "viewer" and role_for({"roles": ["cx-admins"]}, cfg(role_claim="roles")) == "admin"
    assert role_for({"groups": [1, None, {"a": 1}]}, c) is None
    with pytest.raises(SsoError, match="no role"):
        login_from_claims(claims(groups=["x"]), c)
    dom = cfg(allowed_domains=["corp.com"])
    assert login_from_claims(claims(), dom).role == "developer"
    for bad in (claims(email="rae@evil.com"), claims(email_verified=False), claims(email="")):
        with pytest.raises(SsoError, match="not allowed"):
            login_from_claims(bad, dom)


class Idp:
    """A tiny identity provider that checks what a real one would: the client secret, the redirect URI and the PKCE verifier."""

    def __init__(self):
        self.auth = {}
        self.fail_token = False
        self.next_claims = {}
        self.requests = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(str(req.url))
        path = req.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize", "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks"})
        if path == "/jwks":
            return httpx.Response(200, json=JWKS)
        if path == "/token":
            form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            a = self.auth.get(form.get("code"))
            challenge = b64(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
            if self.fail_token or a is None or form["client_secret"] != "shh" or form["redirect_uri"] != REDIRECT or a["code_challenge"] != challenge:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": sign(claims(**{"nonce": a["nonce"], "iat": time.time() - 5, "exp": time.time() + 300, **self.next_claims}))})
        return httpx.Response(404)

    def authorize(self, url: str) -> tuple[str, str]:
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["response_type"] == "code" and q["client_id"] == CLIENT and q["redirect_uri"] == REDIRECT and q["code_challenge_method"] == "S256" and "openid" in q["scope"]
        code = "code-" + q["state"][:6]
        self.auth[code] = q
        return code, q["state"]


def build(idp=None, **cfg_kw):
    idp = idp or Idp()
    ac = AccessControl(bootstrap_key=KEY)
    sso = Sso(cfg(**cfg_kw), b"s" * 32, httpx.AsyncClient(transport=httpx.MockTransport(idp.handler)))
    traces = TraceStore()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), traces)
    app = create_app(rt, traces, {"support": support_agent()}, access=ac, sso=sso)
    return TestClient(app, base_url="https://testserver", follow_redirects=False), idp, ac


def sign_in(c, idp, state_override=None, **claims_over):
    idp.next_claims = claims_over
    r = c.get("/auth/sso/login")
    assert r.status_code == 303
    code, state = idp.authorize(r.headers["location"])
    return c.get("/auth/sso/callback", params={"code": code, "state": state_override or state})


def test_the_full_sign_in_issues_a_role_limited_session_key():
    c, idp, ac = build()
    assert c.get("/auth/sso/config").json() == {"enabled": True, "loginUrl": "/auth/sso/login"}
    r = c.get("/auth/sso/login")
    assert r.status_code == 303 and r.headers["location"].startswith(f"{ISSUER}/authorize?") and "northcx_sso=" in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"] and "samesite=lax" in r.headers["set-cookie"].lower() and "Secure" in r.headers["set-cookie"]
    r = sign_in(c, idp)
    assert r.status_code == 303 and r.headers["location"].startswith("/sso#token=ncx_") and r.headers["cache-control"] == "no-store"
    token = r.headers["location"].split("token=")[1]
    h = {"authorization": f"Bearer {token}"}
    me = c.get("/v1/me", headers=h).json()
    assert me["role"] == "developer" and me["name"] == "sso: rae@corp.com" and "releases:publish" not in me["permissions"] and "versions:create" in me["permissions"]
    assert c.get("/v1/keys", headers=h).status_code == 403  # a developer cannot manage keys
    admin_keys = c.get("/v1/keys", headers={"authorization": f"Bearer {KEY}"}).json()["keys"]
    sess = next(k for k in admin_keys if k["createdBy"] == "sso")
    assert sess["expiresAt"] - time.time() < 8 * 3600 + 5 and sess["role"] == "developer"
    audit = c.get("/v1/audit?limit=20", headers={"authorization": f"Bearer {KEY}"}).json()["entries"]
    assert any(e["action"] == "sso.login" and e["actor"] == "rae@corp.com" for e in audit) and token not in json.dumps(audit)
    assert c.post("/v1/me/logout", headers=h).json() == {"revoked": True}
    assert c.get("/v1/me", headers=h).status_code == 401  # the session is over at once
    assert c.post("/v1/me/logout", headers={"authorization": f"Bearer {KEY}"}).json() == {"revoked": False}  # other keys are left alone


def test_a_second_sign_in_gives_a_new_session_and_admin_groups_give_admin():
    c, idp, ac = build()
    t1 = sign_in(c, idp).headers["location"].split("token=")[1]
    t2 = sign_in(c, idp, groups=["cx-admins"]).headers["location"].split("token=")[1]
    assert t1 != t2 and c.get("/v1/me", headers={"authorization": f"Bearer {t1}"}).json()["role"] == "developer"
    assert c.get("/v1/me", headers={"authorization": f"Bearer {t2}"}).json()["role"] == "admin"


def denied(c, r, why):
    assert r.status_code == 303 and r.headers["location"].startswith("/sso?error="), r.headers.get("location")
    audit = c.get("/v1/audit?limit=20", headers={"authorization": f"Bearer {KEY}"}).json()["entries"]
    assert any(e["action"] == "sso.denied" and why in json.dumps(e["detail"]) for e in audit), audit
    assert not any(e["action"] == "sso.login" for e in audit)


def test_every_way_sign_in_can_go_wrong_is_refused_and_audited():
    c, idp, ac = build()
    denied(c, sign_in(c, idp, groups=["nobody"]), "no role")
    c2, idp2, _ = build()
    denied(c2, sign_in(c2, idp2, state_override="forged"), "bad state")
    c3, idp3, _ = build()
    c3.get("/auth/sso/login")
    denied(c3, c3.get("/auth/sso/callback", params={"code": "x", "state": "y"}), "bad state")
    c4, idp4, _ = build()
    idp4.fail_token = True
    denied(c4, sign_in(c4, idp4), "token endpoint 400")
    c5, idp5, _ = build()
    denied(c5, c5.get("/auth/sso/callback", params={"error": "access_denied"}), "provider error")
    c6, idp6, _ = build(allowed_domains=["other.org"])
    denied(c6, sign_in(c6, idp6), "domain not allowed")
    c7, idp7, _ = build()
    denied(c7, sign_in(c7, idp7, nonce="replayed"), "nonce")  # an ID token for a different sign-in attempt


def test_a_code_cannot_be_used_without_the_browsers_own_state_cookie():
    c, idp, ac = build()
    r = c.get("/auth/sso/login")
    code, state = idp.authorize(r.headers["location"])
    attacker = TestClient(c.app, base_url="https://testserver", follow_redirects=False)  # a different browser, with the victim's code and state but no cookie
    denied(attacker, attacker.get("/auth/sso/callback", params={"code": code, "state": state}), "bad state")


def test_an_unreachable_or_inconsistent_identity_provider_fails_cleanly():
    idp = Idp()
    c, _, _ = build(idp)
    idp.handler = lambda req: httpx.Response(500)  # type: ignore[method-assign]
    c2 = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {"support": support_agent()}, access=AccessControl(bootstrap_key=KEY),
                                sso=Sso(cfg(), b"s" * 32, httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))))), follow_redirects=False)
    r = c2.get("/auth/sso/login")
    assert r.status_code == 303 and r.headers["location"].startswith("/sso?error=")
    wrong = Sso(cfg(), b"s" * 32, httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"issuer": "https://other.example.com"}))))
    with pytest.raises(SsoError, match="does not match"):
        asyncio.run(wrong.metadata())
    insecure = Sso(cfg(), b"s" * 32, httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        "issuer": ISSUER, "authorization_endpoint": "http://idp.example.com/a", "token_endpoint": f"{ISSUER}/t", "jwks_uri": f"{ISSUER}/j"}))))
    with pytest.raises(SsoError, match="insecure"):
        asyncio.run(insecure.metadata())


def test_rotated_signing_keys_are_picked_up_once_a_minute_at_most():
    clock = [NOW]
    fetched = []

    def handler(req):
        fetched.append(req.url.path)
        if req.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/a", "token_endpoint": f"{ISSUER}/t", "jwks_uri": f"{ISSUER}/jwks"})
        return httpx.Response(200, json={"keys": [jwk_rsa(RSA_KEY, "r1")] if len(fetched) < 3 else [jwk_rsa(RSA_KEY, "r1"), jwk_rsa(RSA2_KEY, "r2")]})
    s = Sso(cfg(), b"s" * 32, httpx.AsyncClient(transport=httpx.MockTransport(handler)), lambda: clock[0])

    async def go():
        await s.keys()
        n = len(fetched)
        await s.keys(force=True)
        assert len(fetched) == n  # too soon to ask again
        clock[0] += 61
        return await s.keys(force=True)
    assert {k["kid"] for k in asyncio.run(go())["keys"]} == {"r1", "r2"}


def test_without_sso_configured_the_routes_say_so():
    ac = AccessControl(bootstrap_key=KEY)
    c = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {"support": support_agent()}, access=ac), follow_redirects=False)
    assert c.get("/auth/sso/config").json() == {"enabled": False, "loginUrl": None}
    assert c.get("/auth/sso/login").status_code == 404 and c.get("/auth/sso/callback").status_code == 404


def test_session_keys_do_not_count_as_a_lasting_admin_and_cannot_be_channel_keys():
    c, idp, ac = build()
    loop = asyncio.new_event_loop()
    with pytest.raises(ValueError):
        loop.run_until_complete(ac.issue_session("x", "channel", 1))
    k, _ = loop.run_until_complete(ac.issue_session("boss", "admin", 1))
    ac2 = AccessControl()  # no bootstrap key: the only other admin is an SSO session
    only, _ = loop.run_until_complete(ac2.issue("root", "admin", "setup"))
    loop.run_until_complete(ac2.issue_session("boss", "admin", 1))
    with pytest.raises(ValueError, match="last active admin"):
        loop.run_until_complete(ac2.revoke(only.key_id, "root"))
