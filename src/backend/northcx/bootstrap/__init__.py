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
    uvicorn.run(web, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))
