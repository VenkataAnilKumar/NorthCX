"""Choosing a model per request (WP1.9, WP1.10): hard data constraints first, then the operator's ordered rules, then the fallback chain
restricted to what is allowed. The decision, the rule that made it and every model skipped (with the reason) go into the trace.

Rules are data, not code (docs/04-ai-architecture/NorthCX_Hybrid-Model-Selection.md); the file is `NORTHCX_ROUTING_RULES_FILE`:

```yaml
policy:
  sensitive: [local, private-cloud]          # tiers a sensitive conversation may use (public-cloud is never listed by default)
  normal: [local, private-cloud, public-cloud]
  publicCloudAllowedAgents: [billing]        # an administrator's explicit, named exception (every use is recorded)
sensitiveTopics: [payment, health]           # replaces the default words that mark a conversation sensitive (case-insensitive, start of a word)
qualification:
  required: true                             # a model serves an agent's customers only after passing that agent's scenarios (live run, recorded)
  exempt: ["anthropic:claude-sonnet-5-5"]    # models trusted without a recorded run
rules:                                       # first match wins
  - name: simple questions stay local
    when: {sensitive: false, effect: read, channel: web, agent: support}
    use: {tier: local}                       # or: {model: local:llama3.1:8b}
```"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from northcx.providers.config import WHERE
from northcx.providers.registry import ProviderRegistry, UnknownModel
from northcx.secrets import ConfigError

DEFAULT_TOPICS = ("account", "payment", "card", "invoice", "bank", "medical", "health", "diagnosis", "prescription")  # decision 164; to validate on a pilot
_WHEN = {"sensitive", "channel", "agent", "effect"}


class NoEligibleModel(RuntimeError):
    """No model is allowed for this conversation. The conversation goes to a person, never to a forbidden tier."""


@dataclass
class Rule:
    name: str
    when: dict[str, Any]
    tier: str | None = None
    model: str | None = None

    def matches(self, ctx: dict[str, Any]) -> bool:
        return all(ctx.get(k) == v for k, v in self.when.items())


@dataclass
class Policy:
    sensitive: tuple[str, ...] = ("local", "private-cloud")
    normal: tuple[str, ...] = WHERE
    public_agents: frozenset[str] = frozenset()


@dataclass
class Decision:
    model: str
    tier: str
    rule: str | None
    sensitive: bool
    skipped: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"model": self.model, "tier": self.tier, "rule": self.rule, "sensitive": self.sensitive, "skipped": self.skipped}


class Selector:
    def __init__(self, registry: ProviderRegistry, tiers: dict[str, str], policy: Policy | None = None, rules: list[Rule] | None = None,
                 topics: tuple[str, ...] = DEFAULT_TOPICS, qualification_required: bool = False, exempt: tuple[str, ...] = ()):
        self.registry, self.tiers, self.policy, self.rules = registry, tiers, policy or Policy(), list(rules or [])
        self.topics = tuple(t.lower() for t in topics)
        self._topic_rx = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in self.topics) + r")", re.I) if self.topics else None  # a word starting with a topic: "accounts", not "accountant"-style false hits mid-word
        self.qualification_required = qualification_required
        self.exempt = frozenset(registry.qualify(m) or m for m in exempt)
        self.qualifier: Any = None  # northcx.providers.qualification.Qualifications; set by the server

    def tier_of(self, model: str | None) -> str:
        provider, _ = self.registry.resolve(model)
        return self.tiers.get(provider.name, "public-cloud")  # a provider with no declared tier is treated as the least private

    def is_sensitive_text(self, text: str) -> bool:
        return bool(self._topic_rx and self._topic_rx.search(text))

    def allowed_tiers(self, ctx: dict[str, Any]) -> tuple[str, ...]:
        if not ctx.get("sensitive", True):  # unknown context is treated as sensitive: fail closed
            return self.policy.normal
        tiers = self.policy.sensitive
        if ctx.get("agent") in self.policy.public_agents:
            tiers = tuple(dict.fromkeys(tiers + ("public-cloud",)))
        return tiers

    def _preferred(self, ctx: dict[str, Any]) -> tuple[str | None, Rule | None]:
        for r in self.rules:
            if r.matches(ctx):
                if r.model:
                    return r.model, r
                for name in self.registry.names:  # the first registered provider in that tier
                    if self.tiers.get(name, "public-cloud") == r.tier:
                        return self.registry.qualify(f"{name}:{self.registry.get(name).default_model}") if self.registry.get(name).default_model else None, r
        return None, None

    async def chain(self, requested: str | None, fallbacks: list[str], ctx: dict[str, Any]) -> tuple[list[str], Decision | None]:
        """The models to try, in order: the rule's choice (else the requested one), then the fallbacks, all inside the allowed tiers."""
        allowed = self.allowed_tiers(ctx)
        preferred, rule = self._preferred(ctx)
        # The eligible set is every registered model the constraints allow: the named ones come first, then each provider's own default as a last resort,
        # so a sensitive conversation whose default model is forbidden still finds an allowed one instead of going to a person for no reason.
        rest = [f"{n}:{self_default}" for n in self.registry.names if (self_default := self.registry.get(n).default_model)]
        candidates = [m for m in ([preferred] if preferred else []) + ([requested] if requested else [None]) + fallbacks + rest]
        out: list[str] = []
        skipped: list[dict[str, str]] = []
        for m in candidates:
            try:
                q = self.registry.qualify(m)
            except UnknownModel as e:
                skipped.append({"model": str(m), "reason": str(e)})
                continue
            if q is None or q in out or any(s["model"] == q for s in skipped):
                continue
            tier = self.tier_of(q)
            if tier not in allowed:
                skipped.append({"model": q, "reason": f"{tier} is not allowed for {'a sensitive' if ctx.get('sensitive', True) else 'this'} conversation"})
                continue
            if self.qualification_required and ctx.get("agent") and not ctx.get("evaluation") and q not in self.exempt:  # evaluation runs are how a model earns its qualification
                if self.qualifier is None or not await self.qualifier.is_qualified(ctx["agent"], q, ctx.get("agent_digest")):
                    skipped.append({"model": q, "reason": f"not qualified for agent '{ctx['agent']}' (it has not passed this agent's scenarios for its current definition)"})
                    continue
            caps = self.registry.capabilities_for(q)
            if ctx.get("needs_tools") and not caps.tools:
                skipped.append({"model": q, "reason": "cannot call tools"})
                continue
            out.append(q)
        if not out:
            raise NoEligibleModel("no model is allowed for this conversation: " + "; ".join(f"{s['model']}: {s['reason']}" for s in skipped))
        d = Decision(out[0], self.tier_of(out[0]), rule.name if rule and out[0] == self.registry.qualify(preferred) else None, bool(ctx.get("sensitive", True)), skipped)
        return out, d


def parse_routing(text: str, registry: ProviderRegistry, tiers: dict[str, str]) -> Selector:
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"routing rules file is not valid YAML: {e}") from e
    if not isinstance(doc, dict):
        raise ConfigError("routing rules file must be a mapping")
    unknown = set(doc) - {"policy", "sensitiveTopics", "rules", "qualification"}
    if unknown:
        raise ConfigError(f"routing rules: unknown setting(s) {sorted(unknown)}")
    pol = doc.get("policy") or {}
    def tier_list(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        v = pol.get(key, list(default))
        if not isinstance(v, list) or any(t not in WHERE for t in v):
            raise ConfigError(f"policy.{key} must be a list of {', '.join(WHERE)}")
        return tuple(v)
    policy = Policy(tier_list("sensitive", Policy().sensitive), tier_list("normal", Policy().normal), frozenset(map(str, pol.get("publicCloudAllowedAgents") or [])))
    topics = doc.get("sensitiveTopics", list(DEFAULT_TOPICS))
    if not isinstance(topics, list) or not all(isinstance(t, str) and t.strip() for t in topics):
        raise ConfigError("sensitiveTopics must be a list of words")
    rules: list[Rule] = []
    for i, r in enumerate(doc.get("rules") or []):
        if not isinstance(r, dict) or not r.get("name") or not isinstance(r.get("use"), dict):
            raise ConfigError(f"rules[{i}] needs a name and a use")
        when = r.get("when") or {}
        if set(when) - _WHEN:
            raise ConfigError(f"rules[{i}] ({r['name']}): unknown condition(s) {sorted(set(when) - _WHEN)}")
        use = r["use"]
        if bool(use.get("tier")) == bool(use.get("model")) or set(use) - {"tier", "model"}:
            raise ConfigError(f"rules[{i}] ({r['name']}): use needs exactly one of tier or model")
        if use.get("tier") and use["tier"] not in WHERE:
            raise ConfigError(f"rules[{i}] ({r['name']}): tier must be one of {', '.join(WHERE)}")
        if use.get("model"):
            try:
                registry.qualify(str(use["model"]))
            except UnknownModel as e:
                raise ConfigError(f"rules[{i}] ({r['name']}): {e}") from e
        rules.append(Rule(str(r["name"]), dict(when), use.get("tier"), use.get("model")))
    qual = doc.get("qualification") or {}
    if not isinstance(qual, dict) or set(qual) - {"required", "exempt"}:
        raise ConfigError("qualification takes only required and exempt")
    exempt = qual.get("exempt") or []
    if not isinstance(exempt, list) or not all(isinstance(m, str) for m in exempt):
        raise ConfigError("qualification.exempt must be a list of model names")
    return Selector(registry, tiers, policy, rules, tuple(topics), bool(qual.get("required", False)), tuple(exempt))
