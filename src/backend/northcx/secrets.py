"""Secrets: read from the environment or from files, handed to tools on request, and scrubbed from everything we keep.

Tool credentials are configured as `NORTHCX_SECRET_<NAME>` (or `NORTHCX_SECRET_<NAME>_FILE` pointing at a mounted file,
the form Docker and Kubernetes secrets use). A tool asks for one with `ctx.secret("name")`; it never appears in prompts,
traces, saved history, approvals, handoff packages or replies, because every one of those is passed through `redact`."""
from __future__ import annotations

import os
import re
from typing import Any, Mapping

MIN_SECRET_LENGTH = 8  # shorter values cannot be scrubbed safely: they would match ordinary text


class ConfigError(ValueError):
    pass


def env_or_file(name: str, env: Mapping[str, str] | None = None, default: str | None = None) -> str | None:
    """`NAME`, or the contents of the file named by `NAME_FILE`. Setting both is an error (it is ambiguous)."""
    env = os.environ if env is None else env
    value, path = env.get(name), env.get(f"{name}_FILE")
    if value and path:
        raise ConfigError(f"Set only one of {name} and {name}_FILE")
    if path:
        try:
            with open(path) as f:
                content = f.read().rstrip("\r\n")
        except OSError as e:
            raise ConfigError(f"{name}_FILE: cannot read {path}: {e.strerror}") from e
        if not content:
            raise ConfigError(f"{name}_FILE: {path} is empty")
        return content
    return value or default


class SecretStore:
    def __init__(self, tool_secrets: Mapping[str, str] | None = None, hidden: Mapping[str, str] | None = None):
        """`tool_secrets` may be requested by tools; `hidden` values (the platform's own keys) are only ever scrubbed."""
        self._tool = dict(tool_secrets or {})
        for name, value in {**self._tool, **(hidden or {})}.items():
            if value and len(value) < MIN_SECRET_LENGTH:
                raise ConfigError(f"Secret '{name}' is shorter than {MIN_SECRET_LENGTH} characters, which is too short to be safe")
        self._scrub = sorted({v: n for n, v in {**(hidden or {}), **self._tool}.items() if v}.items(), key=lambda kv: -len(kv[0]))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SecretStore":
        env = os.environ if env is None else env
        tool = {}
        for key in env:
            m = re.fullmatch(r"NORTHCX_SECRET_([A-Z0-9_]+?)(_FILE)?", key)
            if m and m.group(1).lower() not in tool:
                value = env_or_file(f"NORTHCX_SECRET_{m.group(1)}", env)
                if value:
                    tool[m.group(1).lower()] = value
        hidden = {n: v for n in ("NORTHCX_API_KEY", "NORTHCX_WEBHOOK_SECRET", "ANTHROPIC_API_KEY", "NORTHCX_DATABASE_URL")
                  if (v := env_or_file(n, env))}
        return cls(tool, hidden)

    def get(self, name: str) -> str:
        try:
            return self._tool[name.lower()]
        except KeyError:
            raise KeyError(f"Secret '{name}' is not configured (set NORTHCX_SECRET_{name.upper()} or NORTHCX_SECRET_{name.upper()}_FILE)") from None

    def names(self) -> list[str]:
        return sorted(self._tool)

    def redact_text(self, text: str) -> str:
        for value, name in self._scrub:
            if value in text:
                text = text.replace(value, f"[redacted:{name}]")
        return text

    def redact(self, obj: Any) -> Any:
        """Scrub secrets from any JSON-like structure (strings, lists, dicts); other values are returned unchanged."""
        if not self._scrub:
            return obj
        if isinstance(obj, str):
            return self.redact_text(obj)
        if isinstance(obj, list):
            return [self.redact(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(self.redact(x) for x in obj)
        if isinstance(obj, dict):
            return {self.redact(k) if isinstance(k, str) else k: self.redact(v) for k, v in obj.items()}
        return obj


NO_SECRETS = SecretStore()
