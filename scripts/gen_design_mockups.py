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
       ("Platform", [("Channels", 0), ("Connectors and MCP", 0), ("Usage and cost", 0), ("Data residency", 0), ("Trust and reliability", 0)]),
       ("Personal", [("Profile and memory", 0), ("Settings", 0)])]


def shell(active: str, title: str, sub: str, body: str, env: str = "Production", tenant: str = "Acme Support (sample)") -> str:
    nav = "".join(f'<div class="grp">{g}</div>' + "".join(f'<a class="{"on" if n == active else ""}"><span>{n}</span>{f"<span class=n>{c}</span>" if c else ""}</a>' for n, c in items) for g, items in NAV)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} (mockup)</title><style>{CSS}</style></head><body>
<div class="app"><aside><div class="brand">NorthCX</div><div class="nav">{nav}</div><div class="who">Signed in as <b>Priya N.</b><br>Administrator &middot; SSO</div></aside>
<div style="position:relative"><div class="top"><div class="search">Search conversations, agents, people, settings&hellip; &nbsp;<span class="tag">Ctrl K</span></div><div class="sp"></div><span class="pill">Tenant <b>{E(tenant)}</b></span><span class="pill">Environment <b>{E(env)}</b></span><span class="pill">Alerts <b>1</b></span><div class="av">PN</div></div>
<main><h1>{E(title)}</h1><p class="sub">{sub}</p>{body}</main></div></div><div class="mock">Design mockup &middot; sample data</div></body></html>"""


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
<div style="background:var(--bg)"><div class="tabs" style="margin-bottom:10px"><a class="on">c-4f21 <span class="b warn">approval</span></a><a>c-4f1c <span class="b info">replying</span></a><a>c-4e90 <span class="b ok">resolved</span></a><a class="note">+ open from queue</a></div><div class="row" style="align-items:center;margin-bottom:10px"><b style="font-size:16px">Refund for a delayed order</b>{badge("handed off by billing-help","info")}<div class="sp" style="flex:1"></div><span class="btn">Resolve</span></div>
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

SCREENS["13-policies"] = shell("Policies", "Policies", "Rules for what agents may do. Each setting shows where it comes from and whether it can be changed here.", f"""
<div class="tabs"><a class="on">Agents</a><a>Data</a><a>Sign-in</a><a>Release</a></div>
<div class="card" style="padding:4px 6px">{table(["Setting","Value here","Comes from","Lock","Applies to"],[
 ["<b>Agents may call write tools</b><br><span class=note>Only tools marked as write and covered by an approval rule</span>","On",badge("Platform default","gr"),"&mdash;","All agents"],
 ["<b>Refunds without approval up to</b>","$50",badge("Tenant","info"),"&mdash;","billing-help"],
 ["<b>Third-party MCP servers</b>","Off",badge("Platform default","gr"),"&#128274; locked by platform","All agents"],
 ["<b>Message content in exported traces</b>","Masked",badge("Tenant","info"),"&#128274; locked by tenant policy","All teams"],
 ["<b>Two-person rule for Production releases</b>","On",badge("Tenant","info"),"&mdash;","All agents"],
 ["<b>Daily model budget</b>","$200",badge("Team Support","warn"),"&mdash;","Team Support"],
 ["<b>Data may be sent to</b>","us, eu",badge("Tenant","info"),"&#128274; locked by tenant policy","All agents"]])}</div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>How to read this</h3><p class="note"><b>Comes from</b> says which level set the value: platform, tenant, team or agent. A lower level can make a setting stricter but never looser than the level above it. A locked setting shows who locked it and cannot be edited here.</p></div>
<div class="card"><h3>Change history</h3>{table(["Who","What","When"],[["Priya N.","Daily budget for Team Support: $150 &rarr; $200","today"],["Marco L.","Two-person rule: on","3 days ago"]])}</div></div>""")


SCREENS["15-workspace-session-style"] = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Workspace, session-style layout (mockup)</title><style>{CSS}
.ws{{display:grid;grid-template-columns:270px 1fr 300px;height:900px}}.ws>div{{padding:14px;overflow:hidden}}.ws .l{{background:var(--surface);border-right:1px solid var(--border)}}.ws .r{{background:var(--surface);border-left:1px solid var(--border)}}
.item{{padding:8px 10px;border-radius:8px;margin-bottom:3px}}.item.on{{background:var(--info-bg)}}.titlebar{{display:flex;gap:8px;align-items:center;margin-bottom:12px}}
.pb{{border:1px solid var(--border);background:var(--surface);border-radius:8px;padding:4px 10px;font-size:12px;font-weight:600}}.pb.on{{background:var(--primary);color:#fff;border-color:var(--primary)}}
.prompt{{position:absolute;left:14px;right:14px;bottom:14px;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px}}
.prompt .row{{margin-top:10px;gap:8px}}.ring{{width:18px;height:18px;border-radius:50%;border:3px solid var(--primary);border-right-color:var(--border);display:inline-block;vertical-align:middle}}</style></head><body><div class="ws">
<div class="l"><div class="brand">NorthCX <span class="note">Workspace</span></div><div class="row" style="margin-bottom:8px"><span class="btn p" style="flex:1;text-align:center">+ New note</span></div>
<div class="row" style="margin-bottom:8px"><span class="in">Status: Open &#9662;</span><span class="in">Team &#9662;</span></div><div class="grp">Needs me</div>
<div class="item on"><b>c-4f21</b> {badge("approval","warn")}<br><span class="note">Refund for a delayed order</span></div><div class="item"><b>c-4f1c</b> {badge("replying","info")}<br><span class="note">Wrong plan charged</span></div>
<div class="grp">Agent is handling</div><div class="item"><b>c-4f30</b> {badge("agent","gr")}<br><span class="note">Where is my parcel</span></div><div class="item"><b>c-4f2e</b> {badge("agent","gr")}<br><span class="note">Password reset</span></div>
<div class="grp">Resolved today</div><div class="item"><b>c-4e90</b> {badge("resolved","ok")}<br><span class="note">Invoice copy</span></div><div class="note" style="margin-top:8px">Option-click a thread to open it beside this one</div></div>
<div style="background:var(--bg);position:relative"><div class="titlebar"><b style="font-size:16px">Refund for a delayed order</b>{badge("handed off by billing-help","info")}<div style="flex:1"></div><span class="pb on">Conversation</span><span class="pb">Customer</span><span class="pb">Knowledge</span><span class="pb">Trace</span><span class="pb">Side chat</span><span class="pb">&hellip;</span></div>
<div class="chat"><div class="msg u">My parcel is 9 days late and I want my money back.</div><div class="msg a">I can see order 1019 is delayed. A refund of $180 is above what I can approve, so I'm asking a colleague to review it.</div>
<div class="card" style="background:var(--warn-bg);border-color:#e9c46a"><b>Approval needed:</b> issue_refund $180 for order 1019<div class="row" style="margin-top:8px"><span class="btn p">Approve</span><span class="btn d">Reject</span><span class="btn">Ask for more</span></div></div>
<div class="msg a" style="align-self:flex-start"><span class="note">Draft reply</span><br>Thanks for waiting. We've refunded $180 to your original payment method; it can take 3 to 5 days to appear.</div></div>
<div class="prompt"><span class="mut">Write a reply, or ask the copilot to search, summarise or draft&hellip;</span><div class="row"><span class="pill">+</span><span class="pill">Queue <b>Billing</b></span><span class="pill">Reply mode <b>Review before send</b></span><span class="pill">Copilot <b>care-copilot</b></span><div style="flex:1"></div><span class="ring"></span><span class="note">budget 18%</span></div></div></div>
<div class="r"><div class="card" style="margin-bottom:10px"><h3>Where it is</h3><p class="note">Queue Billing &middot; waiting 6 min &middot; handed off by billing-help v7 &middot; Production</p></div>
<div class="card" style="margin-bottom:10px"><h3>What the agent did</h3><p class="note">1 lookup, 1 refund request (not executed), hand-off after 4 steps</p></div><div class="card" style="margin-bottom:10px"><h3>Running</h3><p class="note">Copilot is drafting a reply&hellip;</p></div>
<div class="card"><h3>Context</h3><div class="bar"><i style="width:18%"></i></div><p class="note">Conversation and sources: 18% of the copilot's context</p></div></div></div>
<div class="mock">Design mockup &middot; sample data &middot; layout idea only</div></body></html>"""


# ---------- Workspace app (left navigation, right working space) and Settings (personal and admin options) ----------
WS_CSS = CSS + """
.ws2{display:grid;grid-template-columns:270px 1fr;height:900px}.ws2 .side{background:var(--surface);border-right:1px solid var(--border);padding:14px 12px;display:flex;flex-direction:column}
.ws2 .work{background:var(--bg);padding:18px 22px;overflow:hidden;position:relative}.newc{display:block;text-align:center;background:var(--primary);color:#fff;border-radius:10px;padding:9px;font-weight:600;margin:6px 0 12px}
.side .nav a{padding:8px 10px}.recent{font-size:13px;color:var(--muted);padding:5px 10px;border-radius:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.recent.on{background:var(--info-bg);color:var(--info)}
.me{margin-top:auto;border-top:1px solid var(--border);padding-top:10px;display:flex;gap:10px;align-items:center}.split{display:grid;grid-template-columns:1fr 380px;gap:14px;height:790px}
.art{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px;overflow:hidden}.row2{display:flex;justify-content:space-between;align-items:center}
.sw2{width:36px;height:20px;border-radius:12px;background:var(--primary);position:relative;display:inline-block}.sw2:after{content:"";position:absolute;right:2px;top:2px;width:16px;height:16px;border-radius:50%;background:#fff}.sw2.off{background:var(--border)}.sw2.off:after{right:auto;left:2px}
.setnav a{display:block;padding:8px 12px;border-radius:8px;color:var(--muted)}.setnav a.on{background:var(--info-bg);color:var(--info);font-weight:700}.setnav .grp{padding-top:14px}
"""

WS_NAV = [("Chat", "&#128172;"), ("Assistants", "&#129302;"), ("Search", "&#128269;"), ("Artifacts", "&#128196;"), ("Projects", "&#128193;"), ("Scheduled", "&#9201;"), ("Threads", "&#129525;")]
RECENT = ["Summarise yesterday's refund escalations", "Draft: apology for delayed parcels", "Why did billing-help hand off?", "Weekly QA digest (draft)"]


WS_NAV_FULL = [("Work", [("Threads", "&#129525;"), ("Approvals", "&#9989;"), ("Customers", "&#128100;")]), ("Assist", [("Chat", "&#128172;"), ("Assistants", "&#129302;"), ("Search", "&#128269;"), ("Knowledge", "&#128218;")]),
               ("Create", [("Artifacts", "&#128196;"), ("Projects", "&#128193;"), ("Workflows", "&#128256;"), ("Scheduled", "&#9201;")]), ("Team (leads, reviewers)", [("Reviews", "&#128221;"), ("Insights", "&#128200;")])]


def wsapp(active: str, work: str, title: str, recent_on: int | None = None, full: bool = False) -> str:
    if full:
        nav = "".join(f'<div class="grp" style="padding:8px 10px 2px">{g}</div>' + "".join(f'<a class="{"on" if n == active else ""}"><span>{ic} &nbsp;{n}</span>{"<span class=n>2</span>" if n == "Approvals" else ""}</a>' for n, ic in items) for g, items in WS_NAV_FULL)
    else:
        nav = "".join(f'<a class="{"on" if n == active else ""}"><span>{ic} &nbsp;{n}</span></a>' for n, ic in WS_NAV)
    rec = "".join(f'<div class="recent {"on" if i == recent_on else ""}">{E(r)}</div>' for i, r in enumerate(RECENT))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} (mockup)</title><style>{WS_CSS}</style></head><body><div class="ws2">
<div class="side"><div class="brand">NorthCX <span class="note">Workspace</span></div><a class="newc">+ New chat</a><div class="nav">{nav}</div><div class="grp">Recent</div>{rec}
<div class="me"><div class="av">DK</div><div><b>Dana K.</b><div class="note">Billing team &middot; Reviewer</div></div></div></div>
<div class="work">{work}</div></div><div class="mock">Design mockup &middot; sample data</div></body></html>"""


def head(title, sub, right=""):
    return f'<div class="row2" style="margin-bottom:12px"><div><h1 style="margin:0">{title}</h1><p class="sub" style="margin:2px 0 0">{sub}</p></div><div>{right}</div></div>'


SCREENS["16-workspace-chat"] = wsapp("Chat", f"""<div class="split"><div class="card" style="display:flex;flex-direction:column;position:relative;padding:16px">
<div class="row2"><b>Summarise yesterday's refund escalations</b><span class="pill">Agent <b>care-copilot</b></span></div>
<div class="chat" style="margin-top:14px"><div class="msg u">Summarise yesterday's refund escalations and draft a note for the billing lead.</div>
<div class="msg a">I found 14 refund hand-offs yesterday. 9 were delayed deliveries, 3 duplicate charges and 2 plan changes. 6 were over the $50 limit and needed approval; all were decided within 10 minutes. I've put a summary and a draft note in the panel.<div class="src"><b>Sources</b> &middot; 14 conversations (masked) &middot; Refund policy &middot; Billing escalations playbook</div></div>
<div class="msg u">Add the three duplicate-charge cases with their order numbers.</div><div class="msg a">Done. I added them to the summary, with order numbers only (no customer details).<br><span class="note">Used: search conversations, search knowledge &middot; 2 tool calls</span></div></div>
<div class="prompt" style="position:absolute;left:14px;right:14px;bottom:14px;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px"><span class="mut">Ask, search, or draft&hellip;</span><div class="row" style="margin-top:10px;gap:8px"><span class="pill">+</span><span class="pill">Project <b>Billing escalations</b></span><span class="pill">Sources <b>Knowledge, Conversations</b></span><div style="flex:1"></div><span class="btn p">Send</span></div></div></div>
<div class="art"><div class="row2"><b>Artifact: Refund escalation summary</b><span class="b ok">saved</span></div><p class="note">Draft &middot; version 2 &middot; just now</p>
<table><tr><th>Cause</th><th>Cases</th></tr><tr><td>Delayed delivery</td><td>9</td></tr><tr><td>Duplicate charge</td><td>3</td></tr><tr><td>Plan change</td><td>2</td></tr></table>
<p style="margin-top:10px"><b>Note for the billing lead</b></p><p class="note">Nine of fourteen refund escalations yesterday came from delayed deliveries. All six over-limit approvals were decided within ten minutes. The three duplicate charges (orders 1019, 1042, 1077) point to a billing retry issue worth checking.</p>
<div class="row" style="margin-top:12px"><span class="btn p">Copy</span><span class="btn">Edit</span><span class="btn">Share to team</span><span class="btn">Schedule weekly</span></div></div></div>""", "Chat", 0)

SCREENS["17-workspace-search"] = wsapp("Search", head("Search", "Across knowledge, conversations, hand-offs and artifacts you are allowed to see.") + f"""
<div class="card" style="padding:14px"><div class="search" style="max-width:none;border:1px solid var(--border);border-radius:8px;padding:9px 12px;background:var(--bg);color:var(--text)">refund policy delayed delivery</div>
<div class="row" style="margin-top:10px"><span class="pill"><b>All</b> 18</span><span class="pill">Knowledge 6</span><span class="pill">Conversations 9</span><span class="pill">Hand-offs 2</span><span class="pill">Artifacts 1</span><div style="flex:1"></div><span class="pill">Last 30 days &#9662;</span></div></div>
<div class="card" style="margin-top:12px;padding:4px 14px">{table(["Result","Source","Matched","Access"],[
 ["<b>Refund policy</b><br><span class=note>Orders over 7 days late are eligible for a full refund&hellip;</span>",badge("Knowledge","info"),"policy &middot; delayed","everyone"],
 ["<b>Carrier delays playbook</b><br><span class=note>Check tracking before approving a refund&hellip;</span>",badge("Knowledge","info"),"delayed delivery","everyone"],
 ["<b>c-4f21</b> Refund for a delayed order<br><span class=note>customer reports a 9-day delay&hellip; (masked)</span>",badge("Conversation","gr"),"refund &middot; delayed","Billing team"],
 ["<b>Refund escalation summary</b><br><span class=note>Nine of fourteen refund escalations&hellip;</span>",badge("Artifact","ok"),"refund","you"],
 ["<b>Hand-off h-221</b> Delayed parcel, refund over limit",badge("Hand-off","warn"),"refund","Billing team"]])}</div>
<p class="note" style="margin-top:8px">Each result shows why you can see it. A source that cannot prove your access returns nothing.</p>""", "Search")

SCREENS["18-workspace-projects"] = wsapp("Projects", head("Projects", "A project keeps instructions, sources, chats and artifacts for one piece of work together.", '<span class="btn p">+ New project</span>') + f"""
<div class="g3"><div class="card"><div class="row2"><b>Billing escalations</b>{badge("team","info")}</div><p class="note">Instructions: be brief, cite the policy, never quote card numbers.</p><p class="note">Sources: Refund policy, Billing playbook &middot; 14 chats &middot; 6 artifacts</p><div class="bar"><i style="width:62%"></i></div><p class="note">Context in use: 62%</p></div>
<div class="card"><div class="row2"><b>Weekly QA review</b>{badge("team","info")}</div><p class="note">Instructions: score against the Support scorecard v3.</p><p class="note">Sources: Scorecards, sampled conversations &middot; 5 chats &middot; 9 artifacts</p><p class="note">Scheduled: every Monday 08:00</p></div>
<div class="card"><div class="row2"><b>My drafts</b>{badge("private","gr")}</div><p class="note">Instructions: my tone and signature.</p><p class="note">22 chats &middot; 31 artifacts</p></div></div>
<div class="card" style="margin-top:14px"><div class="row2"><h3>Billing escalations</h3><span class="tag">Instructions</span></div>{table(["Recent chats and artifacts","Type","Updated"],[["Summarise yesterday's refund escalations","Chat","just now"],["Refund escalation summary","Artifact","just now"],["Why did billing-help hand off?","Chat","1 h ago"],["Duplicate charges: order list","Artifact","yesterday"]])}</div>""", "Projects")

SCREENS["19-workspace-scheduled"] = wsapp("Scheduled", head("Scheduled", "Tasks that run on their own and leave an artifact or a message. Every run is listed.", '<span class="btn p">+ New scheduled task</span>') + f"""
<div class="card" style="padding:4px 14px">{table(["Task","Runs","Delivers to","Last run","Next run","Status",""],[
 ["<b>Daily hand-off triage</b><br><span class=note>Tag and rank open hand-offs by urgency</span>","every weekday 07:30","Billing queue","today 07:30","tomorrow 07:30",badge("OK","ok"),'<span class="sw2"></span>'],
 ["<b>Weekly QA digest</b><br><span class=note>Score sampled conversations, summarise trends</span>","Mondays 08:00","Artifact + email to leads","Mon 08:00","next Mon",badge("OK","ok"),'<span class="sw2"></span>'],
 ["<b>SLA breach sweep</b><br><span class=note>Find hand-offs waiting over 30 min</span>","every 15 min","Team channel","12 min ago","in 3 min",badge("1 failed run","warn"),'<span class="sw2"></span>'],
 ["<b>Knowledge freshness check</b><br><span class=note>List sources not updated in 90 days</span>","monthly","Artifact","Nov 1","Dec 1",badge("Paused","gr"),'<span class="sw2 off"></span>']])}</div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Run history: SLA breach sweep</h3>{table(["Started","Duration","Result"],[["13:45","4 s",badge("2 found","ok")],["13:30","5 s",badge("0 found","ok")],["13:15","31 s",badge("failed: search timed out","bad")],["13:00","4 s",badge("1 found","ok")]])}</div>
<div class="card"><h3>What a task may do</h3><p class="note">Scheduled tasks use only the read tools and sources of the person who made them. Anything that writes needs an approval, as in a chat.</p></div></div>""", "Scheduled")

SCREENS["20-workspace-threads"] = wsapp("Threads", head("Threads", "Customer conversations that need a person, and the ones you are handling.", '<span class="pill">Queue <b>Billing</b> &#9662;</span>') + f"""
<div class="split" style="grid-template-columns:340px 1fr"><div class="card" style="padding:10px">
<div class="row" style="margin-bottom:8px"><span class="pill"><b>Needs me</b> 2</span><span class="pill">Agent 4</span><span class="pill">Resolved 12</span></div>
<div style="background:var(--info-bg);border-radius:8px;padding:8px 10px;margin-bottom:6px"><b>c-4f21</b> {badge("approval","warn")}<br><span class="note">Refund for a delayed order &middot; 6 min</span></div>
<div style="padding:8px 10px;margin-bottom:6px"><b>c-4f1c</b> {badge("replying","info")}<br><span class="note">Wrong plan charged &middot; 11 min</span></div>
<div style="padding:8px 10px;margin-bottom:6px"><b>c-4f30</b> {badge("agent","gr")}<br><span class="note">Where is my parcel &middot; billing-help</span></div>
<div style="padding:8px 10px"><b>c-4e90</b> {badge("resolved","ok")}<br><span class="note">Invoice copy &middot; today</span></div></div>
<div class="card" style="padding:16px"><div class="row2"><b style="font-size:16px">Refund for a delayed order</b>{badge("handed off by billing-help","info")}</div><div class="chat" style="margin-top:12px"><div class="msg u">My parcel is 9 days late and I want my money back.</div><div class="msg a">A refund of $180 is above what I can approve, so I'm asking a colleague to review it.</div>
<div class="card" style="background:var(--warn-bg);border-color:#e9c46a"><b>Approval needed:</b> issue_refund $180 for order 1019<div class="row" style="margin-top:8px"><span class="btn p">Approve</span><span class="btn d">Reject</span><span class="btn">Ask for more</span></div></div>
<div class="msg a" style="align-self:flex-start"><span class="note">Draft reply (review before send)</span><br>Thanks for waiting. We've refunded $180 to your original payment method; it can take 3 to 5 days to appear.<div class="row" style="margin-top:8px"><span class="btn p">Send</span><span class="btn">Edit</span><span class="btn">Regenerate</span></div></div></div></div></div>""", "Threads")


def settings_shell(active: str, title: str, sub: str, body: str) -> str:
    personal = ["Profile", "Preferences", "Memory", "Connectors", "MCP servers", "Notifications", "Privacy and data", "Usage and limits", "API keys", "Security and sessions"]
    org = ["Overview", "Agents", "Agent Hub", "Knowledge", "Channels", "Insights", "Review and QA", "Simulations", "Models and budgets", "People and groups", "Policies", "Access keys", "Audit and activity", "Trust and reliability", "Connectors (organization)", "Data residency", "Billing and plan"]
    nav = '<div class="grp">Personal</div>' + "".join(f'<a class="{"on" if n == active else ""}">{n}</a>' for n in personal) + '<div class="grp">Organization (administrators)</div>' + "".join(f'<a class="{"on" if n == active else ""}">{n}</a>' for n in org)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} (mockup)</title><style>{WS_CSS}</style></head><body>
<div class="top"><div class="brand" style="padding:0">NorthCX <span class="note">Settings and admin</span></div><div class="sp"></div><span class="pill">Tenant <b>Acme Support (sample)</b></span><span class="btn">Open Workspace</span><div class="av">PN</div></div>
<div style="display:grid;grid-template-columns:260px 1fr;min-height:844px"><div style="background:var(--surface);border-right:1px solid var(--border);padding:12px" class="setnav">{nav}</div>
<main><h1>{E(title)}</h1><p class="sub">{sub}</p>{body}</main></div><div class="mock">Design mockup &middot; sample data</div></body></html>"""


PROFILE_TABS = lambda on: '<div class="tabs">' + "".join(f'<a class="{"on" if t == on else ""}">{t}</a>' for t in ["About you", "Instructions and persona", "Personal context", "Skills", "My assistants", "Activity and controls"]) + "</div>"

SCREENS["21-settings-profile"] = settings_shell("Profile", "Profile", "How you appear to colleagues, and how your assistants know you.", PROFILE_TABS("About you") + f"""
<div class="g2"><div class="card"><h3>About you</h3><div class="row" style="align-items:center"><div class="av" style="width:56px;height:56px;font-size:18px">PN</div><span class="btn">Change photo</span></div>
<div class="field"><label>Name</label><span class="in">Priya N.</span></div><div class="field"><label>Email (from your identity provider)</label><span class="in">priya@example.com</span></div><div class="field"><label>Team</label><span class="in">Platform admins</span></div>
<div class="field"><label>Language</label><span class="in">English &#9662;</span></div><div class="field"><label>Time zone</label><span class="in">(UTC+01:00) Europe/Amsterdam &#9662;</span></div></div>
<div><div class="card"><h3>How assistants talk to you</h3><div class="field"><label>Default assistant</label><span class="in">care-copilot &#9662;</span></div><div class="field"><label>Reply style</label><span class="in">Brief and friendly, no exclamation marks</span></div><div class="field"><label>Signature</label><span class="in">Priya, Acme Support</span></div></div>
<div class="card" style="margin-top:12px"><h3>Your access</h3><p><span class="b info">Administrator</span> <span class="b info">Release manager</span></p><p class="note">Roles come from your identity provider and cannot be edited here.</p></div>
<div class="card" style="margin-top:12px"><h3>Personal intelligence</h3><p class="note">Off. Turn it on under &ldquo;Personal context&rdquo; to let assistants use your own work context, with your permission and with sources shown.</p></div></div></div>
<div class="row" style="margin-top:14px"><span class="btn p">Save changes</span><span class="btn">Cancel</span></div>""")

SCREENS["44-settings-personal-context"] = settings_shell("Profile", "Profile", "How you appear to colleagues, and how your assistants know you.", PROFILE_TABS("Personal context") + f"""
<div class="card"><div class="row2"><div><b>Use my personal context</b> {badge("opt-in","info")}<p class="note" style="margin:2px 0 0">Assistants may draw on your own work context to be more helpful. They use it only when it helps, say what they used, and never go beyond your own access.</p></div><span class="sw2"></span></div></div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Sources it may use</h3>{table(["Source","Allows","Last used",""],[
 ["<b>My hand-offs and approvals</b>","what I handled and decided","today",'<span class="sw2"></span>'],["<b>My drafts and artifacts</b>","what I wrote and saved","today",'<span class="sw2"></span>'],["<b>My calendar</b>","free time, shifts","3 days ago",'<span class="sw2"></span>'],["<b>Team playbooks</b>","documents my team shares","yesterday",'<span class="sw2"></span>'],["<b>My email</b>","not connected",'&mdash;','<span class="sw2 off"></span>']])}
<p class="note" style="margin-top:8px">It never uses customer conversations you cannot already see, and it never saves customer details into your memory.</p></div>
<div><div class="card"><h3>What it does with it</h3>{table(["Feature",""],[["Daily briefing at 08:00",'<span class="sw2"></span>'],["Suggest next steps in chats",'<span class="sw2"></span>'],["Remind me about waiting approvals",'<span class="sw2"></span>'],["Learn my reply style from my edits",'<span class="sw2 off"></span>']])}</div>
<div class="card" style="margin-top:12px"><h3>Today's briefing (preview)</h3><p class="note">2 approvals are waiting (oldest 11 min). Your Weekly QA digest is ready. You have a team review at 14:00. Two threads you handled yesterday were rated 5.</p><p class="note">Based on: your hand-offs, your artifacts, your calendar</p></div></div></div>""")

SCREENS["45-settings-my-assistants"] = settings_shell("Profile", "Profile", "How you appear to colleagues, and how your assistants know you.", PROFILE_TABS("My assistants") + f"""
<div class="row2" style="margin-bottom:10px"><span class="note">Assistants you made for your own work. Share them with your team when they are ready.</span><span class="btn p">+ New assistant</span></div>
<div class="g2"><div class="card" style="padding:4px 14px">{table(["Assistant","Shared with","Used",""],[["<b>Refund note writer</b><br><span class=note>Turns a decision into a customer-ready note</span>","only me","14 times",'<span class="btn">Edit</span>'],["<b>Monday digest checker</b><br><span class=note>Checks the QA digest for gaps</span>","Support leads","6 times",'<span class="btn">Edit</span>'],["<b>Policy explainer</b><br><span class=note>Explains a policy in plain words</span>","Billing team","31 times",'<span class="btn">Edit</span>']])}</div>
<div class="card"><div class="row2"><h3 style="margin:0">Edit: Refund note writer</h3>{badge("draft","warn")}</div><div class="field"><label>Name</label><span class="in">Refund note writer</span></div><div class="field"><label>What it does</label><span class="in" style="color:var(--text)">Write a short, friendly note explaining a refund decision. Use the refund policy. Never include card numbers.</span></div>
<div class="field"><label>Knowledge it may use</label><span class="in">Refund policy &times; &nbsp; Billing playbook &times;</span></div><div class="field"><label>Tools</label><span class="in">search knowledge (read only)</span></div><div class="field"><label>Who can use it</label><span class="in">Only me &#9662;</span></div>
<div class="row"><span class="btn p">Save</span><span class="btn">Try it</span></div><p class="note" style="margin-top:8px">Your assistants can only use tools and knowledge you can use yourself. Sharing with a team needs a reviewer when an assistant can write anything.</p></div></div>""")

SCREENS["46-settings-activity-controls"] = settings_shell("Profile", "Profile", "How you appear to colleagues, and how your assistants know you.", PROFILE_TABS("Activity and controls") + f"""
<div class="g2"><div class="card"><h3>What my assistants used (last 7 days)</h3>{table(["When","Assistant","Used","For"],[["today 13:52","care-copilot","my hand-offs","draft for c-4f21"],["today 08:00","briefing","calendar, approvals","daily briefing"],["Nov 7","report builder","my artifacts","weekly summary"],["Nov 6","care-copilot","team playbooks","policy answer"]])}<p class="note" style="margin-top:8px">Each answer also shows what it used, with a link to the source.</p></div>
<div><div class="card"><h3>Controls</h3>{table(["Setting",""],[["Save my chats","<b>90 days</b> &#9662;"],["Start the next chat as a temporary chat (not saved)",'<span class="sw2 off"></span>'],["Use my chats to improve my assistants",'<span class="sw2"></span>']])}<div class="row" style="margin-top:10px"><span class="btn">Export my data</span><span class="btn d">Delete my chats</span><span class="btn d">Turn off and erase personal context</span></div></div>
<div class="card" style="margin-top:12px"><h3>What stays out</h3><p class="note">Customer messages and personal details are never saved to your personal context or memory. Your administrator's data policy still applies to everything here, and your actions are recorded in the audit log without their content.</p></div></div></div>""")

SCREENS["22-settings-memory"] = settings_shell("Memory", "Memory", "What your assistants remember. Read it, edit it, erase it. Instructions always win over memory.", f"""
<div class="g2"><div class="card"><div class="row2"><div><b>Remember things for me</b><p class="note" style="margin:0">Assistants save useful, lasting facts about how you work, and you can say &ldquo;remember this&rdquo; at any time.</p></div><span class="sw2"></span></div></div>
<div class="card"><div class="row2"><div><b>Use memory in new chats</b><p class="note" style="margin:0">Turn off to start clean. You can also start a single chat without memory.</p></div><span class="sw2"></span></div></div></div>
<div class="tabs" style="margin-top:14px"><a class="on">Personal (4)</a><a>Project: Billing escalations (3)</a><a>Team: Billing (5)</a></div>
<div class="card" style="padding:4px 14px">{table(["Memory","Where it came from","Applies to","Updated",""],[
 ["Prefers short replies with the policy name cited","you said &ldquo;remember&rdquo; &middot; chat Nov 3","all chats","Nov 3",'<span class="btn">Edit</span> <span class="btn d">Erase</span>'],
 ["Works Monday to Thursday; weekly QA digest goes out Friday","noticed in chat &middot; Oct 28","all chats","Oct 28",'<span class="btn">Edit</span> <span class="btn d">Erase</span>'],
 ["Never include customer names in summaries, use order numbers","you added","all chats","Oct 20",'<span class="btn">Edit</span> <span class="btn d">Erase</span>'],
 ["Billing lead is Marco L.","noticed in chat &middot; Oct 12","all chats","Oct 12",'<span class="btn">Edit</span> <span class="btn d">Erase</span>']])}</div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>How memory and instructions work together</h3><p class="note">Memory is what assistants have learned about you. Instructions are what you or your organization told them to do. <b>If they conflict, instructions win</b>, and organization rules win over both. Memory never overrides a policy, a fact from a source, or a customer's data.</p></div>
<div class="card"><h3>Keep it honest</h3><p class="note">Memory should not make an assistant simply agree with you. Assistants still cite sources and say when a source disagrees with a remembered preference. Review memory now and then; items unused for 90 days are offered for removal.</p></div></div>
<div class="row" style="margin-top:12px"><span class="btn p">+ Add a memory</span><span class="btn">Export</span><span class="btn d">Erase all personal memory</span></div>
<p class="note" style="margin-top:10px">Memory never stores customer messages or personal details. Project memory stays in its project; team memory is shared with the team and edited by team leads.</p>""")

SCREENS["47-settings-instructions-persona"] = settings_shell("Profile", "Profile", "How you appear to colleagues, and how your assistants know you.", PROFILE_TABS("Instructions and persona") + f"""
<div class="g2"><div><div class="card"><div class="row2"><h3 style="margin:0">Your instructions</h3><span class="note">1,140 of 4,000 characters</span></div><p class="note">Standing guidance for every chat you start. Plain language.</p>
<div class="in" style="display:block;color:var(--text);line-height:1.6">Write like a colleague, not a bot. Keep answers short and put the decision first. Cite the policy name when a policy applies. Use order numbers, not customer names, in anything I share. If you are unsure, say so and show the source.</div>
<div class="row" style="margin-top:10px"><span class="btn p">Save</span><span class="btn">Try it on a sample</span></div></div>
<div class="card" style="margin-top:12px"><h3>Persona and style</h3><p class="note">How answers sound to you. Choose one, or teach it from your own writing.</p><div class="row"><span class="pill"><b>Concise</b></span><span class="pill">Formal</span><span class="pill">Friendly</span><span class="pill">Explanatory</span><span class="pill">Custom: my style</span></div>
<div class="field"><label>Custom style from your writing</label><span class="in">3 samples added (a reply, a digest, a note)</span></div><div class="row"><span class="btn">Add a sample</span><span class="btn">Edit custom style</span></div>
<p class="note" style="margin-top:8px">This changes how your assistants write for you. It does not change what the customer-facing agents say; that is set by your administrators.</p></div></div>
<div><div class="card"><h3>What applies to a chat (highest wins)</h3>{table(["Layer","Set by","State"],[["Platform and organization rules","administrators",badge("locked","gr")],["Team instructions (Billing)","team lead",badge("2 rules","info")],["Project instructions","project owner",badge("per project","info")],["Your instructions","you",badge("active","ok")],["Style for this chat","you, per chat",badge("Concise","ok")],["Memory","learned","informs, never overrides"]])}<p class="note" style="margin-top:8px">A closer layer can add or narrow, never loosen a rule above it. &#128274; Locked layers show who set them.</p></div>
<div class="card" style="margin-top:12px"><h3>Preview: same answer, your style</h3><div class="src"><b>Before</b> &middot; I have reviewed the situation and it appears that the refund may be eligible for approval under the applicable policy, subject to the stated limits.</div><div class="src"><b>Your style</b> &middot; Approve it. Order 1019 is 9 days late; the refund policy covers over 7 days (&sect;3). Over $150 needs a lead.</div></div></div></div>""")

SCREENS["23-settings-connectors-mcp"] = settings_shell("Connectors", "Connectors and MCP servers", "Systems your assistants can use on your behalf. You see only what your role allows.", f"""
<div class="tabs"><a class="on">Connectors</a><a>MCP servers</a></div>
<div class="g3"><div class="card"><div class="row2"><b>Helpdesk</b>{badge("Connected","ok")}</div><p class="note">Read hand-offs, add notes</p><p class="note">Scopes: read &middot; write notes</p><div class="row"><span class="btn">Permissions</span><span class="btn d">Disconnect</span></div></div>
<div class="card"><div class="row2"><b>Orders system</b>{badge("Connected","ok")}</div><p class="note">Look up orders and tracking</p><p class="note">Scopes: read only</p><div class="row"><span class="btn">Permissions</span><span class="btn d">Disconnect</span></div></div>
<div class="card"><div class="row2"><b>Calendar</b>{badge("Not connected","gr")}</div><p class="note">Find times, schedule follow-ups</p><p class="note">Needs your approval to connect</p><div class="row"><span class="btn p">Connect</span></div></div></div>
<div class="card" style="margin-top:14px"><div class="row2"><h3>MCP servers</h3><span class="btn p">+ Add server</span></div>{table(["Server","Address","Tools","Mode","Status",""],[
 ["<b>docs-search</b><br><span class=note>added by organization</span>","mcp.docs.example.com","2 of 2 enabled",badge("read-only","ok"),badge("OK","ok"),'<span class="sw2"></span>'],
 ["<b>team-wiki</b><br><span class=note>added by you</span>","wiki.example.com/mcp","3 of 5 enabled",badge("read-only","ok"),badge("OK","ok"),'<span class="sw2"></span>'],
 ["<b>ticket-actions</b><br><span class=note>organization policy: needs approval</span>","tickets.example.com/mcp","&mdash;",badge("write tools","warn"),badge("Waiting for admin","warn"),'<span class="sw2 off"></span>']])}
<p class="note" style="margin:8px 0 2px">Remote tools default to write and need an approval unless an administrator marks them read-only. Tools from servers you add are limited to your own permissions. &#128274; Third-party servers are controlled by organization policy.</p></div>""")


# ---------- New interfaces (round 2): workspace home and artifacts; admin Explorer, Expert Answers, agent improvement, channels, trust, privacy ----------
SCREENS["24-workspace-artifacts"] = wsapp("Artifacts", head("Artifacts", "Everything your assistants have produced for you and your team. Versioned, shareable, schedulable.", '<span class="btn">Export</span>') + f"""
<div class="tools"><span class="in">Search artifacts&hellip;</span><span class="pill"><b>All</b></span><span class="pill">Summaries</span><span class="pill">Drafts</span><span class="pill">Reports</span><span class="pill">Digests</span><div style="flex:1"></div><span class="in">Project: Any &#9662;</span><span class="in">Owner: Me &#9662;</span></div>
<div class="split" style="grid-template-columns:1fr 400px;height:690px"><div class="card" style="padding:4px 14px">{table(["Artifact","Type","Project","Shared","Updated"],[
 ["<b>Refund escalation summary</b><br><span class=note>v2 &middot; from chat</span>",badge("Summary","info"),"Billing escalations","Team","just now"],
 ["<b>Weekly QA digest</b><br><span class=note>v14 &middot; scheduled</span>",badge("Digest","ok"),"Weekly QA review","Leads","Mon 08:00"],
 ["<b>Apology for delayed parcels</b><br><span class=note>v3 &middot; draft</span>",badge("Draft","warn"),"My drafts","Only me","1 h ago"],
 ["<b>Duplicate charges: order list</b><br><span class=note>v1</span>",badge("Report","gr"),"Billing escalations","Team","yesterday"],
 ["<b>Carrier delays: weekly trend</b><br><span class=note>v6 &middot; scheduled</span>",badge("Report","gr"),"Billing escalations","Team","Mon"]])}</div>
<div class="art"><div class="row2"><b>Refund escalation summary</b><span class="b ok">v2 current</span></div><p class="note">Created by care-copilot for you &middot; sources: 14 conversations (masked), Refund policy</p>
<p style="margin-top:8px">Nine of fourteen refund escalations yesterday came from delayed deliveries. All six over-limit approvals were decided within ten minutes&hellip;</p>
<h3 style="margin-top:12px">Versions</h3>{table(["Version","Who","When"],[["v2","you, with care-copilot","just now"],["v1","care-copilot","1 h ago"]])}
<div class="row" style="margin-top:12px"><span class="btn p">Open</span><span class="btn">Share</span><span class="btn">Schedule</span><span class="btn">Export</span><span class="btn d">Delete</span></div><p class="note" style="margin-top:8px">Sharing never exposes conversations you cannot see. Shared copies show the sources they were built from.</p></div></div>""", "Artifacts")

SCREENS["25-workspace-home"] = wsapp("Chat", f"""<div style="max-width:880px;margin:30px auto 0"><h1 style="font-size:28px;margin:0 0 4px">Good afternoon, Dana</h1><p class="sub">2 things need you. Your Monday QA digest is ready.</p>
<div class="card" style="padding:16px;margin-top:14px"><span class="mut" style="font-size:16px">What do you want to do?</span><div class="row" style="margin-top:14px;gap:8px"><span class="pill">+</span><span class="pill">Assistant <b>care-copilot</b></span><span class="pill">Project <b>Billing escalations</b></span><span class="pill">Sources <b>Knowledge, Conversations</b></span><div style="flex:1"></div><span class="btn p">Start</span></div></div>
<div class="row" style="margin-top:12px"><span class="pill">Summarise my open threads</span><span class="pill">Draft replies for waiting approvals</span><span class="pill">What changed in the refund policy?</span><span class="pill">Show conversations that were rated 1 or 2</span></div>
<div class="g3" style="margin-top:20px"><div class="card"><h3>Needs you</h3><p><b>c-4f21</b> approval &middot; refund $180 <span class="b warn">6 min</span></p><p><b>c-4f1c</b> reply waiting <span class="b info">11 min</span></p><span class="btn p">Open Threads</span></div>
<div class="card"><h3>Ready for you</h3><p><b>Weekly QA digest</b><br><span class="note">Scheduled &middot; Mon 08:00 &middot; 240 reviewed</span></p><span class="btn">Open artifact</span></div>
<div class="card"><h3>Recent</h3><p class="note">Refund escalation summary &middot; just now</p><p class="note">Apology for delayed parcels &middot; 1 h ago</p><p class="note">Why did billing-help hand off? &middot; yesterday</p></div></div></div>""", "Home")

SCREENS["26-admin-insights-explorer"] = settings_shell("Insights", "Insights: Explorer", "Ask a question about your conversations in plain language. Answers use masked samples and cite them.", f"""
<div class="card" style="padding:14px"><div class="in" style="font-size:15px;color:var(--text)">Why did refund hand-offs go up last week?</div><div class="row" style="margin-top:10px"><span class="pill">Last 7 days &#9662;</span><span class="pill">Agent <b>billing-help</b></span><span class="pill">Production</span><div style="flex:1"></div><span class="btn p">Ask</span></div></div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Finding</h3><p>Refund hand-offs rose from <b>31</b> to <b>52</b> (+68%). <b>Delayed deliveries</b> explain most of the rise.</p>
{table(["Cause","Hand-offs","Change"],[["Delayed delivery","26",'<span class="b bad">+19</span>'],["Duplicate charge","12",'<span class="b warn">+3</span>'],["Plan change","8","0"],["Other","6","-1"]])}
<p class="note" style="margin-top:8px">52 conversations analysed. 6 shown below as masked samples.</p>
<h3 style="margin-top:12px">Samples (masked)</h3><div class="src"><b>c-4f21</b> customer says the parcel is 9 days late and asks for money back. The agent could not approve $180.</div><div class="src"><b>c-4f0a</b> customer asks where a parcel is after 8 days; no tracking update found.</div><div class="src"><b>c-4ef2</b> customer reports being charged twice; agent verified, hand-off needed for the refund.</div></div>
<div><div class="card"><h3>Recommendations</h3><p><b>1.</b> Knowledge has no answer for carrier delays over 7 days.</p><span class="btn p">Draft an article</span><p style="margin-top:12px"><b>2.</b> The agent hands off refunds over $50; 21 of 26 were under $200 and approved.</p><span class="btn">Review the refund limit</span><p style="margin-top:12px"><b>3.</b> No test covers a delayed-parcel refund.</p><span class="btn">Create scenario</span></div>
<div class="card" style="margin-top:12px"><h3>Follow-ups</h3><div class="row"><span class="pill">Which carriers?</span><span class="pill">Which days?</span><span class="pill">Same for returns?</span></div></div>
<div class="card" style="margin-top:12px"><h3>Why this is safe</h3><p class="note">Samples are masked. You only see conversations your role allows. The question and the conversations opened are recorded in the audit log.</p></div></div></div>""")

SCREENS["27-admin-expert-answers"] = settings_shell("Knowledge", "Knowledge: Suggested articles", "Drafts written from how your people resolved similar cases. Nothing is published until someone approves it.", f"""
<div class="tabs"><a>Sources</a><a>Documents</a><a>Gaps</a><a class="on">Suggested articles <span class="n" style="background:var(--warn-bg);color:var(--warn);border-radius:9px;padding:0 6px;font-size:11px">4</span></a></div>
<div class="g2"><div class="card" style="padding:4px 10px">{table(["Draft","Based on","Asked","Status"],[
 ["<b>Refunds for parcels delayed over 7 days</b>","11 resolved cases","26 times",badge("Needs review","warn")],["<b>Duplicate charge after a retry</b>","5 resolved cases","12 times",badge("Needs review","warn")],["<b>Changing plan mid-cycle</b>","8 resolved cases","8 times",badge("Approved","ok")],["<b>Invoice copy by email</b>","3 resolved cases","6 times",badge("Rejected","gr")]])}</div>
<div class="card"><div class="row2"><b>Refunds for parcels delayed over 7 days</b>{badge("Draft v1","warn")}</div><p class="note">Written from 11 resolved hand-offs by 4 people (masked). Wording is grounded in these cases; each claim links to its source.</p>
<p style="margin-top:8px">If a parcel is more than 7 days late, check tracking first. If the carrier shows no movement for 5 days, the customer is eligible for a full refund. Refunds over $150 need a lead's approval.</p>
<div class="src"><b>Sources</b> &middot; c-4f21, c-4e77, c-4de2 &hellip; (8 more) &middot; Refund policy &sect;3</div><div class="src"><b>Check before publishing</b> &middot; the $150 limit differs from the policy page ($200). Confirm which is right.</div>
<div class="row" style="margin-top:12px"><span class="btn p">Edit and approve</span><span class="btn">Publish to knowledge</span><span class="btn d">Reject</span></div></div></div>""")

SCREENS["28-admin-improve-agent"] = settings_shell("Agents", "Improve billing-help", "An improvement session: investigate, propose a change, test it, then send it to a reviewer. Nothing goes live from here.", f"""
<div class="split" style="grid-template-columns:1fr 440px;height:760px"><div class="card" style="display:flex;flex-direction:column;position:relative"><div class="row2"><b>Session: delayed-parcel refunds</b><span class="pill">Builder assistant</span></div>
<div class="chat" style="margin-top:12px"><div class="msg u">Why did billing-help hand off so many delayed-parcel refunds?</div><div class="msg a">26 of 52 refund hand-offs last week were delayed parcels. In 21 of them the refund was under $200 and was approved. The agent's limit is $50 and it has no guidance for carrier delays.<div class="src">Looked at: 26 conversations (masked) &middot; spec v7 &middot; knowledge gaps</div></div>
<div class="msg u">Propose a fix that keeps people in the loop for large refunds.</div><div class="msg a">I propose raising the no-approval limit to $100 for delayed parcels only, and adding a knowledge article. I replayed 20 past conversations against the change.</div></div></div>
<div><div class="card"><h3>Proposed change to spec</h3><div class="src mono" style="background:#fdecec">- issue_refund: up to $50 without approval</div><div class="src mono" style="background:#e8f6ee">+ issue_refund: up to $100 without approval when reason is delayed_delivery</div><div class="src mono" style="background:#e8f6ee">+ knowledge: Refunds for parcels delayed over 7 days (suggested article, needs approval)</div></div>
<div class="card" style="margin-top:12px"><h3>Tests</h3>{table(["Check","Result"],[["Required scenarios (41)",badge("41 passed","ok")],["New scenario: delayed parcel $90",badge("passes","ok")],["New scenario: delayed parcel $120",badge("hands off","ok")],["Replay of 20 past conversations",badge("17 same, 3 improved","ok")]])}</div>
<div class="card" style="margin-top:12px"><h3>Next</h3><p class="note">A reviewer must approve. Production releases need two people.</p><div class="row"><span class="btn p">Request review</span><span class="btn">Edit proposal</span><span class="btn d">Discard</span></div></div></div></div>""")

SCREENS["29-admin-channels"] = settings_shell("Channels", "Channels", "Where customers reach your agents. One agent, the same rules on every channel.", f"""
<div class="g4">{stat("Channels live","6","web, email, SMS, WhatsApp, Telegram, voice")}{stat("Conversations (7 d)","12,480","")}{stat("Hand-off rate","14%","lowest on web 11%, highest on voice 22%")}{stat("Issues","1","email delivery retrying")}</div>
<div class="card" style="margin-top:12px;padding:4px 10px">{table(["Channel","Address","Agent","7-day volume","Hand-offs","Health",""],[
 ["<b>Web chat</b>","widget on acme.example","support-agent","5,740","11%",badge("OK","ok"),'<span class="btn">Configure</span>'],
 ["<b>Email</b>","support@acme.example","support-agent","2,995","15%",badge("Replies retrying","warn"),'<span class="btn">Configure</span>'],
 ["<b>WhatsApp</b>","+31 20 555 0100 &middot; +31 20 555 0101","support-agent, returns","1,750","13%",badge("OK","ok"),'<span class="btn">Configure</span>'],
 ["<b>SMS</b>","+31 20 555 0102","returns","1,120","12%",badge("OK","ok"),'<span class="btn">Configure</span>'],
 ["<b>Telegram</b>","@acme_support_bot","support-agent","310","14%",badge("OK","ok"),'<span class="btn">Configure</span>'],
 ["<b>Voice</b>","+31 20 555 0103","support-agent","565","22%",badge("OK","ok"),'<span class="btn">Configure</span>']])}</div>
<div class="g3" style="margin-top:12px"><div class="card"><h3>Same rules everywhere</h3><p class="note">Guardrails, approvals and tool scopes come from the agent, not the channel. Channel settings only change delivery: limits, templates, opening hours.</p></div>
<div class="card"><h3>Add a channel</h3><p class="note">Assistant apps and other surfaces can be added through MCP or the API.</p><span class="btn">Browse options</span></div><div class="card"><h3>Test a channel</h3><p class="note">Send a test message through the real path and see the result.</p><span class="btn">Run test</span></div></div>""")

SCREENS["30-admin-trust"] = settings_shell("Trust and reliability", "Trust and reliability", "What protects customers today, how it is performing, and what has not been done yet.", f"""
<div class="g4">{stat("Guardrail blocks (7 d)","212","1.7% of turns")}{stat("Supervisor interventions","38","corrected 31 &middot; handed off 7")}{stat("Adversarial suite","96%","58 of 60 passed &middot; ran Nov 8")}{stat("Audit chain","Verified","checked 10 min ago")}</div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Adversarial scenarios, last 8 runs</h3><div style="display:flex;align-items:flex-end;gap:10px;height:110px;margin:10px 0"><div style="flex:1;background:var(--primary);height:90%"></div><div style="flex:1;background:var(--primary);height:92%"></div><div style="flex:1;background:var(--primary);height:88%"></div><div style="flex:1;background:var(--primary);height:94%"></div><div style="flex:1;background:var(--primary);height:95%"></div><div style="flex:1;background:var(--primary);height:93%"></div><div style="flex:1;background:var(--primary);height:96%"></div><div style="flex:1;background:var(--primary);height:96%"></div></div>
{table(["Failing now","Category","Since"],[["Instruction hidden in a PDF","prompt injection","Nov 8"],["Refund amount split in two requests","policy bypass","Nov 8"]])}</div>
<div class="card"><h3>Protections in place</h3>{table(["Control","State"],[["Supervisor on replies",badge("on","ok")],["Deterministic tool scopes and approvals",badge("on","ok")],["PII masking in traces",badge("on","ok")],["Abuse detection",badge("on","ok")],["Data residency policy",badge("compliant","ok")],["Hash-chained audit log",badge("verified","ok")]])}</div></div>
<div class="card" style="margin-top:12px"><h3>Not done yet (shown on purpose)</h3>{table(["Item","State"],[["Independent penetration test",badge("not done","bad")],["Live-model quality pass",badge("not done","bad")],["SOC 2, ISO 27001",badge("not started","gr")],["Judge agreement with reviewers",badge("not measured","warn")]])}</div>""")

SCREENS["31-settings-privacy"] = settings_shell("Privacy and data", "Privacy and data", "What is stored about you and your work, how long, and how to export or erase it.", f"""
<div class="g2"><div class="card"><h3>What is kept</h3>{table(["Data","Kept for","Where"],[["Your chats with assistants","90 days","eu"],["Artifacts you created","until you delete them","eu"],["Memory notes","until you erase them","eu"],["Audit entries about your actions","2 years (cannot be erased)","eu"]])}<p class="note" style="margin-top:8px">Set by your organization. Customer conversations are masked in everything shown to you here.</p></div>
<div><div class="card"><h3>Your data</h3><div class="row"><span class="btn p">Export my data</span><span class="btn d">Erase my chats</span><span class="btn d">Erase my memory</span></div><p class="note" style="margin-top:8px">Erasing is recorded in the audit log without the content.</p></div>
<div class="card" style="margin-top:12px"><h3>Where your text goes</h3><p class="note">Your messages are sent to the model provider your administrator configured (Anthropic, region us) and to the knowledge search service. See the organization's data residency page.</p></div></div></div>""")


SCREENS["32-admin-models-routing"] = settings_shell("Models and budgets", "Models and routing", "Choose where each kind of request is answered: on your own servers, in a private cloud, or by a public cloud model. Rules first, then cost.", f"""
<div class="g3"><div class="card"><div class="row2"><b>Local</b>{badge("self-hosted, eu","ok")}</div><p class="note">llama-70b-instruct &middot; your servers</p><p>Data never leaves your network</p><p class="note">Tools: single and parallel &middot; no images &middot; p50 1.9 s</p></div>
<div class="card"><div class="row2"><b>Private cloud</b>{badge("eu region","info")}</div><p class="note">your cloud account, open-weight model</p><p>Data stays in your region and account</p><p class="note">Tools: single and parallel &middot; p50 1.2 s</p></div>
<div class="card"><div class="row2"><b>Public cloud</b>{badge("us","warn")}</div><p class="note">anthropic:claude-sonnet-5-5, claude-haiku-5-5</p><p>Text is sent to the provider</p><p class="note">Tools, images, documents &middot; p50 1.0 s</p></div></div>
<div class="card" style="margin-top:12px"><h3>Routing rules (first match wins)</h3>{table(["#","When","Use","Why"],[
 ["1","Conversation holds sensitive data (identity verified, card or ID patterns seen)","<b>Local only</b>",badge("locked by tenant policy","gr")],
 ["2","Channel is voice","<b>Fast model</b> (private cloud, then public)","latency under 1.5 s"],
 ["3","Agent has multi-step tool chains or write tools","<b>Qualified</b> models only","see qualification below"],
 ["4","Simple question the agent answers from knowledge","<b>Local</b>","cheapest model that passed"],
 ["5","Anything else","<b>Default</b> (public cloud)","quality"]])}<p class="note" style="margin-top:6px">Fallback never crosses a tier the data rules forbid: a local-only conversation fails over to another local model or to a person, never to the public cloud.</p></div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Qualification (scenario pass rate)</h3>{table(["Agent","claude-sonnet-5-5","llama-70b (local)","Needed"],[["support-agent",badge("100%","ok"),badge("83% not qualified","bad"),"95%"],["returns",badge("100%","ok"),badge("96% qualified","ok"),"95%"],["billing-help",badge("100%","ok"),badge("71% not qualified","bad"),"95%"]])}<p class="note" style="margin-top:6px">A model serves an agent only after passing that agent's required scenarios. Re-checked on every release.</p></div>
<div class="card"><h3>Last 5 decisions</h3>{table(["Conversation","Chosen","Reason"],[["c-4f30","local llama-70b","rule 4"],["c-4f21","claude-sonnet-5-5","rule 3"],["c-4f1c","local llama-70b","rule 1 (verified identity)"],["c-4f12","private cloud","rule 2"],["c-4f0a","claude-sonnet-5-5","rule 5"]])}<p class="note" style="margin-top:6px">Every decision is saved in the conversation's trace.</p></div></div>
<div class="g4" style="margin-top:12px">{stat("Share local (7 d)","38%","of turns")}{stat("Cost (7 d)","$1,942","est. $3,100 all public")}{stat("Fallbacks","14","0 crossed a forbidden tier")}{stat("Re-qualification due","1","billing-help &middot; local")}</div>""")


SCREENS["33-workspace-model-picker"] = wsapp("Chat", f"""<div class="split"><div class="card" style="display:flex;flex-direction:column;position:relative;padding:16px">
<div class="row2"><b>Draft a note about the duplicate charges</b><span class="pill">Assistant <b>care-copilot</b></span></div>
<div class="chat" style="margin-top:14px"><div class="msg u">Draft a short note to the billing lead about the three duplicate charges, with the customers' details so she can call them.</div>
<div class="msg a">This chat contains customer details, so I'm using a <b>private</b> model that runs on your own servers. Here is the note&hellip;<div class="src">Answered by: local llama-70b &middot; rule 1 (customer data) &middot; <a style="color:var(--primary)">Why this model?</a></div></div></div>
<div style="position:absolute;left:14px;bottom:92px;width:430px;background:var(--surface);border:1px solid var(--border);border-radius:12px;box-shadow:0 10px 30px #0f172a33;padding:8px;z-index:5">
<div class="note" style="padding:4px 8px">Choose how this chat is answered</div>
<div style="padding:8px;border-radius:8px;background:var(--info-bg)"><div class="row2"><b>Auto</b><span class="b ok">recommended</span></div><span class="note">NorthCX picks the model for each message using your organization's rules.</span></div>
<div style="padding:8px"><div class="row2"><b>Faster and cheaper</b><span class="note">~0.6 s &middot; ~$0.002 / message</span></div><span class="note">Smaller model. Good for quick lookups and short drafts.</span></div>
<div style="padding:8px"><div class="row2"><b>Private only</b>{badge("on your servers","ok")}</div><span class="note">Nothing leaves your network. Slower, simpler tasks.</span></div>
<div style="padding:8px;opacity:.55"><div class="row2"><b>Best quality</b><span class="b bad">unavailable now</span></div><span class="note">Strongest cloud model, text is sent to the provider (us). Not allowed here: this chat contains customer data and your organization allows private models only.</span></div>
<div style="border-top:1px solid var(--border);margin-top:4px;padding:6px 8px" class="note">Your default: Auto &middot; change in Preferences</div></div>
<div class="prompt" style="position:absolute;left:14px;right:14px;bottom:14px;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px"><span class="mut">Ask, search, or draft&hellip;</span><div class="row" style="margin-top:10px;gap:8px"><span class="pill">+</span><span class="pill">Project <b>Billing escalations</b></span><span class="pill" style="border-color:var(--primary)">Model <b>Auto &#9662;</b></span><span class="b ok">private</span><div style="flex:1"></div><span class="btn p">Send</span></div></div></div>
<div class="art"><b>Where this chat is answered</b><p class="note">Updates as you type</p>{table(["Check","Result"],[["Contains customer data",badge("yes","warn")],["Allowed tiers",badge("local only","ok")],["Chosen","local llama-70b"],["Leaves your network",badge("no","ok")]])}
<p class="note" style="margin-top:10px">Your administrator sets which models exist and what is allowed for which data. You choose within that. Locked choices say why.</p></div></div>""", "Chat", 0)

SCREENS["34-admin-agent-model-policy"] = settings_shell("Agents", "billing-help: model policy", "Choose which models this agent may use and whether staff can pick. Limits come from your organization's policy.", f"""
<div class="g2"><div class="card"><h3>Allowed models for this agent</h3>{table(["Model","Tier","Qualified","Allowed"],[
 ["claude-sonnet-5-5",badge("public","warn"),badge("100%","ok"),'<span class="sw2"></span>'],["claude-haiku-5-5",badge("public","warn"),badge("97%","ok"),'<span class="sw2"></span>'],["llama-70b (local)",badge("local","ok"),badge("71% not qualified","bad"),'<span class="sw2 off"></span>'],["fast-eu (private cloud)",badge("private","info"),badge("94% not qualified","bad"),'<span class="sw2 off"></span>']])}
<p class="note" style="margin-top:8px">A model can be switched on only after it passes this agent's required scenarios.</p></div>
<div><div class="card"><h3>Default for this agent</h3><div class="field"><label>Selection</label><span class="in">Auto (follow routing rules) &#9662;</span></div><div class="field"><label>Fallback order</label><span class="in">claude-sonnet-5-5 &rarr; claude-haiku-5-5 &rarr; hand off to a person</span></div></div>
<div class="card" style="margin-top:12px"><h3>Who can choose</h3>{table(["Person","May pick a model?"],[["Customers","never (the agent decides)"],["Staff using this agent in Workspace",badge("only Auto and Faster","info")],["Developers testing in Admin",badge("any allowed model","ok")]])}<p class="note" style="margin-top:8px">&#128274; Staff cannot choose a public model for conversations with customer data (organization policy).</p></div></div></div>""")


def _card(title, who, desc, tags, status, btn):
    return f'<div class="card"><div class="row2"><b>{title}</b>{status}</div><p class="note" style="margin:2px 0 6px">{who}</p><p style="margin:0 0 8px">{desc}</p><div style="margin-bottom:10px">{"".join(f"<span class=tag>{t}</span>" for t in tags)}</div><span class="btn {"p" if btn=="Install" else ""}">{btn}</span></div>'


SCREENS["35-admin-agent-hub"] = settings_shell("Agent Hub", "Agent Hub", "Predefined agents you can install, adapt and release. Each comes with the tests that prove it works.", f"""
<div class="tools"><span class="in">Search the hub&hellip;</span><span class="pill"><b>All</b></span><span class="pill">Customer-facing</span><span class="pill">Staff assistants</span><span class="pill">Installed</span><div style="flex:1"></div><span class="in">Category: Any &#9662;</span><span class="in">Channel: Any &#9662;</span><span class="btn">Publish your own</span></div>
<div class="tabs"><a class="on">Browse</a><a>Installed (3)</a><a>Updates (1)</a><a>My organization</a></div>
<div class="g3">{_card("Order status","Customer-facing &middot; built in","Answers where-is-my-order questions from your order system; hands off when it cannot find the order.",["orders-api","web","email","sms"],badge("Installed v2","ok"),"Open")}
{_card("Returns and refunds","Customer-facing &middot; built in","Handles return questions and refund requests; refunds above the limit wait for a person.",["billing-system","approval"],badge("Update v3","warn"),"Update")}
{_card("Knowledge FAQ","Customer-facing &middot; built in","Answers only from your documents, cites them, and hands off when they do not cover the question.",["knowledge","web","whatsapp"],badge("Installed v1","ok"),"Open")}
{_card("Human triage","Customer-facing &middot; built in","Greets the customer, collects what a person needs, and hands the conversation over.",["handoff","all channels"],badge("Available","info"),"Install")}
{_card("Billing and invoices","Customer-facing &middot; proposed","Invoice copies, payment status, duplicate-charge checks; refunds need approval.",["billing-system","approval"],badge("Coming","gr"),"Notify me")}
{_card("Care copilot","Staff assistant &middot; proposed","Drafts replies, summarises conversations and finds sources for support staff; cannot send on its own.",["knowledge","workspace"],badge("Coming","gr"),"Notify me")}</div>
<p class="note" style="margin-top:10px">Built-in agents ship with NorthCX. Your organization's own published agents appear under &ldquo;My organization&rdquo;. Nothing in the hub runs until you install it, test it and release it.</p>""")

SCREENS["36-admin-hub-install"] = settings_shell("Agent Hub", "Install: Returns and refunds", "Fill in your details, check what it needs, run its tests, then release it like any agent.", f"""
<div class="row" style="margin-bottom:12px"><span class="b ok">1 Details</span><span class="b ok">2 Requirements</span><span class="b info">3 Tests</span><span class="b gr">4 Review and release</span></div>
<div class="g2"><div><div class="card"><h3>Requirements check</h3>{table(["Needs","Status"],[["Tool lookup_order (orders-api)",badge("connected","ok")],["Tool issue_refund (billing-system)",badge("connected","ok")],["Approval for refunds above the limit",badge("rule exists","ok")],["Knowledge source: Returns policy",badge("missing","bad")],["Channels web, email",badge("enabled","ok")],["Model qualified for this agent",badge("claude-sonnet-5-5 100%","ok")]])}<p class="note" style="margin-top:8px">One thing is missing. Add the Returns policy to knowledge or install without it (the agent will hand off questions about policy).</p><div class="row"><span class="btn p">Add knowledge source</span><span class="btn">Install without</span></div></div>
<div class="card" style="margin-top:12px"><h3>Your details</h3><div class="field"><label>Company name</label><span class="in">Acme Support</span></div><div class="field"><label>Refund limit without approval</label><span class="in">$50</span></div><div class="field"><label>Return window (days)</label><span class="in">30</span></div></div></div>
<div><div class="card"><h3>Tests that come with it</h3>{table(["Scenario","Result"],[["Asks for a return inside the window",badge("passes","ok")],["Asks for a refund above the limit",badge("hands off for approval","ok")],["Return outside the window",badge("explains the policy","ok")],["Tries to talk the agent past the limit",badge("refused","ok")],["Order not found",badge("hands off","ok")]])}<p class="note" style="margin-top:8px">5 of 5 passed against your settings. These join your required scenarios.</p></div>
<div class="card" style="margin-top:12px"><h3>What this creates</h3><p class="note">A draft agent <b>returns-and-refunds</b> (version 1) in Staging. It is not live. Releasing to Production follows your release rules (two-person approval).</p><div class="row"><span class="btn p">Create draft</span><span class="btn">Cancel</span></div></div></div></div>""")

SCREENS["37-workspace-agent-hub"] = wsapp("Assistants", head("Assistants", "Predefined assistants your organization has made available. Pick one to start a chat with it.") + f"""
<div class="tools"><span class="in">Search assistants&hellip;</span><span class="pill"><b>All</b></span><span class="pill">Favorites</span><span class="pill">My team</span></div>
<div class="g3">{_card("Care copilot","Billing team &middot; v2","Drafts replies, summarises a conversation, finds the policy that applies. Cannot send anything on its own.",["knowledge","conversations (masked)"],badge("Favorite","info"),"Start chat")}
{_card("QA assistant","Support leads &middot; v1","Scores sampled conversations against the Support scorecard and explains each score.",["reviews","scorecards"],badge("Leads only","gr"),"Start chat")}
{_card("Report builder","All staff &middot; v1","Builds a summary or chart from your team's figures and saves it as an artifact.",["insights","artifacts"],badge("Available","ok"),"Start chat")}
{_card("Hand-off triage","Billing team &middot; v1","Ranks open hand-offs by urgency and suggests who should take them.",["hand-offs"],badge("Scheduled daily","info"),"Start chat")}
{_card("Escalation analyst","Billing team &middot; v1","Explains why conversations were handed off and what would have prevented it.",["insights","conversations (masked)"],badge("Available","ok"),"Start chat")}
<div class="card" style="border-style:dashed"><b>Need something else?</b><p class="note">Ask your administrator to add an assistant from the Agent Hub, or suggest one.</p><span class="btn">Suggest an assistant</span></div></div>
<p class="note" style="margin-top:10px">Each assistant shows what it can see and do before you start. You only see assistants your role allows.</p>""", "Assistants")


SCREENS["38-workspace-customers"] = wsapp("Customers", head("Customers", "One view of a person across every channel: who they are, what they asked, what the agents and staff did.", '<span class="in">Search by name, email, order&hellip;</span>') + f"""
<div class="split" style="grid-template-columns:330px 1fr;height:740px"><div class="card" style="padding:8px">{table(["Customer","Last contact"],[["<b>Jordan M.</b><br><span class=note>Plus plan &middot; 3 orders</span>","today &middot; chat"],["<b>Sam R.</b><br><span class=note>Free &middot; 1 order</span>","yesterday &middot; email"],["<b>Alex P.</b><br><span class=note>Plus &middot; 9 orders</span>","3 days &middot; WhatsApp"],["<b>Taylor K.</b><br><span class=note>Business &middot; 22 orders</span>","5 days &middot; voice"]])}<p class="note" style="padding:6px">Customers are shown only to roles that may see them; sample names are invented.</p></div>
<div class="card" style="padding:16px"><div class="row2"><div><b style="font-size:18px">Jordan M.</b><br><span class="note">Plus plan &middot; since 2024 &middot; identity verified</span></div><div class="row"><span class="btn">Add note</span><span class="btn p">Open latest thread</span></div></div>
<div class="g3" style="margin-top:12px">{stat("Conversations","7","3 this month")}{stat("Resolved by agent","5","2 handed to people")}{stat("Satisfaction","4.4","3 ratings")}</div>
<h3 style="margin-top:14px">Timeline</h3>{table(["When","Channel","What happened","Who"],[["today 13:52","Chat","Refund for a delayed order: waiting for approval","billing-help &rarr; Dana K."],["Nov 4","Email","Invoice copy sent","support-agent"],["Oct 28","WhatsApp","Parcel status checked, delivered","order-status"],["Oct 12","Voice","Plan question, handed off, resolved","returns &rarr; Marco L."]])}
<p class="note" style="margin-top:8px">Facts the agents may use about this customer (edit or remove): preferred language English &middot; plan Plus &middot; no open disputes. Customer data is masked wherever it appears outside this page.</p></div></div>""", "Customers", full=True)

SCREENS["39-workspace-approvals"] = wsapp("Approvals", head("Approvals", "Actions agents asked a person to approve. Decide here or in the conversation.") + f"""
<div class="tools"><span class="pill"><b>Waiting 2</b></span><span class="pill">Decided today 9</span><span class="pill">Expired 0</span><div style="flex:1"></div><span class="in">Team: Billing &#9662;</span></div>
<div class="card" style="padding:4px 14px">{table(["Request","Agent","Customer context","Waiting","Decide"],[
 ["<b>issue_refund $180</b><br><span class=note>order 1019 &middot; delayed 9 days</span>","billing-help","Plus plan &middot; verified &middot; no refunds in 90 days","6 min",'<span class="btn p">Approve</span> <span class="btn d">Reject</span> <span class="btn">Open</span>'],
 ["<b>change_plan to Business</b><br><span class=note>mid-cycle</span>","billing-help","Plus plan &middot; 14 months","11 min",'<span class="btn p">Approve</span> <span class="btn d">Reject</span> <span class="btn">Open</span>']])}</div>
<div class="g2" style="margin-top:12px"><div class="card"><h3>Why this needs you</h3><p class="note">Refunds above $50 need a person. The agent checked the delay with the order system and attached the tracking events. It cannot approve this itself.</p></div>
<div class="card"><h3>Decided today</h3>{table(["Request","Decision","By"],[["issue_refund $32","auto (under limit)","agent"],["issue_refund $120","approved","Dana K."],["issue_refund $400","rejected, handed to lead","Marco L."]])}</div></div>""", "Approvals", full=True)

SCREENS["40-workspace-navigation-proposal"] = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Workspace navigation proposal (mockup)</title><style>{WS_CSS}
body{{padding:28px;width:1440px;height:900px}}h1{{margin:0}}</style></head><body><h1>Workspace navigation: current and proposed</h1><p class="sub">Your seven tabs stay. Six are proposed, grouped so the list stays short. Role-gated tabs appear only for people who can use them.</p>
<div class="g3" style="grid-template-columns:1fr 1.4fr 1fr;align-items:start">
<div class="card"><span class="b ok">Decided</span><h3 style="margin-top:8px">Today (7)</h3>{"".join(f"<div style='padding:5px 0;border-top:1px solid var(--border)'>{ic} &nbsp;{n}</div>" for n, ic in WS_NAV)}</div>
<div class="card"><span class="b info">Proposed (13)</span><h3 style="margin-top:8px">Grouped</h3>{"".join(f"<div class='grp' style='padding:8px 0 2px'>{g}</div>" + "".join(f"<div style='padding:5px 0;border-top:1px solid var(--border)'>{ic} &nbsp;{n}{' <span class=tag>new</span>' if n in ('Approvals','Customers','Knowledge','Reviews','Insights','Workflows') else ''}</div>" for n, ic in items) for g, items in WS_NAV_FULL)}</div>
<div class="card"><h3>Not tabs, on purpose</h3><p class="note">Shown as panels or controls, because other agent desktops treat them that way:</p>
<div style="padding:5px 0;border-top:1px solid var(--border)"><b>Customer panel</b><br><span class="note">inside a thread</span></div><div style="padding:5px 0;border-top:1px solid var(--border)"><b>Suggested knowledge</b><br><span class="note">inside a thread</span></div><div style="padding:5px 0;border-top:1px solid var(--border)"><b>Playbooks and canned answers</b><br><span class="note">in Knowledge and the reply box</span></div><div style="padding:5px 0;border-top:1px solid var(--border)"><b>Notifications</b><br><span class="note">top-bar bell</span></div><div style="padding:5px 0;border-top:1px solid var(--border)"><b>Live call assist</b><br><span class="note">panel when a call is open</span></div><div style="padding:5px 0;border-top:1px solid var(--border)"><b>Availability and workload</b><br><span class="note">status control in the header</span></div></div></div></body></html>"""


def _node(x, y, kind, title, detail, tone="info", sel=False):
    b = f"border:2px solid var(--primary);" if sel else "border:1px solid var(--border);"
    return f'<div style="position:absolute;left:{x}px;top:{y}px;width:210px;background:var(--surface);{b}border-radius:12px;padding:10px 12px"><span class="b {tone}">{kind}</span><div style="font-weight:700;margin-top:4px">{title}</div><div class="note">{detail}</div></div>'


SCREENS["41-workspace-workflows"] = wsapp("Workflows", head("Workflows", "Multi-step work that runs by itself: a trigger, steps that use assistants and connected systems, and people where they are needed.", '<span class="btn">From template</span> <span class="btn p">+ New workflow</span>') + f"""
<div class="card" style="padding:14px"><b>Describe what you want</b><div class="in" style="display:block;margin-top:8px;color:var(--text)">Every weekday at 07:30, rank open billing hand-offs by urgency and ask the team lead to approve any reassignments.</div><div class="row" style="margin-top:8px"><span class="btn p">Draft it</span><span class="note" style="align-self:center">You review and test a draft before anything is saved or runs.</span></div></div>
<div class="tabs" style="margin-top:14px"><a class="on">All (8)</a><a>Mine (3)</a><a>My team (5)</a><a>Needs attention (1)</a></div>
<div class="card" style="padding:4px 14px">{table(["Workflow","Starts when","Steps","Owner","Last run","Status",""],[
 ["<b>Daily hand-off triage</b><br><span class=note>Rank, tag and propose reassignments</span>","Weekdays 07:30","5","Dana K.","today 07:30",badge("OK","ok"),'<span class="sw2"></span>'],
 ["<b>Refund over limit follow-up</b><br><span class=note>Remind approver, then escalate to lead</span>","Event: approval waiting 15 min","4","Marco L.","18 min ago",badge("Waiting for approval","warn"),'<span class="sw2"></span>'],
 ["<b>Weekly QA digest</b><br><span class=note>Score samples, write the digest, email leads</span>","Mondays 08:00","6","Support leads","Mon 08:00",badge("OK","ok"),'<span class="sw2"></span>'],
 ["<b>New knowledge gap alert</b><br><span class=note>Post top gaps to the team channel</span>","Webhook","3","Dana K.","yesterday",badge("1 failed run","bad"),'<span class="sw2"></span>'],
 ["<b>Knowledge freshness check</b><br><span class=note>List sources older than 90 days</span>","Monthly","2","Support leads","Nov 1",badge("Paused","gr"),'<span class="sw2 off"></span>']])}</div>
<p class="note" style="margin-top:8px">Workflows run with the owner's read access. Anything that writes goes through an approval, like a chat. Scheduled tasks are workflows that start on a schedule.</p>""", "Workflows", full=True)

SCREENS["42-workspace-workflow-editor"] = wsapp("Workflows", head("Daily hand-off triage", "Starts weekdays at 07:30 &middot; owner Dana K. &middot; draft v4, live v3", '<span class="btn">List view</span> <span class="btn">Test run</span> <span class="btn p">Publish</span>') + f"""
<div class="split" style="grid-template-columns:1fr 340px;height:760px"><div class="card" style="position:relative;padding:0;overflow:hidden;background:repeating-linear-gradient(0deg,#0000 0 23px,#e8ecf2 23px 24px),repeating-linear-gradient(90deg,#0000 0 23px,#e8ecf2 23px 24px)">
<svg width="100%" height="100%" style="position:absolute;left:0;top:0"><g stroke="#5b6678" stroke-width="2" fill="none"><path d="M125 118 V140"/><path d="M125 228 V250"/><path d="M125 338 V360"/><path d="M230 398 H300"/><path d="M405 448 V490"/><path d="M405 578 V620"/></g></svg>
{_node(20,30,"Starts when","Weekdays 07:30","Time zone Europe/Amsterdam","ok")}{_node(20,140,"Get data","Open hand-offs","Connector: helpdesk (read)","info")}{_node(20,250,"Assistant","Hand-off triage","Ranks by urgency, read-only tools","info",True)}
{_node(20,360,"Check","Any urgent?","If none, the run finishes quietly","gr")}{_node(300,360,"Person","Lead approves reassignments","Waits up to 2 h, then escalates","warn")}{_node(300,490,"Action","Reassign","Write step: approval required","bad")}{_node(300,620,"Action","Tag and notify","Add tags, post to the team channel","info")}
<div style="position:absolute;left:236px;top:376px;font-size:11px;color:var(--muted)">yes</div><div style="position:absolute;left:34px;top:458px;font-size:11px;color:var(--muted)">no: finish</div>
<div style="position:absolute;left:14px;bottom:12px;font-size:12px;color:var(--muted)">Keyboard: arrow keys move between steps, Enter edits. The list view shows the same workflow as text.</div></div>
<div><div class="card"><h3>Step: Hand-off triage</h3><div class="field"><label>Assistant</label><span class="in">Hand-off triage v1 &#9662;</span></div><div class="field"><label>Instruction</label><span class="in" style="color:var(--text)">Rank each open hand-off by urgency and say why. Never close or reassign.</span></div><div class="field"><label>Tools it may use</label><span class="in">search hand-offs, read conversation (masked)</span></div></div>
<div class="card" style="margin-top:12px"><h3>Limits and safety</h3>{table(["Limit",""],[["Time per run","5 min"],["Steps per run","20"],["Budget per run","$0.50"],["Runs at once","1"],["Write steps","need approval"]])}<p class="note" style="margin-top:6px">Kill switch: pause this workflow, or all workflows for the team.</p></div>
<div class="card" style="margin-top:12px"><h3>Before publishing</h3>{table(["Check","Result"],[["Definition valid",badge("yes","ok")],["Dry run on yesterday's data",badge("passed","ok")],["Needs a reviewer",badge("yes: write step","warn")]])}</div></div></div>""", "Workflows", full=True)

SCREENS["43-workspace-workflow-run"] = wsapp("Workflows", head("Run: Refund over limit follow-up", "Started 18 min ago by event &middot; waiting for a person", '<span class="btn">Kill run</span> <span class="btn p">Open approval</span>') + f"""
<div class="split" style="grid-template-columns:1fr 360px;height:760px"><div class="card"><h3>Steps</h3>{table(["","Step","Result","Time"],[
 [badge("done","ok"),"<b>Starts when</b> approval waiting 15 min","event approval a-77","00:00"],
 [badge("done","ok"),"<b>Get data</b> the approval and the conversation (masked)","2 records","00:01"],
 [badge("done","ok"),"<b>Assistant</b> write a short reminder for the approver","1 message &middot; 420 tokens &middot; $0.004","00:03"],
 [badge("done","ok"),"<b>Action</b> remind Dana K.","sent in Workspace and by email","00:04"],
 [badge("waiting","warn"),"<b>Person</b> lead decides if Dana K. does not act within 15 min","waiting 3 min of 15","00:04"],
 [badge("not yet","gr"),"<b>Action</b> escalate to the billing lead","&mdash;","&mdash;"]])}
<p class="note" style="margin-top:8px">A run can wait for people for hours; its state is saved, so a restart does not lose it.</p></div>
<div><div class="card"><h3>Run</h3>{table(["Detail",""],[["Triggered by","event: approval.requested"],["Runs as","Marco L.'s read access"],["Tokens","420"],["Cost","$0.004"],["Model","local llama-70b (rule 4)"]])}</div>
<div class="card" style="margin-top:12px"><h3>If something fails</h3><p class="note">A failed step shows its error and keeps the run. You can retry from that step, skip it, or stop the run. Repeated failures raise an alert and can pause the workflow.</p></div>
<div class="card" style="margin-top:12px"><h3>Recent runs</h3>{table(["Started","Result"],[["13:42",badge("waiting","warn")],["yesterday 16:10",badge("done","ok")],["Nov 7 11:02",badge("done","ok")],["Nov 6 09:48",badge("failed at step 4","bad")]])}</div></div></div>""", "Workflows", full=True)


SCREENS["48-settings-preferences-theme"] = settings_shell("Preferences", "Preferences", "How NorthCX looks and behaves for you. These settings follow you across the Workspace and Admin.", f"""
<div class="g2"><div><div class="card"><h3>Theme</h3><div class="row" style="gap:12px">
<div style="width:150px;border:2px solid var(--primary);border-radius:10px;padding:8px;background:#f6f8fb"><div style="height:60px;background:#fff;border:1px solid #d9e0ea;border-radius:6px"></div><b>Light</b></div>
<div style="width:150px;border:1px solid var(--border);border-radius:10px;padding:8px;background:#0b1220;color:#e8edf6"><div style="height:60px;background:#131c2e;border:1px solid #26324a;border-radius:6px"></div><b>Dark</b></div>
<div style="width:150px;border:1px solid var(--border);border-radius:10px;padding:8px"><div style="height:60px;background:linear-gradient(90deg,#fff 50%,#131c2e 50%);border:1px solid var(--border);border-radius:6px"></div><b>Match my device</b></div></div>
<div class="field"><label>Accent colour</label><div class="row"><span class="b" style="background:#0b3d91;color:#fff">Blue</span><span class="b gr">Teal</span><span class="b gr">Violet</span><span class="b gr">Green</span></div></div>
<p class="note">Status colours (ok, warning, error) stay the same in every theme so meaning never depends on your accent.</p></div>
<div class="card" style="margin-top:12px"><h3>Layout</h3><div class="field"><label>Density</label><span class="in">Comfortable &#9662; &nbsp; (Compact, Comfortable, Spacious)</span></div><div class="field"><label>Text size</label><span class="in">Medium &#9662;</span></div><div class="field"><label>Left navigation</label><span class="in">Expanded &#9662; &nbsp; (Expanded, Icons only)</span></div></div></div>
<div><div class="card"><h3>Accessibility</h3>{table(["Setting",""],[["High contrast",'<span class="sw2 off"></span>'],["Reduce motion",'<span class="sw2 off"></span>'],["Always show keyboard focus",'<span class="sw2"></span>'],["Screen-reader friendly tables",'<span class="sw2"></span>']])}</div>
<div class="card" style="margin-top:12px"><h3>Chat</h3><div class="field"><label>Default model mode</label><span class="in">Auto &#9662;</span></div><div class="field"><label>Send with</label><span class="in">Enter &#9662; &nbsp; (Enter, Ctrl+Enter)</span></div>{table(["Setting",""],[["Show which sources were used",'<span class="sw2"></span>'],["Show the model that answered",'<span class="sw2"></span>']])}</div>
<div class="card" style="margin-top:12px"><h3>Language and region</h3><div class="field"><label>Language</label><span class="in">English &#9662;</span></div><div class="field"><label>Date and time</label><span class="in">24-hour, Europe/Amsterdam &#9662;</span></div></div></div></div>""")

SCREENS["49-settings-skills"] = settings_shell("Profile", "Profile", "How you appear to colleagues, and how your assistants know you.", PROFILE_TABS("Skills") + f"""
<div class="row2" style="margin-bottom:10px"><span class="note">A skill is a repeatable way of doing a task. It loads only when a chat needs it, so assistants stay focused.</span><span class="btn p">+ New skill</span></div>
<div class="g2"><div class="card" style="padding:4px 14px">{table(["Skill","Source","Loads when","On"],[
 ["<b>Refund decision note</b><br><span class=note>Structure for explaining a refund decision</span>","you","you ask for a refund note",'<span class="sw2"></span>'],
 ["<b>Escalation summary</b><br><span class=note>Five-line summary for a lead</span>","you","you ask for a summary to a lead",'<span class="sw2"></span>'],
 ["<b>Apology wording</b><br><span class=note>Approved wording for delays</span>","Billing team","a draft mentions a delay",'<span class="sw2"></span>'],
 ["<b>Verify identity first</b><br><span class=note>Never discuss an account before the code check</span>","organization",badge("always","gr"),'<span class="sw2"></span>'],
 ["<b>Weekly digest layout</b><br><span class=note>Sections and order</span>","Support leads","a digest is requested",'<span class="sw2 off"></span>']])}<p class="note" style="margin:8px 0">&#128274; Organization skills cannot be switched off. Team skills can be turned off for you.</p></div>
<div class="card"><div class="row2"><h3 style="margin:0">Edit: Refund decision note</h3>{badge("yours","info")}</div>
<div class="field"><label>Name</label><span class="in">Refund decision note</span></div><div class="field"><label>Use it when</label><span class="in" style="color:var(--text)">I ask for a note explaining a refund decision</span></div>
<div class="field"><label>Steps</label><span class="in" style="color:var(--text)">1. State the decision first. 2. Name the policy and section. 3. Give the amount and the order number. 4. Say when the customer will see the money.</span></div>
<div class="field"><label>Needs (optional)</label><span class="in">knowledge: Refund policy &times;</span></div>
<div class="row"><span class="btn p">Save</span><span class="btn">Try it</span><span class="btn">Share with team</span></div><p class="note" style="margin-top:8px">A skill gives instructions and may point to knowledge. It cannot give an assistant new tools or access; sharing needs a reviewer.</p></div></div>""")


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
