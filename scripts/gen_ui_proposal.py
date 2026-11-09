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
CSS += """
.rail{position:relative;z-index:20;width:72px;padding:14px 10px;display:flex;flex-direction:column;align-items:center;gap:6px;height:calc(900px - 32px)}
.rail .logo{font-weight:700;letter-spacing:-.03em;padding:2px 0 12px;font-size:15px}
.ib{position:relative;width:46px;height:46px;border-radius:14px;display:grid;place-items:center;color:var(--mut)}
.ib.on{background:var(--glass2);color:var(--accent);box-shadow:0 1px 0 var(--line) inset,0 2px 8px rgba(0,0,0,.06)}
.ib svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.ib .bd{position:absolute;top:3px;right:3px;min-width:16px;height:16px;border-radius:99px;background:var(--accent);color:#fff;font-size:10px;font-weight:700;display:grid;place-items:center;padding:0 4px}
.dark .ib .bd{color:#0d0f16}
.tip{position:absolute;left:60px;top:50%;transform:translateY(-50%);white-space:nowrap;padding:6px 12px;border-radius:10px;font-size:12px;font-weight:600;color:var(--ink);background:color-mix(in srgb,var(--bg1) 94%,#fff);border:1px solid var(--hair);box-shadow:var(--sh);z-index:5}
.rail .sp{flex:1}
.hint{display:flex;gap:8px;align-items:center;color:var(--faint);font-size:12px}
.tile{padding:18px;display:flex;flex-direction:column;align-items:center;gap:10px;min-width:0}
.tile .ib{width:56px;height:56px}.tile .ib svg{width:28px;height:28px}
.fw{z-index:20;position:fixed;left:14px;top:50%;transform:translateY(-50%);padding:6px;border-radius:16px}
.fwpill{position:fixed;top:14px;left:50%;transform:translateX(-50%);display:flex;gap:10px;align-items:center;padding:6px 14px;border-radius:99px;font-size:12px}
"""

def page(title, dark, body):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} (mockup)</title><style>{CSS}</style></head><body class="{"dark" if dark else ""}">{body}<div class="mock">Design proposal &middot; invented sample data</div></body></html>'
def nav(items, on, badge=None):
    return "".join(f'<a class="{"on" if n==on else ""}"><span>{n}</span>{f"<span class=n>{badge[n]}</span>" if badge and n in badge else ""}</a>' for n in items)
def seg(items,on): return '<div class="seg">'+"".join(f'<a class="{"on" if n==on else ""}">{n}</a>' for n in items)+'</div>'
def shell(brand, navhtml, main):
    return f'<div class="app"><aside class="g side"><div class="brand">NorthCX<span>{brand}</span></div><nav class="nav">{navhtml}</nav><div class="sp"></div><div class="me"><div class="av">DK</div><div><b>Dana K.</b><div class="d">Billing team</div></div></div></aside><div class="main"><div class="g top"><div class="cmd">Search or jump to&hellip; <span style="margin-left:auto"><kbd>Ctrl K</kbd></span></div><span class="pill ok">Available</span><div class="av">DK</div></div>{main}</div></div>'


ICONS = {
 "Home":'<path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z"/>',
 "Pilot":'<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M18.5 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
 "Work":'<path d="M4 13l2-7h12l2 7v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/><path d="M4 13h4l1 2h6l1-2h4"/>',
 "Assist":'<path d="M5 5h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-7l-4 3.5V15H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/><path d="M9 10h.01M12 10h.01M15 10h.01"/>',
 "Create":'<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
 "Team":'<path d="M5 19v-7M12 19V5M19 19v-4"/>',
 "Overview":'<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
 "Operate":'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
 "Build":'<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
 "Govern":'<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
 "Platform":'<rect x="4" y="5" width="16" height="5" rx="1.5"/><rect x="4" y="14" width="16" height="5" rx="1.5"/><path d="M8 7.5h.01M8 16.5h.01"/>',
 "Personal":'<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-6 8-6s8 2 8 6"/>',
 "Expand":'<path d="M9 6l6 6-6 6"/>',
 "Collapse":'<path d="M15 6l-6 6 6 6"/>',
 "Menu":'<path d="M5 8h14M5 12h14M5 16h14"/>',
}
def icon(name): return f'<svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'
def ib(name,on=False,badge=None,tip=None):
    return f'<div class="ib {"on" if on else ""}">{icon(name)}{f"<span class=bd>{badge}</span>" if badge else ""}{f"<span class=tip>{tip}</span>" if tip else ""}</div>'

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
# 4 Icon sheet
def tile(n,label,on=False,badge=None): return f'<div class="g tile">{ib(n,on,badge)}<b>{label}</b></div>'
sheet=f"""<div style="padding:32px;display:flex;flex-direction:column;gap:22px"><div><h1>Tab icons</h1><div class="sub">One line icon per left item. Same stroke, same size, no fill; the accent appears only on the selected one.</div></div>
<div><div class="k" style="margin-bottom:10px">Workspace</div><div style="display:grid;grid-template-columns:repeat(6,1fr);gap:14px">{tile("Home","Home",True)}{tile("Pilot","Pilot")}{tile("Work","Work",False,"2")}{tile("Assist","Assist")}{tile("Create","Create")}{tile("Team","Team")}</div></div>
<div><div class="k" style="margin-bottom:10px">Admin</div><div style="display:grid;grid-template-columns:repeat(6,1fr);gap:14px">{tile("Overview","Overview",True)}{tile("Operate","Operate",False,"5")}{tile("Build","Build")}{tile("Govern","Govern")}{tile("Platform","Platform")}{tile("Personal","Personal")}</div></div>
<div class="grid3"><div class="g pad"><div class="k">Default</div><div class="row" style="margin-top:8px">{ib("Work")}<span class="mut">muted, 1.6 px line</span></div></div>
<div class="g pad"><div class="k">Selected</div><div class="row" style="margin-top:8px">{ib("Work",True)}<span class="mut">glass plus accent</span></div></div>
<div class="g pad"><div class="k">With waiting work</div><div class="row" style="margin-top:8px">{ib("Work",False,"2")}<span class="mut">count badge</span></div></div></div>
<div class="hint">Rules: sub-tabs and the 25 Admin pages stay text-only; icons appear on the six left items and nowhere else; every icon has a text label (shown, or in a tooltip and for screen readers).</div></div>"""
(OUT/"ui-4-tab-icons.html").write_text(page("Tab icons",False,sheet))
dark_sheet=sheet
# 5 Collapsed rail (Workspace, Work > Inbox)
def collapsed(brandmark, items, on, badges, tipfor, main, dark=False):
    rail="".join(ib(n,n==on,badges.get(n),tipfor if False else (f"{n}" + (f" · {badges[n]} waiting" if n in badges else "")) if n==tipfor else None) for n in items)
    return f'<div class="app" style="grid-template-columns:72px 1fr"><aside class="g rail"><div class="logo">N</div>{rail}<div class="sp"></div>{ib("Expand",tip=None)}<div class="av" style="margin-top:6px">DK</div></aside><div class="main"><div class="g top"><div class="cmd">Search or jump to&hellip; <span style="margin-left:auto"><kbd>Ctrl K</kbd></span></div><span class="pill ok">Available</span><div class="av">DK</div></div>{main}</div></div>'
cmain = f"""<div class="row sb"><div><h1>Inbox</h1><div class="sub">Conversations that need a person</div></div>{seg(["Inbox","Approvals","Customers"],"Inbox")}</div>
<div class="grid2"><div class="g pad"><div class="row sb" style="margin-bottom:6px"><b>Needs me</b><span class="pill">3 waiting</span></div>
<div class="item"><div><div class="t">Duplicate charge on order 1019</div><div class="mut">Customer 1042 &middot; email &middot; 6 min</div></div><span class="pill warn">Needs a reply</span></div>
<div class="item"><div><div class="t">Delivery delayed, asks for compensation</div><div class="mut">Customer 2210 &middot; web chat &middot; 14 min</div></div><span class="pill warn">Over the limit</span></div>
<div class="item"><div><div class="t">Plan change to the annual tier</div><div class="mut">Customer 0877 &middot; web chat &middot; 22 min</div></div><span class="pill">Agent is handling</span></div></div>
<div class="g pad"><div class="k">Agent's summary</div><p style="margin:6px 0 14px">The customer was charged twice for order 1019. A refund of 48.00 needs a person.</p><div class="row"><span class="btn p">Send reply</span><span class="btn">Resolve with note</span></div></div></div>
<div class="hint">Collapsed rail: icons only, tooltip and count on hover or focus, one click or Ctrl B to expand. The page gains about 160 px of width.</div>"""
(OUT/"ui-5-collapsed-rail.html").write_text(page("Collapsed rail",False,collapsed("N",WS,"Work",{"Work":"2"},"Work",cmain)))
# 6 Full window (Pilot, light, rail hidden)
fw = f"""<div style="padding:64px 40px 24px 84px;display:flex;flex-direction:column;gap:16px;min-height:900px">
<div class="g fw">{ib("Menu")}</div>
<div class="g fwpill"><span class="mut">Full window</span><span class="pill">Pilot</span><kbd>Esc</kbd><span class="mut">to show navigation</span></div>
<div class="row sb"><div><h1>Why did delivery complaints rise?</h1><div class="sub">Escalation analyst &middot; Billing escalations</div></div>{seg(["Plan","Result","Files","Sources","Context","Steps","Side chat"],"Result")}</div>
<div style="display:grid;grid-template-columns:1.6fr 1fr;gap:16px;flex:1">
<div class="g pad chat" style="justify-content:space-between"><div class="chat">
<div class="msg me2">Research why delivery complaints rose last week and propose fixes.</div>
<div class="msg ai"><b>Finding:</b> 58% of the rise came from two carriers after a routing change on Monday; 31% were duplicate tracking emails. Sources 1 to 4.</div>
<div class="msg ai">Proposed fixes: add a carrier delay banner to the web chat, and change the tracking email so it sends once.</div></div>
<div class="g comp"><span class="mut">Ask a follow-up&hellip;</span><div class="row sb"><div class="chips"><span class="chip">+</span><span class="chip">Quick answer</span><span class="chip on">Research</span><span class="chip">Private only</span></div><span class="btn p">Send</span></div></div></div>
<div class="g pad"><div class="row sb"><b>Result</b><span class="pill ok">Saved to Outputs</span></div><div class="d" style="margin:4px 0 10px">Version 2 &middot; 4 sources &middot; $0.06</div>
<table><tr><th>Cause</th><th>Share</th></tr><tr><td>Carrier routing change</td><td>58%</td></tr><tr><td>Duplicate tracking email</td><td>31%</td></tr><tr><td>Other</td><td>11%</td></tr></table>
<div class="row" style="margin-top:14px"><span class="btn p">Save as output</span><span class="btn">Share</span><span class="btn">Make an automation</span></div></div></div></div>"""
(OUT/"ui-6-full-window.html").write_text(page("Full window",False,fw))
print("ok2")
