"""Tool sources and fingerprints (Phase 1, WP 1.2): each tool records where it came from, sources register through one function
that refuses a duplicate name, and a tool's definition has a fingerprint that changes when it changes."""
import dataclasses

import pytest
from pydantic import BaseModel

from northcx.agent import Agent, Tool, tool_fingerprint
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.spec import Registry, SpecError
from northcx.store import InMemoryStore
from northcx.trace import TraceStore


class In(BaseModel):
    id: str


class Other(BaseModel):
    id: str
    extra: int = 0


def tool(name="lookup", **kw):
    return Tool(name, "look up an order", In, lambda d, c: {"ok": True}, effect="read", **kw)


def test_a_tool_defaults_to_the_registry_source():
    assert tool().source == "registry"


def test_add_tools_sets_the_source_and_describe_shows_it():
    r = Registry()
    r.add_tools("connectors", [tool("a"), tool("b")])
    r.add_tools("memory", [tool("c")])
    assert {t["name"]: t["source"] for t in r.describe()["tools"]} == {"a": "connectors", "b": "connectors", "c": "memory"}


def test_a_duplicate_name_from_another_source_names_both_sources():
    r = Registry()
    r.add_tools("registry", [tool("lookup")])
    with pytest.raises(SpecError) as e:
        r.add_tools("connectors", [tool("lookup")])
    assert "lookup" in str(e.value) and "connectors" in str(e.value) and "registry" in str(e.value)


def test_a_failed_add_registers_nothing_from_that_batch():
    r = Registry()
    r.add_tools("registry", [tool("b")])
    with pytest.raises(SpecError):
        r.add_tools("connectors", [tool("a"), tool("b")])
    assert r.tool_names() == ["b"]


def test_an_unknown_source_is_refused():
    with pytest.raises(SpecError):
        Registry().add_tools("somewhere", [tool()])


def test_the_fingerprint_is_stable_and_ignores_source_and_code():
    a = tool()
    assert tool_fingerprint(a) == tool_fingerprint(tool())
    assert tool_fingerprint(a) == tool_fingerprint(dataclasses.replace(a, source="memory", run=lambda d, c: 2))
    assert len(tool_fingerprint(a)) == 64


@pytest.mark.parametrize("change", [
    {"name": "lookup2"},
    {"description": "something else"},
    {"input_model": Other},
    {"effect": "write"},
    {"audience": "staff", "permission": "orders.read"},
    {"requires_approval": lambda d: "always"},
])
def test_the_fingerprint_changes_with_each_part_of_the_definition(change):
    assert tool_fingerprint(dataclasses.replace(tool(), **change)) != tool_fingerprint(tool())


def test_a_staff_permission_change_changes_the_fingerprint():
    a = tool("s", audience="staff", permission="orders.read")
    assert tool_fingerprint(a) != tool_fingerprint(dataclasses.replace(a, permission="orders.write"))


async def test_the_tool_call_trace_event_names_the_source():
    t = dataclasses.replace(tool(), source="connectors")
    rt = Runtime(ScriptedLLM([tool_call("lookup", {"id": "1"}, "t1"), text("done")]), InMemoryStore(), TraceStore())
    res = await rt.run(Agent(id="a", instructions="x", tools=[t]), "s1", "hi")
    calls = [e for e in res.trace.events if e.type == "tool_call"]
    assert [c.data["source"] for c in calls] == ["connectors"]
