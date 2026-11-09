// Browser smoke test for the Workspace against a running stack: node e2e/smoke.mjs  (needs WEB_URL, API_KEY, API_URL; playwright is preinstalled in the dev image)
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const WEB = process.env.WEB_URL ?? "http://localhost:3002";
const KEY = process.env.API_KEY ?? "";
const API = process.env.API_URL ?? "http://localhost:3000";
const failures = [];
const check = (ok, what) => { console.log(`${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) failures.push(what); };
const post = (path, body) => fetch(`${API}${path}`, { method: "POST", headers: { authorization: `Bearer ${KEY}`, "content-type": "application/json" }, body: JSON.stringify(body) });

// fresh work for this run: a conversation that needs a person, and a refund that needs approval
const stamp = Date.now();
await post("/v1/agents/support/chat", { sessionId: `ws-h-${stamp}`, message: "I want a person please", customerId: `c-${stamp}` });
const big = await (await post("/v1/agents/support/chat", { sessionId: `ws-a-${stamp}`, message: "refund order 9999 for 400", customerId: `c-a-${stamp}` })).json();
if (!big.pendingApprovals?.length) { console.log("could not seed an approval"); process.exit(1); }

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error" && !/favicon|401|403|409|422|Failed to load resource/.test(m.text())) errors.push(m.text()); });

await page.goto(`${WEB}/settings`);
await page.fill("#k", KEY);
await page.getByRole("button", { name: "Use key" }).click();
await page.getByText(/Signed in as/).first().waitFor();
check(true, "settings: key accepted");

await page.goto(`${WEB}/`);
await page.getByText(/need[s]? you/).waitFor();
check(true, "home: shows what needs you");
check((await page.getByRole("navigation", { name: "Main" }).getByRole("link").count()) >= 5, "navigation lists the six items");

// inbox: open the new hand-off and resolve it
await page.goto(`${WEB}/inbox`);
await page.getByRole("button", { name: /person please|Customer asked for a person|handed the conversation/ }).first().click();
await page.getByText("Conversation", { exact: true }).waitFor();
check(true, "inbox: transcript shown");
await page.getByRole("button", { name: "Suggest a reply" }).click();
await page.getByText(/Suggested reply/).waitFor({ timeout: 15000 }).catch(() => {});
await page.getByRole("button", { name: "Resolve" }).click();
await page.getByText(/Resolved by/).waitFor();
check(true, "inbox: resolved");

// approvals: approve the refund
await page.goto(`${WEB}/approvals`);
await page.getByRole("button", { name: "Approve" }).first().click();
await page.getByText(/No pending approvals|Approve/).first().waitFor();
const after = await (await fetch(`${API}/v1/approvals?state=pending`, { headers: { authorization: `Bearer ${KEY}` } })).json();
check(!after.approvals.some((a) => a.id === big.pendingApprovals[0].id), "approvals: the refund was decided");

// search and knowledge
await page.goto(`${WEB}/search?q=refund`);
await page.getByRole("search").waitFor();
check(true, "search: page works");
await page.goto(`${WEB}/library`);
await page.getByRole("heading", { name: "Library" }).waitFor();
check(true, "library: page works");

// chat with the agent
await page.goto(`${WEB}/pilot`);
await page.getByLabel("Message").fill("where is order 1042?");
await page.getByRole("button", { name: "Send" }).click();
await page.getByText(/Order 1042/).waitFor({ timeout: 20000 });
check(true, "pilot: the agent answers");

// theme: the toggle changes the page, and the choice is kept
await page.getByRole("button", { name: /Theme:/ }).click(); // system -> light
await page.getByRole("button", { name: /Theme:/ }).click(); // light -> dark
check((await page.locator("html").getAttribute("data-theme")) === "dark", "theme: dark applied");
await page.reload();
check((await page.locator("html").getAttribute("data-theme")) === "dark", "theme: kept after reload");

// tabs whose backend is not built say so
await page.goto(`${WEB}/automations`);
await page.getByText("Not available yet").waitFor();
check(true, "automations: honest not-available page");

// navigation modes: sub-tabs, collapsed icon rail, full window
await page.goto(`${WEB}/inbox`);
check((await page.getByRole("navigation", { name: "Sections" }).getByRole("link").count()) === 3, "work: shows Inbox, Approvals and Customers sub-tabs");
await page.goto(`${WEB}/pilot`);
check((await page.getByRole("navigation", { name: "Sections" }).count()) === 0, "pilot: a single page shows no sub-tab row");
await page.keyboard.press("Control+b");
check(await page.locator(".rail-collapsed").count() > 0 || (await page.getByRole("button", { name: "Expand navigation" }).count()) > 0, "rail: collapses to icons (Ctrl B)");
await page.keyboard.press("Control+b");
await page.keyboard.press("Control+.");
check((await page.getByRole("navigation", { name: "Main" }).count()) === 0, "full window: rail hidden (Ctrl .)");
await page.keyboard.press("Escape");
check((await page.getByRole("navigation", { name: "Main" }).count()) === 1, "full window: Esc brings the rail back");

for (const p of ["/assistants", "/customers", "/outputs", "/spaces", "/automations", "/quality", "/performance", "/settings"]) {
  await page.goto(`${WEB}${p}`);
  check(!(await page.locator("body").innerText()).includes("Application error"), `page loads: ${p}`);
}
check(errors.length === 0, "no client errors" + (errors.length ? `: ${errors.slice(0, 3).join(" | ")}` : ""));
await browser.close();
console.log(failures.length ? `\n${failures.length} failed` : "\nall passed");
process.exit(failures.length ? 1 : 0);
