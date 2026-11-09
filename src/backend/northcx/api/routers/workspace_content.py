"""Routes for Outputs and Spaces in the Workspace."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import OutputBody, OutputEditBody, SpaceBody, SpaceEditBody
from northcx.outputs import ContentError, ContentService, InMemoryContent


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime = d.record, d.runtime
    svc: ContentService = getattr(runtime, "content", None) or ContentService(InMemoryContent())
    runtime.content = svc
    app.state.content = svc

    def staff(who: Identity) -> JSONResponse | None:
        if who.session_id is not None or who.role in ("channel", "customer_session", "trigger"):
            return _err(403, "forbidden", "Outputs and spaces are for signed-in staff")
        return None

    def admin(who: Identity) -> bool:
        return who.can("keys:manage")

    def fail(e: ContentError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 403: "forbidden", 404: "not_found", 429: "limit"}.get(e.status, "error"), str(e))

    # ---------------- outputs ----------------
    @app.get("/v1/workspace/outputs")
    async def list_outputs(request: Request, space: str | None = None, kind: str | None = None, mine: bool = False) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        return {"outputs": [o.to_dict() for o in await svc.list_outputs(who.name, admin(who), space, kind, mine)]}

    @app.post("/v1/workspace/outputs", status_code=201)
    async def create_output(body: OutputBody, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            o = await svc.create_output(who.name, body.title, body.body, body.kind, body.visibility, body.space_id, body.source, body.days, admin(who))
        except ContentError as e:
            return fail(e)
        await record(request, "workspace.output_create", o.id, kind=o.kind, source=o.source, space=o.space_id)
        return o.to_dict(full=True)

    @app.get("/v1/workspace/outputs/{output_id}")
    async def get_output(output_id: str, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            return JSONResponse((await svc.get_output(output_id, who.name, admin(who))).to_dict(full=True), headers={"Cache-Control": "no-store"})
        except ContentError as e:
            return fail(e)

    @app.put("/v1/workspace/outputs/{output_id}")
    async def edit_output(output_id: str, body: OutputEditBody, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            o = await svc.edit_output(output_id, who.name, admin(who), body.body, body.title, body.visibility)
        except ContentError as e:
            return fail(e)
        await record(request, "workspace.output_edit", o.id, version=o.versions[-1]["n"], visibility=o.visibility)
        return o.to_dict(full=True)

    @app.delete("/v1/workspace/outputs/{output_id}")
    async def delete_output(output_id: str, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            await svc.delete_output(output_id, who.name, admin(who))
        except ContentError as e:
            return fail(e)
        await record(request, "workspace.output_delete", output_id)
        return {"deleted": True}

    @app.get("/v1/workspace/outputs/{output_id}/export")
    async def export_output(output_id: str, request: Request, format: str = "md", version: int | None = Query(None, ge=1)) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            o = await svc.get_output(output_id, who.name, admin(who))
            content, media, ext = svc.export(o, format, version)
        except ContentError as e:
            return fail(e)
        await record(request, "workspace.output_export", o.id, format=ext, version=version)
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in o.title)[:60] or "output"
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    # ---------------- spaces ----------------
    @app.get("/v1/workspace/spaces")
    async def list_spaces(request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        return {"spaces": [s.to_dict() for s in await svc.list_spaces(who.name, admin(who))]}

    @app.post("/v1/workspace/spaces", status_code=201)
    async def create_space(body: SpaceBody, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            s = await svc.create_space(who.name, body.name, body.description, body.instructions, body.visibility)
        except ContentError as e:
            return fail(e)
        await record(request, "workspace.space_create", s.id, visibility=s.visibility)
        return s.to_dict()

    @app.get("/v1/workspace/spaces/{space_id}")
    async def get_space(space_id: str, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            s = await svc.get_space(space_id, who.name, admin(who))
        except ContentError as e:
            return fail(e)
        return {**s.to_dict(), "outputs": [o.to_dict() for o in await svc.list_outputs(who.name, admin(who), space_id)]}

    @app.put("/v1/workspace/spaces/{space_id}")
    async def edit_space(space_id: str, body: SpaceEditBody, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            s = await svc.edit_space(space_id, who.name, admin(who), name=body.name, description=body.description, instructions=body.instructions, visibility=body.visibility)
        except ContentError as e:
            return fail(e)
        await record(request, "workspace.space_edit", s.id, visibility=s.visibility)
        return s.to_dict()

    @app.delete("/v1/workspace/spaces/{space_id}")
    async def delete_space(space_id: str, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            await svc.delete_space(space_id, who.name, admin(who))
        except ContentError as e:
            return fail(e)
        await record(request, "workspace.space_delete", space_id)
        return {"deleted": True}
