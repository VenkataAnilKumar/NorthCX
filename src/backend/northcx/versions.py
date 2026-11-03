"""Agent versions, releases and rollback.

A version is an immutable snapshot of an agent spec. A release records which version is live and why. Publishing
requires the release gate (see simulation.gate) to be satisfied for that exact version; rollback restores something
that was already live, so it needs no new proof and can be done at any time."""
from __future__ import annotations

import asyncio
import difflib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import yaml

from .agent import Agent
from .catalog import AgentUnavailable
from .simulation.service import SimulationService
from .spec import AgentSpec, BuildContext, Registry, SpecError

PRODUCTION = "production"
ENVIRONMENTS = ("dev", "staging", PRODUCTION)
PROMOTES_FROM = {"staging": "dev", PRODUCTION: "staging"}  # the step before each environment
# An environment with nothing released serves what the next one up serves, so "staging" with no staged version behaves like production.
FALLBACK = {"dev": ("dev", "staging", PRODUCTION), "staging": ("staging", PRODUCTION), PRODUCTION: (PRODUCTION,)}


def check_environment(environment: str) -> str:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {', '.join(ENVIRONMENTS)}")
    return environment


class _NullLLM:
    async def complete(self, req):  # only used to check that a spec can be built
        raise RuntimeError("validation stub")


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


class InvalidSpec(ValueError):
    pass


class GateBlocked(ValueError):
    def __init__(self, reasons: list[str]):
        super().__init__("The release gate is not satisfied: " + "; ".join(reasons[:3]) + (" ..." if len(reasons) > 3 else ""))
        self.reasons = reasons


@dataclass
class AgentVersion:
    agent_id: str
    number: int
    spec: dict[str, Any]
    digest: str
    author: str
    note: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


@dataclass
class Release:
    agent_id: str
    action: str  # publish | rollback
    by: str
    version_id: str | None  # None means the baseline spec file
    number: int | None
    gate: dict[str, Any] = field(default_factory=dict)
    note: str | None = None
    previous_number: int | None = None
    environment: str = PRODUCTION
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    seq: int = 0


class VersionRepo(Protocol):
    async def create(self, agent_id: str, spec: dict[str, Any], digest: str, author: str, note: str | None) -> AgentVersion: ...
    async def get(self, version_id: str) -> AgentVersion | None: ...
    async def get_number(self, agent_id: str, number: int) -> AgentVersion | None: ...
    async def list(self, agent_id: str) -> list[AgentVersion]: ...


class ReleaseRepo(Protocol):
    async def add(self, release: Release) -> Release: ...
    async def list(self, agent_id: str, environment: str = PRODUCTION, limit: int = 100) -> list[Release]: ...
    async def current(self, agent_id: str, environment: str = PRODUCTION) -> Release | None: ...
    async def agents_with_releases(self, environment: str = PRODUCTION) -> list[str]: ...


class InMemoryVersions:
    def __init__(self) -> None:
        self._items: list[AgentVersion] = []
        self._lock = asyncio.Lock()

    async def create(self, agent_id: str, spec: dict[str, Any], digest: str, author: str, note: str | None) -> AgentVersion:
        async with self._lock:
            number = 1 + max((v.number for v in self._items if v.agent_id == agent_id), default=0)
            v = AgentVersion(agent_id, number, json.loads(json.dumps(spec)), digest, author, note)
            self._items.append(v)
            return v

    async def get(self, version_id: str) -> AgentVersion | None:
        return next((v for v in self._items if v.id == version_id), None)

    async def get_number(self, agent_id: str, number: int) -> AgentVersion | None:
        return next((v for v in self._items if v.agent_id == agent_id and v.number == number), None)

    async def list(self, agent_id: str) -> list[AgentVersion]:
        return sorted((v for v in self._items if v.agent_id == agent_id), key=lambda v: v.number, reverse=True)


class InMemoryReleases:
    def __init__(self) -> None:
        self._items: list[Release] = []

    async def add(self, release: Release) -> Release:
        release.seq = len(self._items) + 1
        self._items.append(release)
        return release

    async def list(self, agent_id: str, environment: str = PRODUCTION, limit: int = 100) -> list[Release]:
        return [r for r in reversed(self._items) if r.agent_id == agent_id and r.environment == environment][:limit]

    async def current(self, agent_id: str, environment: str = PRODUCTION) -> Release | None:
        rows = await self.list(agent_id, environment, 1)
        return rows[0] if rows else None

    async def agents_with_releases(self, environment: str = PRODUCTION) -> list[str]:
        return sorted({r.agent_id for r in self._items if r.environment == environment})


# ---------------- diff ----------------
def spec_yaml(spec: dict[str, Any]) -> str:
    return yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)


def _by_name(items: list[Any]) -> dict[str, Any]:
    return {(i["name"] if isinstance(i, dict) else i): i for i in items}


def diff_specs(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """What changed between two spec snapshots, grouped so a reviewer can read it."""
    out: dict[str, Any] = {"identical": a == b, "instructions": None, "tools": {"added": [], "removed": []}, "other": {}}
    if a.get("instructions") != b.get("instructions"):
        out["instructions"] = "\n".join(difflib.unified_diff(
            a.get("instructions", "").splitlines(), b.get("instructions", "").splitlines(), "before", "after", lineterm="", n=2))
    ta, tb = a.get("tools", []), b.get("tools", [])
    out["tools"] = {"added": [t for t in tb if t not in ta], "removed": [t for t in ta if t not in tb]}
    for key in ("guardrails", "input_guardrails", "output_guardrails", "forced_handoff"):
        ia, ib = _by_name(a.get(key, [])), _by_name(b.get(key, []))
        out[key] = {"added": sorted(ib.keys() - ia.keys()), "removed": sorted(ia.keys() - ib.keys()),
                    "changed": sorted(k for k in ia.keys() & ib.keys() if ia[k] != ib[k])}
    for key in sorted((set(a) | set(b)) - {"instructions", "tools", "guardrails", "input_guardrails", "output_guardrails", "forced_handoff"}):
        if a.get(key) != b.get(key):
            out["other"][key] = {"from": a.get(key), "to": b.get(key)}
    return out


# ---------------- service ----------------
class ReleaseService:
    def __init__(self, versions: VersionRepo, releases: ReleaseRepo, registry: Registry, baselines: dict[str, AgentSpec],
                 simulations: SimulationService | None = None, strict_promotion: bool = False):
        self.versions, self.releases, self.registry = versions, releases, registry
        self.baselines, self.simulations = baselines, simulations
        self.strict_promotion = strict_promotion  # production only accepts versions that were live in staging
        self._lock = asyncio.Lock()

    def baseline(self, agent_id: str) -> AgentSpec | None:
        return self.baselines.get(agent_id)

    async def create_version(self, agent_id: str, spec: AgentSpec, by: str, note: str | None = None) -> AgentVersion:
        if spec.id != agent_id:
            raise InvalidSpec(f"The spec's id '{spec.id}' does not match the agent '{agent_id}'")
        problems = self.registry.validate(spec)
        if problems:
            raise InvalidSpec("; ".join(problems))
        try:  # also checks guardrail configuration, which validate() does not (a stub stands in for the model)
            self.registry.build(spec, BuildContext(llm=_NullLLM()))
        except SpecError as e:
            raise InvalidSpec(str(e)) from e
        spec = self.registry.pin_skills(spec)
        existing = await self.versions.list(agent_id)
        if existing and existing[0].digest == spec.digest():
            raise Conflict(f"No changes since version {existing[0].number}")
        return await self.versions.create(agent_id, json.loads(spec.canonical()), spec.digest(), by, note)

    async def preview(self, agent_id: str, spec_data: dict[str, Any]) -> dict[str, Any]:
        """Check a spec as an editor is changing it, without saving: every problem found, whether it differs from the latest version, and what
        changed compared with what is live in production."""
        try:
            spec = AgentSpec.model_validate(spec_data)
        except Exception as e:
            errors = e.errors() if hasattr(e, "errors") else []
            return {"valid": False, "problems": [(".".join(str(p) for p in x["loc"]) + ": " if x.get("loc") else "") + str(x["msg"]) for x in errors] or [str(e)]}
        problems = [] if spec.id == agent_id else [f"The spec's id '{spec.id}' must be '{agent_id}'"]
        problems += self.registry.validate(spec)
        if not problems:
            try:
                self.registry.build(spec, BuildContext(llm=_NullLLM()))
            except SpecError as e:
                problems.append(str(e))
        if problems:
            return {"valid": False, "problems": problems}
        pinned = self.registry.pin_skills(spec)
        latest = await self.versions.list(agent_id)
        v, rel, _ = await self.resolve(agent_id, PRODUCTION)
        base = v.spec if v else (json.loads(self.baselines[agent_id].canonical()) if agent_id in self.baselines else None)
        return {"valid": True, "problems": [], "digest": pinned.digest(), "unchangedSinceLatest": bool(latest) and latest[0].digest == pinned.digest(),
                "diffFromLive": diff_specs(base, json.loads(pinned.canonical())) if base is not None else None}

    async def live(self, agent_id: str, environment: str = PRODUCTION) -> tuple[AgentVersion | None, Release | None]:
        rel = await self.releases.current(agent_id, environment)
        if rel is None or rel.version_id is None:
            return None, rel
        return await self.versions.get(rel.version_id), rel

    async def resolve(self, agent_id: str, environment: str = PRODUCTION) -> tuple[AgentVersion | None, Release | None, str]:
        """What an environment actually serves: its own release, else the next environment up that has one (else the baseline)."""
        for env in FALLBACK[check_environment(environment)]:
            v, rel = await self.live(agent_id, env)
            if rel is not None:
                return v, rel, env
        return None, None, PRODUCTION

    async def environments(self, agent_id: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for env in ENVIRONMENTS:
            v, rel = await self.live(agent_id, env)
            out[env] = {"version": v.number if v else None, "release": rel, "released": rel is not None}
        return out

    async def gate_for(self, version: AgentVersion):
        if self.simulations is None:
            return None
        return await self.simulations.gate_for(version.agent_id, version.digest)

    async def publish(self, agent_id: str, number: int, by: str, note: str | None = None, environment: str = PRODUCTION) -> Release:
        """Release a version to an environment. Dev is for trying things and needs no proof; staging and production need the release
        gate for that exact version, and in strict mode production only accepts what was live in staging."""
        check_environment(environment)
        async with self._lock:
            v = await self.versions.get_number(agent_id, number)
            if v is None:
                raise NotFound(f"Agent '{agent_id}' has no version {number}")
            live_v, live_rel = await self.live(agent_id, environment)
            if live_v is not None and live_v.id == v.id:
                raise Conflict(f"Version {number} is already live in {environment}")
            gate_info: dict[str, Any] = {"satisfied": None, "note": "no gate in dev"}
            if environment != "dev":
                gate = await self.gate_for(v)
                if gate is None:
                    raise GateBlocked(["simulations are not configured, so the release gate cannot be checked"])
                if not gate.satisfied:
                    raise GateBlocked(gate.reasons)
                gate_info = {"satisfied": True, "covered": gate.covered, "required": gate.required, "runIds": gate.run_ids}
            if environment == PRODUCTION and self.strict_promotion:
                staged = any(r.number == v.number for r in await self.releases.list(agent_id, "staging", 1000))
                if not staged:
                    raise GateBlocked([f"version {number} has not been live in staging; promote it there first"])
            return await self.releases.add(Release(agent_id, "publish", by, v.id, v.number, gate_info, note, live_v.number if live_v else None, environment))

    async def checklist(self, agent_id: str, number: int, environment: str = PRODUCTION, permitted: bool = True, active_alerts: list[str] | None = None) -> dict[str, Any]:
        """Everything that must be true (and a few things worth knowing) before this version goes to this environment, in one place.
        A check with status 'fail' blocks the release; 'warn' does not. Publishing still enforces the blocking checks itself."""
        check_environment(environment)
        v = await self.versions.get_number(agent_id, number)
        if v is None:
            raise NotFound(f"Agent '{agent_id}' has no version {number}")
        checks: list[dict[str, Any]] = []

        def add(key: str, title: str, status: str, detail: str) -> None:
            checks.append({"key": key, "title": title, "status": status, "detail": detail})

        add("permission", "You may release to this environment", "pass" if permitted else "fail",
            "" if permitted else f"Releasing to {environment} needs the release permission")
        live_v, _ = await self.live(agent_id, environment)
        if live_v is not None and live_v.id == v.id:
            add("not_live", "Not already live here", "fail", f"Version {number} is already live in {environment}")
        else:
            add("not_live", "Not already live here", "pass", "")
        check = await self.preview(agent_id, v.spec)
        add("valid", "The version builds", "pass" if check["valid"] else "fail", "; ".join(check.get("problems", [])[:5]))
        if environment == "dev":
            add("scenarios", "Required scenarios pass", "info", "Dev needs no proof")
        else:
            gate = await self.gate_for(v)
            if gate is None:
                add("scenarios", "Required scenarios pass", "fail", "Simulations are not configured, so the release gate cannot be checked")
            elif gate.satisfied:
                add("scenarios", "Required scenarios pass", "pass", f"{gate.covered} of {gate.required} required scenarios passed on this exact version")
            else:
                add("scenarios", "Required scenarios pass", "fail", "; ".join(gate.reasons[:5]))
        if environment == PRODUCTION:
            staged = any(r.number == v.number for r in await self.releases.list(agent_id, "staging", 1000))
            if staged:
                add("staged", "Tried in staging first", "pass", "")
            else:
                add("staged", "Tried in staging first", "fail" if self.strict_promotion else "warn",
                    "Not live in staging yet" + ("; production only accepts versions that were" if self.strict_promotion else ""))
            add("alerts", "No alerts are firing", "warn" if active_alerts else "pass", "; ".join(active_alerts or [])[:300])
        base_v, base_rel, _ = await self.resolve(agent_id, environment)
        base = base_v.spec if base_v else (json.loads(self.baselines[agent_id].canonical()) if agent_id in self.baselines else None)
        summary: dict[str, Any] | None = None
        if base is not None:
            d = diff_specs(base, v.spec)
            summary = {"identical": d["identical"], "instructionsChanged": d["instructions"] is not None, "toolsAdded": d["tools"]["added"],
                       "toolsRemoved": d["tools"]["removed"], "otherChanged": sorted(d["other"]),
                       "guardrailsChanged": sorted(k for k in ("guardrails", "input_guardrails", "output_guardrails", "forced_handoff") if any(d[k].values()))}
            add("changes", "Changes from what is live", "info", "Identical to what is live" if d["identical"] else "Differs from what is live; see the summary")
        return {"agent": agent_id, "version": number, "environment": environment, "ready": not any(c["status"] == "fail" for c in checks),
                "checks": checks, "changes": summary, "liveVersion": base_v.number if base_v else None}

    async def promote(self, agent_id: str, to_environment: str, by: str, note: str | None = None) -> Release:
        """Release to an environment the version that is live in the one before it (dev -> staging -> production)."""
        check_environment(to_environment)
        source = PROMOTES_FROM.get(to_environment)
        if source is None:
            raise Conflict("Nothing is promoted into dev; publish a version there directly")
        v, rel = await self.live(agent_id, source)
        if rel is None:
            raise Conflict(f"Nothing is released in {source}, so there is nothing to promote")
        if v is None:
            raise Conflict(f"{source} is running the baseline spec file, which has no version to promote; create a version first")
        return await self.publish(agent_id, v.number, by, note or f"promoted from {source}", to_environment)

    async def rollback(self, agent_id: str, by: str, note: str | None = None, to_number: int | None = None,
                       environment: str = PRODUCTION) -> Release:
        """Restore a version that was live before in this environment (or the baseline spec file). No gate: it already ran there."""
        check_environment(environment)
        async with self._lock:
            history = await self.releases.list(agent_id, environment)
            if not history:
                raise Conflict("Nothing has been released, so there is nothing to roll back")
            current = history[0]
            if to_number is not None:
                target = next((r for r in history if r.number == to_number), None)
                if target is None:
                    if await self.versions.get_number(agent_id, to_number) is None:
                        raise NotFound(f"Agent '{agent_id}' has no version {to_number}")
                    raise Conflict(f"Version {to_number} was never live; publish it instead (that requires the release gate)")
                if current.number == to_number:
                    raise Conflict(f"Version {to_number} is already live")
                version_id, number = target.version_id, target.number
            else:
                earlier = next((r for r in history[1:] if r.number != current.number), None)
                if earlier is not None:
                    version_id, number = earlier.version_id, earlier.number
                elif current.version_id is not None:
                    version_id, number = None, None  # back to the baseline spec file
                else:
                    raise Conflict("The baseline is already live")
            return await self.releases.add(Release(
                agent_id, "rollback", by, version_id, number, {}, note, current.number, environment))


# ---------------- live agents ----------------
class LiveAgents:
    """Serves each agent's live version; until something is released, the spec file's agent (the baseline) runs."""

    def __init__(self, baseline: dict[str, Agent], service: ReleaseService, build: Callable[[AgentSpec], Agent]):
        self.baseline, self.service, self.build = baseline, service, build
        self._cache: dict[str, Agent] = {}

    async def get(self, agent_id: str, environment: str = PRODUCTION) -> Agent | None:
        version, rel, _ = await self.service.resolve(agent_id, environment)
        if rel is None or rel.version_id is None:
            return self.baseline.get(agent_id)
        if version is None:
            raise AgentUnavailable(f"The live version of '{agent_id}' is missing from the version store")
        cached = self._cache.get(version.id)
        if cached is not None:
            return cached
        try:
            agent = self.build(AgentSpec.model_validate(version.spec))
        except Exception as e:  # for example a tool the spec names was removed from the code
            raise AgentUnavailable(f"The live version {version.number} of '{agent_id}' cannot be loaded: {e}") from e
        agent.version, agent.digest = version.number, version.digest
        self._cache[version.id] = agent
        return agent

    async def all(self) -> list[Agent]:
        ids = sorted(set(self.baseline) | set(await self.service.releases.agents_with_releases()))
        found = [await self.get(i) for i in ids]
        return [a for a in found if a is not None]
