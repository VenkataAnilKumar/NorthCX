"""SCIM 2.0 provisioning (WP3.3, RFC 7643 and 7644): an identity provider creates, updates and deactivates people and keeps group
membership in step. Deactivating a person ends their access in the same request: their sign-in sessions are revoked and they cannot sign in again.

What SCIM may and may not do: it manages who exists, whether they are active, and which groups they are in. It never sets roles; roles are bound
to groups by an administrator (Groups), so a compromised provisioning token cannot make anyone an administrator."""
from __future__ import annotations

import asyncio
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
EMAIL_RE = re.compile(r"^[^\s@]{1,100}@[^\s@]{1,100}$")


class ScimError(Exception):
    def __init__(self, status: int, detail: str, scim_type: str | None = None):
        super().__init__(detail)
        self.status, self.detail, self.scim_type = status, detail, scim_type

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schemas": [ERROR_SCHEMA], "status": str(self.status), "detail": self.detail}
        if self.scim_type:
            out["scimType"] = self.scim_type
        return out


@dataclass
class ScimUser:
    id: str
    user_name: str  # the person's sign-in email, lower case
    display_name: str = ""
    external_id: str | None = None
    active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class ScimUserRepo(Protocol):
    async def list(self) -> list[ScimUser]: ...
    async def get(self, user_id: str) -> ScimUser | None: ...
    async def by_name(self, user_name: str) -> ScimUser | None: ...
    async def save(self, u: ScimUser) -> None: ...
    async def delete(self, user_id: str) -> bool: ...


class InMemoryScimUsers:
    def __init__(self) -> None:
        self._items: dict[str, ScimUser] = {}

    async def list(self) -> list[ScimUser]:
        return sorted(self._items.values(), key=lambda u: u.created_at)

    async def get(self, user_id: str) -> ScimUser | None:
        u = self._items.get(user_id)
        return ScimUser(**u.__dict__) if u else None

    async def by_name(self, user_name: str) -> ScimUser | None:
        return next((ScimUser(**u.__dict__) for u in self._items.values() if u.user_name == user_name), None)

    async def save(self, u: ScimUser) -> None:
        self._items[u.id] = ScimUser(**u.__dict__)

    async def delete(self, user_id: str) -> bool:
        return self._items.pop(user_id, None) is not None


def truthy(v: Any) -> bool:
    """Identity providers send booleans as JSON booleans or as the strings 'True' and 'False'."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    raise ScimError(400, "active must be true or false", "invalidValue")


class ScimService:
    def __init__(self, users: ScimUserRepo | None, groups: Any, access: Any, base_url: str = "", require_provisioned: bool = False):
        self.users = users or InMemoryScimUsers()
        self.groups, self.access, self.base_url, self.require_provisioned = groups, access, base_url.rstrip("/"), require_provisioned
        self._lock = asyncio.Lock()
        self.token_hash = ""  # SHA-256 of the provisioning bearer token; set by the server

    # ---- sign-in gate ----
    async def may_sign_in(self, email: str) -> bool:
        u = await self.users.by_name(email.strip().lower())
        if u is None:
            return not self.require_provisioned
        return u.active

    # ---- representations ----
    def user_json(self, u: ScimUser, group_ids: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return {"schemas": [USER_SCHEMA], "id": u.id, "externalId": u.external_id, "userName": u.user_name, "displayName": u.display_name or u.user_name,
                "active": u.active, "emails": [{"value": u.user_name, "primary": True}], "groups": group_ids or [],
                "meta": {"resourceType": "User", "created": _iso(u.created_at), "lastModified": _iso(u.updated_at), "location": f"{self.base_url}/Users/{u.id}"}}

    async def group_refs(self, u: ScimUser) -> list[dict[str, str]]:
        return [{"value": g.id, "display": g.name} for g in await self.groups.repo.list() if u.user_name in g.members]

    async def group_json(self, g: Any) -> dict[str, Any]:
        by_name = {u.user_name: u for u in await self.users.list()}
        members = [{"value": by_name[m].id, "display": by_name[m].display_name or m} for m in g.members if m in by_name]
        return {"schemas": [GROUP_SCHEMA], "id": g.id, "displayName": g.name, "members": members,
                "meta": {"resourceType": "Group", "created": _iso(g.created_at), "location": f"{self.base_url}/Groups/{g.id}"}}

    # ---- users ----
    @staticmethod
    def _name_from(body: dict[str, Any]) -> str:
        name = str(body.get("userName", "")).strip().lower()
        if not EMAIL_RE.fullmatch(name):
            raise ScimError(400, "userName must be the person's email address", "invalidValue")
        return name

    async def create_user(self, body: dict[str, Any], by: str) -> ScimUser:
        name = self._name_from(body)
        async with self._lock:
            if await self.users.by_name(name):
                raise ScimError(409, f"A user named '{name}' already exists", "uniqueness")
            u = ScimUser(secrets.token_hex(8), name, str(body.get("displayName") or "")[:200], (str(body["externalId"])[:200] if body.get("externalId") else None),
                         truthy(body.get("active", True)))
            await self.users.save(u)
        return u

    async def replace_user(self, user_id: str, body: dict[str, Any]) -> tuple[ScimUser, bool]:
        """(user, whether this made them inactive)."""
        async with self._lock:
            u = await self.users.get(user_id)
            if u is None:
                raise ScimError(404, "User not found")
            name = self._name_from(body)
            other = await self.users.by_name(name)
            if other and other.id != u.id:
                raise ScimError(409, f"A user named '{name}' already exists", "uniqueness")
            was = u.active
            u.user_name, u.display_name = name, str(body.get("displayName") or "")[:200]
            u.external_id = str(body["externalId"])[:200] if body.get("externalId") else None
            u.active, u.updated_at = truthy(body.get("active", True)), time.time()
            await self.users.save(u)
        return u, was and not u.active

    async def patch_user(self, user_id: str, body: dict[str, Any]) -> tuple[ScimUser, bool]:
        ops = _ops(body)
        async with self._lock:
            u = await self.users.get(user_id)
            if u is None:
                raise ScimError(404, "User not found")
            was = u.active
            for op in ops:
                kind, path, value = op["op"].lower(), (op.get("path") or "").lower(), op.get("value")
                if kind not in ("add", "replace"):
                    raise ScimError(400, f"Operation '{op['op']}' is not supported on users", "invalidValue")
                pairs = value.items() if not path and isinstance(value, dict) else [(path, value)]
                for k, v in pairs:
                    k = str(k).lower()
                    if k == "active":
                        u.active = truthy(v)
                    elif k == "displayname":
                        u.display_name = str(v or "")[:200]
                    elif k == "externalid":
                        u.external_id = str(v)[:200] if v else None
                    elif k == "username":
                        n = self._name_from({"userName": v})
                        other = await self.users.by_name(n)
                        if other and other.id != u.id:
                            raise ScimError(409, f"A user named '{n}' already exists", "uniqueness")
                        u.user_name = n
                    # other attributes (name, phone numbers, ...) are accepted and ignored: NorthCX keeps only what it uses
            u.updated_at = time.time()
            await self.users.save(u)
        return u, was and not u.active

    async def delete_user(self, user_id: str) -> ScimUser:
        async with self._lock:
            u = await self.users.get(user_id)
            if u is None:
                raise ScimError(404, "User not found")
            await self.users.delete(user_id)
        for g in await self.groups.repo.list():
            if u.user_name in g.members:
                await self.groups.remove_member(g.id, u.user_name)
        return u

    async def end_access(self, u: ScimUser) -> int:
        """Revoke every sign-in session the person has. Returns how many."""
        return await self.access.revoke_sessions_for(u.user_name, "scim")

    async def list_users(self, flt: str | None, start: int, count: int) -> tuple[list[ScimUser], int]:
        items = await self.users.list()
        if flt:
            m = re.fullmatch(r'\s*(userName|externalId|displayName)\s+eq\s+"([^"]*)"\s*', flt, re.I)
            if not m:
                raise ScimError(400, 'Only filters of the form: userName eq "value" (or externalId, displayName) are supported', "invalidFilter")
            attr, val = m.group(1).lower(), m.group(2)
            key = {"username": lambda u: u.user_name, "externalid": lambda u: u.external_id or "", "displayname": lambda u: u.display_name}[attr]
            items = [u for u in items if key(u).lower() == val.lower()]
        return items[max(0, start - 1): max(0, start - 1) + count], len(items)

    # ---- groups ----
    async def _subjects(self, members: Any) -> list[str]:
        out: list[str] = []
        by_id = {u.id: u for u in await self.users.list()}
        for m in members or []:
            if not isinstance(m, dict) or m.get("value") not in by_id:
                raise ScimError(400, "A member must be the id of a user that exists", "invalidValue")
            out.append(by_id[m["value"]].user_name)
        return out

    async def create_group(self, body: dict[str, Any], by: str) -> Any:
        from northcx.groups import GroupError
        try:
            g = await self.groups.create(str(body.get("displayName", "")).strip(), [], by, external_name=str(body.get("externalId") or body.get("displayName") or "") or None)
            for s in await self._subjects(body.get("members")):
                g = await self.groups.add_member(g.id, s)
        except GroupError as e:
            raise ScimError(409 if "already" in str(e) else 400, str(e), "uniqueness" if "already" in str(e) else "invalidValue") from e
        return g

    async def patch_group(self, group_id: str, body: dict[str, Any]) -> Any:
        from northcx.groups import GroupError
        if await self.groups.repo.get(group_id) is None:
            raise ScimError(404, "Group not found")
        try:
            for op in _ops(body):
                kind, path, value = op["op"].lower(), (op.get("path") or ""), op.get("value")
                if path.lower() == "displayname" and kind in ("add", "replace"):
                    raise ScimError(400, "Rename a group in NorthCX; SCIM manages its members", "mutability")
                if path.lower() == "members" or path == "":
                    if kind in ("add",):
                        for s in await self._subjects(value if isinstance(value, list) else (value or {}).get("members")):
                            await self.groups.add_member(group_id, s)
                    elif kind == "replace":
                        cur = await self.groups.repo.get(group_id)
                        want = await self._subjects(value if isinstance(value, list) else (value or {}).get("members"))
                        for s in list(cur.members):
                            if s not in want:
                                await self.groups.remove_member(group_id, s)
                        for s in want:
                            await self.groups.add_member(group_id, s)
                    elif kind == "remove":
                        if value:
                            for s in await self._subjects(value):
                                await self.groups.remove_member(group_id, s)
                        else:
                            for s in list((await self.groups.repo.get(group_id)).members):
                                await self.groups.remove_member(group_id, s)
                elif (m := re.fullmatch(r'members\[value eq "([^"]+)"\]', path, re.I)) and kind == "remove":
                    for s in await self._subjects([{"value": m.group(1)}]):
                        await self.groups.remove_member(group_id, s)
                else:
                    raise ScimError(400, f"Cannot {kind} '{path or 'this attribute'}' on a group", "invalidPath")
        except GroupError as e:
            raise ScimError(400, str(e), "invalidValue") from e
        return await self.groups.repo.get(group_id)


def _ops(body: dict[str, Any]) -> list[dict[str, Any]]:
    if PATCH_SCHEMA not in (body.get("schemas") or []) or not isinstance(body.get("Operations"), list) or not body["Operations"]:
        raise ScimError(400, "A patch needs the PatchOp schema and a non-empty Operations list", "invalidSyntax")
    for o in body["Operations"]:
        if not isinstance(o, dict) or not isinstance(o.get("op"), str):
            raise ScimError(400, "Each operation needs an op", "invalidSyntax")
    return body["Operations"]


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
