"""Routes for Library items in the Workspace: prompts, macros, playbooks and canned answers, and the suggestions the Inbox shows."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.decision_teams import VIEWER_TEAM, team_of
from northcx.api.models import LibraryEditBody, LibraryItemBody, LibrarySuggestBody
from northcx.library_items import LibraryError, LibraryService


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime = d.record, d.runtime
    svc: LibraryService = getattr(runtime, "library", None) or LibraryService()
    runtime.library = svc
    app.state.library = svc

    def staff(who: Identity) -> JSONResponse | None:
        VIEWER_TEAM.set(team_of(who))                     # who is asking, for what is shared with a team
        if who.session_id is not None or who.role in ("channel", "customer_session", "trigger"):
            return _err(403, "forbidden", "The library is for signed-in staff")
        return None

    def fail(e: LibraryError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 403: "forbidden", 404: "not_found", 429: "limit"}.get(e.status, "error"), str(e))

    @app.get("/v1/workspace/library-items")
    async def list_items(request: Request, kind: str | None = None, q: str | None = None, mine: bool = False) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        return {"items": [i.to_dict() for i in await svc.list(who.name, who.can("keys:manage"), kind, q, mine)]}

    @app.post("/v1/workspace/library-items", status_code=201)
    async def create_item(body: LibraryItemBody, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            i = await svc.create(who.name, body.title, body.body, body.kind, body.visibility, body.tags)
        except LibraryError as e:
            return fail(e)
        await record(request, "library.create", i.id, kind=i.kind, visibility=i.visibility)
        return i.to_dict(full=True)

    @app.post("/v1/workspace/library-items/suggest")
    async def suggest(body: LibrarySuggestBody, request: Request) -> Any:
        """Macros and canned answers that fit some text, such as a customer's message. The text is not stored."""
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        return {"suggestions": [i.to_dict() for i in await svc.suggest(who.name, who.can("keys:manage"), body.text, body.limit)]}

    @app.get("/v1/workspace/library-items/{item_id}")
    async def get_item(item_id: str, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            return (await svc.get(item_id, who.name, who.can("keys:manage"))).to_dict(full=True)
        except LibraryError as e:
            return fail(e)

    @app.put("/v1/workspace/library-items/{item_id}")
    async def edit_item(item_id: str, body: LibraryEditBody, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            i = await svc.edit(item_id, who.name, who.can("keys:manage"), body.title, body.body, body.visibility, body.tags)
        except LibraryError as e:
            return fail(e)
        await record(request, "library.edit", i.id, version=i.versions[-1]["n"], visibility=i.visibility)
        return i.to_dict(full=True)

    @app.delete("/v1/workspace/library-items/{item_id}")
    async def delete_item(item_id: str, request: Request) -> Any:
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            await svc.delete(item_id, who.name, who.can("keys:manage"))
        except LibraryError as e:
            return fail(e)
        await record(request, "library.delete", item_id)
        return {"deleted": True}

    @app.post("/v1/workspace/library-items/{item_id}/use")
    async def use_item(item_id: str, request: Request) -> Any:
        """Count one use and return the text, for copying into a reply or the Pilot."""
        who: Identity = request.state.identity
        if (r := staff(who)) is not None:
            return r
        try:
            i, uses = await svc.use(item_id, who.name, who.can("keys:manage"))
        except LibraryError as e:
            return fail(e)
        return {**i.to_dict(full=True), "uses": uses}
