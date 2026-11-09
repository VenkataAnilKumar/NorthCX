import os
import re
import sys
from northcx.access import AccessControl, LimitConfig
from northcx.sso import Sso, config_from_env as sso_config_from_env
from northcx.tokens import TokenSigner, derive_secret
from northcx.db import PgKeys, PgLimiter, create_engine
from northcx.secrets import ConfigError, env_or_file
from types import SimpleNamespace


def _has_keys(db_url: str, access: AccessControl) -> bool:
    """Check for keys with a short-lived connection, before the server's event loop starts."""
    import asyncio

    from sqlalchemy.pool import NullPool

    async def check() -> bool:
        engine = create_engine(db_url, poolclass=NullPool)
        try:
            return await AccessControl(PgKeys(engine), env_or_file("NORTHCX_API_KEY")).enabled()
        finally:
            await engine.dispose()

    return asyncio.run(check())


def build_security(c: SimpleNamespace) -> None:
    """Rate limits, token signing, access control, single sign-on and CORS."""
    api_key = c.api_key
    db_url = c.db_url
    keys_repo = c.keys_repo
    runtime = c.runtime
    engine = c.engine
    limits = None
    if os.environ.get("NORTHCX_RATE_LIMITS", "on") != "off":
        env = os.environ
        limits = LimitConfig(float(env.get("NORTHCX_RATE_LIMIT_PER_MINUTE", 600)),
                             float(env.get("NORTHCX_CHAT_PER_SESSION_PER_MINUTE", 30)),
                             float(env.get("NORTHCX_AUTH_FAILURES_PER_MINUTE", 20)),
                             float(env.get("NORTHCX_CHANNEL_RATE_LIMIT_PER_MINUTE", 6000)))
    token_secret = derive_secret(env_or_file("NORTHCX_TOKEN_SECRET"), api_key)
    if token_secret is None:
        import secrets as _secrets

        token_secret = _secrets.token_bytes(32)
        print("NOTE: chat tokens use a random signing secret (set NORTHCX_TOKEN_SECRET or NORTHCX_API_KEY): tokens stop "
              "working when the server restarts and are not valid across several servers.")
    shared_limiter = PgLimiter(engine) if c.limits_backend == "postgres" else None
    if shared_limiter is not None:
        runtime.shared_limiter = shared_limiter
        print("Rate limits and the daily token budget are shared through the database (every server process counts against one limit).")
    access = AccessControl(keys_repo, api_key, limits, limiter=shared_limiter, signer=TokenSigner(token_secret))
    import asyncio

    if asyncio.run(access.enabled()) if db_url is None else _has_keys(db_url, access):
        print("Authentication is ON (API keys required).")
    elif os.environ.get("NORTHCX_REQUIRE_AUTH") == "1":
        sys.exit("NORTHCX_REQUIRE_AUTH=1 but no API key exists. Set NORTHCX_API_KEY, or create one with "
                 "`python -m northcx.keys create --name <name> --role admin`.")
    else:
        print("WARNING: authentication is OFF. Anyone who can reach this server has admin access. "
              "Set NORTHCX_API_KEY (and NORTHCX_REQUIRE_AUTH=1) before exposing it.")

    sso = None
    try:
        sso_cfg = sso_config_from_env(os.environ, env_or_file("NORTHCX_SSO_CLIENT_SECRET") or "")
    except (ValueError, ConfigError) as e:
        sys.exit(f"Single sign-on: {e}")
    if sso_cfg is not None:
        if not (os.environ.get("NORTHCX_API_KEY") or db_url):
            sys.exit("Single sign-on needs API-key authentication: set NORTHCX_API_KEY (people sign in for a session key with a role)")
        sso = Sso(sso_cfg, token_secret)
        print(f"Single sign-on is ON ({sso_cfg.issuer}); sessions last {sso_cfg.session_hours:g} hours.")

    cors_origins = [o.strip().rstrip("/") for o in os.environ.get("NORTHCX_CORS_ORIGINS", "").split(",") if o.strip()]
    for o in cors_origins:
        if o == "*" or not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?|http://(localhost|127\.0\.0\.1)(:\d+)?", o):
            sys.exit(f"NORTHCX_CORS_ORIGINS: '{o}' must be an https origin such as https://www.example.com (no wildcards, no paths)")
    from northcx.groups import GroupService
    from northcx.db import PgGroups
    from northcx.tenancy import TenantService
    from northcx.db import PgTenants
    access.tenants = TenantService(PgTenants(c.engine) if db_url else None, preview=os.environ.get("NORTHCX_TENANCY_PREVIEW") == "1")
    access.groups = GroupService(PgGroups(c.engine) if db_url else None)
    scim_token = env_or_file("NORTHCX_SCIM_TOKEN")
    if scim_token:
        from northcx.access import hash_secret
        from northcx.db import PgScimUsers
        from northcx.scim import ScimService
        if len(scim_token) < 32:
            sys.exit("NORTHCX_SCIM_TOKEN must be at least 32 characters (a long random value; the identity provider sends it as a bearer token)")
        access.scim = ScimService(PgScimUsers(c.engine) if db_url else None, access.groups, access, "/scim/v2",
                                  require_provisioned=os.environ.get("NORTHCX_SCIM_REQUIRE_PROVISIONED", "") == "1")
        access.scim.token_hash = hash_secret(scim_token)
        print("SCIM provisioning is ON (/scim/v2).")
    c.access = access
    c.cors_origins = cors_origins
    c.sso = sso
