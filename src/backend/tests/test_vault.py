"""WP2.5: each tenant's secrets are sealed with the operator's master key and tied to their tenant; a tenant can have its own model provider."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.audit import InMemoryAudit
from northcx.budget_settings import InMemorySettings
from northcx.llm import ScriptedLLM, text
from northcx.platform_api import create_platform_app
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.tenancy import TENANT, TenantService
from northcx.tenant_limits import TenantLimits
from northcx.trace import TraceStore
from northcx.types import LLMRequest
from northcx.vault import InMemorySecrets, TenantLLM, Vault, VaultError, open_, seal, validate_provider

MASTER = "m" * 40
PKEY = "p" * 40
P = {"authorization": f"Bearer {PKEY}"}


def test_a_sealed_value_opens_only_for_its_tenant_and_name_and_with_the_right_key():
    sealed = seal(MASTER.encode(), "acme", "provider_key", "sk-live-secret")
    assert "sk-live-secret" not in sealed and open_([MASTER.encode()], "acme", "provider_key", sealed) == "sk-live-secret"
    for tenant, name, masters in (("globex", "provider_key", [MASTER.encode()]), ("acme", "other_name", [MASTER.encode()]), ("acme", "provider_key", [b"x" * 40])):
        with pytest.raises(VaultError):
            open_(masters, tenant, name, sealed)                                   # copied to another tenant or name, or the wrong key: refused
    assert seal(MASTER.encode(), "acme", "provider_key", "same") != seal(MASTER.encode(), "acme", "provider_key", "same")           # a new nonce every time
    with pytest.raises(VaultError):
        open_([MASTER.encode()], "acme", "provider_key", "v1:@@@not base64")


async def test_the_vault_stores_lists_names_never_values_and_is_off_without_a_master_key():
    v = Vault(InMemorySecrets(), MASTER)
    await v.put("acme", "provider_key", "sk-1", "platform")
    assert await v.get("acme", "provider_key") == "sk-1" and await v.get("globex", "provider_key") is None
    names = await v.names("acme")
    assert [n["name"] for n in names] == ["provider_key"] and "sk-1" not in json.dumps(names)
    for bad in ("X", "1abc", "has space", "a" * 41):
        with pytest.raises(VaultError):
            await v.put("acme", bad, "v", "p")
    with pytest.raises(VaultError):
        await v.put("acme", "empty", "", "p")
    off = Vault(InMemorySecrets(), None)
    assert not off.enabled
    with pytest.raises(VaultError) as e:
        await off.put("acme", "provider_key", "v", "p")
    assert e.value.status == 501
    with pytest.raises(VaultError):
        Vault(InMemorySecrets(), "short")
    assert await v.delete("acme", "provider_key") and not await v.delete("acme", "provider_key")


async def test_changing_the_master_key_keeps_secrets_readable_until_they_are_sealed_again():
    repo = InMemorySecrets()
    old = Vault(repo, "o" * 40)
    await old.put("acme", "provider_key", "sk-1", "platform")
    new = Vault(repo, "n" * 40, "o" * 40)                                         # new key in use, old one still accepted
    assert await new.get("acme", "provider_key") == "sk-1"
    assert await new.reseal("acme") == 1
    only_new = Vault(repo, "n" * 40)
    assert await only_new.get("acme", "provider_key") == "sk-1"                    # now readable with the new key alone
    with pytest.raises(VaultError):
        await Vault(repo, "o" * 40).get("acme", "provider_key")                   # and no longer with the old


@pytest.mark.parametrize("bad", [
    None, {}, {"baseUrl": "http://api.example.com/v1", "defaultModel": "m", "secret": "k"}, {"baseUrl": "https://u:p@api.example.com/v1", "defaultModel": "m", "secret": "k_k"},
    {"baseUrl": "https://localhost:8000/v1", "defaultModel": "m", "secret": "k_k"}, {"baseUrl": "https://10.0.0.5/v1", "defaultModel": "m", "secret": "k_k"},
    {"baseUrl": "https://169.254.169.254/latest", "defaultModel": "m", "secret": "k_k"}, {"baseUrl": "https://db.internal/v1", "defaultModel": "m", "secret": "k_k"},
    {"baseUrl": "https://api.example.com/v1", "defaultModel": "", "secret": "k_k"}, {"baseUrl": "https://api.example.com/v1", "defaultModel": "m", "secret": "Bad Name"},
    {"baseUrl": "https://api.example.com/v1", "defaultModel": "m", "secret": "k_k", "where": "moon"}, {"baseUrl": "https://api.example.com/v1", "defaultModel": "m", "secret": "k_k", "extra": 1}])
def test_a_tenant_provider_must_be_a_public_https_address_with_a_stored_key(bad):
    with pytest.raises(VaultError):
        validate_provider(bad)


async def test_a_tenant_with_its_own_provider_is_served_by_it_and_others_by_the_platform():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), request.headers.get("authorization"), json.loads(request.content)["model"]))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "from acme's provider"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 4}})
    settings, vault = InMemorySettings(), Vault(InMemorySecrets(), MASTER)
    token = TENANT.set("acme")
    try:
        await settings.put("tenant_provider", {"baseUrl": "https://llm.acme.example/v1", "defaultModel": "acme-model", "secret": "provider_key", "where": "public-cloud"}, "platform")
    finally:
        TENANT.reset(token)
    await vault.put("acme", "provider_key", "sk-acme", "platform")
    llm = TenantLLM(ScriptedLLM([text("from the platform")] * 5), vault, settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    req = LLMRequest(system="s", messages=[{"role": "user", "content": "hi"}], model="claude-something", max_tokens=50)
    token = TENANT.set("acme")
    try:
        got = await llm.complete(req)
    finally:
        TENANT.reset(token)
    assert got.content[0]["text"] == "from acme's provider" and calls == [("https://llm.acme.example/v1/chat/completions", "Bearer sk-acme", "acme-model")]
    token = TENANT.set("globex")
    try:
        assert (await llm.complete(req)).content[0]["text"] == "from the platform"                    # another tenant: the platform's own model
    finally:
        TENANT.reset(token)
    assert len(calls) == 1
    token = TENANT.set("acme")
    try:
        await vault.delete("acme", "provider_key")
        llm.forget("acme")
        with pytest.raises(Exception, match="key is missing"):
            await llm.complete(req)                                                                   # never falls back to the platform's model for a tenant that chose its own
    finally:
        TENANT.reset(token)
    assert llm.selector is None if hasattr(llm.inner, "selector") else True


def world(master=MASTER):
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([text("ok")] * 10), InMemoryStore(), TraceStore())
    settings = InMemorySettings()
    rt.budget_settings = type("B", (), {"repo": settings})()
    rt.tenant_limits = TenantLimits(settings, {})
    ac = AccessControl(bootstrap_key="boot" * 10)
    ac.tenants = TenantService(preview=True)
    audit = InMemoryAudit()
    vault = Vault(InMemorySecrets(), master)
    web = create_app(rt, rt.traces, {"support": support_agent()}, access=ac, audit=audit)
    plat = create_platform_app(PKEY, ac.tenants, rt.tenant_limits, settings, audit, ac, vault, TenantLLM(ScriptedLLM([]), vault, settings))
    key = lambda tenant: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(f"{tenant}-admin", "admin", "t", tenant_id=tenant))[1]}  # noqa: E731
    return TestClient(web), TestClient(plat), key, vault, loop


def test_the_operator_stores_a_key_and_sets_a_tenants_provider_and_the_tenant_can_see_it_without_the_key():
    web, plat, key, vault, loop = world()
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    admin = key("acme")
    body = {"baseUrl": "https://llm.acme.example/v1", "defaultModel": "acme-model", "secret": "provider_key"}
    assert plat.put("/platform/v1/tenants/acme/provider", headers=P, json=body).status_code == 400            # the key must be stored first
    assert plat.put("/platform/v1/tenants/acme/secrets/provider_key", headers=P, json={"value": "sk-acme-123"}).json() == {"name": "provider_key", "stored": True}
    assert plat.get("/platform/v1/tenants/acme/secrets", headers=P).json()["secrets"][0]["name"] == "provider_key" and "sk-acme-123" not in plat.get("/platform/v1/tenants/acme/secrets", headers=P).text
    assert plat.put("/platform/v1/tenants/acme/provider", headers=P, json=body).json() == {"baseUrl": "https://llm.acme.example/v1", "defaultModel": "acme-model", "where": "public-cloud"}
    assert plat.put("/platform/v1/tenants/acme/provider", headers=P, json={**body, "baseUrl": "https://10.1.1.1/v1"}).status_code == 400
    mine = web.get("/v1/tenant/provider", headers=admin).json()
    assert mine["own"] is True and mine["baseUrl"] == "https://llm.acme.example/v1" and mine["keyStored"] is True and "sk-acme" not in json.dumps(mine) and "secret" not in mine
    assert web.put("/v1/tenant/provider", headers=admin, json=body).status_code in (404, 405)                # a tenant cannot set it
    audit = [e for e in web.get("/v1/audit?limit=40", headers=admin).json()["entries"] if e["action"].startswith("platform.")]
    assert {"platform.secret_set", "platform.provider_set"} <= {e["action"] for e in audit} and "sk-acme-123" not in json.dumps(audit)       # the name, never the value
    assert plat.delete("/platform/v1/tenants/acme/provider", headers=P).json() == {"removed": True}
    assert web.get("/v1/tenant/provider", headers=admin).json()["own"] is False
    assert plat.delete("/platform/v1/tenants/acme/secrets/provider_key", headers=P).json() == {"deleted": True} and plat.delete("/platform/v1/tenants/acme/secrets/provider_key", headers=P).status_code == 404


def test_without_a_master_key_the_platform_says_the_vault_is_off():
    web, plat, key, vault, loop = world(master=None)
    plat.post("/platform/v1/tenants", headers=P, json={"id": "acme", "name": "Acme"})
    assert plat.get("/platform/v1/tenants/acme/secrets", headers=P).json() == {"enabled": False, "secrets": []}
    r = plat.put("/platform/v1/tenants/acme/secrets/provider_key", headers=P, json={"value": "x"})
    assert r.status_code == 501 and "NORTHCX_MASTER_KEY" in r.json()["error"]["message"]
    assert plat.post("/platform/v1/vault/reseal", headers=P).status_code == 501
    assert plat.put("/platform/v1/tenants/nope/secrets/provider_key", headers=P, json={"value": "x"}).status_code == 404
    assert plat.put("/platform/v1/tenants/acme/secrets/Bad", headers=P, json={"value": "x"}).status_code in (400, 501)


async def test_sealed_secrets_survive_the_database_and_stay_in_their_tenant(app_engine):
    from northcx.db import PgSecrets
    v = Vault(PgSecrets(app_engine), MASTER)
    await v.put("acme", "provider_key", "sk-acme", "platform")
    await v.put("globex", "provider_key", "sk-globex", "platform")
    assert await v.get("acme", "provider_key") == "sk-acme" and await v.get("globex", "provider_key") == "sk-globex"
    assert [n["name"] for n in await v.names("acme")] == ["provider_key"] and await v.names("nobody") == []
    stored = await v.repo.get("acme", "provider_key")
    assert "sk-acme" not in stored.sealed
    from northcx.vault import Stored
    await v.repo.put("globex", Stored("provider_key", stored.sealed, "attacker", 0.0))               # acme's sealed value copied into globex's row
    with pytest.raises(VaultError):
        await v.get("globex", "provider_key")
    assert await v.delete("acme", "provider_key") and await v.get("acme", "provider_key") is None
