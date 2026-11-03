export type Call = { url: string; method: string; headers: Record<string, string>; body?: string };

/** A fake fetch that answers in order and records what it was asked. */
export function fakeFetch(...answers: (Response | Error | ((c: Call) => Response))[]) {
  const calls: Call[] = [];
  const f = (async (url: string, init: RequestInit = {}) => {
    const h: Record<string, string> = {};
    new Headers(init.headers).forEach((v, k) => { h[k] = v; });
    const call: Call = { url: String(url), method: init.method ?? "GET", headers: h, body: typeof init.body === "string" ? init.body : init.body ? "<blob>" : undefined };
    calls.push(call);
    const a = answers.length > 1 ? answers.shift()! : answers[0]!;
    if (a instanceof Error) throw a;
    return typeof a === "function" ? a(call) : a.clone();
  }) as unknown as typeof fetch;
  return { f, calls };
}

export const json = (body: unknown, status = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
export const err = (status: number, code: string, message = code, headers: Record<string, string> = {}) => json({ error: { code, message } }, status, headers);

export function sse(...events: [string, unknown][]) {
  const enc = new TextEncoder();
  return new Response(new ReadableStream({ start(c) { for (const [e, d] of events) c.enqueue(enc.encode(`event: ${e}\ndata: ${JSON.stringify(d)}\n\n`)); c.close(); } }), { headers: { "content-type": "text/event-stream" } });
}

export const REPLY = { reply: "Hello!", status: "completed", traceId: "t1", pendingApprovals: [], handoffId: null, agentVersion: null };
export const GRANT = { token: "ncxc_abc", sessionId: "web-1", expiresAt: Math.floor(Date.now() / 1000) + 3600 };
