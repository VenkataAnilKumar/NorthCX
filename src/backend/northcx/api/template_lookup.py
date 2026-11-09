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
    # a built-in that cannot be verified is refused: changed, forged, or never signed while a signing key ships. With no key shipped at all there is nothing to check against.
    if p.get("source") == "built-in" and not p.get("verified") and (p.get("signed") or p.get("keyFingerprint")):
        return f"This built-in template is {p.get('status')}, so it cannot be installed. Reinstall NorthCX or restore the file."
    return None
