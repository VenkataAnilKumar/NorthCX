"""Writes the static HTML mockups of the admin platform and staff workspace to docs/07-design/mockups/.
Design artefacts only: every figure is sample data. Screenshots are made by scripts/shoot_mockups.js."""
from __future__ import annotations

import html
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "07-design" / "mockups"
E = html.escape

CSS = """
:root{--bg:#f6f8fb;--surface:#fff;--text:#0f172a;--muted:#5b6678;--border:#d9e0ea;--primary:#0b3d91;--primary-text:#fff;--ok:#0f7b3f;--ok-bg:#dcf5e6;--warn:#8a5300;--warn-bg:#fdecc8;--info:#0b4fb3;--info-bg:#dce9ff;--bad:#a11d1d;--bad-bg:#fde0e0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.app{display:grid;grid-template-columns:232px 1fr;min-height:900px}
aside{background:var(--surface);border-right:1px solid var(--border);padding:16px 12px}
.brand{font-weight:700;color:var(--primary);font-size:18px;padding:4px 10px 12px}
.grp{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);padding:12px 10px 4px}
.nav a{display:flex;justify-content:space-between;align-items:center;padding:7px 10px;border-radius:8px;color:var(--muted);text-decoration:none}
.nav a.on{background:var(--primary);color:var(--primary-text);font-weight:600}.nav .n{font-size:11px;background:var(--bad-bg);color:var(--bad);border-radius:9px;padding:0 6px}
.nav a.on .n{background:#ffffff33;color:#fff}
.who{margin-top:18px;border-top:1px solid var(--border);padding:12px 10px;font-size:12px;color:var(--muted)}
.top{display:flex;gap:12px;align-items:center;padding:10px 24px;background:var(--surface);border-bottom:1px solid var(--border)}
.search{flex:1;max-width:460px;border:1px solid var(--border);border-radius:8px;padding:7px 12px;color:var(--muted);background:var(--bg)}
.pill{border:1px solid var(--border);border-radius:999px;padding:4px 12px;font-size:12px;background:var(--surface)}.pill b{color:var(--primary)}
.sp{flex:1}.av{width:30px;height:30px;border-radius:50%;background:var(--info-bg);color:var(--info);display:grid;place-items:center;font-weight:700;font-size:12px}
main{padding:20px 24px 40px}h1{font-size:22px;margin:0 0 2px}.sub{color:var(--muted);margin:0 0 16px}
.row{display:flex;gap:12px;flex-wrap:wrap}.g4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.g3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.g2{display:grid;grid-template-columns:2fr 1fr;gap:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}.card h3{margin:0 0 8px;font-size:14px}
.stat .l{color:var(--muted);font-size:12px}.stat .v{font-size:26px;font-weight:700}.stat .d{font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse}th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--border)}
td{padding:9px 10px;border-bottom:1px solid var(--border)}tr:last-child td{border-bottom:0}.mut{color:var(--muted)}.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.b{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12px;font-weight:600}.ok{background:var(--ok-bg);color:var(--ok)}.warn{background:var(--warn-bg);color:var(--warn)}.info{background:var(--info-bg);color:var(--info)}.bad{background:var(--bad-bg);color:var(--bad)}.gr{background:#e8ecf2;color:var(--muted)}
.btn{display:inline-block;border:1px solid var(--border);background:var(--surface);border-radius:8px;padding:6px 12px;font-weight:600;font-size:13px}.btn.p{background:var(--primary);color:#fff;border-color:var(--primary)}.btn.d{color:var(--bad)}
.bar{height:8px;background:var(--border);border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:var(--primary)}.bar i.w{background:#c27803}.bar i.r{background:var(--bad)}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--border);margin:0 0 14px}.tabs a{padding:8px 12px;color:var(--muted);border-bottom:2px solid transparent}.tabs a.on{color:var(--primary);border-color:var(--primary);font-weight:600}
.tools{display:flex;gap:8px;align-items:center;margin-bottom:12px}.in{border:1px solid var(--border);border-radius:8px;padding:6px 10px;background:var(--surface);color:var(--muted)}
.drawer{position:absolute;right:0;top:0;bottom:0;width:380px;background:var(--surface);border-left:1px solid var(--border);box-shadow:-8px 0 24px #0f172a22;padding:18px}
.field{margin:10px 0}.field label{display:block;font-size:12px;color:var(--muted);margin-bottom:3px}.field .in{display:block}
.note{font-size:12px;color:var(--muted)}.tag{font-size:11px;border:1px solid var(--border);border-radius:6px;padding:0 6px;margin-right:4px;color:var(--muted)}
.chat{display:flex;flex-direction:column;gap:10px}.msg{max-width:78%;padding:9px 12px;border-radius:12px}.u{background:var(--info-bg);align-self:flex-end}.a{background:var(--surface);border:1px solid var(--border)}
.src{font-size:12px;border:1px solid var(--border);border-radius:8px;padding:6px 8px;margin-top:6px;background:var(--bg)}
.mock{position:fixed;right:12px;bottom:8px;font-size:11px;color:var(--muted);background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:2px 8px}
"""

NAV = [("Operate", [("Overview", 0), ("Conversations", 0), ("Handoffs", 3), ("Approvals", 2), ("Review and QA", 0)]),
       ("Build", [("Agents", 0), ("Knowledge", 0), ("Simulations", 0), ("Models and budgets", 0)]),
       ("Govern", [("People and groups", 0), ("Access keys", 0), ("Policies", 0), ("Audit and activity", 0)]),
       ("Platform", [("Connectors and MCP", 0), ("Usage and cost", 0), ("Data residency", 0), ("Settings", 0)])]


def shell(active: str, title: str, sub: str, body: str, env: str = "Production", tenant: str = "Acme Support (sample)") -> str:
    nav = "".join(f'<div class="grp">{g}</div>' + "".join(f'<a class="{"on" if n == active else ""}"><span>{n}</span>{f"<span class=n>{c}</span>" if c else ""}</a>' for n, c in items) for g, items in NAV)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} (mockup)</title><style>{CSS}</style></head><body>
<div class="app"><aside><div class="brand">NorthCX</div><div class="nav">{nav}</div><div class="who">Signed in as <b>Priya N.</b><br>Administrator &middot; SSO</div></aside>
<div style="position:relative"><div class="top"><div class="search">Search conversations, agents, people, settings&hellip; &nbsp;<span class="tag">Ctrl K</span></div><div class="sp"></div><span class="pill">Tenant <b>{E(tenant)}</b></span><span class="pill">Environment <b>{E(env)}</b></span><span class="pill">Alerts <b>1</b></span><div class="av">PN</div></div>
<main><h1>{E(title)}</h1><p class="sub">{E(sub)}</p>{body}</main></div></div><div class="mock">Design mockup &middot; sample data</div></body></html>"""


def stat(label, value, delta=""):
    return f'<div class="card stat"><div class="l">{label}</div><div class="v">{value}</div><div class="d">{delta}</div></div>'


def badge(text, kind="gr"):
    return f'<span class="b {kind}">{E(text)}</span>'


def table(head, rows):
    return "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>"


def bar(pct, cls=""):
    return f'<div class="bar"><i class="{cls}" style="width:{pct}%"></i></div>'


SCREENS: dict[str, str] = {}

SCREENS["01-admin-overview"] = shell("Overview", "Overview", "What needs attention across your agents, people and spend. Last 7 days.", f"""
<div class="g4">{stat("Conversations", "12,480", "+8% vs previous 7 days")}{stat("Resolved (provisional)", "71%", "contained 83% &middot; 212 pending")}{stat("Model cost", "$1,942", "74% of weekly budget")}{stat("Open handoffs", "3", "oldest waiting 14 min")}</div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Needs attention</h3>{table(["Item","Where","Since","Action"],[
 [badge("Alert","bad")+" Error rate above 10%","Agent <b>billing-help</b> &middot; Production","18 min",'<span class="btn p">Investigate</span>'],
 [badge("Approval","warn")+" Refund over limit waiting","Conversation c-4f21","6 min",'<span class="btn p">Review</span>'],
 [badge("Budget","warn")+" Team Support at 82% of monthly budget","Models and budgets","today",'<span class="btn">Open</span>'],
 [badge("Access","info")+" 2 keys expire in 7 days","Access keys","7 days",'<span class="btn">Open</span>'],
 [badge("Sync","gr")+" SCIM sync last ran 2 h ago, 0 errors","People and groups","2 h",'<span class="btn">Open</span>']])}</div>
<div class="card"><h3>Agents by health</h3>{table(["Agent","Status"],[["support-agent",badge("Healthy","ok")],["billing-help",badge("Alert firing","bad")],["returns",badge("Healthy","ok")],["onboarding (staging)",badge("Draft","gr")]])}<p class="note" style="margin-top:10px">Health comes from error rate, hand-off rate and latency alerts.</p></div></div>
<div class="g3" style="margin-top:12px"><div class="card"><h3>Conversations by channel</h3>{table(["Channel","Share"],[["Web chat","46%"],["Email","24%"],["WhatsApp","14%"],["SMS","9%"],["Voice","7%"]])}</div>
<div class="card"><h3>Spend by team</h3>{table(["Team","Spend","Budget"],[["Support","$1,230",bar(82,"w")],["Billing","$512",bar(51)],["Growth","$200",bar(20)]])}</div>
<div class="card"><h3>Recent changes</h3>{table(["Who","What"],[["Marco L.","Released support-agent v18"],["Priya N.","Created key ci-pipeline"],["Dana K.","Approved refund c-4e90"],["system","Alert cleared: slow-replies"]])}</div></div>""")

SCREENS["02-agent-catalog"] = shell("Agents", "Agents", "Every agent in this tenant, who owns it, what it can do and what it costs.", f"""
<div class="tools"><span class="in">Search agents&hellip;</span><span class="in">Team: All</span><span class="in">Environment: Production</span><span class="in">Status: Any</span><div class="sp" style="flex:1"></div><span class="btn">Import</span><span class="btn p">+ New agent</span></div>
<div class="card" style="padding:4px 6px">{table(["Agent","Owner","Purpose","Model","Release","Tools","7-day cost","Health"],[
 ["<b>support-agent</b><br><span class=note>audience: customers</span>","Support team","Order and delivery questions",'<span class=mono>claude-sonnet-5-5</span>',badge("v18 live","ok")+" <span class=note>2 d ago</span>","6 <span class=note>(2 write)</span>","$1,230",badge("Healthy","ok")],
 ["<b>billing-help</b><br><span class=note>audience: customers</span>","Billing team","Invoices and refunds",'<span class=mono>claude-sonnet-5-5</span>',badge("v7 live","ok")+" <span class=note>9 d ago</span>","8 <span class=note>(4 write)</span>","$512",badge("Alert","bad")],
 ["<b>returns</b><br><span class=note>audience: customers</span>","Support team","Return labels and status",'<span class=mono>claude-haiku-5-5</span>',badge("v3 live","ok")+" <span class=note>21 d ago</span>","4 <span class=note>(1 write)</span>","$146",badge("Healthy","ok")],
 ["<b>care-copilot</b><br><span class=note>audience: staff</span>","Support leads","Drafts replies for people",'<span class=mono>claude-sonnet-5-5</span>',badge("v2 staging","info"),"5 <span class=note>(0 write)</span>","$54",badge("Healthy","ok")],
 ["<b>onboarding</b><br><span class=note>audience: customers</span>","Growth team","Welcome flows",'<span class=mono>claude-haiku-5-5</span>',badge("Draft","gr"),"3","$0",badge("Not released","gr")]])}</div>
<p class="note" style="margin-top:10px">Owner, purpose and team are new catalog fields; release, tools and cost come from the platform. Click a row to open its governance view.</p>""")

SCREENS["03-agent-governance"] = shell("Agents", "billing-help", "Customers &middot; owned by Billing team &middot; live in Production as v7", f"""
<div class="tabs"><a>Overview</a><a>Spec</a><a>Versions and releases</a><a class="on">Governance</a><a>Simulations</a><a>Traces</a></div>
<div class="g2"><div><div class="card"><h3>Tools and what they may do</h3>{table(["Tool","Effect","Scope","Approval"],[
 ["lookup_invoice",badge("read","ok"),"customer's own invoices","none"],["issue_refund",badge("write","warn"),"refunds up to $50 without approval",badge("above $50 needs a person","warn")],
 ["change_plan",badge("write","warn"),"plans in catalog only",badge("always a person","warn")],["send_receipt",badge("write","warn"),"to the address on file","none"]])}</div>
<div class="card" style="margin-top:12px"><h3>Guardrails and supervision</h3>{table(["Check","Applies to","Mode"],[["PII masking","input and output",badge("on","ok")],["Prompt-injection screen","tool results and files",badge("on","ok")],["No card numbers","replies",badge("blocks","ok")],["Abuse detection","input",badge("hand off after 3","ok")],["Policy supervisor","replies",badge("blocks","ok")]])}</div></div>
<div><div class="card"><h3>Limits</h3><p class="note">Budget this month</p>{bar(51)}<p class="note">$512 of $1,000 (Billing team)</p><p class="note" style="margin-top:10px">Tokens per conversation</p><b>40,000</b><p class="note" style="margin-top:10px">Rate</p><b>30 messages / minute / session</b></div>
<div class="card" style="margin-top:12px"><h3>Access</h3><p class="note">Who can change or release this agent</p>{table(["Group","Role"],[["Billing developers","Developer"],["Release managers","Release manager"],["CX leads","Viewer"]])}</div>
<div class="card" style="margin-top:12px"><h3>Release gate</h3><p>Two-person rule in Production</p><p class="note">Last gate: 41 of 41 required scenarios passed</p></div></div></div>""")

SCREENS["04-people-groups"] = shell("People and groups", "People and groups", "Provisioned from your identity provider; roles come from groups.", f"""
<div class="g4">{stat("People","48","44 active &middot; 4 suspended")}{stat("Groups","9","")}{stat("SCIM sync","OK","last run 2 h ago &middot; 0 errors")}{stat("Sign-in","SSO only","password keys disabled")}</div>
<div class="tabs" style="margin-top:14px"><a class="on">People</a><a>Groups</a><a>Role bindings</a><a>Provisioning</a></div>
<div class="tools"><span class="in">Search people&hellip;</span><span class="in">Group: All</span><span class="in">Status: Active</span></div>
<div class="card" style="padding:4px 6px">{table(["Person","Groups","Effective role","Last sign-in","Source","Status"],[
 ["<b>Priya N.</b><br><span class=note>priya@example.com</span>","Admins","Administrator","today",badge("SCIM","info"),badge("Active","ok")],
 ["<b>Marco L.</b><br><span class=note>marco@example.com</span>","Billing developers, Release managers","Release manager","today",badge("SCIM","info"),badge("Active","ok")],
 ["<b>Dana K.</b><br><span class=note>dana@example.com</span>","Reviewers","Reviewer","yesterday",badge("SCIM","info"),badge("Active","ok")],
 ["<b>Sam T.</b><br><span class=note>sam@example.com</span>","Auditors","Auditor","6 days ago",badge("SCIM","info"),badge("Active","ok")],
 ["<b>Lee W.</b><br><span class=note>lee@example.com</span>","&mdash;","none","never",badge("SCIM","info"),badge("Suspended","bad")]])}</div>
<p class="note" style="margin-top:10px">Deactivating a person in the identity provider ends their sessions and revokes their keys in one step. Effective permissions are the union of all their groups.</p>""")

SCREENS["05-access-keys"] = shell("Access keys", "Access keys", "Keys for pipelines, channels and integrations. Each can be limited to agents and environments.", f"""
<div class="tools"><span class="in">Search keys&hellip;</span><span class="in">Role: Any</span><span class="in">Expiring soon</span><div style="flex:1"></div><span class="btn p">+ New key</span></div>
<div class="card" style="padding:4px 6px">{table(["Name","Role","Limited to","Expires","Last used","Status"],[
 ["<b>ci-pipeline</b>","Developer","billing-help, returns &middot; staging","in 6 days","12 min ago",badge("Active","ok")],
 ["<b>web-chat-token-minter</b>","Channel","support-agent &middot; Production","in 80 days","just now",badge("Active","ok")],
 ["<b>voice-bridge</b>","Channel","support-agent &middot; Production","in 80 days","3 min ago",badge("Active","ok")],
 ["<b>old-reporting</b>","Viewer","all","expired","41 days ago",badge("Expired","gr")]])}</div>
<div class="drawer"><h3 style="margin-top:0">New key</h3><div class="field"><label>Name</label><span class="in">nightly-regression</span></div><div class="field"><label>Role</label><span class="in">Developer</span></div>
<div class="field"><label>Agents</label><span class="in">billing-help &times; &nbsp; returns &times;</span></div><div class="field"><label>Environments</label><span class="in">Staging &times;</span></div><div class="field"><label>Expires</label><span class="in">in 30 days</span></div>
<p class="note">The key is shown once after you create it. Limited keys are refused on any other agent or environment.</p><div class="row" style="margin-top:14px"><span class="btn p">Create key</span><span class="btn">Cancel</span></div></div>""")

SCREENS["06-models-budgets"] = shell("Models and budgets", "Models and budgets", "Which models agents may use, what they cost, and how much each team may spend.", f"""
<div class="tabs"><a class="on">Providers</a><a>Budgets</a><a>Routing</a></div>
<div class="card" style="padding:4px 6px">{table(["Provider","Models","Capabilities","Price per million tokens","Region","Status"],[
 ["<b>Anthropic</b>","claude-sonnet-5-5, claude-haiku-5-5","tools &middot; images &middot; documents","set by you",badge("us","info"),badge("Connected","ok")],
 ["<b>Self-hosted (OpenAI-compatible)</b>","llama-70b-instruct","tools &middot; no images","set by you",badge("eu","info"),badge("Connected","ok")]])}</div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Budgets</h3>{table(["Scope","Period","Spent","Limit",""],[
 ["Team Support","month","$1,230","$1,500",bar(82,"w")],["Team Billing","month","$512","$1,000",bar(51)],["Team Growth","month","$200","$1,000",bar(20)],["Per conversation","each","avg $0.16","$2.00",bar(8)]])}</div>
<div class="card"><h3>Fallback order (Production)</h3><ol style="margin:0;padding-left:18px"><li>anthropic:claude-sonnet-5-5</li><li>anthropic:claude-haiku-5-5</li><li>self-hosted:llama-70b-instruct</li></ol><p class="note" style="margin-top:10px">A model without tool support is refused for agents that use tools.</p></div></div>""")

SCREENS["07-audit-activity"] = shell("Audit and activity", "Audit and activity", "Staff actions and agent actions in one searchable record. The chain is verified.", f"""
<div class="g4">{stat("Entries (7 d)","3,204","")}{stat("Agent actions","2,911","")}{stat("Approvals decided","173","median 4 min")}{stat("Integrity","Verified",'<span class="note">head checked 10 min ago</span>')}</div>
<div class="tools" style="margin-top:14px"><span class="in">Search&hellip;</span><span class="in">Type: All</span><span class="in">Actor: All</span><span class="in">Agent: All</span><span class="in">Last 7 days</span><div style="flex:1"></div><span class="btn">Export</span></div>
<div class="card" style="padding:4px 6px">{table(["Time","Who","Action","Target","Detail","Outcome"],[
 ["14:02","<b>billing-help</b> <span class=tag>agent</span>","tool: issue_refund","order 1042","$32 &middot; no approval needed",badge("success","ok")],
 ["13:58","<b>billing-help</b> <span class=tag>agent</span>","tool: issue_refund","order 1019","$180 &middot; waiting",badge("needs approval","warn")],
 ["13:59","<b>Dana K.</b> <span class=tag>person</span>","approval.decide","approval a-77","approved &middot; ref a-77",badge("success","ok")],
 ["13:40","<b>Marco L.</b> <span class=tag>person</span>","release.publish","support-agent v18","Production &middot; gate passed",badge("success","ok")],
 ["13:12","<b>Priya N.</b> <span class=tag>person</span>","key.create","nightly-regression","scoped: 2 agents, staging",badge("success","ok")],
 ["12:30","<b>unknown</b>","auth.denied","POST /v1/keys","needs keys:manage",badge("denied","bad")]])}</div>""")

SCREENS["08-connectors-mcp"] = shell("Connectors and MCP", "Connectors and MCP", "Systems your agents can use. Remote tools are read-only unless you mark them otherwise.", f"""
<div class="tabs"><a class="on">Connectors</a><a>MCP servers</a><a>Webhooks</a></div>
<div class="card" style="padding:4px 6px">{table(["Name","Type","Allowed hosts","Tools","Used by","Last call","Health"],[
 ["<b>orders-api</b>","HTTP connector","orders.example.com","3 (1 write)","support-agent, returns","1 min ago",badge("OK","ok")],
 ["<b>billing-system</b>","HTTP connector","billing.example.com","5 (3 write)","billing-help","4 min ago",badge("OK","ok")],
 ["<b>docs-search</b>","MCP server","mcp.docs.example.com","2 (read-only)","care-copilot","12 min ago",badge("OK","ok")],
 ["<b>helpdesk</b>","Hand-off inbox","help.example.com","&mdash;","all agents","3 min ago",badge("2 retries","warn")]])}</div>
<div class="g3" style="margin-top:12px"><div class="card"><h3>Test a connector</h3><p class="note">Send a sample call and see the result without a conversation.</p><span class="btn">Run test</span></div>
<div class="card"><h3>Status events webhook</h3><p class="note">12 event types &middot; last delivery 2 min ago</p><span class="btn">Send test event</span></div><div class="card"><h3>Residency check</h3><p class="note">All destinations are in allowed regions.</p>{badge("Compliant","ok")}</div></div>""")

SCREENS["09-staff-workspace"] = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Workspace (mockup)</title><style>{CSS}
.ws{{display:grid;grid-template-columns:260px 1fr 320px;height:900px}}.ws>div{{padding:16px;overflow:hidden}}.ws .l{{background:var(--surface);border-right:1px solid var(--border)}}.ws .r{{background:var(--surface);border-left:1px solid var(--border)}}
.item{{padding:9px 10px;border-radius:8px;margin-bottom:4px}}.item.on{{background:var(--info-bg)}}</style></head><body><div class="ws">
<div class="l"><div class="brand">NorthCX <span class="note">Workspace</span></div><div class="in" style="display:block;margin-bottom:10px">Search everything&hellip;</div><div class="grp">Queue (Billing)</div>
<div class="item on"><b>c-4f21</b> {badge("waiting 6 min","warn")}<br><span class="note">Refund for a delayed order</span></div><div class="item"><b>c-4f1c</b><br><span class="note">Wrong plan charged</span></div><div class="item"><b>c-4e90</b> {badge("approved","ok")}<br><span class="note">Invoice copy</span></div>
<div class="grp">My tools</div><div class="item">Drafts</div><div class="item">Saved searches</div><div class="item">Team playbooks</div></div>
<div style="background:var(--bg)"><div class="row" style="align-items:center;margin-bottom:10px"><b style="font-size:16px">Refund for a delayed order</b>{badge("handed off by billing-help","info")}<div class="sp" style="flex:1"></div><span class="btn">Resolve</span></div>
<div class="chat"><div class="msg u">My parcel is 9 days late and I want my money back.</div><div class="msg a">I can see order 1019 is delayed. A refund of $180 is above what I can approve, so I'm asking a colleague to review it.</div>
<div class="card" style="background:var(--warn-bg);border-color:#e9c46a"><b>Approval needed:</b> issue_refund $180 for order 1019<div class="row" style="margin-top:8px"><span class="btn p">Approve</span><span class="btn d">Reject</span><span class="btn">Ask for more</span></div></div>
<div class="msg a" style="align-self:flex-start"><span class="note">Draft reply (you can edit)</span><br>Thanks for waiting. We've refunded $180 to your original payment method; it can take 3 to 5 days to appear.<div class="row" style="margin-top:8px"><span class="btn p">Use draft</span><span class="btn">Regenerate</span></div></div></div></div>
<div class="r"><div class="card" style="margin-bottom:12px"><h3>Summary</h3><p class="note">Customer reports a 9-day delay on order 1019 and asks for a refund. The agent verified the delay and could not approve the amount.</p></div>
<div class="card"><h3>Suggested from knowledge</h3><div class="src"><b>Refund policy</b><br><span class="note">Orders over 7 days late are eligible for a full refund.</span></div><div class="src"><b>Carrier delays playbook</b><br><span class="note">Check tracking before approving.</span></div><div class="src"><b>Billing escalations</b><br><span class="note">Refunds over $150 need a lead.</span></div></div>
<div class="card" style="margin-top:12px"><h3>Customer</h3><p class="note">Plan: Plus &middot; 3 orders &middot; identity verified</p></div></div></div><div class="mock">Design mockup &middot; sample data</div></body></html>"""

SCREENS["10-review-qa"] = shell("Review and QA", "Review and QA", "Sampled conversations scored against your scorecard. Calibrate reviewers so scores mean the same thing.", f"""
<div class="g4">{stat("Reviewed (7 d)","240","of 12,480 &middot; sampled 1.9%")}{stat("Judged correct","92%","target 90%")}{stat("Needed hand-offs","96%","of reviewed hand-offs")}{stat("Reviewer agreement","88%","last calibration: Nov 2")}</div>
<div class="tabs" style="margin-top:14px"><a class="on">Queue</a><a>Scorecards</a><a>Calibration</a><a>Sampling rules</a></div>
<div class="g2"><div class="card" style="padding:4px 6px">{table(["Conversation","Agent","Why it is here","Assigned","Score"],[
 ["c-4f21","billing-help","hand-off","Dana K.","&mdash;"],["c-4eb7","support-agent","random sample","Dana K.","4.5"],["c-4e55","returns","low rating","unassigned","&mdash;"],["c-4d90","support-agent","guardrail block","Sam T.",badge("fail","bad")],["c-4d12","billing-help","outlier: long","unassigned","&mdash;"]])}</div>
<div class="card"><h3>Scorecard: Support v3</h3>{table(["Criterion","Weight"],[["Correct answer","40%"],["Followed policy","30%"],["Tone","15%"],["Right hand-off","15%"]])}<p class="note" style="margin-top:8px">Failed reviews can become regression scenarios.</p><span class="btn">Create scenario from selected</span></div></div>""")

SCREENS["12-components"] = shell("Overview", "Component library", "The parts every screen is built from. All use the shared design tokens, light and dark.", f"""
<div class="g3"><div class="card"><h3>Buttons</h3><div class="row"><span class="btn p">Primary</span><span class="btn">Secondary</span><span class="btn d">Destructive</span></div><h3 style="margin-top:14px">Status badges</h3><div class="row">{badge("Healthy","ok")}{badge("Needs approval","warn")}{badge("Draft","gr")}{badge("Failed","bad")}{badge("SCIM","info")}</div></div>
<div class="card"><h3>Stat tile</h3>{stat("Resolved (provisional)","71%","contained 83% &middot; 212 pending")}<h3 style="margin-top:14px">Progress / budget</h3>{bar(30)}<br>{bar(82,"w")}<br>{bar(97,"r")}</div>
<div class="card"><h3>Form fields</h3><div class="field"><label>Name</label><span class="in">nightly-regression</span></div><div class="field"><label>Role</label><span class="in">Developer &#9662;</span></div><div class="field"><label>Expires</label><span class="in">in 30 days</span></div></div></div>
<div class="g3" style="margin-top:12px"><div class="card"><h3>Empty state</h3><p><b>No connectors yet</b></p><p class="note">Connect a system so your agents can look things up and take actions.</p><span class="btn p">Add connector</span></div>
<div class="card"><h3>Error state</h3><p>{badge("Could not load","bad")}</p><p class="note">The server did not answer. Your data is safe.</p><span class="btn">Try again</span></div><div class="card"><h3>Confirm dialog</h3><p><b>Revoke key ci-pipeline?</b></p><p class="note">Anything using it stops working immediately. This is recorded in the audit log.</p><div class="row"><span class="btn d">Revoke</span><span class="btn">Cancel</span></div></div></div>
<div class="g3" style="margin-top:12px"><div class="card"><h3>Table row actions</h3>{table(["Name","Status",""],[["support-agent",badge("Live","ok"),"&hellip;"],["onboarding",badge("Draft","gr"),"&hellip;"]])}</div><div class="card"><h3>Tabs and filters</h3><div class="tabs"><a class="on">People</a><a>Groups</a></div><div class="row"><span class="in">Search&hellip;</span><span class="in">Status: Active</span></div></div>
<div class="card"><h3>Trace timeline row</h3><p class="mono">user &rarr; llm &rarr; tool_call lookup_invoice &rarr; tool_result &rarr; reply</p><p class="note">Step times, tokens and the approval reference shown inline.</p></div></div>""")

def _col(title, who, items, cls="info"):
    return f'<div class="card" style="padding:14px"><span class="b {cls}">{title}</span><p class="note" style="margin:6px 0 8px">{who}</p>' + "".join(f"<div style='padding:4px 0;border-top:1px solid var(--border)'>{i}</div>" for i in items) + "</div>"


SCREENS["11-information-architecture"] = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Information architecture (mockup)</title><style>{CSS}
body{{padding:28px;min-height:900px}}h1{{margin-bottom:4px}}</style></head><body><h1>NorthCX surfaces and navigation</h1><p class="sub">Who uses what. One sign-in, one design system, separate apps where the audience, policy or deployment differs. Built = in Studio today; New = this design.</p>
<div class="g3">{_col("Customer surfaces","Customers",["Chat widget and SDK (built)","Email, SMS, WhatsApp, Telegram, voice (built)","Identity code check (built)"],"ok")}
{_col("Staff workspace  (new)","Support staff, team leads",["Queue and conversation with agent summary","Approvals inline","Draft replies, suggested knowledge","Search across knowledge, conversations, hand-offs","Saved searches, team playbooks"])}
{_col("Admin platform  (Studio, extended)","Admins, release managers, developers, reviewers, auditors",["<b>Operate</b>: Overview, Conversations, Handoffs, Approvals, Review and QA","<b>Build</b>: Agents (catalog), Knowledge, Simulations, Models and budgets","<b>Govern</b>: People and groups, Access keys, Policies, Audit and activity","<b>Platform</b>: Connectors and MCP, Usage and cost, Data residency, Settings"])}</div>
<div class="g3" style="margin-top:12px">{_col("Developer portal  (new, static)","Developers",["API reference (generated, built)","SDK guides, webhooks and test events (built)","MCP and sandbox recipe"])}
{_col("Ops console  (new, private deployments)","Operators",["Health, versions, upgrade","Replicas, workers, queues","Backups and restore tests"],"warn")}
{_col("Back office  (vendor only)","The company running the platform",["Tenants, plans, licences","Feature flags, support access","Billing export"],"bad")}</div>
<div class="card" style="margin-top:12px"><h3>Cross-cutting</h3><div class="row"><span class="tag">Global search (Ctrl K)</span><span class="tag">Tenant and environment switcher</span><span class="tag">Role-aware navigation (items hide, not grey out)</span><span class="tag">Light and dark</span><span class="tag">Keyboard and screen-reader support</span><span class="tag">Empty, loading and error states</span><span class="tag">Confirm before destructive actions, recorded in audit</span></div></div></body></html>"""


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in SCREENS.items():
        (OUT / f"{name}.html").write_text(text, encoding="utf-8")
    print("wrote", len(SCREENS), "mockups to", OUT)
