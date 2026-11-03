"""Connector library (T5): tools defined as data, so common business systems can be connected without writing code.

A connector file describes an HTTP API (base URL, how to authenticate) and the tools an agent may use against it. Safety
is set by the operator, not the file: calls may only go to hosts listed in NORTHCX_CONNECTOR_HOSTS, always over HTTPS (plain
HTTP only for localhost), without following redirects, with a timeout and a response size cap. Credentials are looked up by
name in the secret store at call time and never appear in tool results. Writes carry a stable idempotency key.

Lists that a system hands out page by page can be read with `pagination` (cursor, page number, offset, or a `Link` header), limited to a few
pages and a hard cap on items, and a connector can sign in with OAuth 2 (client credentials, or a refresh token that does not rotate): the token
is fetched from a token address on an allowed host, kept in memory only until shortly before it expires, and renewed once if the system refuses it.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import yaml
from pydantic import BaseModel, Field, create_model

from .agent import Tool, ToolContext

MAX_RESPONSE = 256 * 1024
PAGE_STYLES = ("cursor", "page", "offset", "link_header")
MAX_PAGES, MAX_ITEMS = 10, 500
OAUTH_KINDS = ("oauth2_client_credentials", "oauth2_refresh_token")
TOKEN_SKEW = 30.0  # renew a token this many seconds before it expires
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
        kinds = ("none", "bearer", "header", "basic", *OAUTH_KINDS)
        if not isinstance(auth, dict) or auth.get("type", "none") not in kinds or set(auth) - {"type", "secret", "header", "user", "token_url", "client_id", "client_secret", "refresh_token", "scope", "client_auth"}:
            raise ConnectorError(f"{source}: auth needs type none, bearer, header, basic, oauth2_client_credentials or oauth2_refresh_token (with the settings that type uses)")
        if auth.get("type") in OAUTH_KINDS:
            self._check_oauth(auth, allowed_hosts, source)
        elif auth.get("type", "none") != "none" and not auth.get("secret"):
            raise ConnectorError(f"{source}: auth type '{auth['type']}' needs the name of a secret")
        if auth.get("type") == "header" and not re.match(r"^[A-Za-z][A-Za-z0-9-]{0,40}$", str(auth.get("header", ""))):
            raise ConnectorError(f"{source}: auth type 'header' needs a header name")
        self.auth = auth
        self._token: tuple[str, float] | None = None  # (access token, expires at); memory only
        self._token_lock = asyncio.Lock()
        self.timeout = float(cfg.get("timeout", 8))
        self._client = client or httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)
        self.tools = [self._tool(t, f"{source} tool {i + 1}") for i, t in enumerate(cfg.get("tools") or [])]
        names = [t.name for t in self.tools]
        if len(set(names)) != len(names):
            raise ConnectorError(f"{source}: tool names must be unique")

    @staticmethod
    def _check_oauth(auth: dict[str, Any], allowed_hosts: set[str], source: str) -> None:
        kind = auth["type"]
        url = urlsplit(str(auth.get("token_url", "")))
        host = (url.hostname or "").lower()
        netloc = host + (f":{url.port}" if url.port else "")
        if url.scheme not in ("https", "http") or not host or url.username or url.password or url.query or url.fragment:
            raise ConnectorError(f"{source}: auth.token_url must look like https://login.example.com/oauth/token (no credentials, query or fragment)")
        if url.scheme == "http" and host not in LOCAL:
            raise ConnectorError(f"{source}: auth.token_url must use https (plain http is only allowed for localhost)")
        if netloc not in allowed_hosts and host not in allowed_hosts:
            raise ConnectorError(f"{source}: the token host '{netloc}' is not in NORTHCX_CONNECTOR_HOSTS; the operator must allow it first")
        needs = ["client_id", "client_secret"] if kind == "oauth2_client_credentials" else ["client_id", "refresh_token"]
        missing = [k for k in needs if not auth.get(k)]
        if missing:
            raise ConnectorError(f"{source}: auth type '{kind}' needs {', '.join(missing)} (the names of secrets)")
        for k in ("client_id", "client_secret", "refresh_token"):
            if k in auth and not re.fullmatch(r"[A-Za-z0-9_]{1,60}", str(auth[k])):
                raise ConnectorError(f"{source}: auth.{k} is the name of a secret (letters, digits and _), not the value")
        if auth.get("client_auth", "post") not in ("post", "basic"):
            raise ConnectorError(f"{source}: auth.client_auth must be post or basic")
        if "scope" in auth and (not isinstance(auth["scope"], str) or len(auth["scope"]) > 300):
            raise ConnectorError(f"{source}: auth.scope must be a short text")

    # ---- building tools ----
    def _tool(self, t: dict[str, Any], where: str) -> Tool:
        if not isinstance(t, dict) or set(t) - {"name", "description", "effect", "method", "path", "inputs", "query", "body", "response", "requires_approval", "dry_run_result", "pagination"}:
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
        spec = {"method": method, "path": path, "query": query, "body": body, "fields": response, "pagination": self._pagination(t.get("pagination"), method, query, where)}

        async def run(data: BaseModel, ctx: ToolContext) -> Any:
            return await self._call(name, spec, data, ctx, effect)

        return Tool(name, str(t.get("description", f"{method} {path}")), model, run, requires_approval=approval, effect=effect,
                    dry_run_result=(lambda d, c, v=dry: v) if isinstance(dry, dict) else None)

    @staticmethod
    def _pagination(p: Any, method: str, query: dict[str, Any], where: str) -> dict[str, Any] | None:
        if p is None:
            return None
        if method != "GET":
            raise ConnectorError(f"{where}: only GET tools can be paginated")
        if not isinstance(p, dict) or set(p) - {"style", "items", "next", "param", "size_param", "page_size", "max_pages", "max_items"}:
            raise ConnectorError(f"{where}: pagination takes style, items, next, param, size_param, page_size, max_pages and max_items")
        style = p.get("style")
        if style not in PAGE_STYLES:
            raise ConnectorError(f"{where}: pagination style must be one of {', '.join(PAGE_STYLES)}")
        for k in ("items", "next"):
            if k in p and not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(p[k])):
                raise ConnectorError(f"{where}: pagination {k} is a dotted field path such as data or meta.next")
        if style == "cursor" and not (p.get("next") and p.get("param")):
            raise ConnectorError(f"{where}: cursor pagination needs 'next' (where the next cursor is in the answer) and 'param' (the query parameter to send it in)")
        if style in ("page", "offset") and not p.get("param"):
            raise ConnectorError(f"{where}: {style} pagination needs 'param' (the query parameter that carries it)")
        for k in ("param", "size_param"):
            if k in p and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,40}", str(p[k])):
                raise ConnectorError(f"{where}: pagination {k} must be a query parameter name")
            if k in p and p[k] in query:
                raise ConnectorError(f"{where}: pagination {k} '{p[k]}' is also set in the tool's own query")
        out = {"style": style, "items": p.get("items"), "next": p.get("next"), "param": p.get("param"), "size_param": p.get("size_param"),
               "page_size": int(p.get("page_size", 25)), "max_pages": int(p.get("max_pages", 5)), "max_items": int(p.get("max_items", 100))}
        if not (1 <= out["max_pages"] <= MAX_PAGES and 1 <= out["max_items"] <= MAX_ITEMS and 1 <= out["page_size"] <= 200):
            raise ConnectorError(f"{where}: pagination max_pages must be 1-{MAX_PAGES}, max_items 1-{MAX_ITEMS} and page_size 1-200")
        return out

    # ---- calling ----
    _now = staticmethod(time.time)

    async def _access_token(self, ctx: ToolContext, force: bool = False) -> str:
        """The OAuth access token: cached in memory until shortly before it expires, fetched again when needed or when the system refused it."""
        async with self._token_lock:
            if not force and self._token and self._token[1] - TOKEN_SKEW > self._now():
                return self._token[0]
            a = self.auth
            form: dict[str, str] = {"grant_type": "client_credentials" if a["type"] == "oauth2_client_credentials" else "refresh_token"}
            if a["type"] == "oauth2_refresh_token":
                form["refresh_token"] = getattr(self, "_rotated", None) or ctx.secret(a["refresh_token"])
            if a.get("scope"):
                form["scope"] = a["scope"]
            cid = ctx.secret(a["client_id"])
            basic = None
            if a["type"] == "oauth2_client_credentials" and a.get("client_auth", "post") == "basic":
                basic = (cid, ctx.secret(a["client_secret"]))
            else:
                form["client_id"] = cid
                if a.get("client_secret"):
                    form["client_secret"] = ctx.secret(a["client_secret"])
            try:
                r = await self._client.post(a["token_url"], data=form, auth=basic, headers={"accept": "application/json"})
            except httpx.HTTPError as e:
                raise CallFailed(f"{self.name}: could not sign in to the system ({type(e).__name__})") from e
            if r.status_code != 200 or len(r.content) > MAX_RESPONSE:
                raise CallFailed(f"{self.name}: could not sign in to the system (the token address returned {r.status_code})")
            try:
                body = r.json()
                token = body["access_token"]
                lifetime = float(body.get("expires_in", 300))
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                raise CallFailed(f"{self.name}: the token address did not return a usable token") from e
            if not isinstance(token, str) or not token:
                raise CallFailed(f"{self.name}: the token address did not return a usable token")
            if isinstance(body.get("refresh_token"), str) and a["type"] == "oauth2_refresh_token":
                self._rotated = body["refresh_token"]  # kept in memory only: a provider that rotates refresh tokens will need a new one after a restart
            self._token = (token, self._now() + max(1.0, min(lifetime, 86400.0)))
            return token

    async def _auth_headers(self, ctx: ToolContext, effect: str) -> tuple[dict[str, str], tuple[str, str] | None]:
        headers, basic = self._headers(ctx, effect)
        if self.auth.get("type") in OAUTH_KINDS:
            headers["authorization"] = f"Bearer {await self._access_token(ctx)}"
        return headers, basic

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

    async def _send(self, tool: str, method: str, url: str, params: dict[str, Any] | None, body: Any, ctx: ToolContext, effect: str) -> httpx.Response:
        r: httpx.Response | None = None
        for attempt in (1, 2):
            headers, basic = await self._auth_headers(ctx, effect)
            try:
                r = await self._client.request(method, url, params=params or None, json=body, headers=headers, auth=basic)
            except httpx.HTTPError as e:
                raise CallFailed(f"{tool}: the system could not be reached ({type(e).__name__})") from e
            if r.status_code == 401 and attempt == 1 and self.auth.get("type") in OAUTH_KINDS:
                self._token = None  # the token was revoked or expired early: get a fresh one, once
                continue
            break
        assert r is not None
        return r

    @staticmethod
    def _json(tool: str, spec: dict[str, Any], r: httpx.Response) -> Any:
        """The answer as data; `None` for 'not found' on a read; raises CallFailed for anything unusable."""
        if len(r.content) > MAX_RESPONSE:
            raise CallFailed(f"{tool}: the response was too large to use")
        if r.status_code == 404 and spec["method"] == "GET":
            return None
        if r.status_code >= 300:
            raise CallFailed(f"{tool}: the system returned {r.status_code}")
        if not r.content:
            return {"ok": True}
        try:
            return r.json()
        except ValueError as e:
            raise CallFailed(f"{tool}: the response was not JSON") from e

    @staticmethod
    def _dig(data: Any, path: str | None) -> Any:
        for part in (path or "").split("."):
            if not part:
                continue
            if isinstance(data, dict) and part in data:
                data = data[part]
            else:
                return None
        return data

    def _next_link(self, tool: str, r: httpx.Response) -> str | None:
        """The address of the next page from a Link header, only if it stays inside this connector's own address."""
        m = re.search(r'<([^>]+)>\s*;[^,]*\brel="?next"?', r.headers.get("link", ""))
        if not m:
            return None
        nxt, base = urlsplit(m.group(1)), urlsplit(self.base)
        if (nxt.scheme, nxt.netloc) != (base.scheme, base.netloc) or not nxt.path.startswith(base.path or "/") or nxt.username or nxt.password or nxt.fragment:
            raise CallFailed(f"{tool}: the system pointed to a page outside its own address, so it was not followed")
        return m.group(1)

    async def _paged(self, tool: str, spec: dict[str, Any], path: str, params: dict[str, Any], ctx: ToolContext) -> Any:
        pg = spec["pagination"]
        items: list[Any] = []
        first = self.base + path
        url, cursor, page, offset = first, None, 1, 0
        pages, more = 0, False
        while pages < pg["max_pages"] and len(items) < pg["max_items"]:
            q: dict[str, Any] = {}
            if url == first:  # (the address a Link header gives already carries everything)
                q = dict(params)
                if pg["size_param"]:
                    q[pg["size_param"]] = pg["page_size"]
                if pg["style"] == "cursor" and cursor is not None:
                    q[pg["param"]] = cursor
                elif pg["style"] == "page":
                    q[pg["param"]] = page
                elif pg["style"] == "offset":
                    q[pg["param"]] = offset
            r = await self._send(tool, "GET", url, q, None, ctx, "read")
            data = self._json(tool, spec, r)
            if data is None:
                return {"found": False}
            batch = self._dig(data, pg["items"]) if pg["items"] else data
            if not isinstance(batch, list):
                raise CallFailed(f"{tool}: the system's answer did not contain the list the connector expects")
            items.extend(_project(x, spec["fields"]) if isinstance(x, dict) else x for x in batch)
            pages += 1
            more = False
            if not batch:
                break
            if pg["style"] == "cursor":
                nxt = self._dig(data, pg["next"])
                if nxt in (None, "", 0, False):
                    break
                if isinstance(nxt, (dict, list)):
                    raise CallFailed(f"{tool}: the system's next-page marker was not a simple value")
                cursor, more = str(nxt)[:500], True
            elif pg["style"] == "link_header":
                nxt_url = self._next_link(tool, r)
                if not nxt_url:
                    break
                url, more = nxt_url, True
            elif pg["style"] == "page":
                if pg["size_param"] and len(batch) < pg["page_size"]:
                    break
                page, more = page + 1, True
            else:
                if pg["size_param"] and len(batch) < pg["page_size"]:
                    break
                offset, more = offset + len(batch), True
        truncated = more or len(items) > pg["max_items"]
        items = items[: pg["max_items"]]
        while items and len(json.dumps(items, default=str)) > MAX_RESPONSE:  # whatever the pages held, what the model gets stays small
            items, truncated = (items[: len(items) // 2] if len(items) > 1 else []), True
        return {"items": items, "count": len(items), "truncated": truncated}

    async def _call(self, tool: str, spec: dict[str, Any], data: BaseModel, ctx: ToolContext, effect: str) -> Any:
        values = data.model_dump()

        def fill(v: Any) -> Any:
            if isinstance(v, str) and (m := _PLACEHOLDER.fullmatch(v)):
                return values.get(m.group(1))
            return v

        path = _PLACEHOLDER.sub(lambda m: quote(str(values[m.group(1)]), safe=""), spec["path"])
        params = {k: fill(v) for k, v in spec["query"].items() if fill(v) is not None}
        body = {k: fill(v) for k, v in spec["body"].items() if fill(v) is not None} if spec["body"] else None
        if spec.get("pagination"):
            return await self._paged(tool, spec, path, params, ctx)
        r = await self._send(tool, spec["method"], self.base + path, params, body, ctx, effect)
        result = self._json(tool, spec, r)
        if result is None:
            return {"found": False}
        if not r.content:
            return {"ok": True}
        return _project(result, spec["fields"])


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
