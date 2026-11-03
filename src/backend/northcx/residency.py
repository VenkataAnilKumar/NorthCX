"""Data residency (P6): say where data may go, and check that every place this deployment sends it to is in an allowed region.

NorthCX is self-hosted, so the data it keeps (conversations, traces, knowledge) rests wherever the operator runs the database
and the files. What can leave is what is sent to other services: the model, an embeddings service, trace exporters, webhooks,
email, SMS and WhatsApp providers, business systems. The operator writes a small policy file naming the region of this
deployment, the regions data may go to, and which host belongs to which region. At start-up every configured destination is
looked up; in strict mode a destination in a region that is not allowed, or one nobody mapped, stops the server from starting.
`/v1/residency` reports each flow, what data it carries and whether it complies, as evidence for a data-processing agreement.

This is a check of declared addresses, not of where a provider's servers physically are: the mapping is the operator's claim,
and a provider can route a request elsewhere behind one address. Use the provider's regional endpoints.
"""
from __future__ import annotations

import fnmatch
import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlsplit

import yaml

REGION = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


class ResidencyError(ValueError):
    pass


@dataclass
class Policy:
    region: str
    allowed: list[str]
    strict: bool = False
    hosts: list[tuple[str, str]] = field(default_factory=list)  # (fnmatch pattern, region)

    def region_of(self, host: str) -> str | None:
        h = host.lower().rstrip(".")
        if h == "localhost" or _is_loopback(h):
            return "local"
        for pattern, region in self.hosts:
            if fnmatch.fnmatchcase(h, pattern):
                return region
        return None


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def parse_policy(text: str) -> Policy:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ResidencyError(f"The residency file is not valid YAML: {e}") from None
    if not isinstance(data, dict):
        raise ResidencyError("The residency file must be a mapping with 'region' and 'hosts'")
    unknown = set(data) - {"region", "allowed_regions", "strict", "hosts"}
    if unknown:
        raise ResidencyError("Unknown setting(s) in the residency file: " + ", ".join(sorted(map(str, unknown))))
    region = data.get("region")
    if not isinstance(region, str) or not REGION.match(region):
        raise ResidencyError("'region' must be a short lowercase name such as eu or us-east")
    allowed = data.get("allowed_regions", [region])
    if not isinstance(allowed, list) or not allowed or not all(isinstance(a, str) and REGION.match(a) for a in allowed):
        raise ResidencyError("'allowed_regions' must be a list of region names")
    strict = data.get("strict", False)
    if not isinstance(strict, bool):
        raise ResidencyError("'strict' must be true or false")
    hosts: list[tuple[str, str]] = []
    for i, h in enumerate(data.get("hosts") or []):
        if not isinstance(h, dict) or set(h) - {"match", "region"} or not isinstance(h.get("match"), str) or not isinstance(h.get("region"), str):
            raise ResidencyError(f"hosts entry {i + 1} needs 'match' (a host name; * allowed) and 'region'")
        m, r = h["match"].strip().lower(), h["region"]
        if not re.fullmatch(r"[a-z0-9*.-]{1,253}", m) or m in ("*", "*.*") or not REGION.match(r):
            raise ResidencyError(f"hosts entry {i + 1}: '{h['match']}' is not a usable host pattern, or the region name is invalid")
        hosts.append((m, r))
    return Policy(region, list(dict.fromkeys(allowed)), strict, hosts)


# (name, environment variable, what travels, default host when only a switch is set)
FLOWS: list[tuple[str, str, str, str | None]] = [
    ("Language model", "ANTHROPIC_BASE_URL", "Conversation text, tool results and knowledge passages the agent reads", "api.anthropic.com"),
    ("Embeddings service", "NORTHCX_EMBEDDINGS_URL", "Knowledge text and customers' questions", None),
    ("Trace export (Langfuse)", "NORTHCX_LANGFUSE_URL", "Traces, redacted as configured", None),
    ("Trace export (OpenTelemetry)", "NORTHCX_OTLP_ENDPOINT", "Traces, redacted as configured", None),
    ("Reply and status webhook", "NORTHCX_WEBHOOK_URL", "Replies, approval results, hand-off notices", None),
    ("Alert webhook", "NORTHCX_ALERT_WEBHOOK_URL", "Alert summaries (no conversation text)", None),
    ("Human inbox webhook", "NORTHCX_INBOX_WEBHOOK_URL", "Hand-off packages: transcript, customer profile, summary", None),
    ("Chatwoot helpdesk", "NORTHCX_CHATWOOT_URL", "Hand-off packages and agent-assist suggestions", None),
    ("Customer context service", "NORTHCX_CONTEXT_URL", "Customer identifier", None),
    ("Attachment scanner", "NORTHCX_ATTACHMENT_SCAN_URL", "Files customers upload", None),
    ("Email (SMTP)", "NORTHCX_SMTP_URL", "Replies to customers", None),
    ("SMS provider", "NORTHCX_SMS_NUMBER", "Texts to and from customers, phone numbers", "api.twilio.com"),
    ("WhatsApp", "NORTHCX_WHATSAPP_PHONE_ID", "Messages to and from customers, phone numbers", "graph.facebook.com"),
    ("Single sign-on provider", "NORTHCX_SSO_ISSUER", "Staff sign-in only", None),
]
OVERRIDES = {"NORTHCX_WHATSAPP_PHONE_ID": "NORTHCX_WHATSAPP_API_URL"}  # a switch whose address can be overridden


def host_of(value: str) -> str | None:
    v = value.strip()
    if not v:
        return None
    try:
        h = urlsplit(v if "://" in v else "//" + v).hostname
    except ValueError:
        return None
    return h.lower() if h else None


def _flow(name: str, kind: str, host: str | None, data: str, policy: Policy | None) -> dict[str, Any]:
    region = policy.region_of(host) if (policy and host) else None
    if policy is None:
        status = "unchecked"
    elif region is None:
        status = "unmapped"
    elif region == "local" or region in policy.allowed:
        status = "ok"
    else:
        status = "not_allowed"
    return {"name": name, "kind": kind, "host": host, "data": data, "region": region, "status": status}


def build_report(env: Mapping[str, str], policy: Policy | None) -> dict[str, Any]:
    flows = []
    db = env.get("NORTHCX_DATABASE_URL") or env.get("DATABASE_URL")
    if db:
        flows.append(_flow("Database", "storage", host_of(db.split("@", 1)[-1] if "@" in db else db), "Everything NorthCX stores: conversations, memories, traces, knowledge, audit log", policy))
    for name, var, data, default_host in FLOWS:
        value = env.get(var, "").strip()
        if var == "NORTHCX_SMTP_URL" and not value:
            value = env.get("NORTHCX_SMTP_URL_FILE", "") and "(file)"
        if var == "ANTHROPIC_BASE_URL":
            if not (value or env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_API_KEY_FILE")):
                continue  # no live model configured (offline demo)
        elif not value:
            continue
        override = env.get(OVERRIDES.get(var, ""), "").strip()
        host = host_of(override or value) if (override or default_host is None) else default_host
        if var == "ANTHROPIC_BASE_URL":
            host = host_of(value) if value else default_host
        if var == "NORTHCX_SMTP_URL" and value == "(file)":
            host = None
        flows.append(_flow(name, "outbound", host, data, policy))
    for h in [x.strip().lower() for x in env.get("NORTHCX_CONNECTOR_HOSTS", "").split(",") if x.strip()]:
        flows.append(_flow(f"Business system ({h})", "outbound", h.split(":")[0], "Tool inputs and results for the connectors that use this host", policy))
    problems = [f for f in flows if f["status"] in ("unmapped", "not_allowed")]
    return {"configured": policy is not None, "region": policy.region if policy else None, "allowedRegions": policy.allowed if policy else [], "strict": bool(policy and policy.strict),
            "flows": flows, "compliant": policy is not None and not problems, "problems": [_describe(f, policy) for f in problems],
            "note": "This checks the addresses the server is configured with against the mapping in the residency file. It cannot see where a provider's servers physically are; "
                    "use the provider's regional endpoint and keep the mapping honest. Websites the crawler reads send no customer data and are not listed."}


def _describe(f: dict[str, Any], policy: Policy | None) -> str:
    where = f["host"] or "an address that could not be read"
    if f["status"] == "unmapped":
        return f"{f['name']} sends data to {where}, which the residency file does not map to a region"
    return f"{f['name']} sends data to {where} in region '{f['region']}', which is not allowed (allowed: {', '.join(policy.allowed) if policy else '-'})"
