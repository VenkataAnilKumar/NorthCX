"""Routes for groups: roles bound to sets of people (WP3.2)."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import GroupBody, GroupUpdateBody, MemberBody
from northcx.groups import GroupError


def register(app: FastAPI, d: AppDeps) -> None:
    access, actor, record = d.access, d.actor, d.record

    def svc() -> Any:
        return access.groups or _err(501, "not_configured", "Groups are not configured on this server")

    @app.get("/v1/groups")
    async def list_groups() -> Any:
        s = svc()
        return s if not hasattr(s, "repo") else {"groups": [g.to_dict() for g in await s.repo.list()]}

    @app.post("/v1/groups", status_code=201)
    async def create_group(body: GroupBody, request: Request) -> Any:
        s = svc()
        if not hasattr(s, "repo"):
            return s
        try:
            g = await s.create(body.name, body.roles, actor(request, None), body.external_name, body.description)
        except GroupError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "group.create", g.name, roles=g.roles, external=g.external_name)
        return g.to_dict()

    @app.put("/v1/groups/{group_id}")
    async def update_group(group_id: str, body: GroupUpdateBody, request: Request) -> Any:
        s = svc()
        if not hasattr(s, "repo"):
            return s
        try:
            g = await s.update(group_id, body.roles, body.external_name or None, body.description, clear_external=body.external_name == "")
        except KeyError:
            return _err(404, "not_found", "Unknown group")
        except GroupError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "group.update", g.name, roles=g.roles, external=g.external_name)
        return g.to_dict()

    @app.delete("/v1/groups/{group_id}")
    async def delete_group(group_id: str, request: Request) -> Any:
        s = svc()
        if not hasattr(s, "repo"):
            return s
        g = await s.repo.get(group_id)
        if g is None:
            return _err(404, "not_found", "Unknown group")
        await s.delete(group_id)
        await record(request, "group.delete", g.name, roles=g.roles)
        return {"deleted": True}

    @app.post("/v1/groups/{group_id}/members", status_code=201)
    async def add_member(group_id: str, body: MemberBody, request: Request) -> Any:
        s = svc()
        if not hasattr(s, "repo"):
            return s
        try:
            g = await s.add_member(group_id, body.subject)
        except KeyError:
            return _err(404, "not_found", "Unknown group")
        except GroupError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "group.member.add", g.name, member=body.subject.strip().lower())
        return g.to_dict()

    @app.delete("/v1/groups/{group_id}/members/{subject}")
    async def remove_member(group_id: str, subject: str, request: Request) -> Any:
        s = svc()
        if not hasattr(s, "repo"):
            return s
        try:
            g = await s.remove_member(group_id, subject)
        except KeyError:
            return _err(404, "not_found", "Unknown group")
        await record(request, "group.member.remove", g.name, member=subject.strip().lower())
        return g.to_dict()
