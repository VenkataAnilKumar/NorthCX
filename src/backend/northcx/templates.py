"""Templates (A7): ready-made agents for common support intents, with the scenarios that prove them.

A template is a YAML file with parameters, an agent spec and scenarios. Parameters fill `{{name}}` placeholders in text only
(nothing is evaluated), every result is validated like a hand-written spec, and the tools the template needs are checked
against what this deployment has, so a template never produces an agent that cannot run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .simulation.scenario import ScenarioError, parse_scenario
from .spec import AgentSpec, Registry

LIBRARY = Path(__file__).parent / "template_library"
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
_ID = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
MAX_PARAM = 300


class TemplateError(ValueError):
    pass


@dataclass
class Param:
    name: str
    description: str
    default: str | None = None
    required: bool = True


@dataclass
class Template:
    id: str
    title: str
    description: str
    intent: str
    params: list[Param]
    spec: dict[str, Any]
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    requires_tools: list[str] = field(default_factory=list)
    # Hub details (WP22.1); every one is optional, so a template written before they existed stays valid
    audience: str = "customer"
    category: str = "General"
    channels: list[str] = field(default_factory=list)       # channels it is meant for
    version: str = "1"
    notes: str = ""
    sees: list[str] = field(default_factory=list)           # what it can see
    does: list[str] = field(default_factory=list)           # what it can do
    requires_knowledge: bool = False
    requires_channels: list[str] = field(default_factory=list)

    def info(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "description": self.description, "intent": self.intent,
                "parameters": [{"name": p.name, "description": p.description, "default": p.default, "required": p.required and p.default is None} for p in self.params],
                "requiresTools": _fill(self.requires_tools, {p.name: p.default or "" for p in self.params}), "scenarios": len(self.scenarios),
                "audience": self.audience, "category": self.category, "channels": self.channels, "version": self.version, "notes": self.notes, "sees": self.sees, "does": self.does,
                "needs": {"tools": _fill(self.requires_tools, {p.name: p.default or "" for p in self.params}), "knowledge": self.requires_knowledge, "channels": self.requires_channels}}


@dataclass
class Rendered:
    spec: AgentSpec
    spec_yaml: str
    scenarios: list[dict[str, Any]]
    scenarios_yaml: str
    missing_tools: list[str]
    warnings: list[str]


def parse_template(data: Any, source: str = "") -> Template:
    where = source or "template"
    if not isinstance(data, dict):
        raise TemplateError(f"{where}: must be a mapping")
    unknown = set(data) - {"id", "title", "description", "intent", "parameters", "spec", "scenarios", "requires", "audience", "category", "channels", "version", "notes", "sees", "does"}
    if unknown:
        raise TemplateError(f"{where}: unknown setting(s) {', '.join(sorted(unknown))}")
    tid = str(data.get("id", ""))
    if not _ID.match(tid):
        raise TemplateError(f"{where}: id must be 2-40 lowercase letters, digits and -")
    params = []
    for name, p in (data.get("parameters") or {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(name)):
            raise TemplateError(f"{where}: parameter name '{name}' must be lowercase letters, digits and _")
        p = p or {}
        params.append(Param(str(name), str(p.get("description", "")), None if p.get("default") is None else str(p["default"]), bool(p.get("required", True))))
    spec = data.get("spec")
    if not isinstance(spec, dict):
        raise TemplateError(f"{where}: needs a 'spec' map")
    declared = {p.name for p in params}
    used = set(_PLACEHOLDER.findall(yaml.safe_dump({"spec": spec, "scenarios": data.get("scenarios") or [], "requires": data.get("requires") or {}})))
    if used - declared - {"agent_id"}:
        raise TemplateError(f"{where}: uses undeclared parameter(s) {', '.join(sorted(used - declared - {'agent_id'}))}")
    req = data.get("requires") or {}
    if str(data.get("audience", "customer")) not in ("customer", "staff"):
        raise TemplateError(f"{where}: audience must be customer or staff")
    lists = {k: [str(x) for x in (data.get(k) or [])] for k in ("channels", "sees", "does")}
    return Template(tid, str(data.get("title", tid)), str(data.get("description", "")), str(data.get("intent", "")), params, spec,
                    list(data.get("scenarios") or []), [str(t) for t in req.get("tools") or []],
                    audience=str(data.get("audience", "customer")), category=str(data.get("category", "General"))[:60], channels=lists["channels"], version=str(data.get("version", "1")),
                    notes=str(data.get("notes", ""))[:500], sees=lists["sees"], does=lists["does"], requires_knowledge=bool(req.get("knowledge", False)),
                    requires_channels=[str(c) for c in req.get("channels") or []])


def load_templates(*paths: str | Path) -> dict[str, Template]:
    out: dict[str, Template] = {}
    for path in paths:
        p = Path(path)
        files = [p] if p.is_file() else sorted(f for f in p.glob("*") if f.suffix in (".yaml", ".yml"))
        for f in files:
            try:
                docs = [d for d in yaml.safe_load_all(f.read_text()) if d]
            except yaml.YAMLError as e:
                raise TemplateError(f"{f}: not valid YAML: {e}") from e
            for d in docs:
                t = parse_template(d, str(f))
                out[t.id] = t  # a later directory can replace a built-in template by reusing its id
    return out


def _fill(value: Any, values: dict[str, str]) -> Any:
    if isinstance(value, str):
        return _PLACEHOLDER.sub(lambda m: values[m.group(1)], value)
    if isinstance(value, list):
        return [_fill(v, values) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, values) for k, v in value.items()}
    return value


def render(t: Template, agent_id: str, params: dict[str, Any], registry: Registry | None = None) -> Rendered:
    problems: list[str] = []
    values: dict[str, str] = {"agent_id": agent_id}
    declared = {p.name for p in t.params}
    for extra in sorted(set(params) - declared):
        problems.append(f"unknown parameter '{extra}'")
    for p in t.params:
        v = params.get(p.name, p.default)
        if v is None or str(v).strip() == "":
            if p.required:
                problems.append(f"parameter '{p.name}' is required ({p.description})" if p.description else f"parameter '{p.name}' is required")
            v = p.default or ""
        v = str(v).strip()
        if len(v) > MAX_PARAM or "\n" in v or "{{" in v:
            problems.append(f"parameter '{p.name}' must be one line of at most {MAX_PARAM} characters and cannot contain '{{{{'")
        values[p.name] = v
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}", agent_id or ""):
        problems.append("agentId must be 2-40 lowercase letters, digits, - or _")
    if problems:
        raise TemplateError("; ".join(problems))
    spec_data = _fill(t.spec, values)
    spec_data.setdefault("spec_version", 1)
    spec_data["id"] = agent_id
    try:
        spec = AgentSpec.model_validate(spec_data)
    except Exception as e:
        raise TemplateError(f"the template produced an invalid agent spec: {e}") from e
    scenarios = []
    for sc in _fill(t.scenarios, values):
        sc = {**sc, "agent": agent_id}
        try:
            parse_scenario(sc, f"{t.id} scenario")
        except ScenarioError as e:
            raise TemplateError(str(e)) from e
        scenarios.append(sc)
    missing, warnings = [], []
    if registry is not None:
        needed = list(dict.fromkeys(list(spec.tools) + _fill(t.requires_tools, values)))
        missing = [x for x in needed if x not in registry.tool_names()]
        for problem in registry.validate(spec):
            if "Unknown tool" not in problem:
                warnings.append(problem)
        if missing:
            warnings.append("This deployment has no tool named " + ", ".join(f"'{m}'" for m in missing) + "; add it (a connector file or code) or change the matching parameter.")
    return Rendered(spec, yaml.safe_dump(spec_data, sort_keys=False, allow_unicode=True, width=100), scenarios,
                    "---\n".join(yaml.safe_dump(s, sort_keys=False, allow_unicode=True, width=100) for s in scenarios), missing, warnings)
