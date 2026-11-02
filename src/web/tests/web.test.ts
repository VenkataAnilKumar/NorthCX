import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, formatTime, getApiKey, setApiKey } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { TraceTimeline } from "@/components/trace-timeline";

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

describe("api client", () => {
  it("sends the API key as a bearer token", async () => {
    setApiKey("secret");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api("/health");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/northcx/health");
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer secret");
  });

  it("raises ApiError with the server message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: "Missing or invalid API key" } }), { status: 401 })));
    await expect(api("/v1/agents")).rejects.toMatchObject({ status: 401, message: "Missing or invalid API key" });
    await expect(api("/v1/agents")).rejects.toBeInstanceOf(ApiError);
  });

  it("clears the key when set to empty", () => {
    setApiKey("a"); setApiKey("");
    expect(getApiKey()).toBe("");
  });

  it("formats epoch seconds", () => {
    expect(formatTime(null)).toBe("");
    expect(formatTime(0)).toBe("");
    expect(formatTime(1_700_000_000)).not.toBe("");
  });
});

describe("components", () => {
  it("renders status badges with readable labels", () => {
    expect(renderToStaticMarkup(createElement(StatusBadge, { status: "needs_approval" }))).toContain("Needs approval");
    expect(renderToStaticMarkup(createElement(StatusBadge, { status: "completed" }))).toContain("Completed");
  });

  it("renders trace events in order with relative times", () => {
    const html = renderToStaticMarkup(createElement(TraceTimeline, { events: [
      { t: 10, type: "user", data: { message: "hi" } },
      { t: 10.25, type: "tool_call", data: { name: "lookup_order", input: { order_id: "1042" } } },
      { t: 10.5, type: "reply", data: { reply: "done", status: "completed" } },
    ] }));
    expect(html.indexOf("hi")).toBeLessThan(html.indexOf("lookup_order"));
    expect(html).toContain("+250 ms");
    expect(html).toContain("done (completed)");
  });
});

describe("approval and outbox calls", () => {
  it("sends the decision note and reads the outbox with the cursor", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return new Response(JSON.stringify(url.includes("outbox") ? { messages: [{ id: 3, kind: "approval_result", reply: "done" }] } : { state: "executed", resume: { reply: "ok" } }), { status: 200 });
    }));
    const { decideApproval, listOutbox } = await import("@/lib/api");
    const res = await decideApproval("a1", false, "rae", "too high");
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ approved: false, by: "rae", note: "too high" });
    expect(res.resume?.reply).toBe("ok");
    await decideApproval("a1", true, "rae");
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ approved: true, by: "rae" });
    const msgs = await listOutbox("sess/1", 2);
    expect(calls[2][0]).toBe("/api/northcx/v1/sessions/sess%2F1/outbox?after=2");
    expect(msgs[0].id).toBe(3);
  });

  it("renders the new approval states and platform notices", () => {
    for (const s of ["executed", "failed", "expired"]) expect(renderToStaticMarkup(createElement(StatusBadge, { status: s }))).toContain(s.charAt(0).toUpperCase() + s.slice(1));
    const html = renderToStaticMarkup(createElement(TraceTimeline, { events: [{ t: 1, type: "system", data: { message: "approved" } }] }));
    expect(html).toContain("Platform notice");
  });
});

describe("handoff calls", () => {
  it("lists by state, loads a package and resolves with a note", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return new Response(JSON.stringify(url.endsWith("/v1/handoffs?state=open") ? { handoffs: [{ id: "h1" }] } : { id: "h1", state: "resolved" }), { status: 200 });
    }));
    const { listHandoffs, getHandoff, resolveHandoff } = await import("@/lib/api");
    expect((await listHandoffs("open"))[0].id).toBe("h1");
    await getHandoff("h1");
    await resolveHandoff("h1", "jo", "called back");
    expect(calls[0][0]).toBe("/api/northcx/v1/handoffs?state=open");
    expect(calls[1][0]).toBe("/api/northcx/v1/handoffs/h1");
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({ by: "jo", note: "called back" });
  });

  it("renders open and resolved badges", () => {
    expect(renderToStaticMarkup(createElement(StatusBadge, { status: "open" }))).toContain("Open");
    expect(renderToStaticMarkup(createElement(StatusBadge, { status: "resolved" }))).toContain("Resolved");
  });
});

describe("forced topic events", () => {
  it("shows which topics sent the conversation to a person", () => {
    const html = renderToStaticMarkup(createElement(TraceTimeline, { events: [{ t: 1, type: "forced_topic", data: { topics: ["legal", "safety"] } }] }));
    expect(html).toContain("Forced topic");
    expect(html).toContain("legal, safety");
  });
});

describe("simulation calls", () => {
  it("runs scenarios with the chosen options and reads gates", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return new Response(JSON.stringify(url.includes("gate") ? { gates: [{ agent: "support", satisfied: true }] } : { id: "r1" }), { status: 200 });
    }));
    const { runSimulation, getGates } = await import("@/lib/api");
    await runSimulation("scripted", true, "legal");
    expect(calls[0][0]).toBe("/api/northcx/v1/simulations/runs");
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ mode: "scripted", skipJudge: true, only: "legal" });
    await runSimulation("scripted", false);
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ mode: "scripted", skipJudge: false });
    expect((await getGates())[0].satisfied).toBe(true);
  });

  it("renders gate and run badges", () => {
    for (const [s, label] of [["satisfied", "Satisfied"], ["passed", "Passed"], ["failed", "Failed"], ["blocked", "Blocked"]])
      expect(renderToStaticMarkup(createElement(StatusBadge, { status: s }))).toContain(label);
  });
});
