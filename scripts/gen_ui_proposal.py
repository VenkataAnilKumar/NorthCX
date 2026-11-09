"""Generates the UI design proposal mockups (glass, minimal colour). Sample data only. Run: python scripts/gen_ui_proposal.py"""
from pathlib import Path
OUT = Path(__file__).resolve().parent.parent / "docs" / "07-design" / "mockups"

CSS = """
:root{--bg1:#eef1f7;--bg2:#e6e4f2;--bg3:#f4f1ec;--ink:#14161f;--mut:#5b6072;--faint:#8b90a0;
--glass:rgba(255,255,255,.58);--glass2:rgba(255,255,255,.78);--line:rgba(255,255,255,.75);--hair:rgba(20,22,31,.08);
--accent:#3b5bfd;--accent-soft:rgba(59,91,253,.12);--ok:#1f8a5b;--warn:#b7791f;--bad:#c2410c;
--sh:0 1px 0 rgba(255,255,255,.8) inset,0 10px 30px rgba(40,44,80,.08);--r:18px}
.dark{--bg1:#0d0f16;--bg2:#141226;--bg3:#0f1620;--ink:#eceef6;--mut:#a3a8ba;--faint:#6f7589;
--glass:rgba(255,255,255,.06);--glass2:rgba(255,255,255,.10);--line:rgba(255,255,255,.12);--hair:rgba(255,255,255,.08);
--accent:#7f95ff;--accent-soft:rgba(127,149,255,.16);--ok:#4cc38a;--warn:#e0a63c;--bad:#f08a5d;
--sh:0 1px 0 rgba(255,255,255,.07) inset,0 12px 34px rgba(0,0,0,.35)}
*{box-sizing:border-box;margin:0}
body::before,body::after{content:'';position:fixed;border-radius:50%;filter:blur(70px);z-index:0;pointer-events:none}
body::before{width:420px;height:420px;left:34%;top:-120px;background:color-mix(in srgb,var(--accent) 14%,transparent)}
body::after{width:380px;height:380px;right:-80px;bottom:60px;background:color-mix(in srgb,var(--accent) 9%,transparent)}
.app{position:relative;z-index:1}
body{font:14px/1.5 Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);min-height:900px;
background:radial-gradient(900px 600px at 12% 8%,var(--bg2),transparent 60%),radial-gradient(800px 600px at 92% 90%,var(--bg3),transparent 60%),var(--bg1)}
.g{background:var(--glass);backdrop-filter:blur(28px) saturate(150%);-webkit-backdrop-filter:blur(28px) saturate(150%);
border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--sh)}
.app{display:grid;grid-template-columns:232px 1fr;gap:16px;padding:16px;min-height:900px}
.side{padding:18px 12px;display:flex;flex-direction:column;gap:4px;height:calc(900px - 32px)}
.brand{font-weight:650;letter-spacing:-.02em;font-size:16px;padding:2px 10px 14px}.brand span{color:var(--faint);font-weight:500;font-size:12px;margin-left:6px}
.nav a{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;border-radius:12px;color:var(--mut);font-weight:500}
.nav a.on{background:var(--glass2);color:var(--ink);box-shadow:0 1px 0 var(--line) inset,0 2px 8px rgba(0,0,0,.05)}
.n{background:var(--accent);color:#fff;border-radius:99px;font-size:11px;padding:0 7px;font-weight:600}
.dark .n{color:#0d0f16}
.side .sp{flex:1}.me{display:flex;gap:10px;align-items:center;padding:10px;border-top:1px solid var(--hair)}
.av{width:30px;height:30px;border-radius:99px;background:var(--accent-soft);color:var(--accent);display:grid;place-items:center;font-weight:600;font-size:12px}
.main{display:flex;flex-direction:column;gap:16px;min-width:0}
.top{display:flex;align-items:center;gap:12px;padding:10px 14px}
.cmd{flex:1;display:flex;gap:8px;align-items:center;color:var(--faint);padding:8px 12px;border-radius:12px;background:var(--glass);border:1px solid var(--hair)}
kbd{font:11px ui-monospace,monospace;border:1px solid var(--hair);border-radius:6px;padding:0 6px;color:var(--mut)}
.seg{display:inline-flex;padding:4px;gap:2px;border-radius:14px;background:var(--glass);border:1px solid var(--hair)}
.seg a{padding:6px 14px;border-radius:10px;color:var(--mut);font-weight:500}
.seg a.on{background:var(--glass2);color:var(--ink);box-shadow:0 1px 0 var(--line) inset,0 2px 6px rgba(0,0,0,.06)}
h1{font-size:26px;letter-spacing:-.03em;font-weight:650}.sub{color:var(--mut);margin-top:2px}
.pad{padding:20px}.row{display:flex;gap:10px;align-items:center}.sb{justify-content:space-between}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.grid2{display:grid;grid-template-columns:1.5fr 1fr;gap:16px}
.k{color:var(--mut);font-size:12px;font-weight:500}.v{font-size:32px;font-weight:650;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.d{color:var(--faint);font-size:12px}
.item{display:flex;justify-content:space-between;align-items:center;padding:14px 4px;border-top:1px solid var(--hair)}
.item:first-child{border-top:0}.t{font-weight:550}.mut{color:var(--mut)}
.pill{display:inline-flex;gap:6px;align-items:center;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:550;background:var(--accent-soft);color:var(--accent)}
.pill.ok{background:color-mix(in srgb,var(--ok) 14%,transparent);color:var(--ok)}.pill.warn{background:color-mix(in srgb,var(--warn) 16%,transparent);color:var(--warn)}
.btn{padding:8px 16px;border-radius:12px;font-weight:600;border:1px solid var(--hair);background:var(--glass2);color:var(--ink)}
.btn.p{background:var(--accent);color:#fff;border-color:transparent;box-shadow:0 6px 18px color-mix(in srgb,var(--accent) 35%,transparent)}.dark .btn.p{color:#0d0f16}
.step{display:flex;gap:12px;padding:10px 0}.dot{width:22px;height:22px;border-radius:99px;display:grid;place-items:center;font-size:11px;font-weight:700;background:var(--glass2);color:var(--mut);flex:none}
.dot.on{background:var(--accent);color:#fff}.dark .dot.on{color:#0d0f16}
.msg{max-width:78%;padding:12px 16px;border-radius:16px}.me2{align-self:flex-end;background:var(--accent-soft)}.ai{background:var(--glass2);border:1px solid var(--hair)}
.chat{display:flex;flex-direction:column;gap:12px}
.comp{padding:14px 16px;display:flex;flex-direction:column;gap:12px}.chips{display:flex;gap:8px}.chip{white-space:nowrap;padding:4px 12px;border-radius:99px;border:1px solid var(--hair);color:var(--mut);font-size:12px;font-weight:550}.chip.on{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.bar{height:6px;border-radius:9px;background:var(--hair);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);border-radius:9px}
.mock{position:fixed;right:14px;bottom:10px;font-size:11px;color:var(--faint)}
table{width:100%;border-collapse:collapse}td,th{padding:12px 4px;text-align:left;border-top:1px solid var(--hair)}th{border-top:0;color:var(--faint);font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:600}
"""
def page(title, dark, body):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} (mockup)</title><style>{CSS}</style></head><body class="{"dark" if dark else ""}">{body}<div class="mock">Design proposal &middot; invented sample data</div></body></html>'
def nav(items, on, badge=None):
    return "".join(f'<a class="{"on" if n==on else ""}"><span>{n}</span>{f"<span class=n>{badge[n]}</span>" if badge and n in badge else ""}</a>' for n in items)
def seg(items,on): return '<div class="seg">'+"".join(f'<a class="{"on" if n==on else ""}">{n}</a>' for n in items)+'</div>'
def shell(brand, navhtml, main):
    return f'<div class="app"><aside class="g side"><div class="brand">NorthCX<span>{brand}</span></div><nav class="nav">{navhtml}</nav><div class="sp"></div><div class="me"><div class="av">DK</div><div><b>Dana K.</b><div class="d">Billing team</div></div></div></aside><div class="main"><div class="g top"><div class="cmd">Search or jump to&hellip; <span style="margin-left:auto"><kbd>Ctrl K</kbd></span></div><span class="pill ok">Available</span><div class="av">DK</div></div>{main}</div></div>'

WS = ["Home","Pilot","Work","Assist","Create","Team"]
# 1 Workspace light: Work > Inbox
inbox = shell("Workspace", nav(WS,"Work",{"Work":"2"}), f"""
<div class="row sb"><div><h1>Inbox</h1><div class="sub">Conversations that need a person</div></div>{seg(["Inbox","Approvals","Customers"],"Inbox")}</div>
<div class="grid2"><div class="g pad"><div class="row sb" style="margin-bottom:6px"><b>Needs me</b><span class="pill">3 waiting</span></div>
<div class="item"><div><div class="t">Duplicate charge on order 1019</div><div class="mut">Customer 1042 &middot; email &middot; handed off 6 min ago</div></div><span class="pill warn">Needs a reply</span></div>
<div class="item"><div><div class="t">Delivery delayed, asks for compensation</div><div class="mut">Customer 2210 &middot; web chat &middot; 14 min</div></div><span class="pill warn">Over the limit</span></div>
<div class="item"><div><div class="t">Plan change to the annual tier</div><div class="mut">Customer 0877 &middot; web chat &middot; 22 min</div></div><span class="pill">Agent is handling</span></div></div>
<div class="g pad"><div class="k">Agent's summary</div><p style="margin:6px 0 14px">The customer was charged twice for order 1019. Both charges are confirmed. A refund of 48.00 needs a person.</p>
<div class="k">Suggested reply</div><div class="msg ai" style="max-width:100%;margin:6px 0 14px">Thanks for your patience. I have confirmed the duplicate charge and started the refund; you will see it in 3 to 5 days.</div>
<div class="row"><span class="btn p">Send reply</span><span class="btn">Edit</span><span class="btn">Resolve with note</span></div></div></div>
<div class="grid3"><div class="g pad"><div class="k">Waiting now</div><div class="v">3</div><div class="d">oldest 14 min</div></div><div class="g pad"><div class="k">Resolved today</div><div class="v">9</div><div class="d">of 12 handed off</div></div><div class="g pad"><div class="k">Median first reply</div><div class="v">3 min</div><div class="d">p90 11 min</div></div></div>""")
(OUT/"ui-1-workspace-light.html").write_text(page("Workspace, light",False,inbox))
# 2 Pilot dark
pilot = shell("Workspace", nav(WS,"Pilot",{"Work":"2"}), f"""
<div class="row sb"><div><h1>Why did delivery complaints rise?</h1><div class="sub">Escalation analyst &middot; Billing escalations</div></div>{seg(["Plan","Result","Files","Sources","Context","Steps","Side chat"],"Plan")}</div>
<div style="display:grid;grid-template-columns:1.4fr 1fr;gap:16px;flex:1">
<div class="g pad chat" style="justify-content:space-between"><div class="chat">
<div class="msg me2">Research why delivery complaints rose last week and propose fixes.</div>
<div class="msg ai">Two quick questions first.<div class="row" style="margin-top:10px"><span class="chip on">Last 7 days</span><span class="chip">Last 30 days</span><span class="chip">Custom</span></div></div>
<div class="msg me2">Last 7 days, web and email.</div>
<div class="msg ai">I wrote a plan. Check it on the right, change anything, then approve and I will start. It keeps running in the background.</div></div>
<div class="g comp"><span class="mut">Describe the task, or ask a question&hellip;</span><div class="row sb"><div class="chips"><span class="chip">+</span><span class="chip">Space: Billing escalations</span><span class="chip">Quick answer</span><span class="chip on">Research</span><span class="chip">Private only</span></div><span class="btn p">Start</span></div></div></div>
<div class="g pad"><div class="row sb"><b>Plan</b><span class="pill warn">Waiting for your approval</span></div><div class="d" style="margin:4px 0 10px">About 4 minutes &middot; about $0.06 &middot; private model &middot; read-only</div>
<div class="step"><span class="dot on">1</span><div><div class="t">Find the conversations</div><div class="mut">Web and email hand-offs about delivery, last 7 days (masked)</div></div></div>
<div class="step"><span class="dot">2</span><div><div class="t">Read the policy</div><div class="mut">Library: carrier delays playbook</div></div></div>
<div class="step"><span class="dot">3</span><div><div class="t">Compare with the week before</div><div class="mut">Count by cause and carrier</div></div></div>
<div class="step"><span class="dot">4</span><div><div class="t">Write findings and fixes</div><div class="mut">Saved as an output</div></div></div>
<div class="row" style="margin-top:14px"><span class="btn p">Approve and run</span><span class="btn">Edit plan</span></div><div class="d" style="margin-top:10px">Nothing is changed in any system. Steps that write ask you first.</div></div></div>""")
(OUT/"ui-2-pilot-dark.html").write_text(page("Pilot, dark",True,pilot))
# 3 Admin overview light
AD = ["Overview","Operate","Build","Govern","Platform","Personal"]
admin = shell("Admin", nav(AD,"Overview",{"Operate":"5"}), f"""
<div class="row sb"><div><h1>Overview</h1><div class="sub">What needs attention across your agents, people and spend</div></div><span class="seg"><a class="on">7 days</a><a>30 days</a></span></div>
<div class="grid3"><div class="g pad"><div class="k">Conversations</div><div class="v">12,480</div><div class="d">+8% vs previous 7 days</div></div>
<div class="g pad"><div class="k">Resolved (provisional)</div><div class="v">71%</div><div class="d">182 of 256 past the window</div></div>
<div class="g pad"><div class="k">Model cost</div><div class="v">$1,942</div><div class="bar" style="margin:8px 0 4px"><i style="width:74%"></i></div><div class="d">74% of weekly budget</div></div></div>
<div class="grid2"><div class="g pad"><b>Needs attention</b>
<div class="item"><div><div class="t">Error rate above 10%</div><div class="mut">billing-help &middot; Production &middot; 18 min</div></div><span class="btn p">Investigate</span></div>
<div class="item"><div><div class="t">Refund over limit waiting</div><div class="mut">Conversation c-4f21 &middot; 6 min</div></div><span class="btn">Review</span></div>
<div class="item"><div><div class="t">2 keys expire in 7 days</div><div class="mut">Access keys</div></div><span class="btn">Open</span></div></div>
<div class="g pad"><b>Agents by health</b><table><tr><th>Agent</th><th>Status</th></tr><tr><td>support-agent</td><td><span class="pill ok">Healthy</span></td></tr><tr><td>billing-help</td><td><span class="pill warn">Alert firing</span></td></tr><tr><td>returns</td><td><span class="pill ok">Healthy</span></td></tr></table></div></div>""")
(OUT/"ui-3-admin-light.html").write_text(page("Admin overview, light",False,admin))
print("ok")
