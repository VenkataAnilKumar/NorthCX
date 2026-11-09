"""Which team answered: when a person resolves a hand-off or decides an approval, the team they were signed in under (their first group, alphabetically) is written down
here, so Performance can show a team's figures. Hand-offs and approvals themselves are not changed. Someone in no group counts under "(no team)"."""
from __future__ import annotations

import time
from typing import Any, Protocol

from .tenancy import current_tenant

NO_TEAM = "(no team)"


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
