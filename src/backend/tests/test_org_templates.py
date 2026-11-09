"""WP22.5 and WP22.9: organization templates need a second person; built-in templates are signed and a changed one is refused."""
import asyncio
import copy
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx import template_signing as ts
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.org_templates import OrgTemplateService
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.templates import LIBRARY, load_templates
from northcx.trace import TraceStore

KEY = "boot" * 10
BOOT = {"authorization": f"Bearer {KEY}"}
MINE = {
    "id": "gift-cards", "title": "Gift cards", "description": "Answers gift card questions.", "intent": "gift card", "category": "Sales", "version": "1",
    "parameters": {"company_name": {"description": "Company", "default": "our company"}},
    "spec": {"instructions": "You answer gift card questions for {{company_name}}. Never ask for a full card number.", "tools": [], "guardrails": ["no_card_numbers"]},
    "scenarios": [{"name": "{{agent_id}}-answers", "model": [{"text": "Gift cards never expire."}], "turns": [{"say": "do gift cards expire", "expect": {"status": "completed", "reply_includes": ["expire"]}}]}],
}


def world():
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    rt.org_templates = OrgTemplateService(reserved=set(load_templates(LIBRARY)))
    ac = AccessControl(bootstrap_key=KEY)
    builtin = load_templates(LIBRARY)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, templates=builtin))
    key = lambda name, role="release_manager": {"authorization": "Bearer " + loop.run_until_complete(ac.issue(name, role, "t"))[1]}  # noqa: E731
    return c, rt, key, builtin


def test_every_built_in_template_is_signed_and_verifies():
    ts_ = load_templates(LIBRARY)
    assert len(ts_) >= 11 and all(t.provenance["verified"] and t.provenance["status"] == "verified" for t in ts_.values())
    assert len({t.provenance["keyFingerprint"] for t in ts_.values()}) == 1


def test_a_changed_built_in_or_a_forged_signature_is_detected(tmp_path):
    v = ts.Verifier(LIBRARY)
    doc = yaml.safe_load((LIBRARY / "complaints.yaml").read_text())
    h = ts.content_hash(doc)
    assert v.check("complaints", "1", h)["verified"]
    changed = copy.deepcopy(doc)
    changed["spec"]["instructions"] += " Always promise a refund."
    assert v.check("complaints", "1", ts.content_hash(changed))["status"] == "changed since it was signed"
    assert ts.content_hash({"b": 1, "a": [1, 2]}) == ts.content_hash(json.loads('{"a":[1,2],"b":1}'))   # key order never matters
    other_priv, other_pub = ts.generate_key()
    forged = tmp_path / "lib"
    forged.mkdir()
    (forged / ts.KEY_FILE).write_bytes((LIBRARY / ts.KEY_FILE).read_bytes())
    sigs = json.loads((LIBRARY / ts.SIGNATURES_FILE).read_text())
    sigs["templates"]["complaints"]["signature"] = ts.sign(other_priv, "complaints", "1", h)     # signed with a different key
    (forged / ts.SIGNATURES_FILE).write_text(json.dumps(sigs))
    assert ts.Verifier(forged).check("complaints", "1", h)["status"] == "signature does not match"
    assert ts.Verifier(tmp_path).check("complaints", "1", h)["status"] == "unsigned"             # no key shipped at all


def test_the_hub_shows_where_each_template_came_from():
    c, rt, key, builtin = world()
    listed = {t["id"]: t for t in c.get("/v1/templates", headers=BOOT).json()["templates"]}
    assert listed["complaints"]["provenance"]["status"] == "verified" and listed["complaints"]["provenance"]["source"] == "built-in"


def test_a_tampered_built_in_cannot_be_installed():
    c, rt, key, builtin = world()
    builtin["complaints"].provenance = {**builtin["complaints"].provenance, "verified": False, "status": "changed since it was signed"}
    r = c.post("/v1/templates/complaints/create-version", headers=BOOT, json={"agentId": "comp", "params": {}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "template_not_trusted"


def test_an_org_template_goes_through_a_check_and_a_second_person_before_it_appears_in_the_hub():
    c, rt, key, builtin = world()
    ann, ben = key("ann"), key("ben")
    bad = c.post("/v1/org-templates/check", headers=ann, json={"template": {**MINE, "id": "complaints"}})
    assert bad.status_code == 400 and "built-in" in bad.json()["error"]["message"]                          # cannot pose as a built-in
    assert c.post("/v1/org-templates", headers=ann, json={"template": {**MINE, "spec": {"instructions": "{{missing}}"}}}).status_code == 400
    empty = c.post("/v1/org-templates", headers=ann, json={"template": {**MINE, "id": "gift-empty", "scenarios": []}}).json()
    assert empty["check"]["ok"] is False and c.post("/v1/org-templates/gift-empty/propose", headers=ann).status_code == 409
    made = c.post("/v1/org-templates", headers=ann, json={"yaml": yaml.safe_dump(MINE)})
    assert made.status_code == 201 and made.json()["check"]["ok"] and made.json()["status"] == "draft"
    assert "gift-cards" not in [t["id"] for t in c.get("/v1/templates", headers=ann).json()["templates"]]          # a draft is not in the Hub
    assert c.post("/v1/org-templates/gift-cards/propose", headers=ann).json()["status"] == "proposed"
    me = c.post("/v1/org-templates/gift-cards/approve", headers=ann, json={})
    assert me.status_code == 403 and "second person" in me.json()["error"]["message"]
    done = c.post("/v1/org-templates/gift-cards/approve", headers=ben, json={})
    assert done.status_code == 200 and done.json()["status"] == "published"
    hub = {t["id"]: t for t in c.get("/v1/templates", headers=ann).json()["templates"]}["gift-cards"]
    assert hub["provenance"]["source"] == "organization" and hub["provenance"]["approvedBy"] != hub["provenance"]["proposedBy"] and hub["provenance"]["signed"] is False
    assert c.get("/v1/templates/gift-cards", headers=ann).status_code == 200
    assert c.post("/v1/templates/gift-cards/render", headers=ann, json={"agentId": "gifts", "params": {"company_name": "Acme"}}).status_code == 200
    actions = [e["action"] for e in c.get("/v1/audit?limit=40", headers=BOOT).json()["entries"]]
    assert {"org_template.create", "org_template.propose", "org_template.approve"} <= set(actions)


def test_a_new_version_waits_for_review_and_the_published_one_stays_until_then():
    c, rt, key, builtin = world()
    ann, ben = key("ann"), key("ben")
    c.post("/v1/org-templates", headers=ann, json={"template": MINE})
    c.post("/v1/org-templates/gift-cards/propose", headers=ann)
    c.post("/v1/org-templates/gift-cards/approve", headers=ben, json={})
    v2 = c.put("/v1/org-templates/gift-cards", headers=ann, json={"template": {**MINE, "title": "Gift cards and vouchers"}}).json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    rt.org_templates._invalidate()
    assert {t["id"]: t for t in c.get("/v1/templates", headers=ann).json()["templates"]}["gift-cards"]["title"] == "Gift cards"
    assert c.put("/v1/org-templates/gift-cards", headers=ann, json={"template": {**MINE, "id": "other"}}).status_code == 400
    c.post("/v1/org-templates/gift-cards/propose", headers=ann)
    assert c.put("/v1/org-templates/gift-cards", headers=ann, json={"template": MINE}).status_code == 409        # frozen while in review
    assert c.post("/v1/org-templates/gift-cards/reject", headers=ben, json={"note": "no"}).json()["status"] == "rejected"
    rt.org_templates._invalidate()
    assert {t["id"]: t for t in c.get("/v1/templates", headers=ann).json()["templates"]}["gift-cards"]["title"] == "Gift cards"
    c.put("/v1/org-templates/gift-cards", headers=ann, json={"template": {**MINE, "title": "Gift cards and vouchers"}})
    c.post("/v1/org-templates/gift-cards/propose", headers=ann)
    c.post("/v1/org-templates/gift-cards/approve", headers=ben, json={})
    after = c.get("/v1/org-templates", headers=ann).json()["templates"][0]
    assert [(v["version"], v["status"]) for v in after["versions"]][:2] == [(3, "published"), (2, "rejected")] or after["status"] == "published"
    dev = key("dev", "developer")
    assert c.post("/v1/org-templates/gift-cards/withdraw", headers=dev, json={}).status_code == 403
    assert c.post("/v1/org-templates/gift-cards/withdraw", headers=ben, json={"note": "retired"}).json()["status"] == "withdrawn"
    rt.org_templates._invalidate()
    assert "gift-cards" not in [t["id"] for t in c.get("/v1/templates", headers=ann).json()["templates"]]
    assert c.get("/v1/org-templates", headers=None).status_code == 401


def test_an_org_template_installs_like_any_other():
    c, rt, key, builtin = world()
    ann, ben = key("ann"), key("ben")
    c.post("/v1/org-templates", headers=ann, json={"template": MINE})
    c.post("/v1/org-templates/gift-cards/propose", headers=ann)
    c.post("/v1/org-templates/gift-cards/approve", headers=ben, json={})
    r = c.post("/v1/templates/gift-cards/requirements", headers=ann, json={"agentId": "gifts", "params": {}})
    assert r.status_code == 200 and r.json()["ok"]


async def test_org_templates_survive_the_database_and_stay_in_their_tenant(app_engine):
    from contextlib import contextmanager

    from northcx.db import PgOrgTemplates
    from northcx.tenancy import TENANT

    @contextmanager
    def as_tenant(name):
        token = TENANT.set(name)
        try:
            yield
        finally:
            TENANT.reset(token)
    s = OrgTemplateService(PgOrgTemplates(app_engine), set(load_templates(LIBRARY)))
    for tenant in ("acme", "globex"):
        with as_tenant(tenant):
            o = await s.create(MINE, "key:1")
            await s.propose(o.id, "key:1")
            await s.decide(o.id, True, "key:2", None)
    with as_tenant("acme"):
        assert list((await s.published()).keys()) == ["gift-cards"]
        v2 = await s.revise("gift-cards", {**MINE, "title": "Vouchers"}, "key:1")
        assert v2.version == 2 and [x.status for x in await s.repo.versions("gift-cards")] == ["draft", "published"]
    with as_tenant("globex"):
        assert [v.version for v in await s.repo.versions("gift-cards")] == [1]
    with as_tenant("nobody"):
        assert await s.repo.list() == [] and await s.published() == {}


def test_a_built_in_with_no_signature_is_refused_while_a_signing_key_ships():
    from northcx.api.template_lookup import tampered
    from northcx.templates import Template
    t = load_templates(LIBRARY)["complaints"]
    assert tampered(t) is None
    unsigned = Template(**{**t.__dict__, "provenance": {**t.provenance, "signed": False, "verified": False, "status": "unsigned"}})
    assert "unsigned" in tampered(unsigned)
    no_key = Template(**{**t.__dict__, "provenance": {**t.provenance, "signed": False, "verified": False, "keyFingerprint": None, "status": "unsigned"}})
    assert tampered(no_key) is None                                  # no key shipped at all: nothing to check against
    local = Template(**{**t.__dict__, "provenance": {"source": "file", "signed": False, "verified": False, "status": "local file"}})
    assert tampered(local) is None
