"""Organization policies (E16): rules that apply to every customer agent, managed like agent versions.

A policy is a ready-made policy from the library (`northcx/policies.py`) with a configuration and its own allow and block cases. Lifecycle:
`draft -> proposed -> active`, or `rejected`. It cannot be proposed until its cases pass (and at least one allows and one blocks), and a different
person with the release permission must approve it; the cases run again at approval. Changing an active policy makes a new draft version, and the
active one stays in force until the new one is approved. An active policy is **locked**: it is applied when each conversation is run, to every
customer agent it covers, so no agent definition can leave it out or weaken it. Retiring one is a deliberate, audited act."""
from __future__ import annotations

import asyncio
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .guardrails import Guardrail, GuardrailContext
from .policies import FACTORIES

STATUSES = ("draft", "proposed", "active", "rejected", "retired", "superseded")
NAME_RE = re.compile(r"^[A-Za-z0-9 _.,'-]{3,80}$")
CACHE_SECONDS = 5.0


class OrgPolicyError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class OrgPolicy:
    id: str
    version: int
    name: str
    policy: str                     # a name from the policy library
    config: dict[str, Any]
    cases: list[dict[str, Any]]     # {"on": "tool"|"reply", "input": text or {"tool": name, "input": {...}}, "expected": "allowed"|"blocked"}
    applies_to: list[str] | None = None   # None: every customer agent; else these agent ids
    status: str = "draft"
    proof: dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    proposed_by: str | None = None
    decided_by: str | None = None
    decision_note: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def locked(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version, "name": self.name, "policy": self.policy, "config": self.config, "cases": self.cases, "appliesTo": self.applies_to,
                "status": self.status, "locked": self.locked, "proof": self.proof, "createdBy": self.created_by, "proposedBy": self.proposed_by, "decidedBy": self.decided_by,
                "decisionNote": self.decision_note, "createdAt": self.created_at, "updatedAt": self.updated_at}


class OrgPolicyRepo(Protocol):
    async def save(self, p: OrgPolicy) -> None: ...
    async def get(self, policy_id: str, version: int | None = None) -> OrgPolicy | None: ...   # latest version when None
    async def versions(self, policy_id: str) -> list[OrgPolicy]: ...
    async def list(self) -> list[OrgPolicy]: ...                                                # the latest version of each policy
    async def active(self) -> list[OrgPolicy]: ...


class InMemoryOrgPolicies:
    def __init__(self) -> None:
        self._items: dict[tuple[str, int], OrgPolicy] = {}

    async def save(self, p: OrgPolicy) -> None:
        p.updated_at = time.time()
        self._items[(p.id, p.version)] = p

    async def versions(self, policy_id: str) -> list[OrgPolicy]:
        return sorted((p for (i, _), p in self._items.items() if i == policy_id), key=lambda p: -p.version)

    async def get(self, policy_id: str, version: int | None = None) -> OrgPolicy | None:
        vs = await self.versions(policy_id)
        return next((p for p in vs if version is None or p.version == version), None)

    async def list(self) -> list[OrgPolicy]:
        ids = {i for i, _ in self._items}
        return sorted([(await self.versions(i))[0] for i in ids], key=lambda p: p.name.lower())

    async def active(self) -> list[OrgPolicy]:
        return [p for p in self._items.values() if p.status == "active"]


def build_guardrail(policy: str, config: dict[str, Any]) -> Guardrail:
    if policy not in FACTORIES:
        raise OrgPolicyError(400, f"Unknown policy '{policy}' (policies: {', '.join(sorted(FACTORIES))})")
    try:
        return FACTORIES[policy](config, None)
    except (TypeError, ValueError) as e:
        raise OrgPolicyError(400, f"Invalid setting for '{policy}': {e}") from e


async def prove(policy: str, config: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the cases against the policy built with this configuration. Passing needs at least one allow case, one block case, and every case to come out as expected."""
    g = build_guardrail(policy, config)
    results: list[dict[str, Any]] = []
    for c in cases:
        try:
            on, expected, inp = c["on"], c["expected"], c["input"]
            if on not in ("tool", "reply") or expected not in ("allowed", "blocked"):
                raise KeyError
            ctx = GuardrailContext("proof", [])
            if on == "tool":
                v = await g.check_tool_call(inp["tool"], inp.get("input", {}), ctx)
            else:
                v = await g.check_reply(str(inp), ctx)
            got = "allowed" if v.allow else "blocked"
            results.append({"on": on, "input": inp, "expected": expected, "got": got, "ok": got == expected, "reason": None if v.allow else v.reason})
        except (KeyError, TypeError):
            results.append({"on": c.get("on"), "input": c.get("input"), "expected": c.get("expected"), "got": None, "ok": False, "reason": "A case needs on (tool or reply), input and expected (allowed or blocked)"})
    kinds = {r["expected"] for r in results}
    problems = []
    if "allowed" not in kinds or "blocked" not in kinds:
        problems.append("Add at least one case that is allowed and one that is blocked")
    problems += [f"Case {i + 1} did not come out as expected" for i, r in enumerate(results) if not r["ok"]]
    return {"passed": not problems, "problems": problems, "results": results, "ranAt": time.time()}


class OrgPolicyService:
    def __init__(self, repo: OrgPolicyRepo | None = None):
        self.repo = repo or InMemoryOrgPolicies()
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, list[tuple[OrgPolicy, Guardrail]]]] = {}

    def _invalidate(self) -> None:
        self._cache.clear()

    async def create(self, name: str, policy: str, config: dict[str, Any], cases: list[dict[str, Any]], applies_to: list[str] | None, by: str) -> OrgPolicy:
        if not NAME_RE.fullmatch(name or ""):
            raise OrgPolicyError(400, "A policy name is 3 to 80 letters, digits, spaces and . , ' _ -")
        if any(p.name.lower() == name.lower() and p.status not in ("retired", "rejected") for p in await self.repo.list()):
            raise OrgPolicyError(409, f"A policy named '{name}' already exists")
        p = OrgPolicy(secrets.token_hex(4), 1, name, policy, config, cases, applies_to or None, created_by=by)
        p.proof = await prove(policy, config, cases)
        await self.repo.save(p)
        return p

    async def revise(self, policy_id: str, config: dict[str, Any] | None, cases: list[dict[str, Any]] | None, applies_to: list[str] | None, by: str) -> OrgPolicy:
        """A new draft version. The version in force stays in force until the new one is approved."""
        cur = await self.repo.get(policy_id)
        if cur is None:
            raise OrgPolicyError(404, "Unknown policy")
        if cur.status in ("draft", "proposed"):
            raise OrgPolicyError(409, f"Version {cur.version} is still {cur.status}; finish or reject it first")
        n = OrgPolicy(policy_id, cur.version + 1, cur.name, cur.policy, config if config is not None else cur.config, cases if cases is not None else cur.cases,
                      applies_to if applies_to is not None else cur.applies_to, created_by=by)
        n.proof = await prove(n.policy, n.config, n.cases)
        await self.repo.save(n)
        return n

    async def edit_draft(self, policy_id: str, config: dict[str, Any] | None, cases: list[dict[str, Any]] | None, applies_to: list[str] | None) -> OrgPolicy:
        p = await self.repo.get(policy_id)
        if p is None:
            raise OrgPolicyError(404, "Unknown policy")
        if p.status != "draft":
            raise OrgPolicyError(409, f"Only a draft can be edited; this version is {p.status}")
        new_config, new_cases = (config if config is not None else p.config), (cases if cases is not None else p.cases)
        proof = await prove(p.policy, new_config, new_cases)            # refuse a bad setting before changing anything
        p.config, p.cases, p.proof = new_config, new_cases, proof
        if applies_to is not None:
            p.applies_to = applies_to or None
        await self.repo.save(p)
        return p

    async def propose(self, policy_id: str, by: str) -> OrgPolicy:
        p = await self.repo.get(policy_id)
        if p is None:
            raise OrgPolicyError(404, "Unknown policy")
        if p.status != "draft":
            raise OrgPolicyError(409, f"Only a draft can be proposed; this version is {p.status}")
        p.proof = await prove(p.policy, p.config, p.cases)
        if not p.proof["passed"]:
            raise OrgPolicyError(409, "It cannot be proposed until its cases pass: " + "; ".join(p.proof["problems"]))
        p.status, p.proposed_by = "proposed", by
        await self.repo.save(p)
        return p

    async def decide(self, policy_id: str, approve: bool, by: str, note: str | None) -> OrgPolicy:
        async with self._lock:
            p = await self.repo.get(policy_id)
            if p is None:
                raise OrgPolicyError(404, "Unknown policy")
            if p.status != "proposed":
                raise OrgPolicyError(409, f"This version is {p.status}; only a proposed one can be decided")
            if approve and by == p.proposed_by:
                raise OrgPolicyError(403, "A policy needs a second person: the person who proposed it cannot approve it")
            if approve:
                p.proof = await prove(p.policy, p.config, p.cases)      # judged again now, on the state at the moment of approval
                if not p.proof["passed"]:
                    raise OrgPolicyError(409, "Its cases no longer pass: " + "; ".join(p.proof["problems"]))
                for old in await self.repo.versions(policy_id):
                    if old.status == "active":
                        old.status = "superseded"
                        await self.repo.save(old)
            p.status, p.decided_by, p.decision_note = ("active" if approve else "rejected"), by, note
            await self.repo.save(p)
            self._invalidate()
            return p

    async def retire(self, policy_id: str, by: str, note: str | None) -> OrgPolicy:
        p = next((v for v in await self.repo.versions(policy_id) if v.status == "active"), None)
        if p is None:
            raise OrgPolicyError(404, "That policy is not active")
        p.status, p.decided_by, p.decision_note = "retired", by, note or "retired"
        await self.repo.save(p)
        self._invalidate()
        return p

    async def guardrails_for(self, agent_id: str) -> list[Guardrail]:
        """The active, locked policies that cover this customer agent, built and ready to run (cached for a few seconds per tenant)."""
        from .tenancy import current_tenant
        tenant = current_tenant()
        hit = self._cache.get(tenant)
        if hit is None or time.monotonic() - hit[0] >= CACHE_SECONDS:
            built: list[tuple[OrgPolicy, Guardrail]] = []
            try:
                for p in await self.repo.active():
                    g = build_guardrail(p.policy, p.config)
                    g.name = f"org:{p.name}"
                    built.append((p, g))
            except Exception:  # noqa: BLE001 - never drop the policies already in force because one failed to build
                if hit is not None:
                    return [g for p, g in hit[1] if p.applies_to is None or agent_id in p.applies_to]
                raise
            self._cache[tenant] = hit = (time.monotonic(), built)
        return [g for p, g in hit[1] if p.applies_to is None or agent_id in p.applies_to]
