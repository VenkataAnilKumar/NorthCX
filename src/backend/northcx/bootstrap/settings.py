import os
import sys
from pathlib import Path
from northcx.config import load_registry
from northcx.reliability import ReliableLLM
from northcx.secrets import SecretStore, env_or_file
from types import SimpleNamespace


def load_settings(c: SimpleNamespace) -> None:
    """Model, secrets and API key."""
    demo = os.environ.get("NORTHCX_DEMO") == "1"
    anthropic_key = env_or_file("ANTHROPIC_API_KEY")
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key  # the SDK reads it from the environment
    providers_file = os.environ.get("NORTHCX_PROVIDERS_FILE", "").strip()
    if not demo and not anthropic_key and not providers_file:
        sys.exit("Set ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY_FILE) to run the server, or NORTHCX_DEMO=1 for the offline demo model.")
    import examples

    registry = lambda: load_registry(os.environ.get("NORTHCX_REGISTRY", "examples.support_agent:registry"))  # noqa: E731
    secrets = SecretStore.from_env()
    api_key = env_or_file("NORTHCX_API_KEY")

    examples_dir = Path(examples.__file__).parent
    if demo:
        from northcx.demo import DemoLLM

        llm = DemoLLM()
    else:
        from northcx.providers.setup import build_providers
        from northcx.secrets import ConfigError

        try:
            providers, c.provider_where = build_providers(providers_file, anthropic_key, os.environ.get("NORTHCX_ANTHROPIC_CLIENT", "sdk").strip() or "sdk")
        except ConfigError as e:
            sys.exit(f"Configuration error: {e}")
        c.providers = providers
        llm = providers
        fallbacks = [m.strip() for m in os.environ.get("NORTHCX_MODEL_FALLBACKS", "").split(",") if m.strip()]
        llm = ReliableLLM(llm, ([providers.qualify(None)] + fallbacks) if fallbacks else [],
                          retries=int(os.environ.get("NORTHCX_MODEL_RETRIES", 2)),
                          timeout=float(os.environ.get("NORTHCX_MODEL_TIMEOUT", 60)) or None)
        llm.provider_where = c.provider_where      # each provider's declared tier, shown on the Models page even when there are no routing rules
        rules_file = os.environ.get("NORTHCX_ROUTING_RULES_FILE", "").strip()
        if rules_file:  # the data policy and routing rules: which tiers a conversation may use, and why a model was chosen
            from northcx.providers.selection import parse_routing
            from northcx.secrets import ConfigError

            try:
                llm.selector = parse_routing(Path(rules_file).read_text(), providers, c.provider_where)
            except (OSError, ConfigError) as e:
                sys.exit(f"Configuration error: NORTHCX_ROUTING_RULES_FILE: {e}")

    c.api_key = api_key
    c.demo = demo
    c.examples_dir = examples_dir
    c.llm = llm
    c.providers = getattr(c, "providers", None)
    c.registry = registry
    c.secrets = secrets
