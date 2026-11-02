import { serve } from "@hono/node-server";
import { AnthropicLLM, InMemoryStore, Runtime, TraceStore } from "../core/index.js";
import { supportAgent } from "../../examples/support/agent.js";
import { createApp } from "./app.js";

if (!process.env.ANTHROPIC_API_KEY) {
  console.error("Set ANTHROPIC_API_KEY to run the server.");
  process.exit(1);
}

const traces = new TraceStore(process.env.NORTHCX_TRACE_DIR);
const runtime = new Runtime({ llm: new AnthropicLLM(), store: new InMemoryStore(), traces });
const app = createApp({ runtime, traces, agents: { support: supportAgent() }, apiKey: process.env.NORTHCX_API_KEY });

const port = Number(process.env.PORT ?? 3000);
serve({ fetch: app.fetch, port });
console.log(`NorthCX listening on http://localhost:${port}`);
