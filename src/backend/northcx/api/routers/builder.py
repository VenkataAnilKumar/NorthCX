"""Routes that draft agents, journeys and scenarios from your material (nothing is saved)."""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yaml

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import BuilderBody, JourneyDraftBody, JourneyScenariosBody, RefineBody, ScenarioDraftBody
from northcx.builder import BuildError, draft_agent, refine_agent
from northcx.catalog import AgentUnavailable
from northcx.journeys import draft_prompt, DraftError, JourneySpec, parse_draft, scenarios as journey_scenarios_list, scenarios_yaml as journey_scenarios_yaml, SYSTEM as JOURNEY_SYSTEM
from northcx.scenario_draft import draft_scenarios
from northcx.spec import parse_spec, SpecError
from northcx.transcribe import TranscribeError
from northcx.types import LLMRequest, text_of

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    need_rel = d.need_rel
    provider = d.provider
    record = d.record
    runtime = d.runtime
    too_many = d.too_many
    transcriber = d.transcriber

    @app.post("/v1/builder/draft")
    async def builder_draft(body: BuilderBody, request: Request) -> Any:
        """A first draft of an agent from procedures and conversation transcripts. Names are checked against what this deployment has;
        personal details are masked before the model sees anything; nothing is saved."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        if not access.limiter.allow(f"builder:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "agent drafts")
        try:
            out = await draft_agent(runtime.llm, svc.registry, body.agent_id, body.goal, [s.model_dump() for s in body.sources])
        except BuildError as e:
            return _err(422, "unusable_draft", str(e))
        except Exception:
            log.exception("agent draft failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "builder.draft", body.agent_id, sources=len(body.sources), warnings=len(out["warnings"]))
        return out

    @app.post("/v1/builder/scenarios")
    async def builder_scenarios(body: ScenarioDraftBody, request: Request) -> Any:
        """Test scenarios for a drafted agent: platform-guarantee tests that are run against the draft, and question tests that need a live model. Saves nothing."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        if not access.limiter.allow(f"builder:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "agent drafts")
        try:
            spec = parse_spec(body.spec)
        except SpecError as e:
            return _err(400, "bad_request", str(e)[:400])
        try:
            out = await draft_scenarios(runtime.llm, svc.registry, spec, body.examples)
        except ValueError as e:
            return _err(422, "unusable_draft", str(e))
        except Exception:
            log.exception("scenario draft failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "builder.scenarios", spec.id, checked=len(out["checked"]), needLiveModel=len(out["needLiveModel"]))
        return out

    @app.post("/v1/builder/refine")
    async def builder_refine(body: RefineBody, request: Request) -> Any:
        """Revise a draft after an instruction ("never promise delivery dates"). Same limits as a first draft; settings the model may not set are carried over untouched."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        if not access.limiter.allow(f"builder:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "agent drafts")
        try:
            out = await refine_agent(runtime.llm, svc.registry, body.current, body.instruction)
        except BuildError as e:
            return _err(422, "unusable_draft", str(e))
        except Exception:
            log.exception("agent refine failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "builder.refine", out["spec"]["id"], changes=len(out["changes"]), warnings=len(out["warnings"]))
        return out

    @app.post("/v1/builder/transcribe")
    async def builder_transcribe(request: Request, language: str | None = None) -> Any:
        """Turn a recording (the request body is the audio file) into transcript text with the operator's transcription service. Nothing is stored."""
        if transcriber is None:
            return _err(501, "not_configured", "Transcription is not configured: set NORTHCX_TRANSCRIBE_URL and NORTHCX_TRANSCRIBE_MODEL")
        who: Identity = request.state.identity
        if not access.limiter.allow(f"transcribe:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "transcriptions")
        if language is not None and not re.fullmatch(r"[a-z]{2,3}", language):
            return _err(400, "bad_request", "language must be a short code such as en")
        cap = 25 * 1024 * 1024
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            return _err(413, "too_large", "The recording is too large")
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > cap:
                return _err(413, "too_large", "The recording is too large")
        try:
            text_ = await transcriber.transcribe(data, language)
        except TranscribeError as e:
            return _err(422, "unusable_recording", str(e))
        await record(request, "builder.transcribe", "recording", size=len(data))
        return {"text": text_, "characters": len(text_), "note": "Read it before using it: transcripts can contain mistakes. Personal details are masked when it is used to draft an agent."}

    @app.post("/v1/agents/{agent_id}/journeys/draft")
    async def journey_draft(agent_id: str, body: JourneyDraftBody, request: Request) -> Any:
        """A journey drafted from a plain-language description by the model. Checked against the agent's real tools; never saved by itself."""
        who: Identity = request.state.identity
        if not access.limiter.allow(f"journey-draft:{who.key_id or 'open'}", 10)[0]:
            return too_many(60, "journey drafts")
        try:
            agent = await provider.get(agent_id)
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            return _err(404, "not_found", "Unknown agent")
        tools = [(t.name, t.description) for t in agent.tools]
        try:
            res = await runtime.llm.complete(LLMRequest(system=JOURNEY_SYSTEM, messages=[{"role": "user", "content": draft_prompt(body.description, tools)}], max_tokens=1500))
        except Exception:
            log.exception("journey draft failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        try:
            journey, warnings = parse_draft(text_of(res.content), {n for n, _ in tools})
        except DraftError as e:
            return _err(422, "unusable_draft", str(e))
        await record(request, "journey.draft", agent_id, steps=len(journey.steps), warnings=len(warnings))
        data = journey.model_dump(mode="json")
        return {"journey": data, "yaml": yaml.safe_dump(data, sort_keys=False, allow_unicode=True), "warnings": warnings,
                "note": "A draft for a person to review. Nothing is saved until it is added to the agent and a version is created."}

    @app.post("/v1/agents/{agent_id}/journeys/scenarios")
    async def journey_scenarios(agent_id: str, body: JourneyScenariosBody) -> Any:
        """Test scenario drafts for a journey, one per sample opening message (not required until someone relies on them)."""
        try:
            j = JourneySpec.model_validate(body.journey)
        except ValueError as e:
            return _err(400, "bad_request", "; ".join(f"{'.'.join(str(p) for p in x['loc'])}: {x['msg']}" for x in getattr(e, "errors", lambda: [])()[:5]) or str(e))
        return {"scenarios": journey_scenarios_list(j, agent_id), "yaml": journey_scenarios_yaml(j, agent_id)}
