"""Secrets, dry-run mode, readiness and configuration."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from examples.support_agent import registry as example_registry, support_agent
from northcx.agent import Agent, Tool
from northcx.approval_flow import ApprovalFlow
from northcx.config import load_registry
from northcx.handoffs import actions
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.secrets import ConfigError, SecretStore, env_or_file
from northcx.server import create_app
from northcx.simulation import SimConfig, SimulationRunner, load_scenarios, parse_scenario
from northcx.spec import BuildContext, Registry, load_specs
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "sk-live-0123456789abcdef"


# ---------------- reading secrets ----------------
def test_env_or_file_prefers_one_source_and_strips_the_newline(tmp_path):
    f = tmp_path / "s"
    f.write_text("from-file\n")
    assert env_or_file("A", {"A": "from-env"}) == "from-env"
    assert env_or_file("A", {"A_FILE": str(f)}) == "from-file"
    assert env_or_file("A", {}) is None and env_or_file("A", {}, "dflt") == "dflt"
    with pytest.raises(ConfigError, match="only one of A and A_FILE"):
        env_or_file("A", {"A": "x", "A_FILE": str(f)})
    with pytest.raises(ConfigError, match="cannot read"):
        env_or_file("A", {"A_FILE": str(tmp_path / "missing")})
    (tmp_path / "e").write_text("\n")
    with pytest.raises(ConfigError, match="is empty"):
        env_or_file("A", {"A_FILE": str(tmp_path / "e")})


def test_secret_store_reads_the_environment_and_files(tmp_path):
    f = tmp_path / "crm"
    f.write_text("crm-secret-value-123\n")
    env = {"NORTHCX_SECRET_PAYMENTS_KEY": TOKEN, "NORTHCX_SECRET_CRM_FILE": str(f), "NORTHCX_API_KEY": "bootstrap-key-123456",
           "ANTHROPIC_API_KEY": "anthropic-key-123456", "UNRELATED": "x"}
    s = SecretStore.from_env(env)
    assert s.names() == ["crm", "payments_key"] and s.get("PAYMENTS_KEY") == TOKEN and s.get("crm") == "crm-secret-value-123"
    with pytest.raises(KeyError) as e:
        s.get("nope")
    assert "NORTHCX_SECRET_NOPE" in str(e.value) and TOKEN not in str(e.value)
    with pytest.raises(KeyError):
        s.get("NORTHCX_API_KEY")  # the platform's own keys are scrubbed but never handed to tools
    assert "bootstrap-key-123456" not in json.dumps(s.names()) and s.redact_text("x bootstrap-key-123456 y") == "x [redacted:NORTHCX_API_KEY] y"


def test_short_secrets_are_refused_because_they_cannot_be_scrubbed_safely():
    with pytest.raises(ConfigError, match="too short"):
        SecretStore({"pin": "1234"})
    with pytest.raises(ConfigError, match="too short"):
        SecretStore.from_env({"NORTHCX_SECRET_PIN": "abc"})


def test_redaction_handles_overlaps_repeats_and_structures():
    s = SecretStore({"short": "secret-abc", "long": "secret-abc-and-more"})
    assert s.redact_text("a secret-abc-and-more b secret-abc c secret-abc") == "a [redacted:long] b [redacted:short] c [redacted:short]"
    obj = {"k": ["x secret-abc", ("secret-abc-and-more", 5)], "secret-abc": {"n": None, "ok": True}, 7: "secret-abc"}
    assert s.redact(obj) == {"k": ["x [redacted:short]", ("[redacted:long]", 5)], "[redacted:short]": {"n": None, "ok": True}, 7: "[redacted:short]"}
    assert SecretStore().redact({"a": "anything"}) == {"a": "anything"}


# ---------------- secrets never leak ----------------
class Q(BaseModel):
    q: str


def leaky_agent(counter=None):
    secrets_seen = []

    def lookup(d: Q, ctx):
        key = ctx.secret("payments_key")
        secrets_seen.append(key)
        if d.q == "boom":
            raise RuntimeError(f"gateway rejected key {key}")
        return {"status": "ok", "echo_of_credentials": key, "nested": [f"Bearer {key}"]}

    return Agent(id="a", instructions="x", tools=[Tool("lookup", "d", Q, lookup, effect="read")]), secrets_seen


def runtime_with_secrets(script, **kw):
    secrets = SecretStore({"payments_key": TOKEN}, {"NORTHCX_API_KEY": "bootstrap-key-123456"})
    return Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore(), secrets=secrets, **kw)


def everything_kept(rt, result):
    """All the places a secret could end up."""
    return json.dumps({"history": result and rt.store._msgs, "trace": result.trace.to_dict(),
                       "traces": [t.to_dict() for t in rt.traces._traces.values()], "reply": result.reply,
                       "handoffs": [h.package for h in rt.handoffs._items.values()]}, default=str)


async def test_a_tool_can_use_a_secret_but_it_never_reaches_the_model_or_anything_we_keep():
    agent, seen = leaky_agent()
    rt = runtime_with_secrets([tool_call("lookup", {"q": "x"}, "t1"), text(f"Done. (internal note: {TOKEN})")])
    r = await rt.run(agent, "s", "check it")
    assert seen == [TOKEN]  # the tool really received the credential
    first_result = json.dumps(rt.llm.requests[1].messages[2])  # the tool result the model was given
    assert TOKEN not in first_result and "[redacted:payments_key]" in first_result  # the model was never shown it
    kept = everything_kept(rt, r)
    assert TOKEN not in kept and "[redacted:payments_key]" in kept  # nor was it stored, including the model's own reply
    assert TOKEN not in r.reply  # even if the model somehow said it


async def test_secrets_in_tool_errors_are_scrubbed_too():
    agent, _ = leaky_agent()
    rt = runtime_with_secrets([tool_call("lookup", {"q": "boom"}, "t1"), text("sorry"), tool_call("handoff_to_human", {"reason": "x"}, "t2")])
    r = await rt.run(agent, "s", "check")
    assert "gateway rejected key [redacted:payments_key]" in json.dumps(rt.llm.requests[1].messages[2])
    assert TOKEN not in everything_kept(rt, r)


async def test_handoff_packages_and_outbox_messages_are_scrubbed_as_well():
    agent, _ = leaky_agent()
    rt = runtime_with_secrets([text(f"I looked and the key {TOKEN} was rejected"), tool_call("handoff_to_human", {"reason": f"key {TOKEN} failed"}, "t")])
    # the first draft is a plain reply, so the second scripted response is used by a second message
    await rt.run(agent, "s", "hello")
    r = await rt.run(agent, "s", "get me a person")
    assert r.status == "escalated"
    h = (await rt.handoffs.list())[0]
    assert TOKEN not in json.dumps(h.package) and TOKEN not in h.reason
    assert any("[redacted:payments_key]" in m["text"] for m in h.package["transcript"])


async def test_a_secret_missing_from_the_configuration_is_a_clear_tool_error():
    agent, _ = leaky_agent()
    rt = Runtime(ScriptedLLM([tool_call("lookup", {"q": "x"}, "t1"), text("sorry")]), InMemoryStore(), TraceStore())  # no secrets
    r = await rt.run(agent, "s", "check")
    assert "NORTHCX_SECRET_PAYMENTS_KEY" in str(rt.llm.requests[1].messages) and r.status == "completed"


async def test_approved_actions_get_secrets_and_scrub_their_results():
    def pay(d: Q, ctx):
        return {"charged": d.q, "auth": ctx.secret("payments_key")}

    agent = Agent(id="a", instructions="x", tools=[Tool("pay", "d", Q, pay, requires_approval=lambda d: "needs a person")])
    rt = runtime_with_secrets([tool_call("pay", {"q": "50"}, "t1"), text("Charged.")])
    held = await rt.run(agent, "s", "pay 50")
    res = await ApprovalFlow(rt).resolve({"a": agent}, held.pending_approvals[0]["id"], True, "rae")
    approval = await rt.approvals.get(held.pending_approvals[0]["id"])
    assert approval.state == "executed" and TOKEN not in json.dumps(approval.result) and "[redacted:payments_key]" in json.dumps(approval.result)
    assert TOKEN not in json.dumps(rt.llm.requests[1].messages[:4]) and TOKEN not in everything_kept(rt, res.run)


# ---------------- dry-run ----------------
class Amt(BaseModel):
    amount: float


class Spy:
    def __init__(self):
        self.reads, self.writes = 0, 0


def spy_agent(spy, with_result=True):
    def read(d: Q, ctx):
        spy.reads += 1
        return {"found": d.q}

    def write(d: Amt, ctx):
        spy.writes += 1
        return {"refunded": d.amount}

    tools = [Tool("look", "d", Q, read, effect="read"),
             Tool("refund", "d", Amt, write, requires_approval=lambda d: "big" if d.amount > 100 else None,
                  dry_run_result=(lambda d, c: {"refunded": d.amount, "pretend": True}) if with_result else None)]
    return Agent(id="a", instructions="x", tools=tools)


async def test_dry_run_reads_normally_and_simulates_writes():
    spy = Spy()
    rt = Runtime(ScriptedLLM([tool_call("look", {"q": "1"}, "t1"), tool_call("refund", {"amount": 20}, "t2"), text("done")]),
                 InMemoryStore(), TraceStore(), dry_run=True)
    r = await rt.run(spy_agent(spy), "s", "go")
    assert (spy.reads, spy.writes) == (1, 0)
    results = [e for e in r.trace.events if e.type == "tool_result"]
    assert results[0].data.get("dry_run") is None and results[1].data["dry_run"] is True
    assert results[1].data["output"] == {"refunded": 20.0, "pretend": True}  # the tool's own simulation
    assert [(a["tool"], a["outcome"]) for a in actions([r.trace])] == [("look", "succeeded"), ("refund", "simulated")]


async def test_without_a_simulation_a_generic_placeholder_is_used():
    spy = Spy()
    rt = Runtime(ScriptedLLM([tool_call("refund", {"amount": 5}, "t1"), text("ok")]), InMemoryStore(), TraceStore(), dry_run=True)
    r = await rt.run(spy_agent(spy, with_result=False), "s", "go")
    out = next(e for e in r.trace.events if e.type == "tool_result").data["output"]
    assert spy.writes == 0 and out == {"dry_run": True, "would_run": "refund", "input": {"amount": 5.0}}


async def test_a_normal_run_executes_writes():
    spy = Spy()
    rt = Runtime(ScriptedLLM([tool_call("refund", {"amount": 5}, "t1"), text("ok")]), InMemoryStore(), TraceStore())
    r = await rt.run(spy_agent(spy), "s", "go")
    assert spy.writes == 1 and next(e for e in r.trace.events if e.type == "tool_result").data.get("dry_run") is None


async def test_approved_actions_are_simulated_in_dry_run_too():
    spy = Spy()
    agent = spy_agent(spy)
    rt = Runtime(ScriptedLLM([tool_call("refund", {"amount": 500}, "t1"), text("ok")]), InMemoryStore(), TraceStore(), dry_run=True)
    held = await rt.run(agent, "s", "go")
    await ApprovalFlow(rt).resolve({"a": agent}, held.pending_approvals[0]["id"], True, "rae")
    a = await rt.approvals.get(held.pending_approvals[0]["id"])
    assert spy.writes == 0 and a.state == "executed" and a.result["dry_run"] is True and a.result["result"]["pretend"] is True


def test_tools_default_to_write_and_reject_unknown_effects():
    assert Tool("t", "d", Q, lambda d, c: 1).effect == "write"  # the safe assumption
    with pytest.raises(ValueError, match="effect must be"):
        Tool("t", "d", Q, lambda d, c: 1, effect="maybe")


async def test_simulations_never_run_write_tools_unless_told_to():
    spy = Spy()
    reg = Registry()
    reg.tool(spy_agent(spy).tools[0])
    reg.tool(spy_agent(spy).tools[1])
    sc = parse_scenario({"name": "s", "agent": "a", "model": [{"tool_call": {"name": "refund", "input": {"amount": 30}}}, {"text": "done"}],
                         "turns": [{"say": "refund me"}], "expect": {"tools_called": ["refund"]}})
    from northcx.spec import parse_spec
    spec = parse_spec("id: a\ninstructions: x\ntools: [look, refund]\n")
    build = lambda aid, llm: reg.build(spec, BuildContext(llm=llm))  # noqa: E731
    assert (await SimulationRunner(build, SimConfig()).run_scenario(sc)).passed
    assert spy.writes == 0
    assert (await SimulationRunner(build, SimConfig(dry_run=False)).run_scenario(sc)).passed
    assert spy.writes == 1


def test_command_line_has_an_explicit_switch_for_real_side_effects(monkeypatch):
    import northcx.simulation.__main__ as cli
    seen = {}

    class Stub:
        def __init__(self, factory, cfg, digests):
            seen["cfg"] = cfg

        async def run_suite(self, scenarios):
            from northcx.simulation.report import SuiteResult
            return SuiteResult("scripted", [])

    monkeypatch.setattr(cli, "SimulationRunner", Stub)
    args = [str(ROOT / "examples" / "scenarios"), "--specs", str(ROOT / "examples"), "--registry", "examples.support_agent:registry"]
    assert cli.main(args) == 0 and seen["cfg"].dry_run is True
    assert cli.main(args + ["--allow-side-effects"]) == 0 and seen["cfg"].dry_run is False


def test_the_example_agent_declares_which_tools_write():
    tools = {t.name: t for t in support_agent().tools}
    assert tools["lookup_order"].effect == "read" and tools["issue_refund"].effect == "write" and tools["issue_refund"].dry_run_result
    with pytest.raises(ValueError, match="delivered"):  # the simulation applies the same business rules
        tools["issue_refund"].dry_run_result(tools["issue_refund"].input_model(order_id="3150", amount=5), None)


# ---------------- readiness ----------------
def app_for(runtime, traces=None):
    traces = traces or TraceStore()
    return TestClient(create_app(runtime, traces, {"support": support_agent()}, api_key="k" * 30))


def test_readiness_is_public_and_reports_a_broken_store():
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = app_for(rt)
    assert c.get("/ready").json() == {"ready": True} and c.get("/health").json() == {"ok": True}  # no key needed
    assert c.get("/v1/agents").status_code == 401

    class Down(InMemoryStore):
        async def load_messages(self, session_id):
            raise ConnectionError("database is down")

    r = app_for(Runtime(ScriptedLLM([]), Down(), TraceStore())).get("/ready")
    assert r.status_code == 503 and r.json() == {"ready": False} and "down" not in r.text  # no internals leaked


async def test_readiness_against_postgres(engine):
    from northcx.db import PgMemoryStore, PgTraceStore
    rt = Runtime(ScriptedLLM([]), PgMemoryStore(engine), PgTraceStore(engine))
    c = app_for(rt, rt.traces)
    assert c.get("/ready").status_code == 200


# ---------------- configuration ----------------
def test_the_tool_registry_comes_from_configuration():
    assert isinstance(load_registry("examples.support_agent:registry"), Registry)
    for ref, msg in [("nonsense", "must look like"), (":fn", "must look like"), ("no.such.module:fn", "cannot import"),
                     ("examples.support_agent:missing", "has no"), ("examples.support_agent:ORDERS", None)]:
        with pytest.raises((ConfigError, TypeError)) as e:
            load_registry(ref)
        if msg:
            assert msg in str(e.value)
    with pytest.raises(ConfigError, match="not a Registry"):
        load_registry("examples.support_agent:support_agent")
