"""Server start-up, one step per module. Each step reads what earlier steps built from a shared
namespace and adds what it builds, in the same order as the original single function."""
import os
from types import SimpleNamespace

import uvicorn

from . import agents, app, integrations, notifiers, observe, optional, runtime, security, settings, storage

STEPS = (settings.load_settings, storage.build_storage, notifiers.build_notifiers, integrations.build_integrations,
         runtime.build_runtime, agents.build_agents, observe.build_observability, security.build_security, optional.build_optional)


def run() -> None:
    c = SimpleNamespace()
    for step in STEPS:
        step(c)
    web = app.build_app(c)
    platform = build_platform(c)
    if platform is None:
        uvicorn.run(web, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))
        return
    import asyncio

    async def both() -> None:        # the platform API is a second listener, by default on this machine only
        servers = [uvicorn.Server(uvicorn.Config(web, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))),
                   uvicorn.Server(uvicorn.Config(platform, host=os.environ.get("NORTHCX_PLATFORM_HOST", "127.0.0.1"), port=int(os.environ.get("NORTHCX_PLATFORM_PORT", "3100"))))]
        await asyncio.gather(*(s.serve() for s in servers))
    asyncio.run(both())


def build_platform(c: SimpleNamespace):
    """The platform API (WP2.8), only when NORTHCX_PLATFORM_KEY is set."""
    key = os.environ.get("NORTHCX_PLATFORM_KEY", "").strip()
    if not key:
        return None
    from northcx.budget_settings import InMemorySettings
    from northcx.platform_api import create_platform_app
    settings_repo = c.runtime.budget_settings.repo if getattr(c.runtime, "budget_settings", None) is not None else InMemorySettings()
    return create_platform_app(key, c.access.tenants, c.runtime.tenant_limits, settings_repo, c.audit_repo, c.access, getattr(c.runtime, "vault", None), getattr(c.runtime, "tenant_llm", None))
