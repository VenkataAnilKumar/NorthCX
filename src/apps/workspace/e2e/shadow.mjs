// Browser check of shadow mode against a running stack whose "support" agent has `shadow: true` (not part of the CI smoke test, whose demo agent answers live):
//   NORTHCX_DEMO=1 NORTHCX_API_KEY=... NORTHCX_AGENTS_DIR=<a copy of examples/ with "shadow: true" added to support.yaml> python -m northcx
//   node e2e/shadow.mjs     (needs API_KEY; WEB_URL and API_URL default to localhost; playwright is preinstalled in the dev image)
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const WEB = process.env.WEB_URL ?? "http://localhost:3002";
const KEY = process.env.API_KEY ?? "";
const API = process.env.API_URL ?? "http://localhost:3000";
const failures = [];
const check = (ok, what) => { console.log(`${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) failures.push(what); };
const call = (path, body) => fetch(`${API}${path}`, { method: body ? "POST" : "GET", headers: { authorization: `Bearer ${KEY}`, "content-type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) });
const outbox = async (session) => (await (await call(`/v1/sessions/${session}/outbox?after=0`)).json()).messages;

const stamp = Date.now();
const [a, b, c] = [`sh-a-${stamp}`, `sh-b-${stamp}`, `sh-c-${stamp}`];
const reply = await (await call("/v1/agents/support/chat", { sessionId: a, message: `where is order 1042? ref ${stamp}`, customerId: `c-${stamp}` })).json();
check(reply.reply === "" && reply.status === "in_review", "the customer's response is empty and in review");
await call("/v1/agents/support/chat", { sessionId: b, message: `where is order 1043? ref ${stamp}`, customerId: `c2-${stamp}` });
await call("/v1/agents/support/chat", { sessionId: c, message: `refund 240 for order 2077 ref ${stamp}`, customerId: `c3-${stamp}` });
check((await outbox(a)).length === 0 && (await outbox(b)).length === 0, "nothing is in the customers' outbox before a person decides");

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 1000 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error" && !/favicon|401|403|409|422|Failed to load resource/.test(m.text())) errors.push(m.text()); });
await page.goto(`${WEB}/settings`);
await page.fill("#k", KEY);
await page.getByRole("button", { name: "Use key" }).click();
await page.getByText(/Signed in as/).first().waitFor();

await page.goto(`${WEB}/drafts`);
const cardFor = (text) => page.locator("li", { hasText: text });
await cardFor(`ref ${stamp}`).filter({ hasText: "1042" }).waitFor();
check(true, "the draft is listed with what the customer wrote");
// send as is
const first = cardFor(`ref ${stamp}`).filter({ hasText: "1042" });
const draftText = await first.getByLabel(/The agent's reply/).inputValue();
await first.getByRole("button", { name: "Send as is" }).click();
await cardFor(`ref ${stamp}`).filter({ hasText: "1042" }).waitFor({ state: "detached" });
let sent = (await outbox(a)).filter((m) => m.kind === "shadow_reply");
check(sent.length === 1 && sent[0].reply === draftText, "send as is: the customer gets the draft, once");
// edit and send
const second = cardFor(`ref ${stamp}`).filter({ hasText: "1043" });
await second.getByLabel(/The agent's reply/).fill("Order 1043 was delivered on Monday. Is there anything else?");
await second.getByLabel("It leaves something out").check();
await second.getByRole("button", { name: "Send my edit" }).click();
await cardFor(`ref ${stamp}`).filter({ hasText: "1043" }).waitFor({ state: "detached" });
sent = (await outbox(b)).filter((m) => m.kind === "shadow_reply");
check(sent.length === 1 && sent[0].reply.startsWith("Order 1043 was delivered on Monday.") && sent[0].edited === true, "edit: the customer gets the person's text");
// reject: the held refund
const third = cardFor(`ref ${stamp}`).filter({ hasText: "2077" });
await third.waitFor();
await third.getByLabel("It is wrong").check();
await third.getByRole("button", { name: "Reject: send nothing" }).click();
await cardFor(`ref ${stamp}`).filter({ hasText: "2077" }).waitFor({ state: "detached" });
check((await outbox(c)).length === 0, "reject: nothing reaches the customer");
const held = (await (await call("/v1/approvals?state=pending")).json()).approvals.filter((x) => x.session_id === c);
check(held.length === 1 && held[0].tool === "issue_refund" && held[0].state === "pending", "the refund is held as an approval and did not run");   // (a refund over the limit is held by its own rule; a small one by shadow mode)
// the summary and the decided tabs
await page.reload();
await page.getByText(/drafts decided/).first().waitFor();
check(/unchanged/.test(await page.getByRole("status").first().innerText()), "the agreement summary is shown with its numbers");
await page.getByRole("tab", { name: "Edited" }).click();
await page.getByText("Sent instead").first().waitFor();
check(true, "the Edited tab shows what was sent instead");
check(errors.length === 0, `no client errors ${JSON.stringify(errors)}`);
await page.goto(`${WEB}/drafts`);
await page.screenshot({ path: process.env.SHOT ?? "/dev/null" });
await browser.close();
if (failures.length) { console.log(`\n${failures.length} failed`); process.exit(1); }
console.log("\nall passed");
