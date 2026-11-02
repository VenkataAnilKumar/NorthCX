"""Roles, API keys, the audit log and rate limits."""
import asyncio
import json
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import (ROLES, AccessControl, ApiKey, InMemoryKeys, LimitConfig, OPEN_IDENTITY, RateLimiter, hash_secret,
                            parse_token)
from northcx.audit import AuditEntry, InMemoryAudit, entry_hash, verify_entries
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import ROUTE_PERMISSIONS, create_app, permission_for
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios
from northcx.spec import BuildContext, load_specs
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, LiveAgents, ReleaseService

ROOT = Path(__file__).resolve().parents[1]
SCEN = load_scenarios(ROOT / "examples" / "scenarios")
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}


# ---------------- rate limiter ----------------
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_rate_limiter_allows_a_burst_then_refills_over_time():
    clock = Clock()
    rl = RateLimiter(clock)
    assert [rl.allow("a", 6)[0] for _ in range(6)] == [True] * 6
    ok, retry = rl.allow("a", 6)
    assert not ok and 9.9 < retry <= 10.0  # six per minute: one token every ten seconds
    clock.t += 10
    assert rl.allow("a", 6)[0] and not rl.allow("a", 6)[0]
    clock.t += 3600
    assert [rl.allow("a", 6)[0] for _ in range(7)] == [True] * 6 + [False]  # never more than the limit stored
    assert rl.allow("b", 6)[0]  # other keys are unaffected


def test_rate_limiter_forgets_idle_keys_instead_of_growing_forever():
    clock = Clock()
    rl = RateLimiter(clock, max_buckets=100)
    for i in range(500):
        clock.t += 1
        rl.allow(f"k{i}", 60)
    assert len(rl._buckets) <= 100


# ---------------- roles ----------------
def test_roles_follow_least_privilege():
    r = ROLES
    assert r["admin"] >= r["release_manager"] >= r["developer"] >= r["viewer"]
    assert "releases:publish" not in r["developer"] and "releases:publish" in r["release_manager"]
    assert "approvals:decide" in r["reviewer"] and "approvals:decide" not in r["release_manager"]
    assert "releases:publish" not in r["reviewer"] and "versions:create" not in r["reviewer"]
    assert r["channel"] == {"chat:send", "outbox:read", "chat:mint", "channel:inbound"}
    assert "audit:read" in r["auditor"] and "audit:read" not in r["release_manager"] and "keys:manage" not in r["auditor"]
    assert not any(p.endswith((":create", ":run", ":publish", ":rollback", ":decide", ":resolve", ":manage", "send")) for p in r["viewer"])
    for perm in {p for _, _, p in ROUTE_PERMISSIONS if p != "authenticated"}:
        assert perm in r["admin"], perm  # every permission the API checks is grantable
        assert any(perm in perms for perms in r.values())


def test_tokens_parse_strictly():
    assert parse_token("ncx_0123abcd_" + "A" * 24) == ("0123abcd", "A" * 24)
    for bad in ["", "ncx_0123abcd_short", "ncx_XYZ_" + "A" * 24, "Bearer x", "ncx_0123abcd" + "A" * 24, "x" * 80]:
        assert parse_token(bad) is None


# ---------------- keys ----------------
async def test_keys_are_issued_checked_and_revoked():
    ac = AccessControl()
    assert not await ac.enabled()
    key, token = await ac.issue("ci bot", "developer", "root", expires_in_days=30)
    assert await ac.enabled() and token.startswith(key.prefix + "_") and key.expires_at
    stored = (await ac.keys.get(key.key_id))
    assert token.split("_", 2)[2] not in json.dumps(stored.__dict__) and stored.key_hash == hash_secret(token.split("_", 2)[2])
    ident = await ac.authenticate(token)
    assert (ident.name, ident.role, ident.key_id) == ("ci bot", "developer", key.key_id)
    assert await ac.authenticate(token[:-1] + ("A" if token[-1] != "A" else "B")) is None  # one wrong character
    assert await ac.authenticate(f"{key.prefix}_" + "x" * 43) is None and await ac.authenticate("garbage") is None
    assert await ac.authenticate(None) is None
    await ac.keys.touch(key.key_id, 5.0)
    await ac.revoke(key.key_id, "root")
    assert await ac.authenticate(token) is None and await ac.enabled()  # revoking never turns authentication off


async def test_expired_keys_stop_working():
    ac = AccessControl()
    key, token = await ac.issue("temp", "viewer", "root", 1)
    assert await ac.authenticate(token)
    (await ac.keys.get(key.key_id)).expires_at = time.time() - 1
    assert await ac.authenticate(token) is None


@pytest.mark.parametrize("name,role,days,message", [
    ("ok", "wizard", None, "Unknown role"), ("", "viewer", None, "Key names"), (" padded ", "viewer", None, "Key names"),
    ("bad/name", "viewer", None, "Key names"), ("x" * 81, "viewer", None, "Key names"),
    ("ok", "viewer", 0, "expiresInDays"), ("ok", "viewer", 99999, "expiresInDays"),
])
async def test_invalid_key_requests_are_refused(name, role, days, message):
    with pytest.raises(ValueError, match=message):
        await AccessControl().issue(name, role, "root", days)


async def test_names_must_be_unique_among_active_keys_and_the_last_admin_is_protected():
    ac = AccessControl()
    a, _ = await ac.issue("Alice", "admin", "root")
    with pytest.raises(ValueError, match="already exists"):
        await ac.issue("alice", "viewer", "root")
    with pytest.raises(ValueError, match="last active admin"):
        await ac.revoke(a.key_id, "root")
    b, _ = await ac.issue("Bob", "admin", "root")
    await ac.revoke(a.key_id, "root")
    await ac.issue("Alice", "viewer", "root")  # the name is free again
    with pytest.raises(ValueError, match="last active admin"):
        await ac.revoke(b.key_id, "root")
    with pytest.raises(ValueError, match="already revoked"):
        await ac.keys.revoke(a.key_id, "root")
    with pytest.raises(KeyError):
        await ac.revoke("deadbeef", "root")
    boot = AccessControl(bootstrap_key="b" * 30)
    s, _ = await boot.issue("Solo", "admin", "x")
    await boot.revoke(s.key_id, "x")  # fine: the bootstrap key remains an admin


async def test_bootstrap_key_is_an_admin_and_use_is_recorded_at_most_once_a_minute():
    secret = "k" * 40
    ac = AccessControl(bootstrap_key=secret)
    ident = await ac.authenticate(secret)
    assert (ident.name, ident.role) == ("bootstrap", "admin") and await ac.authenticate(secret + "x") is None
    key, token = await ac.issue("svc", "channel", "bootstrap")
    for _ in range(5):
        await ac.authenticate(token)
    first = (await ac.keys.get(key.key_id)).last_used_at
    assert first is not None
    await ac.authenticate(token)
    assert (await ac.keys.get(key.key_id)).last_used_at == first  # throttled


# ---------------- audit chain ----------------
async def test_audit_chain_detects_edits_and_removals():
    log = InMemoryAudit()
    for i in range(5):
        await log.append(AuditEntry("rae", "reviewer", "approval.decide", f"a{i}", detail={"n": i}))
    assert (await log.verify()).ok and (await log.verify()).checked == 5
    assert [e.id for e in await log.list(limit=2)] == [5, 4]
    assert [e.id for e in await log.list(before_id=3)] == [2, 1]
    assert len(await log.list(actor="rae")) == 5 and await log.list(actor="nobody") == []
    assert len(await log.list(action="approval.decide")) == 5 and await log.list(action="key.create") == []

    edited = list(log._items)
    edited[2] = AuditEntry(**{**edited[2].__dict__, "detail": {"n": 99}})
    v = verify_entries(edited)
    assert not v.ok and v.broken_at == 3 and "changed" in v.reason
    removed = [e for e in log._items if e.id != 3]
    v = verify_entries(removed)
    assert not v.ok and v.broken_at == 4 and "chain is broken" in v.reason
    forged = list(log._items)
    last = AuditEntry(**{**forged[-1].__dict__, "actor": "mallory"})
    last.hash = entry_hash(last)  # recomputed hash for the edited entry still breaks nothing before it...
    assert verify_entries(forged[:-1] + [last]).ok  # ...the chain only protects entries that have a successor
    assert verify_entries([]).ok and verify_entries([]).head is None
    head = (await log.verify()).head
    assert head == log._items[-1].hash  # publish this value elsewhere to detect removal of the newest entries


# ---------------- the API ----------------
def build(access=None, api_key=None, audit=None, releases=True):
    traces = TraceStore()
    rt = Runtime(ScriptedLLM([text("hello")] * 200), InMemoryStore(), traces)
    sim = rel = None
    live = {"support": support_agent()}
    if releases:
        sim = SimulationService(SCEN, lambda aid, llm: registry().build(SPECS[aid], BuildContext(llm=llm)), InMemorySimRuns(),
                                {i: s.digest() for i, s in SPECS.items()},
                                spec_builder=lambda spec, llm: registry().build(spec, BuildContext(llm=llm)))
        rel = ReleaseService(InMemoryVersions(), InMemoryReleases(), registry(), SPECS, sim)
        live = LiveAgents({"support": support_agent()}, rel, lambda spec: registry().build(spec, BuildContext()))
    audit = audit or InMemoryAudit()
    app = create_app(rt, traces, live, api_key, simulations=sim, releases=rel, access=access, audit=audit)
    return TestClient(app), rt, audit


def H(token):
    return {"authorization": f"Bearer {token}"}


async def mint(ac, role, name=None):
    return (await ac.issue(name or f"{role}-user", role, "root"))[1]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_open_mode_trusts_a_claimed_name_and_says_so():
    c, rt, audit = build()
    me = c.get("/v1/me").json()
    assert (me["name"], me["role"], me["openMode"]) == ("anonymous", "admin", True)
    c.post("/v1/agents/support/versions", json={"fromBaseline": True, "by": "rae"})
    assert run(audit.list())[0].actor == "anonymous"  # the audit actor is the (unauthenticated) identity, not the claim
    v = c.get("/v1/agents/support/versions/1").json()
    assert v["author"] == "rae"  # the claimed name is recorded as the author only in open mode


def test_a_configured_key_protects_the_api_and_disables_the_docs():
    c, _, _ = build(api_key="s" * 40)
    assert c.get("/health").status_code == 200 and c.get("/").status_code == 200
    for path in ("/v1/me", "/v1/agents", "/v1/traces", "/v1/audit"):
        assert c.get(path).status_code == 401
        assert c.get(path, headers=H("wrong")).status_code == 401
    assert c.get("/v1/me", headers=H("s" * 40)).json()["role"] == "admin"
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404


async def _app_with_keys(**kw):
    ac = AccessControl(bootstrap_key="boot" * 10, **kw)
    tokens = {r: await mint(ac, r) for r in ROLES}
    return ac, tokens


CALLS = [  # (permission needed, method, path, body)
    ("agents:read", "GET", "/v1/agents", None),
    ("traces:read", "GET", "/v1/traces", None),
    ("approvals:read", "GET", "/v1/approvals", None),
    ("handoffs:read", "GET", "/v1/handoffs", None),
    ("simulations:read", "GET", "/v1/simulations/scenarios", None),
    ("versions:read", "GET", "/v1/agents/support/versions", None),
    ("chat:send", "POST", "/v1/agents/support/chat", {"sessionId": "s", "message": "hi"}),
    ("outbox:read", "GET", "/v1/sessions/s/outbox", None),
    ("versions:create", "POST", "/v1/agents/support/versions", {"fromBaseline": True}),
    ("simulations:run", "POST", "/v1/simulations/runs", {"only": "order-lookup", "skipJudge": True}),
    ("releases:publish", "POST", "/v1/agents/support/releases", {"version": 1}),
    ("releases:rollback", "POST", "/v1/agents/support/rollback", {}),
    ("approvals:decide", "POST", "/v1/approvals/missing/decision", {"approved": True}),
    ("handoffs:resolve", "POST", "/v1/handoffs/missing/resolve", {}),
    ("chat:mint", "POST", "/v1/chat-tokens", {"sessionId": "s1"}),
    ("channel:inbound", "POST", "/v1/channels/email/inbound", None),
    ("keys:manage", "GET", "/v1/keys", None),
    ("audit:read", "GET", "/v1/audit", None),
]


def test_every_role_can_do_exactly_what_it_is_allowed_to():
    ac, tokens = run(_app_with_keys())
    c, _, audit = build(access=ac)
    seen_denials = 0
    for role, token in tokens.items():
        for perm, method, path, body in CALLS:
            r = c.request(method, path, json=body, headers=H(token))
            allowed = perm in ROLES[role]
            if allowed:
                assert r.status_code != 403, f"{role} should be allowed {perm}: {r.status_code} {r.text[:100]}"
            else:
                assert r.status_code == 403, f"{role} must not be allowed {perm}: {r.status_code}"
                assert perm in r.json()["error"]["message"]
                seen_denials += 1
    denied = run(audit.list(limit=500, action="auth.denied"))
    assert len(denied) == seen_denials and all(e.outcome == "denied" and e.detail["permission"] for e in denied)
    assert {e.role for e in denied} <= set(ROLES)


def test_the_acting_identity_replaces_any_claimed_name():
    ac, tokens = run(_app_with_keys())
    c, rt, audit = build(access=ac)
    run(rt.approvals.add(trace_id="t", session_id="s", agent_id="support", tool="issue_refund", input={"order_id": "2077", "amount": 240}, reason="r"))
    aid = c.get("/v1/approvals?state=pending", headers=H(tokens["reviewer"])).json()["approvals"][0]["id"]
    done = c.post(f"/v1/approvals/{aid}/decision", json={"approved": False, "by": "the-ceo"}, headers=H(tokens["reviewer"])).json()
    assert done["decided_by"] == "reviewer-user"  # not "the-ceo"
    entry = run(audit.list(action="approval.decide"))[0]
    assert (entry.actor, entry.role, entry.target) == ("reviewer-user", "reviewer", aid) and entry.detail["approved"] is False
    v = c.post("/v1/agents/support/versions", json={"fromBaseline": True, "by": "someone-else"}, headers=H(tokens["developer"])).json()
    assert v["author"] == "developer-user"


def test_releases_are_audited_including_blocked_attempts():
    ac, tokens = run(_app_with_keys())
    c, _, audit = build(access=ac)
    dev, rm = H(tokens["developer"]), H(tokens["release_manager"])
    assert c.post("/v1/agents/support/versions", json={"fromBaseline": True}, headers=dev).status_code == 201
    assert c.post("/v1/agents/support/releases", json={"version": 1}, headers=rm).status_code == 409  # unproven
    assert c.post("/v1/simulations/runs", json={"agent": "support", "version": 1, "skipJudge": True}, headers=dev).status_code == 200
    assert c.post("/v1/agents/support/releases", json={"version": 1, "note": "go"}, headers=rm).status_code == 200
    assert c.post("/v1/agents/support/rollback", json={}, headers=rm).status_code == 200
    log = run(audit.list(limit=100))
    by_action = {(e.action, e.outcome): e for e in log if not e.action.startswith("auth.")}
    assert set(by_action) >= {("version.create", "success"), ("release.publish", "blocked"), ("simulation.run", "success"),
                              ("release.publish", "success"), ("release.rollback", "success")}
    blocked = by_action[("release.publish", "blocked")]
    assert blocked.actor == "release_manager-user" and blocked.detail["reasons"] and blocked.target == "support@1"
    assert by_action[("release.publish", "success")].detail["gate"]["satisfied"] is True
    assert [e.id for e in reversed(log)] == sorted(e.id for e in log)  # strictly ordered
    assert run(audit.verify()).ok


def test_audit_entries_never_contain_secrets_or_conversation_text():
    ac, tokens = run(_app_with_keys())
    c, _, audit = build(access=ac)
    made = c.post("/v1/keys", json={"name": "svc", "role": "channel"}, headers=H(tokens["admin"])).json()
    secret = made["key"].split("_", 2)[2]
    c.post("/v1/agents/support/chat", json={"sessionId": "s", "message": "my secret passphrase is plum"}, headers=H(tokens["channel"]))
    c.get("/v1/me", headers=H("bad-" + secret))
    dump = json.dumps([e.__dict__ for e in run(audit.list(limit=500))])
    assert secret not in dump and "plum" not in dump and tokens["admin"] not in dump


def test_key_management_through_the_api():
    ac, tokens = run(_app_with_keys())
    c, _, audit = build(access=ac)
    adm = H(tokens["admin"])
    r = c.post("/v1/keys", json={"name": "web chat", "role": "channel", "expiresInDays": 30}, headers=adm)
    assert r.status_code == 201
    made = r.json()
    assert made["key"].startswith(made["prefix"] + "_") and made["role"] == "channel" and made["expiresAt"] and made["createdBy"] == "admin-user"
    listed = c.get("/v1/keys", headers=adm).json()
    assert "key" not in json.dumps(listed["keys"]) and "hash" not in json.dumps(listed["keys"]).lower()
    assert listed["roles"]["channel"] == ["channel:inbound", "chat:mint", "chat:send", "outbox:read"]
    assert c.get("/v1/me", headers=H(made["key"])).json()["role"] == "channel"
    assert c.get("/v1/agents", headers=H(made["key"])).status_code == 403
    assert c.post("/v1/keys", json={"name": "web chat", "role": "viewer"}, headers=adm).status_code == 400  # name in use
    assert c.post("/v1/keys", json={"name": "x", "role": "wizard"}, headers=adm).status_code == 400
    assert c.post(f"/v1/keys/{made['id']}/revoke", headers=adm).json()["active"] is False
    assert c.get("/v1/me", headers=H(made["key"])).status_code == 401  # revoked at once
    assert c.post(f"/v1/keys/{made['id']}/revoke", headers=adm).status_code == 409
    assert c.post("/v1/keys/00000000/revoke", headers=adm).status_code == 404
    actions = [(e.action, e.target) for e in run(audit.list(limit=50)) if e.action.startswith("key.")]
    assert ("key.create", made["prefix"]) in actions and ("key.revoke", made["prefix"]) in actions


def test_the_audit_api_pages_filters_and_verifies():
    ac, tokens = run(_app_with_keys())
    c, _, _ = build(access=ac)
    for i in range(5):
        c.post("/v1/keys", json={"name": f"k{i}", "role": "viewer"}, headers=H(tokens["admin"]))
    a = H(tokens["auditor"])
    page = c.get("/v1/audit?limit=2", headers=a).json()["entries"]
    assert len(page) == 2 and page[0]["id"] > page[1]["id"]
    older = c.get(f"/v1/audit?limit=100&before={page[1]['id']}", headers=a).json()["entries"]
    assert all(e["id"] < page[1]["id"] for e in older)
    assert {e["action"] for e in c.get("/v1/audit?action=key.create", headers=a).json()["entries"]} == {"key.create"}
    assert all(e["actor"] == "admin-user" for e in c.get("/v1/audit?actor_name=admin-user", headers=a).json()["entries"])
    v = c.get("/v1/audit/verify", headers=a).json()
    assert (v["ok"], v["checked"], v["brokenAt"], v["reason"]) == (True, 5, None, None) and len(v["head"]) == 64
    assert c.get("/v1/audit", headers=H(tokens["viewer"])).status_code == 403


def test_every_route_is_covered_by_the_permission_table_and_nothing_stale_remains():
    c, _, _ = build()
    routes = {(m, r.path) for r in c.app.routes for m in getattr(r, "methods", set()) if m not in ("HEAD", "OPTIONS") and r.path.startswith("/v1")}
    assert routes
    uncovered = [(m, p) for m, p in routes if permission_for(m, re.sub(r"\{[^}]+\}", "x", p)) is None]
    assert not uncovered, f"routes with no permission entry: {uncovered}"
    covered = {(m, rx) for m, rx, _ in ROUTE_PERMISSIONS}
    stale = [(m, rx) for m, rx in covered if not any(m == rm and re.fullmatch(rx, re.sub(r"\{[^}]+\}", "x", rp)) for rm, rp in routes)]
    assert not stale, f"table entries matching no route: {stale}"


def test_an_unlisted_v1_path_is_refused():
    ac, tokens = run(_app_with_keys())
    c, _, _ = build(access=ac)
    assert c.get("/v1/secret-admin", headers=H(tokens["admin"])).status_code == 404
    assert c.delete("/v1/agents", headers=H(tokens["admin"])).status_code == 404


# ---------------- rate limits ----------------
def test_per_key_limits_are_independent_and_report_when_to_retry():
    ac = AccessControl(bootstrap_key="boot" * 10, limits=LimitConfig(per_key_per_minute=5))
    ta, tb = run(mint(ac, "viewer", "a")), run(mint(ac, "viewer", "b"))
    c, _, _ = build(access=ac)
    codes = [c.get("/v1/me", headers=H(ta)).status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and set(codes[5:]) == {429}
    r = c.get("/v1/me", headers=H(ta))
    assert r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
    assert c.get("/v1/me", headers=H(tb)).status_code == 200  # another key is untouched
    assert c.get("/health").status_code == 200  # public routes are not limited


def test_chat_is_limited_per_conversation_not_per_key():
    ac = AccessControl(bootstrap_key="boot" * 10, limits=LimitConfig(per_key_per_minute=1000, chat_per_session_per_minute=3))
    token = run(mint(ac, "channel"))
    c, _, _ = build(access=ac)
    chat = lambda sid: c.post("/v1/agents/support/chat", json={"sessionId": sid, "message": "hi"}, headers=H(token)).status_code
    assert [chat("busy") for _ in range(5)] == [200, 200, 200, 429, 429]
    assert chat("quiet") == 200


def test_guessing_keys_is_throttled_and_does_not_flood_the_log():
    ac = AccessControl(bootstrap_key="boot" * 10, limits=LimitConfig(auth_failures_per_minute=5))
    good = run(mint(ac, "viewer"))
    c, _, audit = build(access=ac)
    codes = [c.get("/v1/me", headers=H(f"guess-{i}")).status_code for i in range(30)]
    assert codes[:5] == [401] * 5 and set(codes[5:]) == {429}
    assert c.get("/v1/me", headers=H(good)).status_code == 200  # a correct key still works
    failed = run(audit.list(limit=500, action="auth.failed"))
    assert 1 <= len(failed) <= 6 and all(e.outcome == "denied" for e in failed)


def test_limits_are_off_unless_configured():
    c, _, _ = build(api_key="s" * 40)
    assert all(c.get("/v1/me", headers=H("s" * 40)).status_code == 200 for _ in range(50))


# ---------------- Postgres ----------------
@pytest.fixture(params=["memory", "postgres"])
def key_repo(request):
    if request.param == "memory":
        return InMemoryKeys()
    from northcx.db import PgKeys
    return PgKeys(request.getfixturevalue("engine"))


@pytest.fixture(params=["memory", "postgres"])
def audit_repo(request):
    if request.param == "memory":
        return InMemoryAudit()
    from northcx.db import PgAudit
    return PgAudit(request.getfixturevalue("engine"))


async def test_key_repository_contract(key_repo):
    ac = AccessControl(keys=key_repo)
    k, token = await ac.issue("svc", "developer", "root", 5)
    got = await key_repo.get(k.key_id)
    assert (got.name, got.role, got.created_by, got.key_hash) == ("svc", "developer", "root", k.key_hash) and got.expires_at
    assert (await ac.authenticate(token)).name == "svc" and (await key_repo.get(k.key_id)).last_used_at is not None
    assert [x.key_id for x in await key_repo.list()] == [k.key_id] and await key_repo.get("missing0") is None
    revoked = await key_repo.revoke(k.key_id, "root")
    assert revoked.revoked_by == "root" and not revoked.active()
    with pytest.raises(ValueError, match="already revoked"):
        await key_repo.revoke(k.key_id, "root")
    with pytest.raises(KeyError):
        await key_repo.revoke("missing0", "root")
    assert await ac.authenticate(token) is None


async def test_audit_repository_contract(audit_repo):
    made = await asyncio.gather(*[audit_repo.append(AuditEntry(f"u{i % 3}", "admin", "x.y", f"t{i}", detail={"i": i, "nested": {"ü": "日本"}}))
                                  for i in range(20)])
    assert sorted(e.id for e in made) == list(range(1, 21))  # gapless and unique even when appends race
    v = await audit_repo.verify()
    assert v.ok and v.checked == 20 and v.head == (await audit_repo.list(limit=1))[0].hash
    newest = (await audit_repo.list(limit=3))
    assert [e.id for e in newest] == [20, 19, 18]
    assert all(e.actor == "u1" for e in await audit_repo.list(limit=50, actor="u1"))
    assert [e.id for e in await audit_repo.list(before_id=4, limit=10)] == [3, 2, 1]
    assert (await audit_repo.list(limit=1, action="x.y"))[0].detail["nested"] == {"ü": "日本"}


async def test_the_database_refuses_to_change_the_audit_log(engine, db_url):
    from sqlalchemy import text
    from northcx.db import PgAudit
    log = PgAudit(engine)
    for i in range(3):
        await log.append(AuditEntry("a", "admin", "k.create", str(i)))
    for sql in ("update audit_log set actor = 'mallory' where id = 2", "delete from audit_log where id = 2", "truncate audit_log"):
        with pytest.raises(Exception, match="append-only"):
            async with engine.begin() as c:
                await c.execute(text(sql))
    assert (await log.verify()).ok and len(await log.list()) == 3
    # Someone with full database rights can switch the trigger off; the hash chain still exposes the edit.
    async with engine.begin() as c:
        await c.execute(text("alter table audit_log disable trigger user"))
        await c.execute(text("update audit_log set detail = '{\"forged\": true}' where id = 2"))
        await c.execute(text("alter table audit_log enable trigger user"))
    v = await log.verify()
    assert not v.ok and v.broken_at == 2 and "changed" in v.reason
    async with engine.begin() as c:
        await c.execute(text("alter table audit_log disable trigger user"))
        await c.execute(text("delete from audit_log where id = 1"))
        await c.execute(text("alter table audit_log enable trigger user"))
    assert not (await log.verify()).ok


async def test_keys_and_the_audit_log_survive_a_restart_and_work_through_the_api(engine, db_url):
    from sqlalchemy.pool import NullPool
    from northcx.db import PgAudit, PgKeys, create_engine
    ac = AccessControl(keys=PgKeys(engine), bootstrap_key="boot" * 10)
    token = await mint(ac, "admin", "alice")
    c, _, _ = build(access=ac, audit=PgAudit(engine))
    made = c.post("/v1/keys", json={"name": "reviewer1", "role": "reviewer"}, headers=H(token)).json()
    eng2 = create_engine(db_url, poolclass=NullPool)
    try:
        ac2 = AccessControl(keys=PgKeys(eng2))  # a restarted server: no bootstrap key, keys come from the database
        assert await ac2.enabled()
        c2, _, audit2 = build(access=ac2, audit=PgAudit(eng2))
        assert c2.get("/v1/me", headers=H(made["key"])).json()["role"] == "reviewer"
        assert c2.get("/v1/me").status_code == 401
        entries = c2.get("/v1/audit", headers=H(token)).json()["entries"]
        assert [e["action"] for e in entries] == ["auth.failed", "key.create"]  # the 401 above was recorded too
        assert entries[1]["actor"] == "alice" and entries[0]["outcome"] == "denied"
        assert c2.get("/v1/audit/verify", headers=H(token)).json()["ok"] is True
    finally:
        await eng2.dispose()


def test_command_line_creates_the_first_admin_key(db_url, engine, monkeypatch, capsys):
    from northcx.keys import main as keys_main
    monkeypatch.setenv("NORTHCX_DATABASE_URL", db_url)
    assert keys_main(["create", "--name", "alice", "--role", "admin", "--days", "30"]) == 0
    out = capsys.readouterr().out
    token = out.strip().splitlines()[-1]
    assert parse_token(token) is not None and "shown once" in out
    assert keys_main(["list"]) == 0 and "alice" in capsys.readouterr().out and token not in capsys.readouterr().out
    assert keys_main(["create", "--name", "alice", "--role", "viewer"]) == 1  # name in use
    assert "already exists" in capsys.readouterr().err
    from northcx.db import PgAudit, PgKeys
    ac = AccessControl(keys=PgKeys(engine))
    assert run(ac.authenticate(token)).role == "admin"
    entries = run(PgAudit(engine).list())
    assert entries[0].action == "key.create" and entries[0].actor == "cli" and token not in json.dumps(entries[0].detail)
    key_id = parse_token(token)[0]
    capsys.readouterr()
    assert keys_main(["revoke", key_id]) == 1 and "last active admin" in capsys.readouterr().err  # cannot lock yourself out
    monkeypatch.delenv("NORTHCX_DATABASE_URL")
    assert keys_main(["list"]) == 2
