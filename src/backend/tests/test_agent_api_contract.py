"""The Agent API contract (Phase 1, WP 1.1): the snapshot matches the code, and a breaking change within /v1 is caught."""
import copy
import json

from tests.test_docs_in_sync import ROOT, load

gen = load("gen_agent_api_contract")
CHAT = "POST /v1/agents/{agent_id}/chat"


def snapshot():
    return json.loads((ROOT / "docs" / "api" / "agent-api-v1.json").read_text())


def test_the_snapshot_matches_the_api_reference():
    current = gen.build_contract(json.loads((ROOT / "docs" / "api" / "openapi.json").read_text()))
    assert gen.breaking_changes(snapshot(), current) == [], "breaking change within /v1"
    assert snapshot() == current, "docs/api/agent-api-v1.json is out of date: run python scripts/gen_agent_api_contract.py"


def test_the_contract_covers_chat_approvals_handoffs_versions_simulations_traces_and_events():
    ops = snapshot()["operations"]
    for key in (CHAT, "POST /v1/agents/{agent_id}/chat/stream", "POST /v1/approvals/{approval_id}/decision", "POST /v1/handoffs/{handoff_id}/reply",
                "POST /v1/agents/{agent_id}/versions", "POST /v1/agents/{agent_id}/releases", "POST /v1/simulations/runs", "GET /v1/traces/{trace_id}", "GET /v1/events"):
        assert key in ops, key
    assert all(" /v1/" in k and k.split("/")[2] in gen.GROUPS for k in ops)
    assert ops[CHAT]["permission"] == "chat:send"


def changed(mutate):
    new = copy.deepcopy(snapshot())
    mutate(new["operations"])
    return gen.breaking_changes(snapshot(), new)


def test_adding_a_route_an_optional_field_or_an_optional_parameter_is_allowed():
    def add(ops):
        ops["GET /v1/agents/{agent_id}/new"] = copy.deepcopy(ops["GET /v1/agents/{agent_id}/live"])
        ops[CHAT]["request"]["schema"]["properties"]["tone"] = {"type": "string"}
        ops["GET /v1/handoffs"]["parameters"].append({"name": "since", "in": "query", "required": False, "schema": {"type": "string"}})
    assert changed(add) == []


def test_removing_a_route_is_breaking():
    assert changed(lambda ops: ops.pop(CHAT)) == [f"{CHAT}: removed"]


def test_removing_or_retyping_a_request_field_is_breaking():
    assert changed(lambda ops: ops[CHAT]["request"]["schema"]["properties"].pop("message")) == [f"{CHAT}: request.message: removed"]
    assert changed(lambda ops: ops[CHAT]["request"]["schema"]["properties"].__setitem__("message", {"type": "integer"})) == [f"{CHAT}: request.message: type changed"]


def test_a_newly_required_request_field_or_parameter_is_breaking():
    assert changed(lambda ops: ops[CHAT]["request"]["schema"]["required"].append("channel")) == [f"{CHAT}: request.channel: newly required"]
    new_param = {"name": "mode", "in": "query", "required": True, "schema": {"type": "string"}}
    assert changed(lambda ops: ops["GET /v1/handoffs"]["parameters"].append(new_param)) == ["GET /v1/handoffs: parameter mode newly required"]


def test_removing_a_parameter_or_an_accepted_value_is_breaking():
    assert changed(lambda ops: ops["GET /v1/handoffs"]["parameters"].clear())[0].startswith("GET /v1/handoffs: parameter ")
    old = {"operations": {"X": {"parameters": [], "request": {"required": True, "schema": {"type": "string", "enum": ["a", "b"]}}}}}
    new = {"operations": {"X": {"parameters": [], "request": {"required": True, "schema": {"type": "string", "enum": ["a"]}}}}}
    assert gen.breaking_changes(old, new) == ["X: request: no longer accepts ['b']"]
