import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../src/widget";
import type { NorthCXChat } from "../src/widget";
import { GRANT, REPLY, fakeFetch, json, sse } from "./helpers";

const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); await new Promise((r) => setTimeout(r, 0)); };

function mount(attrs: Record<string, string> = {}, fetcher?: ReturnType<typeof fakeFetch>) {
  const fx = fetcher ?? fakeFetch(json({ messages: [] }));
  vi.stubGlobal("fetch", fx.f);
  const el = document.createElement("northcx-chat") as NorthCXChat;
  for (const [k, v] of Object.entries({ "base-url": "https://api.example.com", agent: "support", "poll-ms": "100000", ...attrs })) el.setAttribute(k, v);
  el.configure({ token: "ncxc_abc", sessionId: "web-1", fetch: fx.f });
  document.body.append(el);
  return { el, fx, root: el.shadowRoot!, log: () => el.shadowRoot!.querySelector(".log")!, type: (t: string) => {
    const ta = el.shadowRoot!.querySelector("textarea")!; ta.value = t;
    ta.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  } };
}

beforeEach(() => { document.body.innerHTML = ""; });
afterEach(() => { vi.unstubAllGlobals(); });

describe("<northcx-chat>", () => {
  it("is accessible: a live conversation log, labelled fields", () => {
    const { root } = mount({ title: "Help" });
    expect(root.querySelector("header")!.textContent).toBe("Help");
    expect(root.querySelector(".log")!.getAttribute("role")).toBe("log");
    expect(root.querySelector(".log")!.getAttribute("aria-live")).toBe("polite");
    expect(root.querySelector("textarea")!.getAttribute("aria-label")).toBeTruthy();
  });
  it("sends on Enter and shows the reply", async () => {
    const fx = fakeFetch(sse(["delta", { text: "Hel" }], ["delta", { text: "lo!" }], ["done", REPLY]));
    const w = mount({}, fx);
    w.type("hi there");
    await flush();
    const texts = Array.from(w.log().querySelectorAll(".m")).map((m) => m.textContent);
    expect(texts).toEqual(["hi there", "Hello!"]);
    expect(fx.calls.some((c) => c.url.endsWith("/chat/stream"))).toBe(true);
    expect((w.root.querySelector("textarea") as HTMLTextAreaElement).value).toBe("");
  });
  it("never turns what anyone writes into markup", async () => {
    const evil = '<img src=x onerror="window.pwned=1"><script>window.pwned=1</script>';
    const fx = fakeFetch(sse(["done", { ...REPLY, reply: evil }]));
    const w = mount({}, fx);
    w.type(evil);
    await flush();
    expect(w.log().querySelector("img, script")).toBeNull();
    expect(Array.from(w.log().querySelectorAll(".m")).map((m) => m.textContent)).toEqual([evil, evil]);
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });
  it("does not send an empty message or a second one while waiting", async () => {
    const fx = fakeFetch(sse(["done", REPLY]));
    const w = mount({}, fx);
    w.type("   ");
    await flush();
    expect(fx.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });
  it("tells the customer when a teammate is taking over, and shows the teammate's replies", async () => {
    vi.useFakeTimers();
    const fx = fakeFetch(sse(["done", { ...REPLY, status: "escalated", reply: "I'm connecting you with a teammate." }]));
    const w = mount({ "poll-ms": "1000" }, fx);
    w.type("person please");
    await vi.advanceTimersByTimeAsync(10);
    expect(w.log().textContent).toContain("A teammate has been asked to take over");
    fx.calls.length = 0;
    const msgs = fakeFetch(json({ messages: [{ id: 1, kind: "person_reply", createdAt: 1, reply: "Hi, Sam here", by: "Sam" }] }));
    w.el.configure({ token: "ncxc_abc", sessionId: "web-1", fetch: msgs.f });
    await vi.advanceTimersByTimeAsync(1200);
    vi.useRealTimers();
    expect(w.log().querySelector(".m.person")!.textContent).toContain("Hi, Sam here");
    expect(w.log().querySelector(".m.person small")!.textContent).toBe("Teammate");
  });
  it("shows a plain apology, not an error dump, when sending fails", async () => {
    const fx = fakeFetch(new TypeError("network down"));
    const w = mount({}, fx);
    w.type("hi");
    await flush();
    expect(w.log().querySelector(".err")!.textContent).toBe("Sorry, that did not go through. Please try again.");
  });
  it("draws nothing for a reply that a person has not approved yet, and shows the approved text when it arrives", async () => {
    vi.useFakeTimers();
    const fx = fakeFetch(sse(["done", { ...REPLY, reply: "", status: "in_review" }]));
    const w = mount({ rating: "", "poll-ms": "1000" }, fx);
    w.type("where is my order?");
    await vi.advanceTimersByTimeAsync(10);
    expect(Array.from(w.log().querySelectorAll(".m")).map((m) => m.textContent)).toEqual(["where is my order?"]);   // no empty bubble
    expect(w.log().querySelector(".note, .err")).toBeNull();                                                          // and no notice either
    expect((w.root.querySelector(".rate") as HTMLElement).hidden).toBe(true);
    const later = fakeFetch(json({ messages: [{ id: 1, kind: "shadow_reply", createdAt: 1, reply: "It ships Monday." }] }));
    w.el.configure({ token: "ncxc_abc", sessionId: "web-1", fetch: later.f });
    await vi.advanceTimersByTimeAsync(1200);
    vi.useRealTimers();
    expect(Array.from(w.log().querySelectorAll(".m")).map((m) => m.textContent)).toEqual(["where is my order?", "It ships Monday."]);
  });
  it("shows the options the agent offered as buttons, sends the chosen words like a typed message, and clears them", async () => {
    const fx = fakeFetch(sse(["done", { ...REPLY, reply: "Which order?", choices: ["1042", "<b>1043</b>"] }]), sse(["done", { ...REPLY, reply: "It shipped." }]));
    const w = mount({}, fx);
    w.type("where is my order?");
    await flush();
    const group = w.root.querySelector('[role=group][aria-label="Quick answers"]')!;
    const buttons = Array.from(group.querySelectorAll("button"));
    expect(buttons.map((b) => b.textContent)).toEqual(["1042", "<b>1043</b>"]);       // as text, never as markup
    expect(group.querySelector("b")).toBeNull();
    buttons[0].click();
    await flush();
    const sent = fx.calls.filter((c) => c.method === "POST" && c.url.endsWith("/chat/stream")).map((c) => JSON.parse(c.body!).message);
    expect(sent).toEqual(["where is my order?", "1042"]);
    expect(w.root.querySelector(".opts")).toBeNull();
    expect(Array.from(w.log().querySelectorAll(".m")).map((m) => m.textContent)).toEqual(["where is my order?", "Which order?", "1042", "It shipped."]);
  });
  it("takes the buttons away when the customer types an answer instead", async () => {
    const fx = fakeFetch(sse(["done", { ...REPLY, reply: "Yes or no?", choices: ["Yes", "No"] }]), sse(["done", REPLY]));
    const w = mount({}, fx);
    w.type("hello");
    await flush();
    expect(w.root.querySelector(".opts")).not.toBeNull();
    w.type("maybe");
    await flush();
    expect(w.root.querySelector(".opts")).toBeNull();
  });
  it("offers attachments only when asked, and rating once a reply has arrived", async () => {
    expect(mount().root.querySelector(".attach")!.hasAttribute("hidden")).toBe(true);
    document.body.innerHTML = "";
    const fx = fakeFetch(sse(["done", REPLY]), json({ saved: true }));
    const w = mount({ attachments: "", rating: "" }, fx);
    expect(w.root.querySelector(".attach")!.hasAttribute("hidden")).toBe(false);
    expect(w.root.querySelector(".rate")!.hasAttribute("hidden")).toBe(true);
    w.type("hi");
    await flush();
    const bar = w.root.querySelector(".rate") as HTMLElement;
    expect(bar.hidden).toBe(false);
    (bar.querySelectorAll("button")[3] as HTMLButtonElement).click();
    await flush();
    expect(bar.textContent).toContain("Thanks");
    expect(fx.calls.some((c) => c.url.includes("/feedback") && JSON.parse(c.body!).rating === 4)).toBe(true);
  });
  it("gets its token from your server when given token-url", async () => {
    const fx = fakeFetch((c) => (c.url === "/chat-token" ? json(GRANT) : c.url.includes("/outbox") ? json({ messages: [] }) : json(REPLY)));
    vi.stubGlobal("fetch", fx.f);
    const el = document.createElement("northcx-chat") as NorthCXChat;
    el.setAttribute("base-url", "https://api.example.com"); el.setAttribute("agent", "support"); el.setAttribute("token-url", "/chat-token"); el.setAttribute("poll-ms", "100000");
    document.body.append(el);
    const ta = el.shadowRoot!.querySelector("textarea")!;
    ta.value = "hello";
    ta.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await flush();
    const posts = fx.calls.filter((c) => c.url === "/chat-token");
    expect(posts).toHaveLength(1);
    expect(fx.calls.find((c) => c.url.includes("/v1/agents/"))!.headers["authorization"]).toBe(`Bearer ${GRANT.token}`);
  });
  it("says so when it is not set up, instead of failing silently", () => {
    const el = document.createElement("northcx-chat");
    vi.stubGlobal("fetch", fakeFetch(json({})).f);
    document.body.append(el);
    expect(el.shadowRoot!.querySelector(".err")!.textContent).toMatch(/baseUrl|agent|getToken/);
  });
});
