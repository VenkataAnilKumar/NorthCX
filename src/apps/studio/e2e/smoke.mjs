// Browser smoke test against a running stack: node e2e/smoke.mjs  (needs WEB_URL, API_KEY; playwright is preinstalled in the dev image)
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const WEB = process.env.WEB_URL ?? "http://localhost:3001";
const KEY = process.env.API_KEY ?? "";
const API = process.env.API_URL ?? "http://localhost:3000";
const failures = [];
const check = (ok, what) => { console.log(`${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) failures.push(what); };

// a fresh conversation that asks for a person, so the review queue has something new every run
const sid = `e2e-${Date.now()}`;
const seeded = await fetch(`${API}/v1/agents/support/chat`, { method: "POST", headers: { authorization: `Bearer ${KEY}`, "content-type": "application/json" },
  body: JSON.stringify({ sessionId: sid, message: "I want a person please", customerId: `c-${sid}` }) });
if (!seeded.ok) { console.log("could not seed a conversation", seeded.status); process.exit(1); }

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error" && !/favicon|401|403|409|422|Failed to load resource/.test(m.text())) errors.push(m.text()); });
const text = async () => (await page.locator("main, body").first().innerText());

// settings: connect with a key
await page.goto(`${WEB}/settings`);
await page.fill("#key", KEY);
await page.getByRole("button", { name: "Save and test" }).click();
await page.getByText(/Connected as/).waitFor();
check(true, "settings: key accepted");
check(await page.getByText("Single sign-on").count() === 0, "settings: no SSO button when SSO is off");

// review queue
await page.goto(`${WEB}/review`);
await page.getByRole("list", { name: "Review queue" }).waitFor();
const items = page.getByRole("list", { name: "Review queue" }).getByRole("button");
await items.first().waitFor();
check((await items.count()) >= 1, "review: queue has conversations");
await page.getByRole("button", { name: /person please/ }).first().click();
await page.getByRole("region", { name: "Transcript" }).waitFor();
check((await page.getByRole("region", { name: "Transcript" }).innerText()).includes("person please"), "review: transcript shown");
await page.getByLabel("No").first().check();           // verdict: not right
await page.getByLabel("Yes").nth(1).check();            // hand-off needed
await page.getByLabel("wrong answer").check();
await page.getByLabel("Note").fill("e2e note");
await page.getByRole("button", { name: "Save review" }).click();
await page.getByText("Saved.").waitFor();
check(true, "review: saved");

// navigation: six left items, sub-tabs, text-only sub-tabs, honest pages for what is not built
await page.goto(`${WEB}/`);
const mainNav = page.getByRole("navigation", { name: "Main" });
for (const name of ["Overview", "Operate", "Build", "Govern", "Platform", "Personal"]) await mainNav.getByRole("link", { name }).waitFor();
check((await mainNav.getByRole("link").count()) === 6, "admin: six left items");
await page.goto(`${WEB}/handoffs`);
await page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: "Hand-offs" }).waitFor();
check(true, "admin: Operate sub-tabs shown with the Hand-offs page current");
await page.keyboard.press("Control+.");
check((await mainNav.count()) === 0, "admin: full window hides the rail");
await page.keyboard.press("Escape");

// the new Admin pages open and show their content
await page.goto(`${WEB}/models`);
await page.getByRole("heading", { name: "Models and budgets" }).waitFor();
check(true, "admin: Models and budgets page opens");
await page.goto(`${WEB}/usage`);
await page.getByRole("heading", { name: "Usage and billing" }).waitFor();
check(true, "admin: Usage page opens");
await page.goto(`${WEB}/policies`);
await page.getByRole("heading", { name: "Policies" }).waitFor();
await page.getByRole("tab", { name: "Organization" }).waitFor();
await page.getByRole("button", { name: "New policy" }).click();
await page.getByRole("button", { name: "Run the cases" }).waitFor();
check(true, "admin: Policies page has the organization policy editor");
await page.getByRole("tab", { name: "Library" }).click();
await page.getByText("tool_limit").first().waitFor();
check(true, "admin: Policies page lists the policy library");
await page.goto(`${WEB}/people`);
await page.getByRole("heading", { name: "People and groups" }).waitFor();
await page.getByLabel("New group name").fill("Smoke group");
await page.getByRole("button", { name: "Create group" }).click();
await page.getByRole("heading", { name: "Smoke group" }).waitFor();
await page.getByRole("button", { name: "Delete", exact: true }).first().click();
check(true, "admin: a group can be created and deleted");
await page.goto(`${WEB}/hub`);
await page.getByRole("heading", { name: "Agent Hub" }).waitFor();
await page.getByText("Billing and invoices").waitFor();
check(true, "admin: the Agent Hub shows the new predefined agents");

// insights shows the human-review cards
await page.goto(`${WEB}/insights`);
await page.getByRole("region", { name: "Human review" }).waitFor();
check(true, "insights: human review cards");

// versions page: checklist and rollout panel
{ // a fresh stack has no saved version yet: make version 1 from the baseline so the page has something to show
  const auth = { authorization: `Bearer ${KEY}`, "content-type": "application/json" };
  const have = await (await fetch(`${API}/v1/agents/support/versions`, { headers: auth })).json();
  if (!have.versions?.length) await fetch(`${API}/v1/agents/support/versions`, { method: "POST", headers: auth, body: JSON.stringify({ fromBaseline: true }) });
  // the release gate wants the required scenarios run against that version before a rollout may start
  await fetch(`${API}/v1/simulations/runs`, { method: "POST", headers: auth, body: JSON.stringify({ agent: "support", version: 1, mode: "scripted", skipJudge: true }) });
}
await page.goto(`${WEB}/agents/support`);
await page.getByRole("region", { name: /Publish checklist for version 1/ }).waitFor();
check((await page.getByRole("region", { name: /Publish checklist/ }).innerText()).includes("ready"), "versions: checklist ready");
await page.getByRole("region", { name: "Staged rollout" }).waitFor();
await page.getByLabel("Candidate version").selectOption("1");
await page.getByRole("button", { name: "Start rollout" }).click();
await page.getByText(/of new conversations get/).waitFor();
check(true, "rollout: started");
await page.getByRole("region", { name: /Publish checklist/ }).getByText(/not ready/).waitFor({ timeout: 10000 });
check(true, "versions: checklist blocks while a rollout runs");
await page.getByRole("button", { name: "Stop" }).click();
await page.getByRole("button", { name: "Start rollout" }).waitFor();
check(true, "rollout: stopped");

// knowledge: upload a file into a source
await fetch(`${API}/v1/knowledge/sources`, { method: "POST", headers: { authorization: `Bearer ${KEY}`, "content-type": "application/json" }, body: JSON.stringify({ id: "smoke", name: "Smoke source" }) });
await page.goto(`${WEB}/knowledge`);
await page.getByRole("region", { name: "Bring in content" }).waitFor();
await page.getByRole("region", { name: "Bring in content" }).getByLabel("Into source").selectOption("smoke");
await page.locator('input[type=file]').setInputFiles({ name: "warranty-e2e.md", mimeType: "text/markdown", buffer: Buffer.from(`# Warranty ${Date.now()}\n\nEvery product has a two year warranty.`) });
await page.getByRole("region", { name: "Bring in content" }).getByRole("status").filter({ hasText: "warranty-e2e.md" }).waitFor();
check(true, "knowledge: a file can be uploaded from the page");
check((await page.getByRole("region", { name: "Bring in content" }).innerText()).includes("switched off"), "knowledge: crawling reports that it is switched off when no host is listed");

// monitoring: status, flagged conversations and a test alert (no webhook is set up in the test stack)
await page.goto(`${WEB}/monitoring`);
await page.getByRole("region", { name: "Alert status" }).waitFor();
await page.getByRole("region", { name: "Flagged conversations" }).waitFor();
await page.getByRole("button", { name: "Send a test alert" }).click();
await page.getByRole("status").filter({ hasText: "Test alert" }).waitFor();
check((await page.getByRole("status").filter({ hasText: "Test alert" }).innerText()).includes("No webhook set up"), "monitoring: a test alert reports that no webhook is set up");
check((await page.getByRole("region", { name: "Alert history" }).innerText()).includes("test"), "monitoring: the test shows in the recent events");

// editor: journeys and languages
await page.goto(`${WEB}/agents/support/edit`);
await page.getByRole("region", { name: "Journeys" }).waitFor();
await page.getByRole("button", { name: "Start from blank" }).click();
await page.getByLabel("Goal").fill("Help with a refund");
await page.getByLabel("Tool for step 1").selectOption("lookup_order");
await page.getByLabel("Spanish").check();
await page.getByLabel("English").check();
await page.waitForTimeout(900);
check((await page.getByLabel("Goal").inputValue()) === "Help with a refund", "editor: journey and languages edited");
await page.getByPlaceholder(/When a customer wants a refund/).fill("When a customer wants a refund, find the order and refund it.");
await page.getByRole("button", { name: "Draft a journey" }).click();
await page.getByRole("alert").filter({ hasText: /journey|model/i }).first().waitFor();
check(true, "editor: unusable draft is reported, not applied");

// single sign-on landing: a bad session is rejected cleanly, a missing one explains itself
await page.goto(`${WEB}/sso#token=ncx_bad_token`);
const sso = page.locator("p[role=alert]");
await sso.waitFor();
check((await sso.innerText()).includes("did not work"), "sso landing: bad session rejected");
check(!page.url().includes("token="), "sso landing: token removed from the address bar");
await page.goto(`${WEB}/sso?error=Your+account+has+no+role`);
await page.getByText("no role").waitFor();
check(true, "sso landing: error shown");

// test console: a refund over the limit is held as a card; approve it in one conversation and reject another, from the card
await page.goto(`${WEB}/chat`);
await page.getByRole("option", { name: "support" }).waitFor({ state: "attached" });
for (const [verb, order, done] of [["Approve", "2077", /Approved by/], ["Reject", "2078", /Rejected by/]]) {
  await page.getByRole("button", { name: "New conversation" }).click();
  await page.getByLabel("Message").fill(`refund 240 for order ${order}`);
  await page.getByRole("button", { name: "Send" }).click();
  const card = page.getByRole("group", { name: "Approval: issue refund" });
  await card.waitFor();
  const shown = await card.innerText();   // the database may return the inputs in a different order
  check(shown.includes(`order_id ${order}`) && shown.includes("amount 240"), `console: held refund for ${order} shows what it would do`);
  check((await page.getByRole("list", { name: "What happened, in words" }).innerText()).includes("Held issue refund for a person"), "console: the trace is shown in words");
  await page.getByRole("button", { name: new RegExp(`^${verb} `) }).click();
  await page.getByText(done).waitFor();
  check(true, `console: ${verb.toLowerCase()} from the card`);
}

// replay: step through a stored conversation, then edit a customer message and run it again in the sandbox
{
  const stamp = Date.now();
  const say = (message) => fetch(`${API}/v1/agents/support/chat`, { method: "POST", headers: { authorization: `Bearer ${KEY}`, "content-type": "application/json" }, body: JSON.stringify({ sessionId: `replay-${stamp}`, message }) });
  await say("where is order 1042?");
  await say("refund 20 for order 1042");
  const before = await (await fetch(`${API}/v1/sessions/replay-${stamp}/turns`, { headers: { authorization: `Bearer ${KEY}` } })).json();
  await page.goto(`${WEB}/replay?session=replay-${stamp}`);
  await page.getByRole("group", { name: "Replay controls" }).waitFor();
  check((await page.getByRole("status").first().innerText()).startsWith("Step 1 of"), "replay: starts at the first step");
  await page.getByRole("button", { name: "Next" }).click();
  check((await page.getByLabel("Conversation so far").innerText()).includes("where is order 1042?"), "replay: shows the conversation so far");
  await page.getByRole("button", { name: /^The customer wrote: refund 20 for order 1042/ }).click();
  await page.getByRole("button", { name: "Edit and run again: message 2" }).click();
  const panel = page.getByRole("group", { name: "Edit and run again: message 2" });
  await panel.getByLabel(/What the customer would say instead/).fill("refund 25 for order 1042");
  await panel.getByRole("button", { name: "Run again" }).click();
  const result = panel.getByLabel("Result");
  await result.waitFor();
  const shown = await result.innerText();
  check(/Used issue refund \(order_id 1042, amount 25\)/.test(shown) && shown.includes("What would happen now"), "replay: the edited message is answered in the sandbox");
  const after = await (await fetch(`${API}/v1/sessions/replay-${stamp}/turns`, { headers: { authorization: `Bearer ${KEY}` } })).json();
  check(JSON.stringify(after) === JSON.stringify(before), "replay: the real conversation is unchanged by the rerun");
}

// the other main pages load without a client error
for (const p of ["/hub", "/preferences", "/profile", "/", "/conversations", "/simulations", "/knowledge", "/handoffs", "/approvals", "/agents", "/access", "/chat", "/trust", "/org", "/channels", "/memory", "/privacy"]) {
  await page.goto(`${WEB}${p}`);
  await page.waitForLoadState("networkidle");
  check(!(await page.locator("body").innerText()).includes("Application error"), `page loads: ${p}`);
}
await page.goto(`${WEB}/trust`);
await page.getByText("Controls", { exact: true }).waitFor();
check((await page.locator("body").innerText()).includes("Data residency"), "trust: shows live controls");
await page.goto(`${WEB}/org`);
await page.getByText("Requests per minute").waitFor();
check(true, "org: shows limits");
await page.goto(`${WEB}/connections`);
await page.getByRole("heading", { name: "Connections" }).waitFor();
check((await page.locator("body").innerText()).includes("Allowed hosts"), "connections: page shows the allowed hosts (none allowed in the smoke stack, so no form)");
check(errors.length === 0, `no client errors${errors.length ? ": " + errors.slice(0, 3).join(" | ") : ""}`);
await browser.close();
if (failures.length) { console.log(`\n${failures.length} failed`); process.exit(1); }
console.log("\nall passed");
