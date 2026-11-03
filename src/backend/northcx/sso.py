"""Single sign-on for the Studio (P5): OpenID Connect, authorization-code flow with PKCE.

NorthCX acts as a relying party. The browser is sent to the company's identity provider; on return, NorthCX exchanges the code,
checks the signed ID token (signature, issuer, audience, expiry, nonce), maps the person's groups to one of its roles, and issues
an ordinary short-lived session key with that role. Everything after sign-in (permissions, audit, revocation, rate limits) is the
same as for any other key. Sign-in state lives in a signed cookie, so no server memory is needed and several replicas can serve it.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils

# Roles a person can get by signing in, most powerful first. `channel` is for servers and is never given to people.
PRIVILEGE = ("admin", "release_manager", "developer", "reviewer", "auditor", "viewer")
DEFAULT_SESSION_HOURS, MAX_SESSION_HOURS = 8.0, 24.0
STATE_TTL = 600
LEEWAY = 60


class SsoError(Exception):
    """Sign-in failed. The message is safe to show; `detail` is for the audit log."""

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message)
        self.detail = detail or message


@dataclass
class SsoConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    role_claim: str = "groups"
    role_map: dict[str, str] = field(default_factory=dict)
    default_role: str | None = None
    allowed_domains: list[str] = field(default_factory=list)
    session_hours: float = DEFAULT_SESSION_HOURS
    landing: str = "/sso"
    scopes: str = "openid email profile"

    def __post_init__(self) -> None:
        self.issuer = self.issuer.rstrip("/")
        for url, what in ((self.issuer, "issuer"), (self.redirect_uri, "redirect URI")):
            p = urlparse(url)
            local = p.hostname in ("localhost", "127.0.0.1", "::1")
            if p.scheme != "https" and not (p.scheme == "http" and local):
                raise ValueError(f"The single sign-on {what} must use https (http is allowed only for localhost)")
        bad = sorted({r for r in [*self.role_map.values(), self.default_role] if r is not None and r not in PRIVILEGE})
        if bad:
            raise ValueError(f"Single sign-on can give these roles: {', '.join(PRIVILEGE)} (not {', '.join(bad)})")
        if not 0 < self.session_hours <= MAX_SESSION_HOURS:
            raise ValueError(f"The single sign-on session must last between 0 and {MAX_SESSION_HOURS:g} hours")
        if not self.landing.startswith("/") or self.landing.startswith("//") or "\\" in self.landing:
            raise ValueError("The single sign-on landing page must be a path on this site")
        if not self.role_map and self.default_role is None:
            raise ValueError("Set NORTHCX_SSO_ROLE_MAP or NORTHCX_SSO_DEFAULT_ROLE, otherwise nobody could sign in")


def parse_role_map(text: str | None) -> dict[str, str]:
    """`group=role,other-group=role` (a group name may not contain a comma or an equals sign)."""
    out: dict[str, str] = {}
    for part in (text or "").split(","):
        if not part.strip():
            continue
        group, sep, role = part.partition("=")
        if not sep or not group.strip() or not role.strip():
            raise ValueError(f"Bad single sign-on role map entry '{part.strip()}' (expected group=role)")
        out[group.strip()] = role.strip()
    return out


def config_from_env(env: Mapping[str, str], secret: str) -> SsoConfig | None:
    """None when single sign-on is not configured (no issuer)."""
    issuer = env.get("NORTHCX_SSO_ISSUER", "").strip()
    if not issuer:
        return None
    need = {"NORTHCX_SSO_CLIENT_ID": env.get("NORTHCX_SSO_CLIENT_ID", "").strip(), "NORTHCX_SSO_REDIRECT_URI": env.get("NORTHCX_SSO_REDIRECT_URI", "").strip()}
    missing = [k for k, v in need.items() if not v]
    if missing or not secret:
        raise ValueError("Single sign-on needs " + ", ".join([*missing, *(["NORTHCX_SSO_CLIENT_SECRET"] if not secret else [])]))
    return SsoConfig(
        issuer, need["NORTHCX_SSO_CLIENT_ID"], secret, need["NORTHCX_SSO_REDIRECT_URI"],
        env.get("NORTHCX_SSO_ROLE_CLAIM", "").strip() or "groups", parse_role_map(env.get("NORTHCX_SSO_ROLE_MAP")),
        env.get("NORTHCX_SSO_DEFAULT_ROLE", "").strip() or None,
        [d.strip().lower().lstrip("@") for d in env.get("NORTHCX_SSO_ALLOWED_DOMAINS", "").split(",") if d.strip()],
        float(env.get("NORTHCX_SSO_SESSION_HOURS", "").strip() or DEFAULT_SESSION_HOURS),
        env.get("NORTHCX_SSO_LANDING", "").strip() or "/sso")


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------------- ID token verification ----------------
def public_key(jwk: Mapping[str, Any]) -> Any:
    kty = jwk.get("kty")
    if kty == "RSA":
        return rsa.RSAPublicNumbers(int.from_bytes(unb64(jwk["e"]), "big"), int.from_bytes(unb64(jwk["n"]), "big")).public_key()
    if kty == "EC" and jwk.get("crv") == "P-256":
        return ec.EllipticCurvePublicNumbers(int.from_bytes(unb64(jwk["x"]), "big"), int.from_bytes(unb64(jwk["y"]), "big"), ec.SECP256R1()).public_key()
    raise SsoError("The identity provider uses a key type NorthCX does not support", f"unsupported key {kty}")


def verify_id_token(token: str, jwks: Mapping[str, Any], cfg: SsoConfig, nonce: str, now: float | None = None) -> dict[str, Any]:
    """The claims of a correctly signed, current ID token meant for this client, or SsoError. Only RS256 and ES256 are accepted."""
    now = time.time() if now is None else now
    try:
        head_b64, body_b64, sig_b64 = token.split(".")
        header, claims = json.loads(unb64(head_b64)), json.loads(unb64(body_b64))
        signature = unb64(sig_b64)
    except (ValueError, TypeError):
        raise SsoError("The identity provider returned a malformed token", "malformed id token") from None
    alg = header.get("alg")
    if alg not in ("RS256", "ES256"):
        raise SsoError("The identity provider signed the token in a way NorthCX does not accept", f"alg {alg}")
    candidates = [k for k in jwks.get("keys", []) if k.get("use", "sig") == "sig" and (header.get("kid") is None or k.get("kid") == header.get("kid"))]
    if not candidates:
        raise SsoError("The token was signed with an unknown key", f"kid {header.get('kid')}")
    signed = f"{head_b64}.{body_b64}".encode()
    ok = False
    for jwk in candidates:
        try:
            key = public_key(jwk)
            if alg == "RS256" and isinstance(key, rsa.RSAPublicKey):
                key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
            elif alg == "ES256" and isinstance(key, ec.EllipticCurvePublicKey) and len(signature) == 64:
                key.verify(utils.encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")), signed, ec.ECDSA(hashes.SHA256()))
            else:
                continue
            ok = True
            break
        except (InvalidSignature, SsoError, KeyError, ValueError):
            continue
    if not ok:
        raise SsoError("The token's signature is not valid", "bad signature")
    if claims.get("iss") != cfg.issuer:
        raise SsoError("The token was issued by a different identity provider", f"iss {claims.get('iss')}")
    aud = claims.get("aud")
    audiences = aud if isinstance(aud, list) else [aud]
    if cfg.client_id not in audiences or (len(audiences) > 1 and claims.get("azp") != cfg.client_id):
        raise SsoError("The token was not issued for this application", "audience mismatch")
    exp, iat = claims.get("exp"), claims.get("iat", now)
    if not isinstance(exp, (int, float)) or exp + LEEWAY < now or not isinstance(iat, (int, float)) or iat - LEEWAY > now:
        raise SsoError("The sign-in has expired; try again", "token time")
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SsoError("The sign-in response did not match this browser; try again", "nonce mismatch")
    if not claims.get("sub"):
        raise SsoError("The token has no subject", "no sub")
    return claims


# ---------------- who gets which role ----------------
def role_for(claims: Mapping[str, Any], cfg: SsoConfig) -> str | None:
    """The most powerful role any of the person's groups maps to, else the default, else None (sign-in refused)."""
    raw = claims.get(cfg.role_claim, [])
    groups = [raw] if isinstance(raw, str) else [g for g in raw if isinstance(g, str)] if isinstance(raw, list) else []
    granted = {cfg.role_map[g] for g in groups if g in cfg.role_map}
    for role in PRIVILEGE:
        if role in granted:
            return role
    return cfg.default_role


@dataclass
class Login:
    subject: str
    email: str
    name: str
    role: str


def login_from_claims(claims: Mapping[str, Any], cfg: SsoConfig) -> Login:
    email = str(claims.get("email", "")).strip().lower()
    if cfg.allowed_domains:
        if not email or claims.get("email_verified") is False or email.rpartition("@")[2] not in cfg.allowed_domains:
            raise SsoError("Your email address is not allowed to sign in here", f"domain not allowed: {email.rpartition('@')[2] or 'none'}")
    role = role_for(claims, cfg)
    if role is None:
        raise SsoError("Your account has no role here; ask an administrator to add you to a group", f"no role for {email or claims['sub']}")
    name = email or str(claims.get("name") or claims["sub"])
    return Login(str(claims["sub"]), email or str(claims["sub"]), str(claims.get("name") or name)[:80], role)


# ---------------- the flow ----------------
class Sso:
    def __init__(self, cfg: SsoConfig, secret: bytes, client: httpx.AsyncClient | None = None, clock: Callable[[], float] = time.time):
        self.cfg, self._secret, self._clock = cfg, secret, clock
        self._http = client or httpx.AsyncClient(timeout=10.0, follow_redirects=False)
        self._meta: tuple[float, dict[str, Any]] | None = None
        self._jwks: tuple[float, dict[str, Any]] | None = None

    def _sign(self, payload: str) -> str:
        return b64(hmac.new(self._secret, b"sso-state:" + payload.encode(), hashlib.sha256).digest())

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            r = await self._http.get(url)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            raise SsoError("The identity provider could not be reached", f"fetch failed: {url}") from None
        if not isinstance(data, dict):
            raise SsoError("The identity provider sent an unexpected answer", f"not an object: {url}")
        return data

    async def metadata(self) -> dict[str, Any]:
        now = self._clock()
        if self._meta and now - self._meta[0] < 3600:
            return self._meta[1]
        meta = await self._get_json(f"{self.cfg.issuer}/.well-known/openid-configuration")
        if meta.get("issuer") != self.cfg.issuer:
            raise SsoError("The identity provider's configuration does not match the configured issuer", "issuer mismatch")
        for k in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            u = urlparse(str(meta.get(k, "")))
            if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")):
                raise SsoError("The identity provider's configuration is incomplete or insecure", f"bad {k}")
        self._meta = (now, meta)
        return meta

    async def keys(self, force: bool = False) -> dict[str, Any]:
        now = self._clock()
        if self._jwks and not force and now - self._jwks[0] < 3600:
            return self._jwks[1]
        if self._jwks and force and now - self._jwks[0] < 60:  # an unknown key id cannot make us refetch more than once a minute
            return self._jwks[1]
        jwks = await self._get_json((await self.metadata())["jwks_uri"])
        self._jwks = (now, jwks)
        return jwks

    async def begin(self) -> tuple[str, str]:
        """(URL to send the browser to, value of the state cookie)."""
        meta = await self.metadata()
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        challenge = b64(hashlib.sha256(verifier.encode()).digest())
        query = urlencode({"response_type": "code", "client_id": self.cfg.client_id, "redirect_uri": self.cfg.redirect_uri, "scope": self.cfg.scopes,
                           "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"})
        payload = b64(json.dumps({"s": state, "n": nonce, "v": verifier, "x": int(self._clock() + STATE_TTL)}, separators=(",", ":")).encode())
        return f"{meta['authorization_endpoint']}?{query}", f"{payload}.{self._sign(payload)}"

    def _open_cookie(self, cookie: str | None, state: str | None) -> dict[str, Any]:
        try:
            payload, _, sig = (cookie or "").partition(".")
            if not payload or not hmac.compare_digest(self._sign(payload), sig):
                raise ValueError
            data = json.loads(unb64(payload))
            if data["x"] < self._clock() or not state or not hmac.compare_digest(str(data["s"]), state):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise SsoError("The sign-in could not be matched to this browser; start again", "bad state") from None
        return data

    async def finish(self, code: str | None, state: str | None, cookie: str | None) -> Login:
        st = self._open_cookie(cookie, state)
        if not code:
            raise SsoError("The identity provider did not return a code", "no code")
        meta = await self.metadata()
        try:
            r = await self._http.post(meta["token_endpoint"], data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": self.cfg.redirect_uri, "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret, "code_verifier": st["v"]}, headers={"accept": "application/json"})
            body = r.json()
        except (httpx.HTTPError, ValueError):
            raise SsoError("The identity provider could not be reached", "token request failed") from None
        if r.status_code != 200 or not isinstance(body, dict) or not isinstance(body.get("id_token"), str):
            raise SsoError("The identity provider refused the sign-in", f"token endpoint {r.status_code}: {str(body.get('error') if isinstance(body, dict) else '')[:60]}")
        try:
            claims = verify_id_token(body["id_token"], await self.keys(), self.cfg, st["n"], self._clock())
        except SsoError as e:
            if e.detail.startswith("kid"):  # the provider may have rotated its keys
                claims = verify_id_token(body["id_token"], await self.keys(force=True), self.cfg, st["n"], self._clock())
            else:
                raise
        return login_from_claims(claims, self.cfg)
