"""Startup configuration helpers."""
from __future__ import annotations

import importlib

from .secrets import ConfigError
from .spec import Registry


def load_registry(ref: str) -> Registry:
    """`module:function` returning the tool registry; this is how a deployment supplies its own tools."""
    module, sep, func = ref.partition(":")
    if not sep or not module or not func:
        raise ConfigError(f"NORTHCX_REGISTRY must look like 'package.module:function', got {ref!r}")
    try:
        fn = getattr(importlib.import_module(module), func)
    except ImportError as e:
        raise ConfigError(f"NORTHCX_REGISTRY: cannot import {module!r}: {e}") from e
    except AttributeError:
        raise ConfigError(f"NORTHCX_REGISTRY: module {module!r} has no {func!r}") from None
    registry = fn()
    if not isinstance(registry, Registry):
        raise ConfigError(f"NORTHCX_REGISTRY: {ref} returned {type(registry).__name__}, not a Registry")
    return registry
