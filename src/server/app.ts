import { Hono } from "hono";
import { z } from "zod";
import type { AgentDef } from "../core/agent.js";
import type { Runtime } from "../core/runtime.js";
import type { TraceStore } from "../core/trace.js";
import { WIDGET_HTML } from "./widget.js";

type Agent = Required<AgentDef>;

const chatBody = z.object({
  sessionId: z.string().min(1).max(200),
  message: z.string().min(1).max(8000),
  customerId: z.string().max(200).optional(),
});

const err = (code: string, message: string) => ({ error: { code, message } });

export function createApp(opts: {
  runtime: Runtime;
  traces: TraceStore;
  agents: Record<string, Agent>;
  apiKey?: string;
}) {
  const app = new Hono();

  app.get("/", (c) => c.html(WIDGET_HTML));
  app.get("/health", (c) => c.json({ ok: true }));

  app.use("/v1/*", async (c, next) => {
    if (opts.apiKey && c.req.header("authorization") !== `Bearer ${opts.apiKey}`) {
      return c.json(err("unauthorized", "Missing or invalid API key"), 401);
    }
    await next();
  });

  app.post("/v1/agents/:id/chat", async (c) => {
    const agent = opts.agents[c.req.param("id")];
    if (!agent) return c.json(err("not_found", "Unknown agent"), 404);
    let json: unknown;
    try { json = await c.req.json(); } catch { return c.json(err("bad_request", "Body must be JSON"), 400); }
    const body = chatBody.safeParse(json);
    if (!body.success) return c.json(err("bad_request", body.error.message), 400);
    try {
      const r = await opts.runtime.run(agent, body.data);
      return c.json({ reply: r.reply, status: r.status, traceId: r.traceId, pendingApprovals: r.pendingApprovals });
    } catch (e) {
      console.error(e);
      return c.json(err("internal", "Run failed"), 500);
    }
  });

  app.get("/v1/traces/:id", (c) => {
    const t = opts.traces.get(c.req.param("id"));
    return t ? c.json(t) : c.json(err("not_found", "Unknown trace"), 404);
  });

  app.get("/v1/traces", (c) => {
    const sessionId = c.req.query("sessionId");
    return c.json({ traces: opts.traces.list(sessionId).map((t) => ({ id: t.id, agentId: t.agentId, sessionId: t.sessionId, events: t.events.length })) });
  });

  app.get("/v1/approvals", (c) => {
    const state = c.req.query("state") as "pending" | "approved" | "rejected" | undefined;
    return c.json({ approvals: opts.runtime.approvals.list(state) });
  });

  // Records the decision only. Resuming the run is a Phase 2 feature.
  app.post("/v1/approvals/:id/decision", async (c) => {
    const body = z.object({ approved: z.boolean(), by: z.string().min(1) }).safeParse(await c.req.json().catch(() => null));
    if (!body.success) return c.json(err("bad_request", body.error.message), 400);
    try {
      return c.json(opts.runtime.approvals.decide(c.req.param("id"), body.data.approved, body.data.by));
    } catch (e) {
      return c.json(err("conflict", String((e as Error).message)), 409);
    }
  });

  return app;
}
