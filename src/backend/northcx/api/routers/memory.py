"""Routes for a customer's long-term memories."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.privacy import customer_ref


def register(app: FastAPI, d: AppDeps) -> None:
    record = d.record
    runtime = d.runtime

    # ---- long-term memory ----
    @app.get("/v1/memories")
    async def memories_list(customerId: str, request: Request) -> Any:
        if runtime.memories is None:
            return _err(501, "not_configured", "Memory is not enabled")
        items = await runtime.memories.list(customerId)
        await record(request, "memory.read", customer_ref(customerId), count=len(items))
        return JSONResponse({"customerId": customerId, "memories": [m.to_dict() for m in items]}, headers={"Cache-Control": "no-store"})

    @app.delete("/v1/memories/{memory_id}")
    async def memories_forget(memory_id: str, customerId: str, request: Request) -> Any:
        if runtime.memories is None:
            return _err(501, "not_configured", "Memory is not enabled")
        if not await runtime.memories.forget(customerId, memory_id):
            return _err(404, "not_found", "Unknown memory")
        await record(request, "memory.forget", customer_ref(customerId), memory=memory_id)
        return {"deleted": True}

    @app.delete("/v1/memories")
    async def memories_forget_all(customerId: str, request: Request) -> Any:
        if runtime.memories is None:
            return _err(501, "not_configured", "Memory is not enabled")
        n = await runtime.memories.forget_all(customerId)
        await record(request, "memory.forget_all", customer_ref(customerId), count=n)
        return {"deleted": n}
