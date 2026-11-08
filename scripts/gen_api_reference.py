"""Writes (or checks) the generated API reference: docs/api/openapi.json and docs/api/index.html.

Both come from the application's own schema, enriched with the permission each route needs, so the reference cannot
drift from the code. The live schema endpoint stays switched off on the server.
    python scripts/gen_api_reference.py            # rewrite the files
    python scripts/gen_api_reference.py --check    # exit 1 if they are out of date
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "api"
sys.path.insert(0, str(ROOT / "src" / "backend"))


def build_schema() -> dict:
    from northcx import __version__
    from northcx.demo import DemoLLM
    from northcx.runtime import Runtime
    from northcx.server import PUBLIC_ROUTES, create_app, permission_for
    from northcx.store import InMemoryStore
    from northcx.trace import TraceStore

    rt = Runtime(DemoLLM(), InMemoryStore(), TraceStore())
    app = create_app(rt, rt.traces, {})
    app.openapi_url = "/openapi.json"  # the server serves none; this only lets the schema be built
    schema = app.openapi()
    schema["info"] = {"title": "NorthCX API", "version": __version__,
                      "description": "Every request to /v1 carries `Authorization: Bearer <key>` unless it is marked public. `x-required-permission` names the permission the key's role needs. "
                                     "Errors are `{\"error\": {\"code\": ..., \"message\": ...}}`."}
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            concrete = re.sub(r"\{[^}]+\}", "x1", path)
            if (method.upper(), concrete) in PUBLIC_ROUTES or not path.startswith("/v1/"):
                op["x-required-permission"] = None
                op["x-public"] = True
            else:
                op["x-required-permission"] = permission_for(method.upper(), concrete)
            op["tags"] = [path.split("/")[2] if path.startswith("/v1/") and len(path.split("/")) > 2 else "service"]
    schema["paths"] = dict(sorted(schema["paths"].items()))
    return schema


def render_json(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=False) + "\n"


def _ref(schema: dict, node: dict) -> dict:
    if "$ref" in node:
        return schema["components"]["schemas"].get(node["$ref"].rsplit("/", 1)[-1], {})
    return node


def _type(schema: dict, node: dict) -> str:
    if "$ref" in node:
        return node["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in node:
        return " or ".join(_type(schema, n) for n in node["anyOf"])
    if node.get("type") == "array":
        return f"list of {_type(schema, node.get('items', {}))}"
    return node.get("type", "any")


def _fields(schema: dict, node: dict) -> str:
    body = _ref(schema, node)
    props, required = body.get("properties", {}), set(body.get("required", []))
    if not props:
        return ""
    rows = "".join(f"<tr><td><code>{html.escape(k)}</code></td><td>{html.escape(_type(schema, v))}</td><td>{'yes' if k in required else ''}</td>"
                   f"<td>{html.escape(str(v.get('description', '')))}</td></tr>" for k, v in props.items())
    return f"<table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th></th></tr></thead><tbody>{rows}</tbody></table>"


def render_html(schema: dict) -> str:
    groups: dict[str, list[str]] = {}
    count = 0
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            count += 1
            perm = op.get("x-required-permission")
            badge = '<span class="perm public">public</span>' if op.get("x-public") else f'<span class="perm">{html.escape(perm or "authenticated")}</span>'
            params = "".join(f"<tr><td><code>{html.escape(p['name'])}</code></td><td>{html.escape(p['in'])}</td><td>{html.escape(_type(schema, p.get('schema', {})))}</td><td>{'yes' if p.get('required') else ''}</td></tr>"
                             for p in op.get("parameters", []))
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            codes = ", ".join(c for c in op.get("responses", {}) if c != "422")
            text = html.escape((op.get("description") or op.get("summary") or "").strip()).replace("\n", "<br>")
            groups.setdefault(op["tags"][0], []).append(
                f'<article id="{html.escape(op["operationId"])}"><h3><span class="m {method}">{method.upper()}</span> <code>{html.escape(path)}</code> {badge}</h3>'
                f"<p>{text}</p>"
                + (f"<h4>Parameters</h4><table><thead><tr><th>Name</th><th>In</th><th>Type</th><th>Required</th></tr></thead><tbody>{params}</tbody></table>" if params else "")
                + (f"<h4>Request body: {html.escape(_type(schema, body))}</h4>{_fields(schema, body)}" if body else "")
                + f'<p class="codes">Responses: {html.escape(codes)}</p></article>')
    nav = " · ".join(f'<a href="#g-{html.escape(g)}">{html.escape(g)}</a>' for g in sorted(groups))
    sections = "".join(f'<section id="g-{html.escape(g)}"><h2>{html.escape(g)}</h2>{"".join(items)}</section>' for g, items in sorted(groups.items()))
    info = schema["info"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(info['title'])} {html.escape(info['version'])}</title>
<style>
:root{{--bg:#f6f8fb;--surface:#fff;--text:#0f172a;--muted:#5b6678;--border:#d9e0ea;--primary:#0b3d91}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0b1220;--surface:#131c2e;--text:#e8edf6;--muted:#9aa7bd;--border:#26324a;--primary:#6ea0ff}}}}
body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 ui-sans-serif,system-ui,sans-serif}}
main{{max-width:60rem;margin:0 auto;padding:1rem 16px 4rem}}a{{color:var(--primary)}}
article{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:.5rem 1rem;margin:.75rem 0;overflow-x:auto}}
h3{{font-size:1rem;margin:.5rem 0}}h4{{margin:.75rem 0 .25rem;font-size:.85rem;color:var(--muted)}}code{{font-size:.9em}}
table{{border-collapse:collapse;width:100%;font-size:.85rem}}th,td{{text-align:left;border-bottom:1px solid var(--border);padding:.25rem .5rem}}
.m{{display:inline-block;min-width:3.5rem;text-align:center;border-radius:4px;padding:0 .4rem;font-size:.75rem;font-weight:700;color:#fff;background:var(--primary)}}
.m.delete{{background:#a11d1d}}.m.get{{background:#0f7b3f}}.m.put,.m.patch{{background:#8a5300}}
.perm{{font-size:.75rem;border:1px solid var(--border);border-radius:4px;padding:0 .4rem;color:var(--muted)}}.perm.public{{color:#0f7b3f}}.codes{{color:var(--muted);font-size:.8rem}}
</style></head><body><main>
<h1>{html.escape(info['title'])} <small>{html.escape(info['version'])}</small></h1>
<p>{html.escape(info['description'])}</p><p>{count} operations. Generated from the application's schema by <code>scripts/gen_api_reference.py</code>; machine-readable copy: <a href="openapi.json">openapi.json</a>.</p>
<p>{nav}</p>{sections}</main></body></html>
"""


def outputs() -> dict[str, str]:
    schema = build_schema()
    return {"openapi.json": render_json(schema), "index.html": render_html(schema)}


if __name__ == "__main__":
    want = outputs()
    if "--check" in sys.argv:
        stale = [n for n, text in want.items() if not (OUT / n).exists() or (OUT / n).read_text() != text]
        if stale:
            sys.exit("out of date: " + ", ".join(stale) + " (run python scripts/gen_api_reference.py)")
        print("API reference is up to date")
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        for n, text in want.items():
            (OUT / n).write_text(text)
        print("wrote", ", ".join(f"docs/api/{n}" for n in want))
