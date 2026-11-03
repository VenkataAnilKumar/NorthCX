import { afterEach, describe, expect, it, vi } from "vitest";
import { NorthCXClient, NorthCXError } from "../src/client";
import { GRANT, REPLY, err, fakeFetch, json, sse } from "./helpers";

const make = (f: typeof fetch, extra = {}) => new NorthCXClient({ baseUrl: "https://api.example.com/", agent: "support", token: "ncxc_abc", sessionId: "web-1", fetch: f, ...extra });
afterEach(() => { vi.useRealTimers(); });

describe("setup", () => {
  it("needs a place, an agent and a way to get a token", () => {
    const { f } = fakeFetch(json({}));
    expect(() => new NorthCXClient({ baseUrl: "", agent: "a", token: "t", sessionId: "s", fetch: f })).toThrow();
    expect(() => new NorthCXClient({ baseUrl: "https://x", agent: "a", fetch: f })).toThrow(/getToken/);
    expect(() => new NorthCXClient({ baseUrl: "https://x", agent: "a", token: "t", fetch: f })).toThrow(/getToken/);
  });
  it("asks your server for a token once, and knows the session afterwards", async () => {
    const { f } = fakeFetch(json(REPLY));
    const getToken = vi.fn(async () => GRANT);
    const c = new NorthCXClient({ baseUrl: "https://x", agent: "support", getToken, fetch: f });
    expect(c.sessionId).toBeUndefined();
    expect(await c.start()).toBe("web-1");
    await c.start();
    expect(getToken).toHaveBeenCalledTimes(1);
    expect(c.sessionId).toBe("web-1");
  });
  it("renews a token that is about to expire, keeping the same conversation", async () => {
    const getToken = vi.fn(async (prev?: { sessionId: string }) => ({ token: "t2", sessionId: prev?.sessionId ?? "web-1", expiresAt: Math.floor(Date.now() / 1000) + 10 }));
    const c = new NorthCXClient({ baseUrl: "https://x", agent: "a", getToken, fetch: fakeFetch(json({})).f });
    await c.start();
    await c.start();
    expect(getToken).toHaveBeenCalledTimes(2);
    expect(getToken.mock.calls[1]![0]).toEqual({ sessionId: "web-1" });
  });
});

describe("sending", () => {
  it("sends one request with an idempotency key and the bearer token when not streaming", async () => {
    const { f, calls } = fakeFetch(json(REPLY));
    const r = await make(f).send("hi");
    expect(r.reply).toBe("Hello!");
    expect(calls[0]!.url).toBe("https://api.example.com/v1/agents/support/chat");
    expect(calls[0]!.headers["authorization"]).toBe("Bearer ncxc_abc");
    expect(calls[0]!.headers["idempotency-key"]).toMatch(/\S{8,}/);
    expect(JSON.parse(calls[0]!.body!)).toEqual({ sessionId: "web-1", message: "hi" });
  });
  it("includes attachment ids", async () => {
    const { f, calls } = fakeFetch(json(REPLY));
    await make(f).send("see", { attachments: ["a1", "a2"] });
    expect(JSON.parse(calls[0]!.body!).attachments).toEqual(["a1", "a2"]);
  });
  it("streams replies and tool progress when asked for callbacks", async () => {
    const { f, calls } = fakeFetch(sse(["started", {}], ["progress", { type: "tool", name: "lookup_order" }], ["delta", { text: "Hel" }], ["delta", { text: "lo!" }], ["done", REPLY]));
    const deltas: string[] = [], tools: string[] = [];
    const r = await make(f).send("hi", { onDelta: (t) => deltas.push(t), onProgress: (t) => tools.push(t) });
    expect(calls[0]!.url).toContain("/chat/stream");
    expect(calls[0]!.headers["idempotency-key"]).toBeUndefined();   // the stream endpoint does not take one
    expect([deltas.join(""), tools, r.status]).toEqual(["Hello!", ["lookup_order"], "completed"]);
  });
  it("reports a stream that ends early or fails, and does not repeat it", async () => {
    const { f, calls } = fakeFetch(sse(["delta", { text: "Hel" }]));
    await expect(make(f).send("hi", { onDelta: () => undefined })).rejects.toMatchObject({ code: "interrupted" });
    expect(calls).toHaveLength(1);
    const e = fakeFetch(sse(["error", { code: "internal", message: "Run failed" }]));
    await expect(make(e.f).send("hi", { onDelta: () => undefined })).rejects.toMatchObject({ code: "internal", message: "Run failed" });
  });
  it("renews an expired token once and carries on", async () => {
    const getToken = vi.fn(async () => ({ token: "fresh", sessionId: "web-1" }));
    const { f, calls } = fakeFetch(err(401, "token_expired"), json(REPLY));
    const c = new NorthCXClient({ baseUrl: "https://x", agent: "support", token: "old", sessionId: "web-1", getToken, fetch: f });
    expect((await c.send("hi")).reply).toBe("Hello!");
    expect(calls.map((x) => x.headers["authorization"])).toEqual(["Bearer old", "Bearer fresh"]);
    expect(getToken).toHaveBeenCalledTimes(1);
  });
  it("gives up on a token that keeps being refused", async () => {
    const { f, calls } = fakeFetch(err(401, "token_expired"));
    const c = new NorthCXClient({ baseUrl: "https://x", agent: "a", token: "old", sessionId: "s", getToken: async () => ({ token: "n", sessionId: "s" }), fetch: f });
    await expect(c.send("hi")).rejects.toMatchObject({ status: 401 });
    expect(calls).toHaveLength(2);
  });
  it("without a way to renew, an expired token is reported", async () => {
    await expect(make(fakeFetch(err(401, "token_expired", "expired")).f).send("hi")).rejects.toMatchObject({ code: "token_expired", message: "expired" });
  });
});

describe("retries", () => {
  it("repeats a safe request with the same idempotency key after a temporary failure", async () => {
    vi.useFakeTimers();
    const { f, calls } = fakeFetch(err(503, "unavailable"), new TypeError("network"), json(REPLY));
    const p = make(f).send("hi");
    await vi.runAllTimersAsync();
    expect((await p).reply).toBe("Hello!");
    expect(calls).toHaveLength(3);
    expect(new Set(calls.map((c) => c.headers["idempotency-key"])).size).toBe(1);
  });
  it("waits as long as the server asks when rate limited", async () => {
    vi.useFakeTimers();
    const { f, calls } = fakeFetch(err(429, "rate_limited", "slow down", { "retry-after": "7" }), json(REPLY));
    const p = make(f).send("hi");
    await vi.advanceTimersByTimeAsync(6000);
    expect(calls).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1500);
    expect((await p).status).toBe("completed");
  });
  it("does not repeat a request the server refused for good", async () => {
    const { f, calls } = fakeFetch(err(400, "bad_request", "no"));
    await expect(make(f).send("hi")).rejects.toMatchObject({ status: 400, code: "bad_request" });
    expect(calls).toHaveLength(1);
  });
  it("stops after the allowed attempts and says what happened", async () => {
    vi.useFakeTimers();
    const { f, calls } = fakeFetch(err(503, "unavailable"));
    const p = make(f, { retries: 1 }).send("hi").catch((e) => e);
    await vi.runAllTimersAsync();
    expect(await p).toBeInstanceOf(NorthCXError);
    expect(calls).toHaveLength(2);
  });
  it("can be cancelled", async () => {
    const ctl = new AbortController();
    const f = (async (_u: string, init: RequestInit) => new Promise((_, rej) => {  // like a real fetch: fails at once if already aborted
      const stop = () => rej(new DOMException("Aborted", "AbortError"));
      if (init.signal!.aborted) stop(); else init.signal!.addEventListener("abort", stop);
    })) as unknown as typeof fetch;
    const p = make(f).send("hi", { signal: ctl.signal }).catch((e) => e);
    ctl.abort();
    expect(await p).toBeInstanceOf(NorthCXError);
  });
});

describe("attachments, incoming messages and ratings", () => {
  it("uploads a file with its name and returns its id", async () => {
    const { f, calls } = fakeFetch(json({ id: "a1", name: "photo.png", kind: "image", mediaType: "image/png", size: 3 }, 201));
    const info = await make(f).upload(new Blob(["abc"]), "my photo.png");
    expect(info.id).toBe("a1");
    expect(calls[0]).toMatchObject({ method: "PUT", url: "https://api.example.com/v1/sessions/web-1/attachments?filename=my%20photo.png" });
  });
  it("reads what arrived outside a request", async () => {
    const { f, calls } = fakeFetch(json({ messages: [{ id: 4, kind: "person_reply", createdAt: 1, reply: "Hi, Sam here", by: "Sam" }] }));
    expect((await make(f).messages(3))[0]!.reply).toBe("Hi, Sam here");
    expect(calls[0]!.url).toBe("https://api.example.com/v1/sessions/web-1/outbox?after=3");
  });
  it("watches without repeating messages and stops when told", async () => {
    vi.useFakeTimers();
    const { f, calls } = fakeFetch(json({ messages: [{ id: 1, kind: "person_reply", createdAt: 1, reply: "one" }] }), json({ messages: [{ id: 2, kind: "person_reply", createdAt: 2, reply: "two" }] }), json({ messages: [] }));
    const got: string[] = [];
    const c = make(f);
    const stop = c.watch((m) => got.push(String(m.reply)), { intervalMs: 1000 });
    await vi.advanceTimersByTimeAsync(1100);
    await vi.advanceTimersByTimeAsync(1100);
    expect(got).toEqual(["one", "two"]);
    expect(calls[1]!.url).toContain("after=1");
    stop();
    const n = calls.length;
    await vi.advanceTimersByTimeAsync(10_000);
    expect(calls).toHaveLength(n);
  });
  it("backs off when polling fails and reports it", async () => {
    vi.useFakeTimers();
    const { f, calls } = fakeFetch(new TypeError("offline"));
    const errors: unknown[] = [];
    const c = make(f, { retries: 0 });
    c.watch(() => undefined, { intervalMs: 1000, onError: (e) => errors.push(e) });
    await vi.advanceTimersByTimeAsync(1100);
    const first = calls.length;
    await vi.advanceTimersByTimeAsync(1500);     // the next wait is longer than the first
    expect(calls.length).toBe(first);
    expect(errors.length).toBeGreaterThan(0);
    c.close();
  });
  it("sends a rating", async () => {
    const { f, calls } = fakeFetch(json({ saved: true }));
    await make(f).rate(4, "good");
    expect(calls[0]!.url).toContain("/v1/sessions/web-1/feedback");
    expect(JSON.parse(calls[0]!.body!)).toEqual({ rating: 4, comment: "good" });
  });
});
