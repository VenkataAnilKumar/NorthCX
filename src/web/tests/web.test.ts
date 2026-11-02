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
