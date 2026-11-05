"""Everything the routers share. `create_app` builds one of these after its setup and hands it to every router.

The fields are the objects and helper functions the handlers close over. Typed fields come later; for now they are `Any`
so the move of the handlers out of `create_app` changes no behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AppDeps:
    MAX_EMAIL_BYTES: Any
    SSO_COOKIE: Any
    access: Any
    actor: Any
    agents: Any
    alerts: Any
    audit: Any
    call_repo: Any
    crawl_scheduler: Any
    crawler: Any
    email: Any
    events: Any
    fb: Any
    flow: Any
    insight: Any
    kb: Any
    limits: Any
    need_env: Any
    need_rel: Any
    privacy: Any
    provider: Any
    record: Any
    regression: Any
    rel_error: Any
    releases: Any
    residency: Any
    review_repo: Any
    rollouts: Any
    runtime: Any
    secure_cookie: Any
    simulations: Any
    skills: Any
    sms: Any
    sso: Any
    tag_repo: Any
    telegram: Any
    templates: Any
    too_many: Any
    traces: Any
    transcriber: Any
    version_json: Any
    voice: Any
    whatsapp: Any
