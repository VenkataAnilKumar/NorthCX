/**
 * <northcx-chat> - a drop-in chat window.
 *
 *   <script src="https://api.example.com/sdk/northcx-widget.js"></script>
 *   <northcx-chat base-url="https://api.example.com" agent="support" token-url="/chat-token" attachments rating></northcx-chat>
 *
 * `token-url` is an endpoint on YOUR server that mints a chat token (it holds the channel key) and answers {token, sessionId, expiresAt}.
 * Everything is rendered with textContent, so nothing a customer, an agent or a teammate writes can inject markup.
 * Style it with CSS variables: --northcx-primary, --northcx-bg, --northcx-text, --northcx-radius, --northcx-font.
 */
import { NorthCXClient, NorthCXError, type AttachmentInfo, type ChatReply, type ClientOptions, type TokenGrant } from "./client";

const CSS = `
:host{--p:var(--northcx-primary,#2f5bea);--bg:var(--northcx-bg,#fff);--tx:var(--northcx-text,#1b1f2a);--mu:#667085;--bd:#d8dce5;--r:var(--northcx-radius,12px);display:block;font:14px/1.45 var(--northcx-font,system-ui,sans-serif);color:var(--tx);max-width:100%}
@media (prefers-color-scheme:dark){:host{--bg:var(--northcx-bg,#171a21);--tx:var(--northcx-text,#e8eaf0);--bd:#333948;--mu:#9aa3b5}}
.box{display:flex;flex-direction:column;height:var(--northcx-height,480px);max-height:100vh;background:var(--bg);border:1px solid var(--bd);border-radius:var(--r);overflow:hidden}
header{padding:10px 14px;border-bottom:1px solid var(--bd);font-weight:600}
.log{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}
.m{max-width:85%;padding:8px 12px;border-radius:var(--r);white-space:pre-wrap;overflow-wrap:anywhere}
.m.me{align-self:flex-end;background:var(--p);color:#fff}.m.bot{align-self:flex-start;border:1px solid var(--bd)}.m.person{align-self:flex-start;border:1px solid var(--p)}
.m small{display:block;color:var(--mu);font-size:11px}.me small{color:#e8edff}
.note{align-self:center;color:var(--mu);font-size:12px}
.err{align-self:stretch;color:#b42318;font-size:13px}
form{display:flex;gap:6px;padding:8px;border-top:1px solid var(--bd);align-items:flex-end}
textarea{flex:1;resize:none;border:1px solid var(--bd);border-radius:8px;padding:8px;font:inherit;color:inherit;background:transparent;min-height:38px;max-height:120px}
button{font:inherit;border:1px solid var(--bd);background:transparent;color:inherit;border-radius:8px;padding:8px 12px;cursor:pointer}
button.go{background:var(--p);border-color:var(--p);color:#fff}button:disabled{opacity:.5;cursor:default}
:focus-visible{outline:2px solid var(--p);outline-offset:2px}
.rate{display:flex;gap:4px;justify-content:center;padding:6px;border-top:1px solid var(--bd);align-items:center;font-size:12px;color:var(--mu)}
.files{padding:0 12px 4px;font-size:12px;color:var(--mu)}
.opts{align-self:flex-start;display:flex;flex-wrap:wrap;gap:6px}.opts button{border-radius:999px;border-color:var(--p);color:var(--p)}
input[type=file]{position:absolute;width:1px;height:1px;opacity:0}
`;

type Line = { who: "me" | "bot" | "person" | "note" | "err"; text: string };

export class NorthCXChat extends HTMLElement {
  static observedAttributes = ["base-url", "agent", "token-url"];
  private client?: NorthCXClient;
  private opts?: Partial<ClientOptions>;
  private root!: ShadowRoot;
  private log!: HTMLElement;
  private input!: HTMLTextAreaElement;
  private status!: HTMLElement;
  private sendBtn!: HTMLButtonElement;
  private fileList!: HTMLElement;
  private pending: AttachmentInfo[] = [];
  private stopWatch?: () => void;
  private busy = false;

  /** Configure from code instead of attributes, for example with your own `getToken`. */
  configure(opts: Partial<ClientOptions>): void { this.opts = opts; this.client?.close(); this.client = undefined; if (this.isConnected) this.connect(); }

  connectedCallback(): void {
    if (this.root) return;
    this.root = this.attachShadow({ mode: "open" });
    const title = this.getAttribute("title") || "Chat with us";
    this.root.innerHTML = `<style>${CSS}</style><div class="box"><header></header><div class="log" role="log" aria-live="polite" aria-label="Conversation" tabindex="0"></div>
      <div class="files" hidden></div><div role="status" class="note" hidden></div>
      <form><label class="attach" hidden><button type="button" class="paperclip" aria-label="Attach a file">\u{1F4CE}</button><input type="file" multiple accept="image/png,image/jpeg,image/gif,image/webp,application/pdf,text/plain"></label>
      <textarea rows="1" aria-label="Your message"></textarea><button class="go" type="submit">Send</button></form><div class="rate" hidden></div></div>`;
    (this.root.querySelector("header") as HTMLElement).textContent = title;
    this.log = this.root.querySelector(".log") as HTMLElement;
    this.input = this.root.querySelector("textarea") as HTMLTextAreaElement;
    this.input.placeholder = this.getAttribute("placeholder") || "Type a message";
    this.status = this.root.querySelector("[role=status]") as HTMLElement;
    this.sendBtn = this.root.querySelector(".go") as HTMLButtonElement;
    this.fileList = this.root.querySelector(".files") as HTMLElement;
    const form = this.root.querySelector("form") as HTMLFormElement;
    form.addEventListener("submit", (e) => { e.preventDefault(); void this.submit(); });
    this.input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); void this.submit(); } });
    if (this.hasAttribute("attachments")) {
      const label = this.root.querySelector(".attach") as HTMLElement;
      const file = label.querySelector("input") as HTMLInputElement;
      label.hidden = false;
      label.querySelector("button")!.addEventListener("click", () => file.click());
      file.addEventListener("change", () => { void this.attach(file.files); file.value = ""; });
    }
    this.connect();
  }

  disconnectedCallback(): void { this.stopWatch?.(); this.client?.close(); this.client = undefined; }
  attributeChangedCallback(): void { if (this.isConnected && this.root) { this.client?.close(); this.client = undefined; this.connect(); } }

  private connect(): void {
    const baseUrl = this.opts?.baseUrl ?? this.getAttribute("base-url") ?? "";
    const agent = this.opts?.agent ?? this.getAttribute("agent") ?? "";
    const tokenUrl = this.getAttribute("token-url");
    let getToken = this.opts?.getToken;
    if (!getToken && tokenUrl) {
      const creds = (this.getAttribute("credentials") as RequestCredentials | null) ?? "same-origin";
      getToken = async (prev) => {
        const r = await fetch(tokenUrl, { method: "POST", credentials: creds, headers: { "content-type": "application/json" }, body: JSON.stringify(prev ?? {}) });
        if (!r.ok) throw new NorthCXError(r.status, "token_service", "Could not start the chat");
        return (await r.json()) as TokenGrant;
      };
    }
    try {
      this.client = new NorthCXClient({ ...this.opts, baseUrl, agent, getToken });
    } catch (e) { this.line("err", e instanceof Error ? e.message : "Chat is not set up"); return; }
    this.stopWatch?.();
    this.stopWatch = this.client.watch((m) => {
      if (m.kind === "person_reply" && m.reply) this.line("person", m.reply, "Teammate");
      else if (m.reply) this.line("bot", m.reply);
    }, { intervalMs: Number(this.getAttribute("poll-ms")) || 4000 });
  }

  private line(who: Line["who"], text: string, label?: string): HTMLElement {
    const el = document.createElement("div");
    el.className = who === "note" ? "note" : who === "err" ? "err" : `m ${who}`;
    if (label) { const s = document.createElement("small"); s.textContent = label; el.append(s); }
    el.append(document.createTextNode(text));
    this.log.append(el);
    this.log.scrollTop = this.log.scrollHeight;
    return el;
  }

  /** The options the agent offered, as buttons; choosing one sends its words like a typed message. */
  private offer(choices: string[]): void {
    const box = document.createElement("div");
    box.className = "opts"; box.setAttribute("role", "group"); box.setAttribute("aria-label", "Quick answers");
    for (const c of choices) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = c;
      b.addEventListener("click", () => { this.input.value = c; void this.submit(); });
      box.append(b);
    }
    this.log.append(box);
    this.log.scrollTop = this.log.scrollHeight;
  }

  private setStatus(text: string | null): void { this.status.hidden = !text; this.status.textContent = text ?? ""; }

  private async attach(list: FileList | null): Promise<void> {
    if (!list?.length || !this.client) return;
    try {
      for (const f of Array.from(list).slice(0, 5 - this.pending.length)) this.pending.push(await this.client.upload(f));
      this.fileList.hidden = !this.pending.length;
      this.fileList.textContent = "Attached: " + this.pending.map((p) => p.name).join(", ");
    } catch (e) { this.line("err", e instanceof Error ? e.message : "The file could not be attached"); }
  }

  private async submit(): Promise<void> {
    const text = this.input.value.trim();
    if (!text || this.busy || !this.client) return;
    const files = this.pending;
    this.pending = []; this.fileList.hidden = true;
    this.input.value = ""; this.busy = true; this.sendBtn.disabled = true;
    this.log.querySelector(".opts")?.remove();  // quick answers are for the last reply only
    this.line("me", files.length ? `${text}\n\u{1F4CE} ${files.map((f) => f.name).join(", ")}` : text);
    this.setStatus("Thinking…");
    const live: { el: HTMLElement | null } = { el: null };
    try {
      const r: ChatReply = await this.client.send(text, {
        attachments: files.map((f) => f.id),
        onProgress: () => this.setStatus("Looking into it…"),
        onDelta: (piece) => { this.setStatus(null); live.el = live.el ?? this.line("bot", ""); live.el.append(document.createTextNode(piece)); },
      });
      if (live.el) live.el.replaceChildren(document.createTextNode(r.reply)); else if (r.reply) this.line("bot", r.reply);  // a reply a person has not yet approved (shadow mode) is empty: no bubble
      if (r.choices?.length) this.offer(r.choices);
      if (r.status === "escalated") this.line("note", "A teammate has been asked to take over. You can keep writing here.");
      if (r.status === "needs_approval") this.line("note", "This needs a teammate's approval. We will tell you here when it is done.");
      if (r.reply) this.maybeRating();
      this.dispatchEvent(new CustomEvent("northcx:reply", { detail: r }));
    } catch (e) {
      live.el?.remove();
      this.line("err", e instanceof NorthCXError && e.code === "attachment_not_accepted" ? e.message : e instanceof NorthCXError && e.status === 429 ? "You are sending messages too quickly. Please wait a moment." : "Sorry, that did not go through. Please try again.");
      this.dispatchEvent(new CustomEvent("northcx:error", { detail: e }));
    } finally { this.busy = false; this.sendBtn.disabled = false; this.setStatus(null); this.input.focus(); }
  }

  private rated = false;
  private maybeRating(): void {
    if (!this.hasAttribute("rating") || this.rated) return;
    const bar = this.root.querySelector(".rate") as HTMLElement;
    bar.hidden = false;
    bar.replaceChildren(document.createTextNode("How are we doing?"));
    for (let n = 1; n <= 5; n++) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = String(n); b.setAttribute("aria-label", `${n} out of 5`);
      b.addEventListener("click", async () => {
        try { await this.client?.rate(n); this.rated = true; bar.textContent = "Thanks for your feedback."; } catch { bar.textContent = "Could not send your rating."; }
      });
      bar.append(b);
    }
  }
}

if (typeof customElements !== "undefined" && !customElements.get("northcx-chat")) customElements.define("northcx-chat", NorthCXChat);
