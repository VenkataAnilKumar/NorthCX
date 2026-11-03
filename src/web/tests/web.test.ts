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

describe("version and release calls", () => {
  it("creates versions from YAML, publishes with a note and keeps gate reasons on errors", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      if (url.endsWith("/releases") && init?.method === "POST")
        return new Response(JSON.stringify({ error: { code: "gate_not_satisfied", message: "The release gate is not satisfied", reasons: ["a: not run", "b: failed"] } }), { status: 409 });
      return new Response(JSON.stringify({ number: 2 }), { status: 200 });
    }));
    const { createVersion, publishVersion, rollbackAgent, diffVersions, versionGate, runForVersion, ApiError } = await import("@/lib/api");
    await createVersion("support", "id: support\n", "dev", "tweak");
    expect(calls[0][0]).toBe("/api/northcx/v1/agents/support/versions");
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ specYaml: "id: support\n", by: "dev", note: "tweak" });
    const err = await publishVersion("support", 2, "rel", "go").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.reasons).toEqual(["a: not run", "b: failed"]);
    await rollbackAgent("support", "oncall");
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({ by: "oncall" });
    await diffVersions("support", 1, 2);
    expect(calls[3][0]).toBe("/api/northcx/v1/agents/support/versions/1/diff/2");
    await runForVersion("support", 2);
    expect(JSON.parse(String(calls[4][1]?.body))).toEqual({ mode: "scripted", skipJudge: true, agent: "support", version: 2 });
    await versionGate("support", 2).catch(() => undefined);
    expect(calls[5][0]).toBe("/api/northcx/v1/simulations/gate?agent=support&version=2");
  });

  it("renders release action badges", () => {
    for (const [s, label] of [["live", "Live"], ["publish", "Publish"], ["rollback", "Rollback"]])
      expect(renderToStaticMarkup(createElement(StatusBadge, { status: s }))).toContain(label);
  });
});

describe("access calls", () => {
  it("creates keys, reads the audit log with filters, and omits the claimed name when signed in", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return new Response(JSON.stringify(url.includes("/v1/audit?") ? { entries: [{ id: 1 }] } : { ok: true }), { status: 200 });
    }));
    const { createKey, listAudit, decideApproval, resolveHandoff, publishVersion, getMe } = await import("@/lib/api");
    await createKey("svc", "channel", 30);
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ name: "svc", role: "channel", expiresInDays: 30 });
    expect((await listAudit("release.publish", "rae", 9))[0].id).toBe(1);
    expect(calls[1][0]).toBe("/api/northcx/v1/audit?limit=100&action=release.publish&actor_name=rae&before=9");
    await decideApproval("a1", true, undefined, "ok");
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({ approved: true, note: "ok" });
    await resolveHandoff("h1");
    expect(JSON.parse(String(calls[3][1]?.body))).toEqual({});
    await publishVersion("support", 2, "claimed");
    expect(JSON.parse(String(calls[4][1]?.body))).toEqual({ version: 2, by: "claimed" });
    await getMe();
    expect(calls[5][0]).toBe("/api/northcx/v1/me");
  });

  it("shows a 403's message from the server", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { code: "forbidden", message: "The 'viewer' role cannot do this (needs approvals:decide)" } }), { status: 403 })));
    const { decideApproval } = await import("@/lib/api");
    await expect(decideApproval("a", true)).rejects.toMatchObject({ status: 403, message: expect.stringContaining("viewer") });
  });
});

describe("revoked keys", () => {
  it("are labelled as revoked", () => {
    expect(renderToStaticMarkup(createElement(StatusBadge, { status: "revoked" }))).toContain("Revoked");
  });
});

describe("streaming chat", () => {
  const sse = (...events: [string, unknown][]) => events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
  const streamOf = (text: string, size: number) => new ReadableStream<Uint8Array>({
    start(c) { const b = new TextEncoder().encode(text); for (let i = 0; i < b.length; i += size) c.enqueue(b.slice(i, i + size)); c.close(); },
  });

  it("reports progress and pieces, even when events are split across chunks", async () => {
    const done = { reply: "Hello there", status: "completed", traceId: "t1", pendingApprovals: [], handoffId: null, agentVersion: null };
    const body = sse(["started", {}], ["progress", { type: "tool", name: "lookup_order" }], ["delta", { text: "Hello " }], ["delta", { text: "there" }], ["done", done]);
    for (const size of [1, 7, 1000]) {
      const calls: [string, RequestInit | undefined][] = [];
      vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => { calls.push([url, init]); return new Response(streamOf(body, size), { status: 200 }); }));
      const { chatStream, setApiKey } = await import("@/lib/api");
      setApiKey("k");
      const seen: string[] = [];
      const r = await chatStream("support", "s1", "hi", { onProgress: (t) => seen.push(`tool:${t}`), onDelta: (t) => seen.push(t) });
      expect(r.reply).toBe("Hello there");
      expect(seen).toEqual(["tool:lookup_order", "Hello ", "there"]);
      expect(calls[0][0]).toBe("/api/northcx/v1/agents/support/chat/stream");
      expect(new Headers(calls[0][1]?.headers).get("authorization")).toBe("Bearer k");
    }
  });

  it("turns refusals, server errors and cut-off streams into errors", async () => {
    const { chatStream } = await import("@/lib/api");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { message: "Too many messages" } }), { status: 429 })));
    await expect(chatStream("a", "s", "m")).rejects.toThrow("Too many messages");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(streamOf(sse(["started", {}], ["error", { message: "Run failed" }]), 5), { status: 200 })));
    await expect(chatStream("a", "s", "m")).rejects.toThrow("Run failed");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(streamOf(sse(["started", {}], ["delta", { text: "x" }]), 5), { status: 200 })));
    await expect(chatStream("a", "s", "m")).rejects.toThrow("closed before");
  });
});

describe("routing calls", () => {
  it("filters hand-offs by queue and reads queue status", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => { calls.push(url); return new Response(JSON.stringify(url.includes("routing") ? { timezone: "UTC", defaultQueue: "general", holidays: [], queues: [{ name: "general", open: true, nextOpen: null, topics: [], triggers: [] }] } : { handoffs: [] }), { status: 200 }); }));
    const { listHandoffs, getRouting } = await import("@/lib/api");
    await listHandoffs("open", "billing");
    await listHandoffs();
    expect((await getRouting()).queues[0].name).toBe("general");
    expect(calls).toEqual(["/api/northcx/v1/handoffs?state=open&queue=billing", "/api/northcx/v1/handoffs", "/api/northcx/v1/routing"]);
  });
});

describe("environment calls", () => {
  it("reads environments, promotes, and sends the environment with streamed chat", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    const done = `event: done\ndata: ${JSON.stringify({ reply: "ok", status: "completed", traceId: "t", pendingApprovals: [], handoffId: null, agentVersion: null })}\n\n`;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return url.includes("chat/stream") ? new Response(done, { status: 200 }) : new Response(JSON.stringify({ environments: {}, agentId: "support", strictPromotion: false }), { status: 200 });
    }));
    const { getEnvironments, promoteAgent, chatStream } = await import("@/lib/api");
    await getEnvironments("support");
    await promoteAgent("support", "staging", "jo", "ok");
    await chatStream("support", "s1", "hi", {}, "dev");
    await chatStream("support", "s2", "hi", {}, "production");
    expect(calls[0][0]).toBe("/api/northcx/v1/agents/support/environments");
    expect(calls[1][0]).toBe("/api/northcx/v1/agents/support/promote");
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ to: "staging", by: "jo", note: "ok" });
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({ sessionId: "s1", message: "hi", environment: "dev" });
    expect(JSON.parse(String(calls[3][1]?.body))).toEqual({ sessionId: "s2", message: "hi" });
  });
});

describe("insights and search calls", () => {
  it("asks for a window, environment and agent, and searches and tags conversations", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => { calls.push([url, init]); return new Response(JSON.stringify({ conversations: [], tags: ["a"], causes: [], points: [] }), { status: 200 }); }));
    const { getOverview, getSeries, getFailures, searchConversations, addTag, removeTag } = await import("@/lib/api");
    await getOverview(24, "support", "staging");
    await getSeries(24 * 7);
    await getFailures(24);
    await searchConversations({ q: "gift", tag: "needs-article", handedOff: true });
    await addTag("s 1", "wrong-answer");
    await removeTag("s 1", "wrong-answer");
    const u = (i: number) => new URL(calls[i][0], "http://x");
    expect(u(0).pathname).toBe("/api/northcx/v1/insights/overview");
    expect(u(0).searchParams.get("agent")).toBe("support");
    expect(u(0).searchParams.get("environment")).toBe("staging");
    expect(Number(u(0).searchParams.get("to")) - Number(u(0).searchParams.get("from"))).toBeCloseTo(86400, -1);
    expect(u(1).searchParams.get("bucket")).toBe("day");
    expect(u(1).searchParams.get("environment")).toBeNull();
    expect(u(3).searchParams.get("q")).toBe("gift");
    expect(u(3).searchParams.get("handedOff")).toBe("true");
    expect(calls[4][0]).toBe("/api/northcx/v1/sessions/s%201/tags/wrong-answer");
    expect(calls[4][1]?.method).toBe("PUT");
    expect(calls[5][1]?.method).toBe("DELETE");
  });
});

describe("studio calls", () => {
  it("loads the catalog, previews a spec without saving it, and saves a version from the spec", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => { calls.push([url, init]); return new Response(JSON.stringify({ valid: true, problems: [], number: 3 }), { status: 200 }); }));
    const { getCatalog, previewSpec, saveSpec } = await import("@/lib/api");
    await getCatalog();
    await previewSpec("support", { id: "support", instructions: "hi" });
    await saveSpec("support", { id: "support", instructions: "hi" }, "jo", "tweak");
    expect(calls[0][0]).toBe("/api/northcx/v1/catalog");
    expect(calls[1][0]).toBe("/api/northcx/v1/agents/support/versions/preview");
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ spec: { id: "support", instructions: "hi" } });
    expect(calls[2][0]).toBe("/api/northcx/v1/agents/support/versions");
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({ spec: { id: "support", instructions: "hi" }, by: "jo", note: "tweak" });
  });
});

describe("scenario editor calls", () => {
  it("validates, creates, updates and deletes saved scenarios", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => { calls.push([url, init]); return new Response(JSON.stringify({ valid: true, problems: [], name: "x", revision: 1, deleted: true }), { status: 200 }); }));
    const { validateScenario, createScenario, updateScenario, deleteScenario, getScenario } = await import("@/lib/api");
    await validateScenario({ scenario: { name: "a" } });
    await createScenario({ yaml: "name: a" });
    await updateScenario("my scenario", { scenario: { name: "my scenario" } });
    await deleteScenario("my scenario");
    await getScenario("my scenario");
    expect(calls.map((c) => [c[0], c[1]?.method ?? "GET"])).toEqual([
      ["/api/northcx/v1/simulations/scenarios/validate", "POST"], ["/api/northcx/v1/simulations/scenarios", "POST"],
      ["/api/northcx/v1/simulations/scenarios/my%20scenario", "PUT"], ["/api/northcx/v1/simulations/scenarios/my%20scenario", "DELETE"],
      ["/api/northcx/v1/simulations/scenarios/my%20scenario", "GET"]]);
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ scenario: { name: "a" } });
  });
});

describe("knowledge calls", () => {
  it("encodes document ids with slashes, and searches within a source", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => { calls.push([url, init]); return new Response(JSON.stringify({ sources: [], documents: [], passages: [], status: "created", deleted: true }), { status: 200 }); }));
    const { listKnowledgeDocs, getKnowledgeDoc, putKnowledgeDoc, deleteKnowledgeDoc, searchKnowledge, createKnowledgeSource } = await import("@/lib/api");
    await listKnowledgeDocs("help center", true);
    await getKnowledgeDoc("help", "policies/returns v2");
    await putKnowledgeDoc("help", "policies/returns", { title: "Returns", text: "x" });
    await deleteKnowledgeDoc("help", "a/b");
    await searchKnowledge("refund time?", "help");
    await createKnowledgeSource("help", "Help", 30);
    expect(calls[0][0]).toBe("/api/northcx/v1/knowledge/documents?source=help+center&stale=true");
    expect(calls[1][0]).toBe("/api/northcx/v1/knowledge/sources/help/documents/policies/returns%20v2");
    expect(calls[2][1]?.method).toBe("PUT");
    expect(calls[3][1]?.method).toBe("DELETE");
    expect(calls[4][0]).toBe("/api/northcx/v1/knowledge/search?q=refund+time%3F&source=help");
    expect(JSON.parse(String(calls[5][1]?.body))).toEqual({ id: "help", name: "Help", staleAfterDays: 30 });
  });
});
