"""Groups (WP3.2): named sets of people with roles bound to them. A person's effective permissions are the union of the roles of every
group they belong to, whether they were added by hand or arrived in the identity provider's groups claim.

A group's `external_name` is the name the identity provider uses for it in the groups claim; a person is a member when the claim lists it
or when they were added by subject (their sign-in email or id). Roles are those single sign-on may give (not `channel`)."""
from __future__ import annotations

import asyncio
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

GRANTABLE = ("admin", "release_manager", "developer", "reviewer", "auditor", "viewer")
NAME_RE = re.compile(r"^[A-Za-z0-9 _.@-]{1,80}$")
SUBJECT_RE = re.compile(r"^[^\s]{1,200}$")


@dataclass
class Group:
    id: str
    name: str
    roles: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)  # subjects added by hand (email or id, lower case)
    external_name: str | None = None  # the identity provider's name for this group
    description: str = ""
    created_by: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "roles": self.roles, "members": self.members, "externalName": self.external_name,
                "description": self.description, "createdBy": self.created_by, "createdAt": self.created_at}


class GroupRepo(Protocol):
    async def list(self) -> list[Group]: ...
    async def get(self, group_id: str) -> Group | None: ...
    async def save(self, group: Group) -> None: ...
    async def delete(self, group_id: str) -> bool: ...


class InMemoryGroups:
    def __init__(self) -> None:
        self._items: dict[str, Group] = {}

    async def list(self) -> list[Group]:
        return sorted(self._items.values(), key=lambda g: g.name.lower())

    async def get(self, group_id: str) -> Group | None:
        g = self._items.get(group_id)
        return Group(**{**g.__dict__, "roles": list(g.roles), "members": list(g.members)}) if g else None

    async def save(self, group: Group) -> None:
        self._items[group.id] = Group(**{**group.__dict__, "roles": list(group.roles), "members": list(group.members)})

    async def delete(self, group_id: str) -> bool:
        return self._items.pop(group_id, None) is not None


class GroupError(ValueError):
    pass


class GroupService:
    def __init__(self, repo: GroupRepo | None = None) -> None:
        self.repo = repo or InMemoryGroups()
        self._lock = asyncio.Lock()

    @staticmethod
    def _check_roles(roles: list[str]) -> list[str]:
        bad = [r for r in roles if r not in GRANTABLE]
        if bad or len(set(roles)) != len(roles):
            raise GroupError(f"roles must be different values from: {', '.join(GRANTABLE)}")
        return list(roles)

    async def create(self, name: str, roles: list[str], by: str, external_name: str | None = None, description: str = "") -> Group:
        if not NAME_RE.fullmatch(name) or name != name.strip():
            raise GroupError("Group names use letters, digits, spaces and . _ @ - (1 to 80 characters)")
        async with self._lock:
            if any(g.name.lower() == name.lower() for g in await self.repo.list()):
                raise GroupError(f"A group named '{name}' already exists")
            if external_name and any(g.external_name == external_name for g in await self.repo.list()):
                raise GroupError(f"Another group already maps the identity provider group '{external_name}'")
            g = Group(secrets.token_hex(4), name, self._check_roles(roles), [], external_name or None, description[:500], by)
            await self.repo.save(g)
            return g

    async def update(self, group_id: str, roles: list[str] | None = None, external_name: str | None = None, description: str | None = None,
                     clear_external: bool = False) -> Group:
        async with self._lock:
            g = await self.repo.get(group_id)
            if g is None:
                raise KeyError(group_id)
            if roles is not None:
                g.roles = self._check_roles(roles)
            if clear_external:
                g.external_name = None
            elif external_name is not None:
                if any(o.external_name == external_name and o.id != g.id for o in await self.repo.list()):
                    raise GroupError(f"Another group already maps the identity provider group '{external_name}'")
                g.external_name = external_name or None
            if description is not None:
                g.description = description[:500]
            await self.repo.save(g)
            return g

    async def add_member(self, group_id: str, subject: str) -> Group:
        subject = subject.strip().lower()
        if not SUBJECT_RE.fullmatch(subject):
            raise GroupError("A member is an email address or an identity provider id, without spaces")
        async with self._lock:
            g = await self.repo.get(group_id)
            if g is None:
                raise KeyError(group_id)
            if subject not in g.members:
                if len(g.members) >= 5000:
                    raise GroupError("A group holds at most 5000 hand-added members; map the identity provider group instead")
                g.members.append(subject)
                await self.repo.save(g)
            return g

    async def remove_member(self, group_id: str, subject: str) -> Group:
        async with self._lock:
            g = await self.repo.get(group_id)
            if g is None:
                raise KeyError(group_id)
            g.members = [m for m in g.members if m != subject.strip().lower()]
            await self.repo.save(g)
            return g

    async def delete(self, group_id: str) -> bool:
        return await self.repo.delete(group_id)

    async def effective_roles(self, subjects: list[str], idp_groups: list[str]) -> tuple[list[str], list[str]]:
        """(roles, names of the groups that gave them). The roles are the union over every group the person is in."""
        subs = {s.strip().lower() for s in subjects if s}
        roles: set[str] = set()
        names: list[str] = []
        for g in await self.repo.list():
            if (g.external_name and g.external_name in idp_groups) or subs & set(g.members):
                roles.update(g.roles)
                names.append(g.name)
        return [r for r in GRANTABLE if r in roles], names
