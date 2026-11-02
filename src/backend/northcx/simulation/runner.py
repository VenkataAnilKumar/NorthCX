"""Runs scenarios against an agent with fresh in-memory stores. Every scenario also checks platform invariants
(valid saved history) so a regression in the runtime itself cannot hide behind a passing scripted conversation."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..agent import Agent
from ..approval_flow import ApprovalFlow
from ..approvals import ApprovalStore
from ..handoffs import Handoff, InMemoryHandoffs
from ..llm import ScriptedLLM, text, tool_call
from ..outbox import Outbox
from ..runtime import Runtime
from ..store import InMemoryStore
from ..trace import TraceStore
from ..types import LLM, LLMRequest, LLMResponse
from .judge import Judge
from .report import Failure, ScenarioResult, SuiteResult, TrialResult
from .scenario import Decide, ExpireApprovals, FinalExpect, Say, Scenario, StepExpect

AgentFactory = Callable[[str, LLM], Agent]


@dataclass
class SimConfig:
    mode: str = "scripted"  # scripted | demo | live
    live_llm: LLM | None = None  # the model under test in live mode
    judge_llm: LLM | None = None
    skip_judge: bool = False  # skip judge checks (reported as a note) instead of failing them


class RecordingLLM:
    """Wraps the model under test: records what it was sent and what went wrong."""

    def __init__(self, inner: LLM):
        self.inner = inner
        self.requests: list[LLMRequest] = []
        self.errors: list[str] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        try:
            return await self.inner.complete(req)
        except Exception as e:
            self.errors.append(str(e))
            raise

    def sent(self) -> str:
        return "\n".join(r.system + "\n" + json.dumps(r.messages, default=str) for r in self.requests)


@dataclass
class StepData:
    status: str | None = None
    reply: str | None = None
    tools: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    handoff: Handoff | None = None
    approval_state: str | None = None
    expired: int | None = None


def history_problems(messages: list[dict[str, Any]]) -> list[str]:
    """Invariants every saved conversation must satisfy."""
    problems = []
    for i, m in enumerate(messages):
        c = m["content"]
        if isinstance(c, str):
            if "[supervisor]" in c:
                problems.append(f"message {i} still contains supervisor feedback")
            continue
        ids = [b["id"] for b in c if b.get("type") == "tool_use"]
        if m["role"] == "assistant" and ids:
            nxt = messages[i + 1] if i + 1 < len(messages) else None
            answered = {b.get("tool_use_id") for b in nxt["content"]} if nxt and not isinstance(nxt["content"], str) else set()
            missing = [x for x in ids if x not in answered]
            if missing:
                problems.append(f"message {i}: tool_use {missing} has no tool_result")
    if messages and messages[-1]["role"] != "assistant":
        problems.append("saved history does not end on an assistant turn")
    return problems


def check_step(where: str, exp: StepExpect, d: StepData, out: list[Failure]) -> None:
    def fail(check: str, expected: Any, actual: Any) -> None:
        out.append(Failure(where, check, expected, actual))

    if exp.status is not None and d.status != exp.status:
        fail("status", exp.status, d.status)
    for t in exp.tools_called:
        if t not in d.tools:
            fail("tools_called", t, d.tools)
    for t in exp.tools_not_called:
        if t in d.tools:
            fail("tools_not_called", f"not {t}", d.tools)
    reply = (d.reply or "")
    for s in exp.reply_includes:
        if s.lower() not in reply.lower():
            fail("reply_includes", s, reply)
    for s in exp.reply_excludes:
        if s.lower() in reply.lower():
            fail("reply_excludes", f"without {s!r}", reply)
    if exp.reply_matches is not None and not re.search(exp.reply_matches, reply, re.IGNORECASE):
        fail("reply_matches", exp.reply_matches, reply)
    for g in exp.guardrail_hits:
        if g not in d.guardrails:
            fail("guardrail_hits", g, d.guardrails)
    if exp.handoff == "none" and d.handoff is not None:
        fail("handoff", "none", f"{d.handoff.trigger} ({d.handoff.reason})")
    elif exp.handoff not in (None, "none"):
        if d.handoff is None:
            fail("handoff", "a handoff", "none")
        else:
            if exp.handoff.trigger is not None and d.handoff.trigger != exp.handoff.trigger:
                fail("handoff.trigger", exp.handoff.trigger, d.handoff.trigger)
            if exp.handoff.topics is not None and sorted(d.handoff.topics) != sorted(exp.handoff.topics):
                fail("handoff.topics", exp.handoff.topics, d.handoff.topics)
    if exp.approval_state is not None and d.approval_state != exp.approval_state:
        fail("approval_state", exp.approval_state, d.approval_state)
    if exp.expired is not None and d.expired != exp.expired:
        fail("expired", exp.expired, d.expired)


class SimulationRunner:
    def __init__(self, agent_factory: AgentFactory, config: SimConfig | None = None,
                 agent_digests: dict[str, str] | None = None):
        self.agent_factory = agent_factory
        self.cfg = config or SimConfig()
        self.agent_digests = agent_digests or {}

    # ---- model selection ----
    def _inner_llm(self, sc: Scenario) -> tuple[LLM | None, str | None]:
        if self.cfg.mode == "scripted":
            if sc.model is None:
                return None, "no scripted model for this scenario (add 'model:' or run with --model demo/live)"
            script = [text(m.text) if m.text is not None else tool_call(m.tool_call["name"], m.tool_call.get("input", {}))
                      for m in sc.model]
            return ScriptedLLM(script), None
        if self.cfg.mode == "demo":
            from ..demo import DemoLLM

            return DemoLLM(), None
        if self.cfg.live_llm is None:
            return None, "live mode needs a model (set ANTHROPIC_API_KEY)"
        return self.cfg.live_llm, None

    # ---- running ----
    async def run_scenario(self, sc: Scenario) -> ScenarioResult:
        n = sc.trials if self.cfg.mode == "live" else 1
        trials = [await self._trial(sc, i) for i in range(n)]
        rate = sum(t.passed for t in trials) / len(trials)
        notes = []
        if sc.judge and self.cfg.skip_judge:
            notes.append("judge check skipped")
        return ScenarioResult(sc.name, sc.required, rate >= sc.min_pass_rate, trials, rate, sc.source, notes,
                              agent=sc.agent, scenario_digest=sc.digest(), agent_digest=self.agent_digests.get(sc.agent))

    async def _trial(self, sc: Scenario, index: int) -> TrialResult:
        started = time.time()
        failures: list[Failure] = []
        inner, problem = self._inner_llm(sc)
        if inner is None:
            return TrialResult(False, [Failure("scenario", "model", "a usable model", problem)])
        rec = RecordingLLM(inner)
        try:
            agent = self.agent_factory(sc.agent, rec)
        except Exception as e:
            return TrialResult(False, [Failure("scenario", "agent", f"agent '{sc.agent}' available", str(e))])

        store, traces, approvals, handoffs = InMemoryStore(), TraceStore(), ApprovalStore(), InMemoryHandoffs()
        rt = Runtime(rec, store, traces, approvals, Outbox(), handoffs)
        flow = ApprovalFlow(rt)
        agents = {agent.id: agent}
        sid = f"sim-{sc.name}-{index}"
        if sc.facts:
            if not sc.customer_id:
                return TrialResult(False, [Failure("scenario", "facts", "customer_id set when facts are given", None)])
            for k, v in sc.facts.items():
                await store.set_fact(sc.customer_id, k, v)

        all_tools: list[str] = []
        all_guards: list[str] = []
        trace_ids: list[str] = []
        model_calls = 0
        last: StepData = StepData()

        async def latest_handoff() -> Handoff | None:
            found = await handoffs.list(session_id=sid)
            return found[0] if found else None

        for n, step in enumerate(sc.turns, 1):
            d = StepData()
            if isinstance(step, Say):
                where = f"step {n} (say {step.say[:40]!r})"
                r = await rt.run(agent, sid, step.say, sc.customer_id)
                d.status, d.reply = r.status, r.reply
                d.tools = r.trace.tools_called()
                d.guardrails = [e.data.get("guardrail", "") for e in r.trace.events if e.type == "guardrail"]
                d.handoff = await handoffs.get(r.handoff_id) if r.handoff_id else None
                trace_ids.append(r.trace_id)
                model_calls += sum(e.type == "llm" for e in r.trace.events)
            elif isinstance(step, Decide):
                where = f"step {n} ({step.decide})"
                pending = [a for a in await approvals.list("pending") if a.session_id == sid and (not step.tool or a.tool == step.tool)]
                if not pending:
                    failures.append(Failure(where, "pending approval", f"one{' for ' + step.tool if step.tool else ''}", "none"))
                    last = d
                    continue
                target = pending[-1]
                res = await flow.resolve(agents, target.id, step.decide == "approve", step.by, step.note)
                d.approval_state = (await approvals.get(target.id)).state
                if res.run is not None:
                    d.status, d.reply = res.run.status, res.run.reply
                    d.tools = res.run.trace.tools_called()
                    d.guardrails = [e.data.get("guardrail", "") for e in res.run.trace.events if e.type == "guardrail"]
                    d.handoff = await handoffs.get(res.run.handoff_id) if res.run.handoff_id else None
                    trace_ids.append(res.run.trace_id)
                    model_calls += sum(e.type == "llm" for e in res.run.trace.events)
                if res.error:
                    failures.append(Failure(where, "decision", "completed without error", res.error))
            else:
                where = f"step {n} (expire_approvals)"
                done = await flow.expire_stale(agents, 3600, now=time.time() + 7200)
                d.expired = len(done)
                d.handoff = await latest_handoff()
                d.status = "escalated" if done else None
            all_tools += d.tools
            all_guards += d.guardrails
            if step.expect:
                check_step(where, step.expect, d, failures)
            last = d

        # ---- scenario-level checks ----
        fin: FinalExpect = sc.expect
        agg = StepData(status=last.status, reply=last.reply, tools=all_tools, guardrails=all_guards,
                       handoff=await latest_handoff(), approval_state=last.approval_state)
        check_step("scenario", fin, agg, failures)
        sent = rec.sent()
        for s in fin.model_input_includes:
            if s not in sent:
                failures.append(Failure("scenario", "model_input_includes", s, "not sent to the model"))
        for s in fin.model_input_excludes:
            if s in sent:
                failures.append(Failure("scenario", "model_input_excludes", f"{s!r} never sent to the model", "it was sent"))
        if fin.max_model_calls is not None and model_calls > fin.max_model_calls:
            failures.append(Failure("scenario", "max_model_calls", f"<= {fin.max_model_calls}", model_calls))
        all_approvals = [a for a in await approvals.list() if a.session_id == sid]
        for want in fin.approvals:
            if not any(a.tool == want.tool and a.state == want.state for a in all_approvals):
                failures.append(Failure("scenario", "approvals", f"{want.tool} {want.state}", [(a.tool, a.state) for a in all_approvals]))
        if fin.outbox_kinds is not None:
            kinds = [m.kind for m in await rt.outbox.list(sid)]
            if kinds != fin.outbox_kinds:
                failures.append(Failure("scenario", "outbox_kinds", fin.outbox_kinds, kinds))

        # ---- invariants ----
        messages = await store.load_messages(sid)
        for p in history_problems(messages):
            failures.append(Failure("scenario", "invariant: saved history", "valid", p))
        if isinstance(inner, ScriptedLLM):
            if inner.script:
                failures.append(Failure("scenario", "model script", "every scripted response used", f"{len(inner.script)} unused"))
            if any("script exhausted" in e for e in rec.errors):
                failures.append(Failure("scenario", "model script", "enough responses",
                                        "the agent made more model calls than the scenario scripts"))

        # ---- judge ----
        judge_result = None
        if sc.judge and not self.cfg.skip_judge:
            if self.cfg.judge_llm is None:
                failures.append(Failure("scenario", "judge", "a judge model (--judge-model live, or --skip-judge)", "none configured"))
            else:
                v = await Judge(self.cfg.judge_llm).evaluate(sc.judge.rubric, messages, sc.judge.min_score)
                judge_result = {"score": v.score, "reason": v.reason, "passed": v.passed, "error": v.error}
                if not v.passed:
                    failures.append(Failure("scenario", "judge", f"score >= {sc.judge.min_score}", v.error or f"{v.score}: {v.reason}"))

        return TrialResult(not failures, failures, trace_ids, judge_result, model_calls, time.time() - started)

    async def run_suite(self, scenarios: list[Scenario]) -> SuiteResult:
        started = time.time()
        results = [await self.run_scenario(s) for s in scenarios]
        used = {s.agent for s in scenarios}
        return SuiteResult(self.cfg.mode, results, {a: d for a, d in self.agent_digests.items() if a in used}, time.time() - started)


async def run_scenarios(scenarios: list[Scenario], agent_factory: AgentFactory, config: SimConfig | None = None) -> SuiteResult:
    return await SimulationRunner(agent_factory, config).run_suite(scenarios)
