"""A snapshot of how the app dispatches every route: for each route and method, an example URL and which handler wins for it.

Used by tests/test_route_dispatch.py and scripts/gen_route_golden.py. The snapshot does not depend on the order routes were
registered in, only on the outcome, so handlers can move between modules without changing what any URL does.
"""
from __future__ import annotations

import re
from typing import Any

from starlette.routing import Match


def example_path(path: str) -> str:
    path = re.sub(r"\{[^}:]+:path\}", "a/b", path)
    return re.sub(r"\{[^}]+\}", "x", path)


def build_app() -> Any:
    from examples.support_agent import registry, support_agent
    from northcx.access import AccessControl
    from northcx.knowledge import InMemoryKnowledge
    from northcx.llm import ScriptedLLM
    from northcx.regression import RegressionRunner
    from northcx.runtime import Runtime
    from northcx.server import create_app
    from northcx.simulation import InMemorySimRuns, SimulationService
    from northcx.store import InMemoryStore
    from northcx.templates import LIBRARY, load_templates
    from northcx.trace import TraceStore
    from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService
    r = registry()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    sim = SimulationService([], lambda a, l: None, InMemorySimRuns(), {})
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, {}, sim)
    return create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key="boot" * 10), releases=svc, simulations=sim,
                      knowledge=InMemoryKnowledge(), regression=RegressionRunner(sim, rt.monitor.repo), skills=r.skill_info(), templates=load_templates(LIBRARY))


def snapshot(app: Any) -> dict[str, Any]:
    routes = list(app.router.routes)
    entries: set[tuple[str, str, str]] = set()
    dispatch: dict[str, str] = {}
    for r in routes:
        endpoint = getattr(r, "endpoint", None)
        name = getattr(endpoint, "__name__", None) or getattr(r, "name", "?")
        methods = sorted((getattr(r, "methods", None) or {"WS" if "WebSocket" in type(r).__name__ else "ANY"}) - {"HEAD", "OPTIONS"})
        for m in methods:
            entries.add((m, r.path, name))
            ex = example_path(r.path)
            scope = {"type": "websocket" if m == "WS" else "http", "method": m if m != "WS" else "GET", "path": ex, "root_path": "", "headers": [], "query_string": b""}
            for cand in routes:
                match, _ = cand.matches(scope)
                if match == Match.FULL:
                    dispatch[f"{m} {ex}"] = f"{cand.path} -> {getattr(getattr(cand, 'endpoint', None), '__name__', getattr(cand, 'name', '?'))}"
                    break
    return {"routes": sorted(entries), "dispatch": dict(sorted(dispatch.items()))}
