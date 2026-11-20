// src/client.ts
var e = class extends Error {
	constructor(e, t, n, r) {
		super(n), this.status = e, this.code = t, this.retryAfter = r, this.name = "NorthCXError";
	}
}, t = (e, t) => new Promise((n, r) => {
	let i = setTimeout(n, e);
	t?.addEventListener("abort", () => {
		clearTimeout(i), r(new DOMException("Aborted", "AbortError"));
	}, { once: !0 });
}), n = () => globalThis.crypto?.randomUUID?.() ?? `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`, r = class r {
	constructor(e) {
		if (this.o = e, this.watchers = /* @__PURE__ */ new Set(), !e.baseUrl || !e.agent) throw Error("baseUrl and agent are required");
		if (!e.getToken && !(e.token && e.sessionId)) throw Error("Give getToken, or both token and sessionId");
		this.token = e.token, this.session = e.sessionId, this.f = e.fetch ?? ((...e) => globalThis.fetch(...e));
	}
	get base() {
		return this.o.baseUrl.replace(/\/+$/, "");
	}
	get sessionId() {
		return this.session;
	}
	async refresh() {
		if (!this.o.getToken) throw new e(401, "token_expired", "The chat session expired");
		let t = await this.o.getToken(this.session ? { sessionId: this.session } : void 0);
		if (!t?.token || !t.sessionId) throw new e(0, "bad_token", "The token service returned no token");
		this.token = t.token, this.session = t.sessionId, this.expiresAt = t.expiresAt;
	}
	async start() {
		return (!this.token || this.o.getToken && this.expiresAt && this.expiresAt * 1e3 - Date.now() < 3e4) && await this.refresh(), this.session;
	}
	async raw(e, t = {}, n = !0) {
		await this.start();
		let r = new Headers(t.headers);
		r.set("authorization", `Bearer ${this.token}`);
		let i = new AbortController(), a = n ? setTimeout(() => i.abort(), this.o.timeoutMs ?? 3e4) : void 0;
		t.signal?.aborted && i.abort(), t.signal?.addEventListener("abort", () => i.abort(), { once: !0 });
		try {
			return await this.f(`${this.base}${e}`, {
				...t,
				headers: r,
				signal: i.signal
			});
		} finally {
			a && clearTimeout(a);
		}
	}
	static async fail(t) {
		let n = await t.json().catch(() => ({})), r = Number(t.headers.get("retry-after"));
		return new e(t.status, n?.error?.code ?? "error", n?.error?.message ?? `Request failed (${t.status})`, Number.isFinite(r) && r > 0 ? r : void 0);
	}
	async call(n, i = {}, a = !1) {
		let o = a ? (this.o.retries ?? 2) + 1 : 1, s = !1;
		for (let a = 0;; a++) {
			let c, l;
			try {
				c = await this.raw(n, i);
			} catch (e) {
				l = e;
			}
			if (c?.ok) return c;
			if (c && c.status === 401 && !s && this.o.getToken) {
				let e = await r.fail(c.clone());
				if (e.code === "token_expired" || e.code === "unauthorized") {
					s = !0, await this.refresh(), a--;
					continue;
				}
			}
			let u = c ? await r.fail(c) : l;
			if (!(c ? [
				429,
				502,
				503,
				504
			].includes(c.status) : !(l instanceof DOMException && l.name === "AbortError" && i.signal?.aborted)) || a + 1 >= o) throw u instanceof e ? u : new e(0, "network", "Could not reach the service");
			await t(u instanceof e && u.retryAfter ? u.retryAfter * 1e3 : Math.min(500 * 2 ** a, 8e3) * (.5 + Math.random() / 2), i.signal);
		}
	}
	async send(t, i = {}) {
		let a = await this.start(), o = JSON.stringify({
			sessionId: a,
			message: t,
			...i.attachments?.length ? { attachments: i.attachments } : {}
		}), s = encodeURIComponent(this.o.agent);
		if (!(i.stream ?? (typeof ReadableStream < "u" && !!(i.onDelta || i.onProgress)))) return await (await this.call(`/v1/agents/${s}/chat`, {
			method: "POST",
			headers: {
				"content-type": "application/json",
				"idempotency-key": n()
			},
			body: o,
			signal: i.signal
		}, !0)).json();
		let c = await this.call(`/v1/agents/${s}/chat/stream`, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: o,
			signal: i.signal
		});
		if (!c.body) return await c.json();
		for await (let [t, n] of r.events(c.body)) {
			let r = n;
			if (t === "progress" && r.type === "tool") i.onProgress?.(String(r.name));
			else if (t === "delta") i.onDelta?.(String(r.text));
			else if (t === "done") return r;
			else if (t === "error") throw new e(500, String(r.code ?? "internal"), String(r.message ?? "The reply failed"));
		}
		throw new e(502, "interrupted", "The connection closed before the reply finished");
	}
	static async *events(e) {
		let t = e.getReader(), n = new TextDecoder(), r = "";
		for (;;) {
			let { done: e, value: i } = await t.read();
			r += n.decode(i, { stream: !e });
			let a;
			for (; (a = r.indexOf("\n\n")) >= 0;) {
				let e = r.slice(0, a);
				r = r.slice(a + 2);
				let t = /^event: (.*)$/m.exec(e)?.[1], n = /^data: (.*)$/m.exec(e)?.[1];
				if (t && n) try {
					yield [t, JSON.parse(n)];
				} catch {}
			}
			if (e) return;
		}
	}
	async upload(e, t) {
		let n = await this.start(), r = t ?? e.name ?? "file";
		return await (await this.call(`/v1/sessions/${encodeURIComponent(n)}/attachments?filename=${encodeURIComponent(r)}`, {
			method: "PUT",
			headers: { "content-type": "application/octet-stream" },
			body: e
		})).json();
	}
	async messages(e = 0) {
		let t = await this.start();
		return (await (await this.call(`/v1/sessions/${encodeURIComponent(t)}/outbox?after=${e}`, {}, !0)).json()).messages;
	}
	watch(e, n = {}) {
		let r = !1, i = n.after ?? 0, a = 0, o = n.intervalMs ?? 3e3, s = () => {
			r = !0, this.watchers.delete(s);
		};
		return this.watchers.add(s), (async () => {
			for (; !r;) {
				let s = typeof document < "u" && document.hidden;
				if (await t(Math.min(o * (s ? 5 : 1) * 2 ** Math.min(a, 4), 6e4)).catch(() => void 0), r) return;
				try {
					for (let t of await this.messages(i)) i = Math.max(i, t.id), e(t);
					a = 0;
				} catch (e) {
					a++, n.onError?.(e);
				}
			}
		})(), s;
	}
	async rate(e, t = "") {
		let n = await this.start();
		await this.call(`/v1/sessions/${encodeURIComponent(n)}/feedback`, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({
				rating: e,
				comment: t
			})
		});
	}
	close() {
		for (let e of [...this.watchers]) e();
	}
}, i, a = "\n:host{--p:var(--northcx-primary,#2f5bea);--bg:var(--northcx-bg,#fff);--tx:var(--northcx-text,#1b1f2a);--mu:#667085;--bd:#d8dce5;--r:var(--northcx-radius,12px);display:block;font:14px/1.45 var(--northcx-font,system-ui,sans-serif);color:var(--tx);max-width:100%}\n@media (prefers-color-scheme:dark){:host{--bg:var(--northcx-bg,#171a21);--tx:var(--northcx-text,#e8eaf0);--bd:#333948;--mu:#9aa3b5}}\n.box{display:flex;flex-direction:column;height:var(--northcx-height,480px);max-height:100vh;background:var(--bg);border:1px solid var(--bd);border-radius:var(--r);overflow:hidden}\nheader{padding:10px 14px;border-bottom:1px solid var(--bd);font-weight:600}\n.log{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}\n.m{max-width:85%;padding:8px 12px;border-radius:var(--r);white-space:pre-wrap;overflow-wrap:anywhere}\n.m.me{align-self:flex-end;background:var(--p);color:#fff}.m.bot{align-self:flex-start;border:1px solid var(--bd)}.m.person{align-self:flex-start;border:1px solid var(--p)}\n.m small{display:block;color:var(--mu);font-size:11px}.me small{color:#e8edff}\n.note{align-self:center;color:var(--mu);font-size:12px}\n.err{align-self:stretch;color:#b42318;font-size:13px}\nform{display:flex;gap:6px;padding:8px;border-top:1px solid var(--bd);align-items:flex-end}\ntextarea{flex:1;resize:none;border:1px solid var(--bd);border-radius:8px;padding:8px;font:inherit;color:inherit;background:transparent;min-height:38px;max-height:120px}\nbutton{font:inherit;border:1px solid var(--bd);background:transparent;color:inherit;border-radius:8px;padding:8px 12px;cursor:pointer}\nbutton.go{background:var(--p);border-color:var(--p);color:#fff}button:disabled{opacity:.5;cursor:default}\n:focus-visible{outline:2px solid var(--p);outline-offset:2px}\n.rate{display:flex;gap:4px;justify-content:center;padding:6px;border-top:1px solid var(--bd);align-items:center;font-size:12px;color:var(--mu)}\n.files{padding:0 12px 4px;font-size:12px;color:var(--mu)}\ninput[type=file]{position:absolute;width:1px;height:1px;opacity:0}\n", o = class extends HTMLElement {
	constructor(...e) {
		super(...e), this.pending = [], this.busy = !1, this.rated = !1;
	}
	configure(e) {
		this.opts = e, this.client?.close(), this.client = void 0, this.isConnected && this.connect();
	}
	connectedCallback() {
		if (this.root) return;
		this.root = this.attachShadow({ mode: "open" });
		let e = this.getAttribute("title") || "Chat with us";
		if (this.root.innerHTML = `<style>${a}</style><div class="box"><header></header><div class="log" role="log" aria-live="polite" aria-label="Conversation" tabindex="0"></div>
      <div class="files" hidden></div><div role="status" class="note" hidden></div>
      <form><label class="attach" hidden><button type="button" class="paperclip" aria-label="Attach a file">\u{1F4CE}</button><input type="file" multiple accept="image/png,image/jpeg,image/gif,image/webp,application/pdf,text/plain"></label>
      <textarea rows="1" aria-label="Your message"></textarea><button class="go" type="submit">Send</button></form><div class="rate" hidden></div></div>`, this.root.querySelector("header").textContent = e, this.log = this.root.querySelector(".log"), this.input = this.root.querySelector("textarea"), this.input.placeholder = this.getAttribute("placeholder") || "Type a message", this.status = this.root.querySelector("[role=status]"), this.sendBtn = this.root.querySelector(".go"), this.fileList = this.root.querySelector(".files"), this.root.querySelector("form").addEventListener("submit", (e) => {
			e.preventDefault(), this.submit();
		}), this.input.addEventListener("keydown", (e) => {
			e.key === "Enter" && !e.shiftKey && !e.isComposing && (e.preventDefault(), this.submit());
		}), this.hasAttribute("attachments")) {
			let e = this.root.querySelector(".attach"), t = e.querySelector("input");
			e.hidden = !1, e.querySelector("button").addEventListener("click", () => t.click()), t.addEventListener("change", () => {
				this.attach(t.files), t.value = "";
			});
		}
		this.connect();
	}
	disconnectedCallback() {
		this.stopWatch?.(), this.client?.close(), this.client = void 0;
	}
	attributeChangedCallback() {
		this.isConnected && this.root && (this.client?.close(), this.client = void 0, this.connect());
	}
	connect() {
		let t = this.opts?.baseUrl ?? this.getAttribute("base-url") ?? "", n = this.opts?.agent ?? this.getAttribute("agent") ?? "", i = this.getAttribute("token-url"), a = this.opts?.getToken;
		if (!a && i) {
			let t = this.getAttribute("credentials") ?? "same-origin";
			a = async (n) => {
				let r = await fetch(i, {
					method: "POST",
					credentials: t,
					headers: { "content-type": "application/json" },
					body: JSON.stringify(n ?? {})
				});
				if (!r.ok) throw new e(r.status, "token_service", "Could not start the chat");
				return await r.json();
			};
		}
		try {
			this.client = new r({
				...this.opts,
				baseUrl: t,
				agent: n,
				getToken: a
			});
		} catch (e) {
			this.line("err", e instanceof Error ? e.message : "Chat is not set up");
			return;
		}
		this.stopWatch?.(), this.stopWatch = this.client.watch((e) => {
			e.kind === "person_reply" && e.reply ? this.line("person", e.reply, "Teammate") : e.reply && this.line("bot", e.reply);
		}, { intervalMs: Number(this.getAttribute("poll-ms")) || 4e3 });
	}
	line(e, t, n) {
		let r = document.createElement("div");
		if (r.className = e === "note" ? "note" : e === "err" ? "err" : `m ${e}`, n) {
			let e = document.createElement("small");
			e.textContent = n, r.append(e);
		}
		return r.append(document.createTextNode(t)), this.log.append(r), this.log.scrollTop = this.log.scrollHeight, r;
	}
	setStatus(e) {
		this.status.hidden = !e, this.status.textContent = e ?? "";
	}
	async attach(e) {
		if (e?.length && this.client) try {
			for (let t of Array.from(e).slice(0, 5 - this.pending.length)) this.pending.push(await this.client.upload(t));
			this.fileList.hidden = !this.pending.length, this.fileList.textContent = "Attached: " + this.pending.map((e) => e.name).join(", ");
		} catch (e) {
			this.line("err", e instanceof Error ? e.message : "The file could not be attached");
		}
	}
	async submit() {
		let t = this.input.value.trim();
		if (!t || this.busy || !this.client) return;
		let n = this.pending;
		this.pending = [], this.fileList.hidden = !0, this.input.value = "", this.busy = !0, this.sendBtn.disabled = !0, this.line("me", n.length ? `${t}\n\u{1F4CE} ${n.map((e) => e.name).join(", ")}` : t), this.setStatus("Thinking…");
		let r = { el: null };
		try {
			let e = await this.client.send(t, {
				attachments: n.map((e) => e.id),
				onProgress: () => this.setStatus("Looking into it…"),
				onDelta: (e) => {
					this.setStatus(null), r.el = r.el ?? this.line("bot", ""), r.el.append(document.createTextNode(e));
				}
			});
			r.el ? r.el.replaceChildren(document.createTextNode(e.reply)) : e.reply && this.line("bot", e.reply), e.status === "escalated" && this.line("note", "A teammate has been asked to take over. You can keep writing here."), e.status === "needs_approval" && this.line("note", "This needs a teammate's approval. We will tell you here when it is done."), e.reply && this.maybeRating(), this.dispatchEvent(new CustomEvent("northcx:reply", { detail: e }));
		} catch (t) {
			r.el?.remove(), this.line("err", t instanceof e && t.code === "attachment_not_accepted" ? t.message : t instanceof e && t.status === 429 ? "You are sending messages too quickly. Please wait a moment." : "Sorry, that did not go through. Please try again."), this.dispatchEvent(new CustomEvent("northcx:error", { detail: t }));
		} finally {
			this.busy = !1, this.sendBtn.disabled = !1, this.setStatus(null), this.input.focus();
		}
	}
	maybeRating() {
		if (!this.hasAttribute("rating") || this.rated) return;
		let e = this.root.querySelector(".rate");
		e.hidden = !1, e.replaceChildren(document.createTextNode("How are we doing?"));
		for (let t = 1; t <= 5; t++) {
			let n = document.createElement("button");
			n.type = "button", n.textContent = String(t), n.setAttribute("aria-label", `${t} out of 5`), n.addEventListener("click", async () => {
				try {
					await this.client?.rate(t), this.rated = !0, e.textContent = "Thanks for your feedback.";
				} catch {
					e.textContent = "Could not send your rating.";
				}
			}), e.append(n);
		}
	}
};
i = o, i.observedAttributes = [
	"base-url",
	"agent",
	"token-url"
], typeof customElements < "u" && !customElements.get("northcx-chat") && customElements.define("northcx-chat", o);
export { o as NorthCXChat, r as NorthCXClient, e as NorthCXError };
