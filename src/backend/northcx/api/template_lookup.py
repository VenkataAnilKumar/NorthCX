"""Find templates: the built-in and local ones, plus this organization's own approved templates."""
from __future__ import annotations

from typing import Any

from northcx.api.deps import AppDeps
from northcx.templates import Template


async def org_published(d: AppDeps) -> dict[str, Template]:
    svc = getattr(d.runtime, "org_templates", None)
    return await svc.published() if svc is not None else {}


async def all_templates(d: AppDeps) -> dict[str, Template]:
    return {**(d.templates or {}), **{k: v for k, v in (await org_published(d)).items() if k not in (d.templates or {})}}   # a built-in id can never be replaced by an organization template


async def lookup(d: AppDeps, template_id: str) -> Template | None:
    return (d.templates or {}).get(template_id) or (await org_published(d)).get(template_id)


def tampered(t: Template) -> str | None:
    """A built-in whose content no longer matches its signature is not installed."""
    p: dict[str, Any] = t.provenance
    return f"This built-in template is {p.get('status')}, so it cannot be installed. Reinstall NorthCX or restore the file." if p.get("source") == "built-in" and p.get("signed") and not p.get("verified") else None
