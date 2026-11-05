import os
import sys
from pathlib import Path
from northcx.config import load_registry
from northcx.reliability import ReliableLLM
from northcx.llm import DEFAULT_MODEL
from northcx.llm import AnthropicLLM
from northcx.secrets import SecretStore, env_or_file
from types import SimpleNamespace


def load_settings(c: SimpleNamespace) -> None:
    """Model, secrets and API key."""
    demo = os.environ.get("NORTHCX_DEMO") == "1"
    anthropic_key = env_or_file("ANTHROPIC_API_KEY")
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key  # the SDK reads it from the environment
    if not demo and not anthropic_key:
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
        llm = AnthropicLLM()
        fallbacks = [m.strip() for m in os.environ.get("NORTHCX_MODEL_FALLBACKS", "").split(",") if m.strip()]
        llm = ReliableLLM(llm, ([DEFAULT_MODEL] + fallbacks) if fallbacks else [],
                          retries=int(os.environ.get("NORTHCX_MODEL_RETRIES", 2)),
                          timeout=float(os.environ.get("NORTHCX_MODEL_TIMEOUT", 60)) or None)

    c.api_key = api_key
    c.demo = demo
    c.examples_dir = examples_dir
    c.llm = llm
    c.registry = registry
    c.secrets = secrets
