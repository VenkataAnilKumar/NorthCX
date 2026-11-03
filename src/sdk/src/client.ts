/** NorthCX chat client. No dependencies; works in browsers, workers and any runtime with `fetch` (streaming is used when the runtime supports it). */

export interface TokenGrant { token: string; sessionId: string; expiresAt?: number }
export interface ClientOptions {
  /** Where the NorthCX server is, for example https://support-api.example.com */
  baseUrl: string;
  /** The agent customers talk to. */
  agent: string;
  /** Asks your own server for a chat token (your server holds a channel key and calls POST /v1/chat-tokens). Called again when the token expires, with the current session so the conversation continues. */
  getToken?: (previous?: { sessionId: string }) => Promise<TokenGrant>;
  /** Or give a ready token and its session. */
  token?: string;
  sessionId?: string;
  fetch?: typeof fetch;
  /** Extra attempts for requests that are safe to repeat (default 2). */
  retries?: number;
  /** Per-request timeout in milliseconds (default 30000; replies that stream are not cut off while they are arriving). */
  timeoutMs?: number;
}

export type Status = "completed" | "escalated" | "needs_approval" | "with_person" | "unknown";
export interface ChatReply { reply: string; status: Status; traceId: string; pendingApprovals: { id: string; tool: string; reason: string }[]; handoffId: string | null; agentVersion: number | null }
export interface AttachmentInfo { id: string; name: string; kind: "image" | "pdf" | "text"; mediaType: string; size: number }
export interface IncomingMessage { id: number; kind: string; createdAt: number; reply?: string; by?: string; [key: string]: unknown }
export interface SendOptions {
  attachments?: string[];
  onProgress?: (tool: string) => void;
  onDelta?: (text: string) => void;
  signal?: AbortSignal;
  /** Force or forbid streaming. Default: stream when the runtime can. */
  stream?: boolean;
}

export class NorthCXError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter?: number) { super(message); this.name = "NorthCXError"; }
}

const sleep = (ms: number, signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
  const t = setTimeout(resolve, ms);
  signal?.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
});
const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`);

export class NorthCXClient {
  private token?: string;
  private expiresAt?: number;
  private session?: string;
  private readonly f: typeof fetch;
  private readonly watchers = new Set<() => void>();

  constructor(private readonly o: ClientOptions) {
    if (!o.baseUrl || !o.agent) throw new Error("baseUrl and agent are required");
    if (!o.getToken && !(o.token && o.sessionId)) throw new Error("Give getToken, or both token and sessionId");
    this.token = o.token;
    this.session = o.sessionId;
    this.f = o.fetch ?? ((...a) => globalThis.fetch(...a));
  }

  private get base() { return this.o.baseUrl.replace(/\/+$/, ""); }

  /** The conversation this client is in (known once the first token is obtained). */
  get sessionId(): string | undefined { return this.session; }

  private async refresh(): Promise<void> {
    if (!this.o.getToken) throw new NorthCXError(401, "token_expired", "The chat session expired");
    const g = await this.o.getToken(this.session ? { sessionId: this.session } : undefined);
    if (!g?.token || !g.sessionId) throw new NorthCXError(0, "bad_token", "The token service returned no token");
    this.token = g.token; this.session = g.sessionId; this.expiresAt = g.expiresAt;
  }

  /** Gets a token if there is none, or it is about to expire. Call it first to learn the session id. */
  async start(): Promise<string> {
    if (!this.token || (this.o.getToken && this.expiresAt && this.expiresAt * 1000 - Date.now() < 30_000)) await this.refresh();
    return this.session as string;
  }

  private async raw(path: string, init: RequestInit & { signal?: AbortSignal } = {}, timeout = true): Promise<Response> {
    await this.start();
    const headers = new Headers(init.headers);
    headers.set("authorization", `Bearer ${this.token}`);
    const ctl = new AbortController();
    const timer = timeout ? setTimeout(() => ctl.abort(), this.o.timeoutMs ?? 30_000) : undefined;
    if (init.signal?.aborted) ctl.abort();
    init.signal?.addEventListener("abort", () => ctl.abort(), { once: true });
    try {
      return await this.f(`${this.base}${path}`, { ...init, headers, signal: ctl.signal });
    } finally { if (timer) clearTimeout(timer); }
  }

  private static async fail(res: Response): Promise<NorthCXError> {
    const body = await res.json().catch(() => ({}));
    const ra = Number(res.headers.get("retry-after"));
    return new NorthCXError(res.status, body?.error?.code ?? "error", body?.error?.message ?? `Request failed (${res.status})`, Number.isFinite(ra) && ra > 0 ? ra : undefined);
  }

  /** One request with token renewal (once) and, for requests that are safe to repeat, retries with back-off. */
  private async call(path: string, init: RequestInit & { signal?: AbortSignal } = {}, repeatable = false): Promise<Response> {
    const attempts = repeatable ? (this.o.retries ?? 2) + 1 : 1;
    let renewed = false;
    for (let n = 0; ; n++) {
      let res: Response | undefined, err: unknown;
      try { res = await this.raw(path, init); } catch (e) { err = e; }
      if (res?.ok) return res;
      if (res && res.status === 401 && !renewed && this.o.getToken) {
        const e = await NorthCXClient.fail(res.clone());
        if (e.code === "token_expired" || e.code === "unauthorized") { renewed = true; await this.refresh(); n--; continue; }
      }
      const e = res ? await NorthCXClient.fail(res) : err;
      const transient = res ? [429, 502, 503, 504].includes(res.status) : !(err instanceof DOMException && err.name === "AbortError" && init.signal?.aborted);
      if (!transient || n + 1 >= attempts) throw e instanceof NorthCXError ? e : new NorthCXError(0, "network", "Could not reach the service");
      const wait = e instanceof NorthCXError && e.retryAfter ? e.retryAfter * 1000 : Math.min(500 * 2 ** n, 8000) * (0.5 + Math.random() / 2);
      await sleep(wait, init.signal);
    }
  }

  /** Sends a message and resolves with the final reply. Replies stream in through `onDelta` when the runtime supports it. */
  async send(message: string, opts: SendOptions = {}): Promise<ChatReply> {
    const sid = await this.start();
    const body = JSON.stringify({ sessionId: sid, message, ...(opts.attachments?.length ? { attachments: opts.attachments } : {}) });
    const agent = encodeURIComponent(this.o.agent);
    const canStream = opts.stream ?? (typeof ReadableStream !== "undefined" && !!(opts.onDelta || opts.onProgress));
    if (!canStream) {
      const res = await this.call(`/v1/agents/${agent}/chat`, { method: "POST", headers: { "content-type": "application/json", "idempotency-key": newKey() }, body, signal: opts.signal }, true);
      return (await res.json()) as ChatReply;
    }
    const res = await this.call(`/v1/agents/${agent}/chat/stream`, { method: "POST", headers: { "content-type": "application/json" }, body, signal: opts.signal });
    if (!res.body) return (await res.json()) as ChatReply;
    for await (const [ev, data] of NorthCXClient.events(res.body)) {
      const d = data as Record<string, unknown>;
      if (ev === "progress" && d.type === "tool") opts.onProgress?.(String(d.name));
      else if (ev === "delta") opts.onDelta?.(String(d.text));
      else if (ev === "done") return d as unknown as ChatReply;
      else if (ev === "error") throw new NorthCXError(500, String(d.code ?? "internal"), String(d.message ?? "The reply failed"));
    }
    throw new NorthCXError(502, "interrupted", "The connection closed before the reply finished");
  }

  /** Server-sent events from a byte stream. */
  static async *events(body: ReadableStream<Uint8Array>): AsyncGenerator<[string, unknown]> {
    const reader = body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      buf += dec.decode(value, { stream: !done });
      let i: number;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const ev = /^event: (.*)$/m.exec(block)?.[1];
        const data = /^data: (.*)$/m.exec(block)?.[1];
        if (ev && data) { try { yield [ev, JSON.parse(data)]; } catch { /* a malformed event is skipped */ } }
      }
      if (done) return;
    }
  }

  /** Uploads one picture, PDF or text file. Pass the returned `id` in `send(..., { attachments: [id] })`. */
  async upload(file: Blob, name?: string): Promise<AttachmentInfo> {
    const sid = await this.start();
    const filename = name ?? (file as File).name ?? "file";
    const res = await this.call(`/v1/sessions/${encodeURIComponent(sid)}/attachments?filename=${encodeURIComponent(filename)}`, { method: "PUT", headers: { "content-type": "application/octet-stream" }, body: file });
    return (await res.json()) as AttachmentInfo;
  }

  /** Messages that arrive outside a request: a teammate's replies, results of approvals. */
  async messages(after = 0): Promise<IncomingMessage[]> {
    const sid = await this.start();
    const res = await this.call(`/v1/sessions/${encodeURIComponent(sid)}/outbox?after=${after}`, {}, true);
    return ((await res.json()) as { messages: IncomingMessage[] }).messages;
  }

  /** Calls `onMessage` for each new incoming message, polling politely (slower when the tab is hidden or the service is struggling). Returns a function that stops it. */
  watch(onMessage: (m: IncomingMessage) => void, opts: { intervalMs?: number; after?: number; onError?: (e: unknown) => void } = {}): () => void {
    let stopped = false, after = opts.after ?? 0, failures = 0;
    const base = opts.intervalMs ?? 3000;
    const stop = () => { stopped = true; this.watchers.delete(stop); };
    this.watchers.add(stop);
    (async () => {
      while (!stopped) {
        const hidden = typeof document !== "undefined" && document.hidden;
        await sleep(Math.min(base * (hidden ? 5 : 1) * 2 ** Math.min(failures, 4), 60_000)).catch(() => undefined);
        if (stopped) return;
        try {
          for (const m of await this.messages(after)) { after = Math.max(after, m.id); onMessage(m); }
          failures = 0;
        } catch (e) { failures++; opts.onError?.(e); }
      }
    })();
    return stop;
  }

  /** Rates the conversation from 1 to 5. */
  async rate(rating: number, comment = ""): Promise<void> {
    const sid = await this.start();
    await this.call(`/v1/sessions/${encodeURIComponent(sid)}/feedback`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rating, comment }) });
  }

  /** Stops background polling. */
  close(): void { for (const s of [...this.watchers]) s(); }
}
