"""Connector library (T5): tools defined as data, so common business systems can be connected without writing code.

A connector file describes an HTTP API (base URL, how to authenticate) and the tools an agent may use against it. Safety
is set by the operator, not the file: calls may only go to hosts listed in NORTHCX_CONNECTOR_HOSTS, always over HTTPS (plain
HTTP only for localhost), without following redirects, with a timeout and a response size cap. Credentials are looked up by
name in the secret store at call time and never appear in tool results. Writes carry a stable idempotency key.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import yaml
from pydantic import BaseModel, Field, create_model

from .agent import Tool, ToolContext

MAX_RESPONSE = 256 * 1024
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
TYPES = {"string": str, "integer": int, "number": float, "boolean": bool}
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_INPUT = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_HOST_OK = re.compile(r"^[a-z0-9.-]+(:\d+)?$")
LOCAL = {"localhost", "127.0.0.1", "::1"}


class ConnectorError(ValueError):
    """The connector file is wrong. Messages name the file and the problem."""


class CallFailed(RuntimeError):
    """A call to the external system failed. The message is safe to show the model: no URL, no credentials, no response body."""


def allowed_hosts_from(value: str | None) -> set[str]:
    hosts = {h.strip().lower() for h in (value or "").split(",") if h.strip()}
    for h in hosts:
        if not _HOST_OK.match(h):
            raise ConnectorError(f"NORTHCX_CONNECTOR_HOSTS: '{h}' is not a host name (use names like api.shop.example.com, optionally with :port)")
    return hosts


def _input_model(tool: str, inputs: dict[str, Any], where: str) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for name, spec in inputs.items():
        if not _INPUT.match(name):
            raise ConnectorError(f"{where}: input name '{name}' must be lowercase letters, digits and _")
        spec = spec or {}
        if not isinstance(spec, dict) or set(spec) - {"type", "description", "required", "enum", "pattern", "min", "max", "max_length"}:
            raise ConnectorError(f"{where}: input '{name}' may only have type, description, required, enum, pattern, min, max, max_length")
        typ = spec.get("type", "string")
        if typ not in TYPES:
            raise ConnectorError(f"{where}: input '{name}' type must be one of {', '.join(TYPES)}")
        kw: dict[str, Any] = {"description": spec.get("description", "")}
        if typ == "string":
            kw["max_length"] = int(spec.get("max_length", 200))
            kw["pattern"] = spec.get("pattern")
            if kw["pattern"]:
                try:
                    re.compile(kw["pattern"])
                except re.error as e:
                    raise ConnectorError(f"{where}: input '{name}' pattern is not a valid expression: {e}") from e
        if typ in ("integer", "number"):
            if "min" in spec:
                kw["ge"] = spec["min"]
            if "max" in spec:
                kw["le"] = spec["max"]
        py: Any = TYPES[typ]
        if spec.get("enum"):
            from typing import Literal
            py = Literal[tuple(spec["enum"])]  # type: ignore[valid-type]
        required = spec.get("required", True)
        fields[name] = (py, Field(..., **{k: v for k, v in kw.items() if v is not None})) if required else (py | None, Field(None, **{k: v for k, v in kw.items() if v is not None}))
    return create_model(f"{tool}_input", **fields)


def _project(data: Any, fields: list[str] | None) -> Any:
    """Keep only the listed fields (dotted paths); everything else the system returned is dropped."""
    if not fields:
        return data

    def pick(obj: Any, path: list[str]) -> Any:
        for p in path:
            if isinstance(obj, dict) and p in obj:
                obj = obj[p]
            else:
                return None
        return obj

    if isinstance(data, list):
        return [_project(x, fields) for x in data[:50]]
    out: dict[str, Any] = {}
    for f in fields:
        v = pick(data, f.split("."))
        if v is not None:
            out[f] = v
    return out


class Connector:
    def __init__(self, cfg: dict[str, Any], allowed_hosts: set[str], source: str = "connector", client: httpx.AsyncClient | None = None):
        self.source = source
        unknown = set(cfg) - {"name", "description", "base_url", "auth", "timeout", "tools"}
        if unknown:
            raise ConnectorError(f"{source}: unknown setting(s) {', '.join(sorted(unknown))}")
        self.name = str(cfg.get("name", ""))
        if not _NAME.match(self.name):
            raise ConnectorError(f"{source}: name must be 2-40 lowercase letters, digits and _")
        url = urlsplit(str(cfg.get("base_url", "")))
        host = (url.hostname or "").lower()
        netloc = host + (f":{url.port}" if url.port else "")
        if url.scheme not in ("https", "http") or not host or url.username or url.password or url.query or url.fragment:
            raise ConnectorError(f"{source}: base_url must look like https://api.example.com/v1 (no credentials, query or fragment)")
        if url.scheme == "http" and host not in LOCAL:
            raise ConnectorError(f"{source}: base_url must use https (plain http is only allowed for localhost)")
        if netloc not in allowed_hosts and host not in allowed_hosts:
            raise ConnectorError(f"{source}: host '{netloc}' is not in NORTHCX_CONNECTOR_HOSTS; the operator must allow it first")
        self.base = f"{url.scheme}://{netloc}{url.path.rstrip('/')}"
        auth = cfg.get("auth") or {"type": "none"}
        if not isinstance(auth, dict) or auth.get("type", "none") not in ("none", "bearer", "header", "basic") or set(auth) - {"type", "secret", "header", "user"}:
            raise ConnectorError(f"{source}: auth needs type none, bearer, header or basic (with secret, and header or user where relevant)")
        if auth.get("type", "none") != "none" and not auth.get("secret"):
            raise ConnectorError(f"{source}: auth type '{auth['type']}' needs the name of a secret")
        if auth.get("type") == "header" and not re.match(r"^[A-Za-z][A-Za-z0-9-]{0,40}$", str(auth.get("header", ""))):
            raise ConnectorError(f"{source}: auth type 'header' needs a header name")
        self.auth = auth
        self.timeout = float(cfg.get("timeout", 8))
        self._client = client or httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)
        self.tools = [self._tool(t, f"{source} tool {i + 1}") for i, t in enumerate(cfg.get("tools") or [])]
        names = [t.name for t in self.tools]
        if len(set(names)) != len(names):
            raise ConnectorError(f"{source}: tool names must be unique")

    # ---- building tools ----
    def _tool(self, t: dict[str, Any], where: str) -> Tool:
        if not isinstance(t, dict) or set(t) - {"name", "description", "effect", "method", "path", "inputs", "query", "body", "response", "requires_approval", "dry_run_result"}:
            raise ConnectorError(f"{where}: unknown or missing settings")
        name = str(t.get("name", ""))
        if not _NAME.match(name):
            raise ConnectorError(f"{where}: name must be 2-40 lowercase letters, digits and _")
        where = f"{self.source} tool '{name}'"
        method = str(t.get("method", "GET")).upper()
        effect = t.get("effect", "read" if method == "GET" else "write")
        if method not in METHODS or effect not in ("read", "write"):
            raise ConnectorError(f"{where}: method must be one of {', '.join(METHODS)} and effect read or write")
        if method != "GET" and effect == "read":
            raise ConnectorError(f"{where}: {method} changes things, so its effect must be 'write'")
        path = str(t.get("path", ""))
        if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
            raise ConnectorError(f"{where}: path must start with / and contain no '..', '?' or '#' (use 'query' for parameters)")
        inputs = t.get("inputs") or {}
        used = set(_PLACEHOLDER.findall(path))
        query, body = t.get("query") or {}, t.get("body") or {}
        if not isinstance(query, dict) or not isinstance(body, dict):
            raise ConnectorError(f"{where}: query and body must be maps")
        for label, mapping in (("query", query), ("body", body)):
            for k, v in mapping.items():
                if isinstance(v, str) and (m := _PLACEHOLDER.fullmatch(v)):
                    used.add(m.group(1))
        missing = used - set(inputs)
        if missing:
            raise ConnectorError(f"{where}: uses undeclared input(s) {', '.join(sorted(missing))}")
        model = _input_model(name, inputs, where)
        if method in ("GET", "DELETE") and body:
            raise ConnectorError(f"{where}: {method} requests have no body")
        if effect == "write" and not t.get("description"):
            raise ConnectorError(f"{where}: write tools need a description so the agent knows when to use them")
        response = (t.get("response") or {}).get("fields") if isinstance(t.get("response"), dict) else None
        rule = t.get("requires_approval")
        approval = None
        if rule:
            if not isinstance(rule, dict) or set(rule) - {"always", "input", "above", "reason"}:
                raise ConnectorError(f"{where}: requires_approval takes always, or input and above, plus a reason")
            reason = str(rule.get("reason", "This action needs approval"))
            if rule.get("always"):
                approval = lambda d, r=reason: r  # noqa: E731
            elif rule.get("input") in inputs and isinstance(rule.get("above"), (int, float)):
                key, limit = rule["input"], rule["above"]
                approval = lambda d, k=key, lim=limit, r=reason: r if (getattr(d, k, None) or 0) > lim else None  # noqa: E731
            else:
                raise ConnectorError(f"{where}: requires_approval needs 'always: true', or a declared 'input' with a numeric 'above'")
        dry = t.get("dry_run_result")
        spec = {"method": method, "path": path, "query": query, "body": body, "fields": response}

        async def run(data: BaseModel, ctx: ToolContext) -> Any:
            return await self._call(name, spec, data, ctx, effect)

        return Tool(name, str(t.get("description", f"{method} {path}")), model, run, requires_approval=approval, effect=effect,
                    dry_run_result=(lambda d, c, v=dry: v) if isinstance(dry, dict) else None)

    # ---- calling ----
    def _headers(self, ctx: ToolContext, effect: str) -> tuple[dict[str, str], tuple[str, str] | None]:
        headers = {"accept": "application/json"}
        basic = None
        a = self.auth
        kind = a.get("type", "none")
        if kind == "bearer":
            headers["authorization"] = f"Bearer {ctx.secret(a['secret'])}"
        elif kind == "header":
            headers[a["header"]] = ctx.secret(a["secret"])
        elif kind == "basic":
            basic = (str(a.get("user", "")), ctx.secret(a["secret"]))
        if effect == "write" and ctx.idempotency_key:
            headers["idempotency-key"] = ctx.idempotency_key
        return headers, basic

    async def _call(self, tool: str, spec: dict[str, Any], data: BaseModel, ctx: ToolContext, effect: str) -> Any:
        values = data.model_dump()

        def fill(v: Any) -> Any:
            if isinstance(v, str) and (m := _PLACEHOLDER.fullmatch(v)):
                return values.get(m.group(1))
            return v

        path = _PLACEHOLDER.sub(lambda m: quote(str(values[m.group(1)]), safe=""), spec["path"])
        params = {k: fill(v) for k, v in spec["query"].items() if fill(v) is not None}
        body = {k: fill(v) for k, v in spec["body"].items() if fill(v) is not None} if spec["body"] else None
        headers, basic = self._headers(ctx, effect)
        try:
            r = await self._client.request(spec["method"], self.base + path, params=params or None, json=body, headers=headers, auth=basic)
        except httpx.HTTPError as e:
            raise CallFailed(f"{tool}: the system could not be reached ({type(e).__name__})") from e
        if len(r.content) > MAX_RESPONSE:
            raise CallFailed(f"{tool}: the response was too large to use")
        if r.status_code == 404 and spec["method"] == "GET":
            return {"found": False}
        if r.status_code >= 300:
            raise CallFailed(f"{tool}: the system returned {r.status_code}")
        if not r.content:
            return {"ok": True}
        try:
            return _project(r.json(), spec["fields"])
        except ValueError as e:
            raise CallFailed(f"{tool}: the response was not JSON") from e


def load_connectors(path: str | Path, allowed_hosts: set[str], client: httpx.AsyncClient | None = None) -> list[Tool]:
    p = Path(path)
    files = [p] if p.is_file() else sorted(f for f in p.glob("*") if f.suffix in (".yaml", ".yml", ".json") and ".example." not in f.name)
    tools: list[Tool] = []
    seen: set[str] = set()
    for f in files:
        try:
            docs = [d for d in yaml.safe_load_all(f.read_text()) if d]
        except yaml.YAMLError as e:
            raise ConnectorError(f"{f}: not valid YAML or JSON: {e}") from e
        for d in docs:
            if not isinstance(d, dict):
                raise ConnectorError(f"{f}: must be a mapping")
            for t in Connector(d, allowed_hosts, str(f), client).tools:
                if t.name in seen:
                    raise ConnectorError(f"{f}: tool name '{t.name}' is used by another connector")
                seen.add(t.name)
                tools.append(t)
    return tools
