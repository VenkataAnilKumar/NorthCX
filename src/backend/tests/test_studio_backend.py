"""What the Studio editor needs from the server: a catalog of building blocks and a no-save check of a spec."""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios
from northcx.spec import AgentSpec, load_specs
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}
KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def setup():
    r = registry()
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, SPECS, SimulationService(load_scenarios(ROOT / "examples" / "scenarios"), lambda a, l: None, InMemorySimRuns(), {}))
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc)), ac, svc


def base_spec():
    return json.loads(SPECS["support"].canonical())


def test_the_catalog_lists_every_building_block_with_enough_to_choose():
    d = registry().describe()
    tools = {t["name"]: t for t in d["tools"]}
    assert tools["issue_refund"]["effect"] == "write" and tools["issue_refund"]["approval"] is True and tools["issue_refund"]["inputs"] == ["order_id", "amount"]
    assert tools["lookup_order"]["effect"] == "read" and tools["lookup_order"]["approval"] is False
    g = {x["name"]: x for x in d["guardrails"]}
    assert g["tool_limit"]["example"] == {"tool": "issue_refund", "field": "amount", "max": 100} and "numeric" in g["tool_limit"]["description"] and "no_card_numbers" in g
    assert {x["name"] for x in d["inputGuardrails"]} >= {"pii_detection", "prompt_injection"} and {x["name"] for x in d["outputGuardrails"]} >= {"tool_output_injection"}
    assert [s["name"] for s in d["skills"]] == ["order_status", "refund_flow"] and d["skills"][1]["steps"][0].startswith("Look up") and d["flexibility"] == ["strict", "guided", "free"]


def test_api_catalog_and_permissions():
    c, ac, svc = setup()
    assert c.get("/v1/catalog", headers=H).json()["tools"]
    chan = asyncio.new_event_loop().run_until_complete(ac.issue("c", "channel", "root"))[1]
    assert c.get("/v1/catalog", headers={"authorization": f"Bearer {chan}"}).status_code == 403
    off = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {"support": support_agent()}))
    assert off.get("/v1/catalog").status_code == 501


async def test_preview_reports_every_problem_and_never_saves():
    c, ac, svc = setup()
    spec = base_spec()
    ok = await svc.preview("support", spec)
    assert ok["valid"] and ok["problems"] == [] and ok["diffFromLive"]["identical"] is False or ok["diffFromLive"]["identical"] is True
    assert await svc.versions.list("support") == []  # nothing saved
    bad = await svc.preview("support", {**spec, "tools": ["nope", "lookup_order"], "guardrails": ["ghost"], "max_steps": 999, "skills": [{"name": "missing"}]})
    assert bad["valid"] is False and any("Most steps per message" in p for p in bad["problems"])
    named = await svc.preview("support", {**spec, "tools": ["nope"], "guardrails": ["ghost"], "skills": [{"name": "missing"}]})
    text = "; ".join(named["problems"])
    assert "a tool called 'nope'" in text and "The reply check 'ghost' does not exist" in text and "The skill 'missing' does not exist" in text
    assert (await svc.preview("support", {**spec, "id": "other"}))["problems"] == ["The agent id is 'other' but this agent is 'support'. Change the id back to 'support'."]
    assert (await svc.preview("support", {"nonsense": 1}))["valid"] is False
    cfg = await svc.preview("support", {**spec, "guardrails": [{"name": "tool_limit", "config": {}}]})
    assert cfg["valid"] is False and "guardrail configuration for 'tool_limit'" in cfg["problems"][0] and "tool" in cfg["problems"][0] and "field" in cfg["problems"][0]


async def test_preview_shows_what_changes_compared_with_production_and_whether_it_is_already_saved():
    c, ac, svc = setup()
    spec = base_spec()
    same = await svc.preview("support", spec)
    assert same["diffFromLive"]["identical"] is True and same["unchangedSinceLatest"] is False
    changed = {**spec, "instructions": spec["instructions"] + "\nAlways greet by name.\n", "max_steps": 5, "tools": ["lookup_order"]}
    d = (await svc.preview("support", changed))["diffFromLive"]
    assert "+Always greet by name." in d["instructions"] and d["tools"]["removed"] == ["issue_refund"] and d["other"]["max_steps"] == {"from": 8, "to": 5}
    await svc.create_version("support", AgentSpec.model_validate(changed), "dev")
    assert (await svc.preview("support", changed))["unchangedSinceLatest"] is True


def test_api_preview_endpoint():
    c, ac, svc = setup()
    r = c.post("/v1/agents/support/versions/preview", json={"spec": base_spec()}, headers=H).json()
    assert r["valid"] and len(r["digest"]) == 64
    assert c.post("/v1/agents/support/versions/preview", json={"spec": {**base_spec(), "tools": ["nope"]}}, headers=H).json()["valid"] is False
    assert c.post("/v1/agents/support/versions/preview", json={}, headers=H).status_code == 400
    assert c.get("/v1/agents/support/versions", headers=H).json()["versions"] == []
    loop = asyncio.new_event_loop()
    for role, code in [("developer", 200), ("viewer", 403), ("reviewer", 403)]:
        k = loop.run_until_complete(ac.issue(role, role, "root"))[1]
        assert c.post("/v1/agents/support/versions/preview", json={"spec": base_spec()}, headers={"authorization": f"Bearer {k}"}).status_code == code, role


async def test_a_valid_preview_says_in_plain_sentences_what_the_agent_will_do():
    c, ac, svc = setup()
    out = await svc.preview("support", base_spec())
    assert out["valid"] is True and out["summary"][0] == "This agent answers customers." and any("lookup order" in s for s in out["summary"])
    assert "summary" not in (await svc.preview("support", {"nonsense": 1}))
