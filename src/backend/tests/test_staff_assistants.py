"""Staff assistants as Hub entries (audience: staff) and the Workspace Assistants catalog."""
import asyncio

from fastapi.testclient import TestClient

from examples.support_agent import registry as example_registry
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.spec import BuildContext
from northcx.store import InMemoryStore
from northcx.templates import LIBRARY, load_templates, render
from northcx.trace import TraceStore
from northcx.workspace import WorkspaceService, register_staff_tools

KEY = "boot" * 10


class NoDraft:
    """A staff policy that withholds one tool."""
    model = None

    def allows(self, role, tool):
        return tool != "draft_reply"


def world(policy=None):
    loop = asyncio.new_event_loop()
    llm = ScriptedLLM([text("Three hand-offs are waiting [1].")] * 4)
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    rt.workspace_policy = policy
    reg = example_registry()
    register_staff_tools(reg, WorkspaceService(rt, rt.traces, None, None, None, None))
    templates = load_templates(LIBRARY)
    agents = {}
    for tid in ("handoff-assistant", "shift-briefing"):
        r = render(templates[tid], tid, {}, reg)
        assert r.warnings == [] and r.spec.audience == "staff"
        agents[tid] = reg.build(r.spec, BuildContext(llm=llm))
    ac = AccessControl(bootstrap_key=KEY)
    c = TestClient(create_app(rt, rt.traces, agents, access=ac))
    key = lambda name, role="viewer": {"authorization": "Bearer " + loop.run_until_complete(ac.issue(name, role, "t"))[1]}  # noqa: E731
    return c, rt, key


def test_the_staff_templates_are_for_staff_only_and_a_customer_agent_cannot_use_their_tools():
    templates = load_templates(LIBRARY)
    staff = {t.id for t in templates.values() if t.audience == "staff"}
    assert staff == {"handoff-assistant", "shift-briefing", "conversation-analyst", "policy-guide"}
    reg = example_registry()
    register_staff_tools(reg, WorkspaceService(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), None, None, None, None, None))
    from northcx.spec import AgentSpec
    problems = reg.validate(AgentSpec.model_validate({"spec_version": 1, "id": "sneaky", "instructions": "x", "tools": ["list_handoffs"]}))
    assert any("only for agents that help your own staff" in p for p in problems)                      # audience customer: refused


def test_the_catalog_lists_live_staff_assistants_with_what_this_person_can_use():
    c, rt, key = world()
    out = c.get("/v1/workspace/assistants", headers=key("rae")).json()["assistants"]
    ids = {a["id"]: a for a in out}
    assert set(ids) == {"handoff-assistant", "shift-briefing"}
    assert [t["name"] for t in ids["handoff-assistant"]["tools"]] == ["list_handoffs", "get_conversation", "summarise_conversation", "draft_reply"] and ids["handoff-assistant"]["unavailableTools"] == []
    assert ids["handoff-assistant"]["description"].startswith("You are a staff assistant")
    assert c.get("/v1/workspace/assistants").status_code == 401


def test_the_staff_policy_narrows_what_an_assistant_may_use_for_each_person():
    c, rt, key = world(NoDraft())
    rae = key("rae")
    ids = {a["id"]: a for a in c.get("/v1/workspace/assistants", headers=rae).json()["assistants"]}
    assert "draft_reply" not in [t["name"] for t in ids["handoff-assistant"]["tools"]] and ids["handoff-assistant"]["unavailableTools"] == ["draft_reply"]
    r = c.post("/v1/workspace/assistants/handoff-assistant/chat", headers=rae, json={"message": "What is waiting for me?"}).json()
    assert r["tools"] == ["list_handoffs", "get_conversation", "summarise_conversation"] and "waiting" in r["reply"]


def test_chatting_with_an_assistant_runs_it_for_the_person_and_keeps_its_own_history():
    c, rt, key = world()
    rae = key("rae")
    first = c.post("/v1/workspace/assistants/shift-briefing/chat", headers=rae, json={"message": "Brief me"})
    assert first.status_code == 200 and first.json()["assistant"] == "shift-briefing" and first.json()["traceId"]
    again = c.post("/v1/workspace/assistants/shift-briefing/chat", headers=rae, json={"message": "More", "chatId": first.json()["chatId"]})
    assert again.json()["chatId"] == first.json()["chatId"]
    assert c.post("/v1/workspace/assistants/nope/chat", headers=rae, json={"message": "hi"}).status_code == 404
    assert c.post("/v1/workspace/assistants/support/chat", headers=rae, json={"message": "hi"}).status_code == 404    # not a staff assistant
    temp = c.post("/v1/workspace/assistants/shift-briefing/chat", headers=rae, json={"message": "Secret", "temporary": True}).json()
    assert temp["traceId"] is None and temp["temporary"] is True
    actions = [e["action"] for e in c.get("/v1/audit?limit=20", headers={"authorization": f"Bearer {KEY}"}).json()["entries"]]
    assert "workspace.assistant_chat" in actions


def test_a_chat_token_for_customers_cannot_reach_the_assistants():
    c, rt, key = world()
    r = c.post("/v1/workspace/assistants/shift-briefing/chat", headers=key("bot", "channel"), json={"message": "hi"})
    assert r.status_code in (401, 403)
