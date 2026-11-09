"use client";
import Link from "next/link";
import { useState } from "react";
import { checkOrgTemplate, createOrgTemplate, decideOrgTemplate, hubInstall, hubInstalls, hubRequirements, hubUpdate, hubUpdatePreview, listAgents, listTemplates, orgTemplate, orgTemplates, proposeOrgTemplate, reviseOrgTemplate, useLoad, useMe, type HubInstall, type HubRequirements, type HubUpdatePreview, type OrgTemplate, type TemplateInfo } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

function Checks({ req }: { req: HubRequirements }) {
  return (
    <ul className="mt-1 space-y-1 text-sm" aria-label="Requirements">
      {req.checks.map((c) => (
        <li key={c.id + c.label} className={c.ok ? "" : c.blocking ? "text-[var(--bad)]" : "text-[var(--warn)]"}>
          {c.ok ? "✓" : c.blocking ? "✗" : "!"} <strong>{c.label}</strong>: {c.detail}
        </li>
      ))}
    </ul>
  );
}

function Install({ t, installed, onClose, onDone }: { t: TemplateInfo; installed: boolean; onClose: () => void; onDone: () => void }) {
  const { can } = useMe();
  const [agentId, setAgentId] = useState(t.id);
  const [params, setParams] = useState<Record<string, string>>(Object.fromEntries(t.parameters.map((p) => [p.name, p.default ?? ""])));
  const [req, setReq] = useState<HubRequirements | null>(null);
  const [done, setDone] = useState<Awaited<ReturnType<typeof hubInstall>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(null); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const missingRequired = t.parameters.some((p) => p.required && !params[p.name]);
  return (
    <GlassCard title={`Install: ${t.title}`} action={<button className="btn" onClick={onClose}>Close</button>} className="mt-4">
      <ol className="mb-3 flex gap-2 text-xs"><li className="pill">1 Details</li><li className="pill">2 Requirements</li><li className="pill">3 Draft and tests</li></ol>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm">Agent id<input className="field mt-1" value={agentId} onChange={(e) => setAgentId(e.target.value)} aria-describedby="hub-id-help" />
          <span id="hub-id-help" className="mt-1 block text-xs text-muted">2 to 40 characters. {installed ? "An agent with this id already exists: a new version is added to it." : "A new agent with this id is created as a draft."}</span></label>
        {t.parameters.map((p) => (
          <label key={p.name} className="text-sm">{p.description}{p.required ? " *" : ""}
            <input className="field mt-1" value={params[p.name] ?? ""} onChange={(e) => setParams({ ...params, [p.name]: e.target.value })} /></label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn" disabled={busy || missingRequired} onClick={() => run(async () => { setDone(null); setReq(await hubRequirements(t.id, agentId, params)); })}>Check requirements</button>
        <button className="btn btn-primary" disabled={busy || missingRequired || !req?.ok || !can("versions:create")} onClick={() => run(async () => { setDone(await hubInstall(t.id, agentId, params)); onDone(); })}>Create draft and run its tests</button>
        {!can("versions:create") && <span className="text-xs text-muted">Your role cannot create versions.</span>}
      </div>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      {req && <div className="mt-3"><p className="text-sm font-semibold">Requirements for this deployment</p><Checks req={req} /></div>}
      {done && (
        <div className="mt-3 rounded-xl border border-border bg-[var(--ok-bg)] p-3 text-sm" role="status">
          Created <strong>{done.agent}</strong> version {done.version} as a draft. It is not live. {done.scenariosSaved.length} test scenario(s) saved.{" "}
          {done.tests.ran ? (done.tests.passed ? `All ${done.tests.counts?.total} tests passed.` : `${done.tests.counts?.failed} of ${done.tests.counts?.total} tests failed: open the agent to see which.`) : `Tests did not run${done.tests.reason ? ` (${done.tests.reason})` : ""}.`}{" "}
          <Link href={`/agents/${done.agent}`} className="underline">Open the agent</Link> to release it through the usual checks.
        </div>
      )}
    </GlassCard>
  );
}

const STARTER = `id: my-agent
title: My agent
description: What it does, in one sentence.
category: General
version: "1"
parameters:
  company_name: {description: Your company name, default: our company}
spec:
  instructions: |
    You help customers of {{company_name}}. Be brief and polite.
  tools: []
  guardrails: [no_card_numbers]
scenarios:
  - name: "{{agent_id}}-greets"
    model:
      - text: Hello, how can I help?
    turns:
      - say: hi
        expect: {status: completed, reply_includes: [help]}
`;

function Mine({ reload }: { reload: () => void }) {
  const { can } = useMe();
  const { data, error, loading, reload: again } = useLoad(() => orgTemplates());
  const [text, setText] = useState(STARTER);
  const [editing, setEditing] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = async (f: () => Promise<unknown>, ok?: string) => { setErr(null); setNote(null); try { await f(); if (ok) setNote(ok); again(); reload(); } catch (e) { setErr((e as Error).message); } };
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={again} />;
  const pill = (s: OrgTemplate["status"]) => ({ draft: "Draft", proposed: "Waiting for a second person", published: "Published to your Hub", rejected: "Rejected", superseded: "Replaced", withdrawn: "Withdrawn" })[s];
  const load = async (o: OrgTemplate) => { const full = await orgTemplate(o.id); setText(full.yaml ?? ""); setEditing(o.id); };
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">Write your own agents as templates. A template is checked, proposed, and published to this Hub only after a second person approves it. It then appears for your organization with who approved it.</p>
      {(data ?? []).map((o) => (
        <GlassCard key={o.id} title={`${o.title} (version ${o.version})`} action={<span className="pill">{pill(o.status)}</span>}>
          <p className="text-xs text-muted">{o.id} · {o.audience === "staff" ? "for staff" : "customer-facing"} · {o.scenarios} test scenario{o.scenarios === 1 ? "" : "s"}{o.proposedBy ? ` · proposed by ${o.proposedBy}` : ""}{o.decidedBy ? ` · decided by ${o.decidedBy}` : ""}</p>
          {!o.check.ok && <p className="mt-1 text-sm text-[var(--bad)]">Not ready: {o.check.problems.join("; ")}</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            <button className="btn" onClick={() => void go(() => load(o))}>Open in the editor</button>
            {o.status === "draft" && <button className="btn" disabled={!o.check.ok || !can("versions:create")} onClick={() => void go(() => proposeOrgTemplate(o.id), "Proposed. A second person must approve it.")}>Propose</button>}
            {o.status === "proposed" && <><button className="btn btn-primary" disabled={!can("releases:publish")} onClick={() => void go(() => decideOrgTemplate(o.id, "approve"), "Published.")}>Approve (not the proposer)</button><button className="btn" disabled={!can("releases:publish")} onClick={() => void go(() => decideOrgTemplate(o.id, "reject"))}>Reject</button></>}
            {o.status === "published" && <button className="btn" disabled={!can("releases:publish")} onClick={() => { if (confirm("Remove this template from your Hub? Agents already installed keep working.")) void go(() => decideOrgTemplate(o.id, "withdraw", "withdrawn from the Admin app")); }}>Withdraw</button>}
          </div>
        </GlassCard>
      ))}
      <GlassCard title={editing ? `Editor: ${editing}` : "New template"}>
        <label className="text-sm">Template (YAML). The same format as the built-in ones.<textarea className="field mt-1 h-72 w-full font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} /></label>
        <div className="mt-2 flex flex-wrap gap-2">
          <button className="btn" onClick={() => void go(async () => { const r = await checkOrgTemplate(text); setNote(r.ok ? `Looks good: ${r.scenarios} scenario(s).` : "Not ready: " + r.problems.join("; ")); })}>Check</button>
          <button className="btn btn-primary" disabled={!can("versions:create")} onClick={() => void go(async () => { if (editing) await reviseOrgTemplate(editing, text); else await createOrgTemplate(text); }, "Saved as a draft.")}>{editing ? "Save changes" : "Save as draft"}</button>
          {editing && <button className="btn" onClick={() => { setEditing(null); setText(STARTER); }}>Start a new one</button>}
        </div>
        {note && <p className="mt-2 text-sm" role="status">{note}</p>}
        {err && <div className="mt-2"><ErrorBox message={err} /></div>}
      </GlassCard>
    </div>
  );
}

function Diff({ title, d }: { title: string; d: HubUpdatePreview["templateChanges"] }) {
  const other = Object.keys(d.other);
  if (d.identical) return <p className="text-sm text-muted">{title}: no changes.</p>;
  return (
    <div className="text-sm"><p className="font-medium">{title}</p>
      {d.instructions && <pre className="mt-1 max-h-48 overflow-auto rounded-lg border border-border p-2 text-xs">{d.instructions}</pre>}
      {(d.tools.added.length > 0 || d.tools.removed.length > 0) && <p className="text-xs">Tools: {d.tools.added.length ? `added ${d.tools.added.join(", ")}` : ""} {d.tools.removed.length ? `removed ${d.tools.removed.join(", ")}` : ""}</p>}
      {other.length > 0 && <p className="text-xs">Other settings changed: {other.join(", ")}</p>}
    </div>
  );
}

function Updates({ installs, reload }: { installs: HubInstall[]; reload: () => void }) {
  const { can } = useMe();
  const [open, setOpen] = useState<string | null>(null);
  const [pre, setPre] = useState<HubUpdatePreview | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const look = async (i: HubInstall) => { setError(null); setMsg(null); try { setPre(await hubUpdatePreview(i.template, i.agent)); setOpen(i.agent); } catch (e) { setError((e as Error).message); } };
  const apply = async (i: HubInstall) => { try { const r = await hubUpdate(i.template, i.agent); setMsg(`Created version ${r.version} of ${i.agent} as a draft. It is not live.`); setOpen(null); setPre(null); reload(); } catch (e) { setError((e as Error).message); } };
  if (installs.length === 0) return <Empty>Nothing has been installed from the hub yet.</Empty>;
  return (
    <div className="space-y-3">
      {msg && <p className="rounded-xl border border-border bg-[var(--ok-bg)] p-3 text-sm" role="status">{msg}</p>}
      {error && <ErrorBox message={error} />}
      {installs.map((i) => (
        <GlassCard key={i.agent} title={`${i.agent} · ${i.title}`} action={i.updateAvailable ? <span className="pill">Update available</span> : <span className="text-xs text-muted">Up to date</span>}>
          <p className="text-sm">Installed from template version {i.templateVersion}{i.currentTemplateVersion && i.currentTemplateVersion !== i.templateVersion ? `, now ${i.currentTemplateVersion}` : ""} as version {i.version} of the agent. {i.tests.ran ? (i.tests.passed ? "Its tests passed." : "Some of its tests failed.") : ""}</p>
          <div className="mt-2 flex gap-2"><Link className="btn" href={`/agents/${i.agent}`}>Open the agent</Link>{i.updateAvailable && <button className="btn" onClick={() => void look(i)}>See what changed</button>}</div>
          {open === i.agent && pre && (
            <div className="mt-3 space-y-3"><Diff title={`What the template changed (${pre.from} → ${pre.to})`} d={pre.templateChanges} /><Diff title="What people changed on this agent since the install" d={pre.localChanges} />
              <p className="text-sm">Tests: {pre.scenarios.added.length} added, {pre.scenarios.removed.length} no longer in the template.</p>
              <p className="text-xs text-muted">Updating creates a new draft from the template's newer text. Local changes are shown above and are not merged for you: copy over what you want to keep, then run the tests and release as usual.</p>
              <button className="btn btn-primary" disabled={!can("versions:create")} onClick={() => void apply(i)}>Create the updated draft</button></div>)}
        </GlassCard>
      ))}
    </div>
  );
}

export default function Hub() {
  const { data, error, loading, reload } = useLoad(async () => ({ templates: await listTemplates(), agents: await listAgents(), installs: await hubInstalls() }));
  const [tab, setTab] = useState<"browse" | "installed" | "mine">("browse");
  const [category, setCategory] = useState("All");
  const [open, setOpen] = useState<string | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const { templates, agents, installs } = data!;
  const ids = new Set(agents.map((a) => a.id));
  const categories = ["All", ...Array.from(new Set(templates.map((t) => t.category ?? "General"))).sort()];
  const shown = templates.filter((t) => category === "All" || (t.category ?? "General") === category);
  const selected = templates.find((t) => t.id === open) ?? null;
  const updates = installs.filter((i) => i.updateAvailable).length;
  return (
    <>
      <PageHeader title="Agent Hub" subtitle="Predefined agents you can install, test and release. Installing creates a draft and runs its tests; nothing goes live from here." />
      <div className="seg mb-4" role="tablist" aria-label="Hub">
        <a role="tab" aria-selected={tab === "browse"} aria-current={tab === "browse" ? "page" : undefined} href="#" onClick={(e) => { e.preventDefault(); setTab("browse"); }}>Browse</a>
        <a role="tab" aria-selected={tab === "installed"} aria-current={tab === "installed" ? "page" : undefined} href="#" onClick={(e) => { e.preventDefault(); setTab("installed"); }}>Installed{updates ? <span className="seg-badge" aria-label={`${updates} updates`}>{updates}</span> : null}</a>
        <a role="tab" aria-selected={tab === "mine"} aria-current={tab === "mine" ? "page" : undefined} href="#" onClick={(e) => { e.preventDefault(); setTab("mine"); }}>My organization</a>
      </div>
      {tab === "mine" ? <Mine reload={reload} /> : tab === "installed" ? <Updates installs={installs} reload={reload} /> : (
        <>
          <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Category">{categories.map((c) => <button key={c} className={`pill ${category === c ? "font-semibold text-primary" : ""}`} aria-pressed={category === c} onClick={() => setCategory(c)}>{c}</button>)}</div>
          {shown.length === 0 ? <Empty>No templates in this category.</Empty> : (
            <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {shown.map((t) => (
                <li key={t.id} className="glass flex flex-col p-4">
                  <div className="flex items-start justify-between gap-2"><h2 className="font-semibold">{t.title}</h2>{ids.has(t.id) && <span className="pill">Agent exists</span>}</div>
                  <p className="mt-1 text-xs text-muted">{t.audience === "staff" ? "For staff" : "Customer-facing"} · {t.category ?? "General"} · version {t.version ?? "1"}</p>
                  {t.provenance && <p className="mt-1 text-xs" title={t.provenance.keyFingerprint ? `Signing key ${t.provenance.keyFingerprint}` : undefined}>{t.provenance.source === "built-in" ? (t.provenance.verified ? "✓ Built in, signed and verified" : `! Built in, ${t.provenance.status}`) : t.provenance.source === "organization" ? `Your organization, approved by ${t.provenance.approvedBy ?? "a reviewer"}` : "Local file, not signed"}</p>}
                  <p className="mt-2 text-sm">{t.description}</p>
                  {t.notes && <p className="mt-1 text-xs text-muted">{t.notes}</p>}
                  {t.sees && t.sees.length > 0 && <p className="mt-2 text-xs"><strong>Can see:</strong> {t.sees.join("; ")}</p>}
                  {t.does && t.does.length > 0 && <p className="mt-1 text-xs"><strong>Can do:</strong> {t.does.join("; ")}</p>}
                  <p className="mt-2 flex-1 text-xs text-muted">Tools: {t.requiresTools.join(", ") || "none"} · {t.scenarios} test scenario{t.scenarios === 1 ? "" : "s"}</p>
                  <button className="btn mt-3 self-start" onClick={() => setOpen(t.id)}>{ids.has(t.id) ? "Add a version" : "Install"}</button>
                </li>
              ))}
            </ul>
          )}
          {selected && <Install key={selected.id} t={selected} installed={ids.has(selected.id)} onClose={() => setOpen(null)} onDone={reload} />}
        </>
      )}
      <p className="mt-4 text-xs text-muted">Built-in templates are signed; a changed one is shown and cannot be installed. Your own templates need a second person to approve them.</p>
    </>
  );
}
