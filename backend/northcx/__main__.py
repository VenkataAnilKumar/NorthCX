import os
import sys

import uvicorn

from .llm import AnthropicLLM
from .runtime import Runtime
from .server import create_app
from .store import InMemoryStore
from .trace import TraceStore


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY to run the server.")
    from examples.support_agent import support_agent

    traces = TraceStore(os.environ.get("NORTHCX_TRACE_DIR"))
    runtime = Runtime(AnthropicLLM(), InMemoryStore(), traces)
    app = create_app(runtime, traces, {"support": support_agent()}, os.environ.get("NORTHCX_API_KEY"))
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
