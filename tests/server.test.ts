import { describe, expect, it } from "vitest";
import { InMemoryStore, Runtime, ScriptedLLM, TraceStore, text, toolCall } from "../src/core/index.js";
import { createApp } from "../src/server/app.js";
import { supportAgent } from "../examples/support/agent.js";

const build = (script: any[], apiKey?: string) => {
  const traces = new TraceStore();
  const runtime = new Runtime({ llm: new ScriptedLLM(script), store: new InMemoryStore(), traces });
  return { app: createApp({ runtime, traces, agents: { support: supportAgent() }, apiKey }), runtime };
};
const post = (app: any, path: string, body: unknown, headers: Record<string, string> = {}) =>
  app.request(path, { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) });

describe("server", () => {
  it("serves health and the widget", async () => {
    const { app } = build([]);
    expect((await app.request("/health")).status).toBe(200);
    expect(await (await app.request("/")).text()).toContain("NorthCX");
  });

  it("answers a chat with a tool call and exposes the trace", async () => {
    const { app } = build([toolCall("lookup_order", { orderId: "1042" }, "t1"), text("Order 1042 was delivered.")]);
    const res = await post(app, "/v1/agents/support/chat", { sessionId: "s1", message: "where is 1042?" });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("completed");
    const trace = await (await app.request(`/v1/traces/${body.traceId}`)).json();
    expect(trace.events.some((e: any) => e.type === "tool_result")).toBe(true);
    const list = await (await app.request("/v1/traces?sessionId=s1")).json();
    expect(list.traces).toHaveLength(1);
  });

  it("refunds small amounts and holds large ones for approval", async () => {
    const small = build([toolCall("issue_refund", { orderId: "1042", amount: 60 }, "t1"), text("Refunded 60.")]);
    expect((await (await post(small.app, "/v1/agents/support/chat", { sessionId: "a", message: "refund" })).json()).status).toBe("completed");

    const big = build([toolCall("issue_refund", { orderId: "2077", amount: 240 }, "t1")]);
    const body = await (await post(big.app, "/v1/agents/support/chat", { sessionId: "b", message: "refund" })).json();
    expect(body.status).toBe("needs_approval");
    const pending = await (await big.app.request("/v1/approvals?state=pending")).json();
    expect(pending.approvals).toHaveLength(1);
    const id = pending.approvals[0].id;
    const decided = await post(big.app, `/v1/approvals/${id}/decision`, { approved: true, by: "reviewer" });
    expect((await decided.json()).state).toBe("approved");
    expect((await post(big.app, `/v1/approvals/${id}/decision`, { approved: false, by: "x" })).status).toBe(409);
  });

  it("rejects bad input and unknown agents", async () => {
    const { app } = build([]);
    expect((await post(app, "/v1/agents/support/chat", { message: "no session" })).status).toBe(400);
    expect((await post(app, "/v1/agents/nope/chat", { sessionId: "s", message: "x" })).status).toBe(404);
    expect((await app.request("/v1/traces/missing")).status).toBe(404);
  });

  it("requires the API key when configured", async () => {
    const { app } = build([text("hi")], "secret");
    expect((await post(app, "/v1/agents/support/chat", { sessionId: "s", message: "x" })).status).toBe(401);
    const ok = await post(app, "/v1/agents/support/chat", { sessionId: "s", message: "x" }, { authorization: "Bearer secret" });
    expect(ok.status).toBe(200);
    expect((await app.request("/health")).status).toBe(200);
  });
});
