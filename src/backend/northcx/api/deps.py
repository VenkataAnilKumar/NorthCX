"""Everything the routers share. `create_app` builds one of these after its setup and hands it to every router.

The fields are the objects and helper functions the handlers close over. Typed fields come later; for now they are `Any`
so the move of the handlers out of `create_app` changes no behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AppDeps:
    actor: Any
    need_rel: Any
    privacy: Any
    record: Any
    rel_error: Any
    releases: Any
    runtime: Any
    simulations: Any
    skills: Any
    templates: Any
    version_json: Any
