"""Route for editing a customer message and running the conversation again from there, in a sandbox."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import RerunBody, TryBody
from northcx.catalog import AgentUnavailable
from northcx.regression import scenario_from_traces
from northcx.rerun import customer_turns, original_reply, rerun, sandbox_run
from northcx.simulation.scenario import ScenarioError
from northcx.spec import AgentSpec, BuildContext, SpecError


def register(app: FastAPI, d: AppDeps) -> None:
    runtime, traces, provider, record = d.runtime, d.traces, d.provider, d.record

    @app.get("/v1/sessions/{session_id}/turns")
    async def session_turns(session_id: str) -> Any:
        """The customer's messages in a conversation, numbered the way `rerun` takes them, each with the reply it got."""
        if not await traces.summaries(session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        messages = await runtime.store.load_messages(session_id)
        return {"sessionId": session_id, "turns": [{"turn": n, "message": messages[i]["content"], "reply": original_reply(messages, i)} for n, i in enumerate(customer_turns(messages), 1)]}

    @app.post("/v1/agents/{agent_id}/try")
    async def try_draft(agent_id: str, body: TryBody, request: Request) -> Any:
        """Try an agent definition that has not been saved: answer one message (after the conversation so far) in a sandbox, with the steps,
        and a test that could be saved from the exchange. Nothing is saved, sent or run for real."""
        svc = d.need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        preview = await svc.preview(agent_id, body.spec)
        if not preview["valid"]:
            return _err(400, "bad_request", " ".join(preview["problems"][:5]))
        spec = AgentSpec.model_validate(body.spec)
        try:
            agent = svc.registry.build(spec, BuildContext(llm=runtime.llm))
        except SpecError as e:
            return _err(400, "bad_request", str(e))
        if agent.audience == "staff":
            return _err(400, "bad_request", "Trying a draft is for agents that talk to customers; this one works for staff")
        history = [{"role": h.role, "content": h.text} for h in body.history]

        async def resolver(agent_id_: str, environment: str, sid: str) -> Any:
            return await provider.get(agent_id_, environment, sid)

        out = await sandbox_run(runtime, agent, resolver, history, body.message)
        trace = out.pop("trace")
        try:
            test = scenario_from_traces([trace], f"try-{trace.id}")  # a different name every time, so saving two tries does not collide
            out["testYaml"], out["testWarnings"] = test.yaml, test.warnings
        except ScenarioError:
            out["testYaml"], out["testWarnings"] = None, []
        await record(request, "agent.try", agent_id, length=len(body.message), status=out["status"])
        return {"agent": agent_id, "sandbox": True, **out, "note": "Nothing was saved or sent, and actions were only simulated. The copy has no customer record, memory or company context."}

    @app.post("/v1/sessions/{session_id}/rerun")
    async def rerun_turn(session_id: str, body: RerunBody, request: Request) -> Any:
        """Answer an edited customer message after the conversation that came before it. Nothing is saved, sent or run for real: the copy has its own stores and simulates every write."""
        summaries = sorted(await traces.summaries(session_id, 200), key=lambda t: t.started_at or 0)
        if not summaries:
            return _err(404, "not_found", "Unknown conversation")
        messages = await runtime.store.load_messages(session_id)
        turns = customer_turns(messages)
        if not 1 <= body.turn <= len(turns):
            return _err(400, "bad_request", f"This conversation has {len(turns)} customer message{'' if len(turns) == 1 else 's'}; choose a turn from 1 to {len(turns)}")
        first = summaries[0]
        try:
            agent = await provider.get(first.agent_id, first.environment or "production", session_id)
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            return _err(404, "not_found", f"The agent '{first.agent_id}' no longer exists")
        if agent.audience == "staff":
            return _err(400, "bad_request", "Reruns are for conversations with customers; this agent works for staff")
        index = turns[body.turn - 1]

        async def resolver(agent_id: str, environment: str, sid: str) -> Any:
            return await provider.get(agent_id, environment, sid)

        out = await rerun(runtime, agent, resolver, messages, index, body.message)
        await record(request, "session.rerun", session_id, turn=body.turn, length=len(body.message), status=out["status"])
        return {"sessionId": session_id, "turn": body.turn, "agent": agent.id, "sandbox": True,
                "original": {"message": messages[index]["content"], "reply": original_reply(messages, index)}, "rerun": out,
                "note": "Nothing was saved or sent, and writes were simulated. The copy has no customer record, memory or company context, so answers that depend on them may differ from the live ones."}
