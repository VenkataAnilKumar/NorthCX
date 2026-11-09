"""Which team answered: when a person resolves a hand-off or decides an approval, the team they were signed in under (their first group, alphabetically) is written down
here, so Performance can show a team's figures. Hand-offs and approvals themselves are not changed. Someone in no group counts under "(no team)"."""
from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any, Protocol

from .tenancy import current_tenant

NO_TEAM = "(no team)"
VIEWER_TEAM: ContextVar[str] = ContextVar("northcx_viewer_team", default=NO_TEAM)     # the team of whoever the current request is for; set when a route starts


def current_team() -> str:
    return VIEWER_TEAM.get()


def team_visible(owner: str, owner_team: str, visibility: str, who: str, admin: bool) -> bool:
    """Private: its owner (and an administrator). Shared: everyone who uses the Workspace. Team: people signed in under the same team as its owner, when it has one."""
    if owner == who or admin or visibility == "shared":
        return True
    return visibility == "team" and bool(owner_team) and owner_team != NO_TEAM and owner_team == current_team()


def require_team() -> str:
    """The team to record on something shared with a team; refused for someone in no team, because nobody would be able to see it."""
    return current_team()


def team_of(identity: Any) -> str:
    groups = getattr(identity, "groups", ()) or ()
    return sorted(groups)[0][:80] if groups else NO_TEAM


async def note_team(runtime: Any, request: Any, kind: str, item_id: str) -> None:
    """Write down which team answered. It never fails the decision it is recorded for."""
    import logging
    try:
        if getattr(runtime, "decision_teams", None) is None:
            runtime.decision_teams = InMemoryTeams()
        await runtime.decision_teams.record(kind, item_id, team_of(request.state.identity))
    except Exception:  # noqa: BLE001
        logging.getLogger("northcx.teams").exception("could not record the team")


class TeamRepo(Protocol):
    async def record(self, kind: str, item_id: str, team: str) -> None: ...
    async def for_ids(self, kind: str, ids: list[str]) -> dict[str, str]: ...


class InMemoryTeams:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], tuple[str, float]] = {}

    async def record(self, kind: str, item_id: str, team: str) -> None:
        self._items[(current_tenant(), kind, item_id)] = (team, time.time())

    async def for_ids(self, kind: str, ids: list[str]) -> dict[str, str]:
        t = current_tenant()
        return {i: self._items[(t, kind, i)][0] for i in ids if (t, kind, i) in self._items}
