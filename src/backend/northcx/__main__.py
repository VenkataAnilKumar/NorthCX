import os
import sys

import uvicorn

from .llm import AnthropicLLM
from .runtime import Runtime
from .server import create_app
from .store import InMemoryStore
from .trace import TraceStore


def main() -> None:
    demo = os.environ.get("NORTHCX_DEMO") == "1"
    if not demo and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY to run the server (or NORTHCX_DEMO=1 for the offline demo model).")
    from examples.support_agent import support_agent

    traces = TraceStore(os.environ.get("NORTHCX_TRACE_DIR"))
    if demo:
        from .demo import DemoLLM

        llm = DemoLLM()
    else:
        llm = AnthropicLLM()
    runtime = Runtime(llm, InMemoryStore(), traces)
    app = create_app(runtime, traces, {"support": support_agent()}, os.environ.get("NORTHCX_API_KEY"))
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
