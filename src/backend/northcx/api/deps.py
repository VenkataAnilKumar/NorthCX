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
    audit: Any
    email: Any
    limits: Any
    need_rel: Any
    privacy: Any
    record: Any
    rel_error: Any
    releases: Any
    runtime: Any
    secure_cookie: Any
    simulations: Any
    skills: Any
    sms: Any
    sso: Any
    telegram: Any
    templates: Any
    too_many: Any
    version_json: Any
    whatsapp: Any
