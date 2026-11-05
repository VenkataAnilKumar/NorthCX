"""Routes that need no key: the demo page, the browser SDK files, health and readiness."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response

from northcx.api.common import _err, SDK_FILES
from northcx.api.deps import AppDeps
from northcx.widget import WIDGET_HTML

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    runtime = d.runtime
    traces = d.traces

    @app.get("/sdk/{name}")
    async def sdk_file(name: str) -> Any:
        """The browser SDK and the drop-in <northcx-chat> widget, so a site can load them from the same place it calls."""
        f = SDK_FILES.get(name)
        if f is None:
            return _err(404, "not_found", "No such file")
        return Response(f.read_bytes(), media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})

    @app.get("/", response_class=HTMLResponse)
    async def widget() -> str:
        return WIDGET_HTML

    @app.get("/health")
    async def health() -> dict[str, bool]:
        """Liveness: the process is up."""
        return {"ok": True}

    @app.get("/ready")
    async def ready() -> Any:
        """Readiness: the stores answer (for Postgres, the database is reachable). Used by load balancers and orchestrators."""
        try:
            await runtime.store.load_messages("__readiness_probe__")
            await traces.summaries(limit=1)
        except Exception:
            log.exception("readiness check failed")
            return JSONResponse({"ready": False}, status_code=503)
        return {"ready": True}
