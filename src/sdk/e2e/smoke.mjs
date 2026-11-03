// Browser test of the drop-in widget from a DIFFERENT website than the API (so CORS is exercised for real).
// Needs a running NorthCX with NORTHCX_CORS_ORIGINS=http://localhost:8080 and an admin key:
//   API_URL=http://localhost:3000 ADMIN_KEY=... node e2e/smoke.mjs
import http from "node:http";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const API = process.env.API_URL ?? "http://localhost:3000";
const ADMIN = process.env.ADMIN_KEY ?? "";
const HOST = 8080;
let bad = 0;
const check = (ok, what) => { console.log(`${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) bad++; };
const admin = { authorization: `Bearer ${ADMIN}`, "content-type": "application/json" };

// a channel key, as the company's own server would hold
const ck = await (await fetch(`${API}/v1/keys`, { method: "POST", headers: admin, body: JSON.stringify({ name: `sdk-e2e-${Date.now()}`, role: "channel" }) })).json();
const channelKey = ck.secret ?? ck.key ?? ck.token;
if (!channelKey) { console.log("could not create a channel key", JSON.stringify(ck)); process.exit(1); }

// "the company's website": a page with the widget, and an endpoint that mints chat tokens with the channel key
const server = http.createServer(async (req, res) => {
  if (req.method === "POST" && req.url === "/chat-token") {
    let body = ""; for await (const c of req) body += c;
    const prev = body ? JSON.parse(body) : {};
    const r = await fetch(`${API}/v1/chat-tokens`, { method: "POST", headers: { authorization: `Bearer ${channelKey}`, "content-type": "application/json" },
      body: JSON.stringify({ customerId: "shopper-1", agent: "support", ...(prev.sessionId ? { sessionId: prev.sessionId } : {}) }) });
    res.writeHead(r.status, { "content-type": "application/json" }); res.end(await r.text()); return;
  }
  res.writeHead(200, { "content-type": "text/html" });
  res.end(`<!doctype html><title>Shop</title><body><h1>Our shop</h1>
    <script src="${API}/sdk/northcx-widget.js"></script>
    <northcx-chat base-url="${API}" agent="support" token-url="/chat-token" rating poll-ms="1000" title="Help"></northcx-chat></body>`);
});
await new Promise((r) => server.listen(HOST, r));

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error" && !/favicon/.test(m.text())) errors.push(m.text()); });
await page.goto(`http://localhost:${HOST}/`);
const chat = page.locator("northcx-chat");
const say = async (t) => { await chat.locator("textarea").fill(t); await chat.locator("textarea").press("Enter"); };
const texts = async () => chat.locator(".m").allInnerTexts();

await say("where is order 1042?");
await chat.locator(".m.bot").first().waitFor();
check((await texts()).some((t) => /1042/.test(t) && /delivered/i.test(t)), "a customer on another website gets an answer (cross-origin)");
await chat.locator(".rate button").nth(4).waitFor();
await chat.locator(".rate button").nth(4).click();
await chat.getByText("Thanks for your feedback.").waitFor();
check(true, "rating sent");

await say("I want to talk to a person please");
await chat.getByText(/teammate has been asked to take over/).waitFor();
check(true, "hand-off is explained to the customer");
const trace = await (await fetch(`${API}/v1/handoffs?state=open`, { headers: admin })).json();
const mine = trace.handoffs.find((h) => h.customerId === "shopper-1");
check(!!mine, "the hand-off exists for the shopper");
await say("hello? anyone there?");
await chat.getByText(/looking after this conversation/).waitFor();
check(true, "while a person has it, the customer is told so");
await fetch(`${API}/v1/handoffs/${mine.id}/reply`, { method: "POST", headers: admin, body: JSON.stringify({ text: "Hi, this is Sam. I can help." }) });
await chat.locator(".m.person").waitFor({ timeout: 15000 });
check((await chat.locator(".m.person").innerText()).includes("Sam"), "a teammate's reply appears without a refresh");

// markup typed by a customer stays text
await fetch(`${API}/v1/handoffs/${mine.id}/resolve`, { method: "POST", headers: admin, body: JSON.stringify({}) });
await say('<img src=x onerror="window.pwned=1"> hi');
await chat.locator(".m.me").nth(3).waitFor();
check((await chat.locator("img").count()) === 0 && (await page.evaluate(() => window.pwned)) === undefined, "markup is shown as text, never run");

// a different website is refused by the browser
const evil = await browser.newPage();
await evil.goto("about:blank");
const blocked = await evil.evaluate(async (api) => { try { await fetch(`${api}/v1/agents`, { headers: { authorization: "Bearer x" } }); return false; } catch { return true; } }, API);
check(blocked, "a site that is not listed cannot call the API from a browser");

check(errors.length === 0, `no console errors${errors.length ? ": " + errors.slice(0, 3).join(" | ") : ""}`);
await browser.close(); server.close();
process.exit(bad ? 1 : 0);
