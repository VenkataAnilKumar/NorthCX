"""Writes (or checks) the Agent API contract: docs/api/agent-api-v1.json.

The contract is the part of /v1 that other software builds on: every operation tagged agents, sessions, simulations, handoffs,
approvals, traces or events in docs/api/openapi.json. For each operation it records the permission, the parameters and the request body,
references resolved. Responses are included only where a route declares a response model (northcx/api/responses.py); untyped responses are not covered.
The stability rule (docs/04-integrations/NorthCX_API-Design.md): within /v1 a
field may be added; a route, parameter or field is never removed, retyped or newly required.
    python scripts/gen_agent_api_contract.py            # rewrite the snapshot; refuses if the change is breaking
    python scripts/gen_agent_api_contract.py --check    # exit 1 if the snapshot is out of date or the change is breaking
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = ROOT / "docs" / "api" / "openapi.json"
SNAPSHOT = ROOT / "docs" / "api" / "agent-api-v1.json"
GROUPS = ("agents", "sessions", "simulations", "handoffs", "approvals", "traces", "events")
_DROP = {"title", "description", "examples", "example", "default"}


def _resolve(node, components, seen=()):
    if isinstance(node, list):
        return [_resolve(x, components, seen) for x in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        if name in seen:
            return {"$cycle": name}
        return _resolve(components[name], components, seen + (name,))
    return {k: _resolve(v, components, seen) for k, v in node.items() if k not in _DROP}


def _json_schema(content):
    return (content or {}).get("application/json", {}).get("schema")


def build_contract(openapi: dict) -> dict:
    components = openapi.get("components", {}).get("schemas", {})
    ops = {}
    for path, methods in openapi["paths"].items():
        for method, op in methods.items():
            if op.get("tags", [""])[0] not in GROUPS:
                continue
            body = _json_schema((op.get("requestBody") or {}).get("content"))
            responses = {code: _resolve(sch, components) for code, r in op.get("responses", {}).items()
                         if code.startswith("2") and (sch := _json_schema(r.get("content"))) and ({"$ref", "type", "properties", "items"} & sch.keys())}  # only typed responses
            ops[f"{method.upper()} {path}"] = {
                "permission": op.get("x-required-permission"),
                "parameters": [{"name": p["name"], "in": p["in"], "required": p.get("required", False), "schema": _resolve(p.get("schema", {}), components)}
                               for p in sorted(op.get("parameters", []), key=lambda p: (p["in"], p["name"]))],
                "request": {"required": (op.get("requestBody") or {}).get("required", False), "schema": _resolve(body, components)} if body else None,
                "responses": responses}
    return {"contract": "NorthCX Agent API", "version": "v1", "groups": list(GROUPS), "operations": dict(sorted(ops.items()))}


def _kind(schema) -> str:
    return json.dumps({k: schema.get(k) for k in ("type", "anyOf", "oneOf", "$cycle") if k in schema}, sort_keys=True)


LIMITS_UPPER = ("maxLength", "maxItems", "maxProperties", "maximum", "exclusiveMaximum")  # a lower value rejects input that was accepted
LIMITS_LOWER = ("minLength", "minItems", "minProperties", "minimum", "exclusiveMinimum")  # a higher value does


def _tighter_limits(old: dict, new: dict, where: str) -> list[str]:
    """A request that now enforces a limit it did not enforce, or a stricter one, rejects input a client could send before."""
    out = [f"{where}: {k} is now {new[k]}" for k in LIMITS_UPPER if k in new and (k not in old or new[k] < old[k])]
    out += [f"{where}: {k} is now {new[k]}" for k in LIMITS_LOWER if k in new and (k not in old or new[k] > old[k])]
    if "pattern" in new and new["pattern"] != old.get("pattern"):
        out.append(f"{where}: pattern is now {new['pattern']}")
    return out


def _schema_breaks(old, new, where: str, request: bool = True) -> list[str]:
    """Differences that break a client. A request must still accept everything it accepted; a response must still give everything it gave."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return []
    out = []
    if _kind(old) != _kind(new):
        return [f"{where}: type changed"]
    if "enum" in old and "enum" in new:
        old_values, new_values = set(map(str, old["enum"])), set(map(str, new["enum"]))
        if request and old_values - new_values:
            out.append(f"{where}: no longer accepts {sorted(old_values - new_values)}")
        if not request and new_values - old_values:
            out.append(f"{where}: can now be {sorted(new_values - old_values)}")
    old_props, new_props = old.get("properties", {}), new.get("properties", {})
    for name, sub in old_props.items():
        if name not in new_props:
            out.append(f"{where}.{name}: removed")
        else:
            out += _schema_breaks(sub, new_props[name], f"{where}.{name}", request)
    if request:
        out += _tighter_limits(old, new, where)
        out += [f"{where}.{n}: newly required" for n in new.get("required", []) if n not in old.get("required", [])]
    else:
        out += [f"{where}.{n}: no longer always present" for n in old.get("required", []) if n not in new.get("required", [])]
    if "items" in old and "items" in new:
        out += _schema_breaks(old["items"], new["items"], f"{where}[]", request)
    return out


def breaking_changes(old: dict, new: dict) -> list[str]:
    """What a client of `old` could not rely on in `new`; empty when `new` only adds."""
    out = []
    for key, a in old["operations"].items():
        b = new["operations"].get(key)
        if b is None:
            out.append(f"{key}: removed")
            continue
        if a["permission"] != b["permission"]:
            out.append(f"{key}: permission changed from {a['permission']} to {b['permission']}")
        new_params = {(p["name"], p["in"]): p for p in b["parameters"]}
        for p in a["parameters"]:
            q = new_params.get((p["name"], p["in"]))
            if q is None:
                out.append(f"{key}: parameter {p['name']} removed")
            else:
                out += _schema_breaks(p["schema"], q["schema"], f"{key}: parameter {p['name']}")
        old_params = {(p["name"], p["in"]) for p in a["parameters"]}
        out += [f"{key}: parameter {p['name']} newly required" for p in b["parameters"] if p["required"] and (p["name"], p["in"]) not in old_params]
        if a["request"] and not b["request"]:
            out.append(f"{key}: request body removed")
        elif a["request"] and b["request"]:
            out += _schema_breaks(a["request"]["schema"], b["request"]["schema"], f"{key}: request")
        elif b["request"] and b["request"]["required"]:
            out.append(f"{key}: request body newly required")
        for code, schema in a.get("responses", {}).items():
            out += [f"{key}: response {code} removed"] if code not in b["responses"] else _schema_breaks(schema, b["responses"][code], f"{key}: response {code}", False)
    return out


def render(contract: dict) -> str:
    return json.dumps(contract, indent=2) + "\n"


def main(argv: list[str]) -> int:
    current = build_contract(json.loads(OPENAPI.read_text()))
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    broken = breaking_changes(old, current) if old else []
    if broken:
        print("Breaking change to the Agent API within /v1:\n  " + "\n  ".join(broken))
        return 1
    if "--check" in argv:
        if not SNAPSHOT.exists() or SNAPSHOT.read_text() != render(current):
            print("docs/api/agent-api-v1.json is out of date: run python scripts/gen_agent_api_contract.py")
            return 1
        return 0
    SNAPSHOT.write_text(render(current))
    print(f"wrote {SNAPSHOT.relative_to(ROOT)}: {len(current['operations'])} operations")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
