"use client";
import Link from "next/link";
import { useState } from "react";
import { createFromTemplate, listAgents, listTemplates, renderTemplate, useLoad, useMe, type TemplateInfo, type TemplateInstall, type TemplateRender } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

function Install({ t, installed, onClose }: { t: TemplateInfo; installed: boolean; onClose: () => void }) {
  const { can } = useMe();
  const [agentId, setAgentId] = useState(t.id);
  const [params, setParams] = useState<Record<string, string>>(Object.fromEntries(t.parameters.map((p) => [p.name, p.default ?? ""])));
  const [check, setCheck] = useState<TemplateRender | null>(null);
  const [done, setDone] = useState<TemplateInstall | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(null); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const missingRequired = t.parameters.some((p) => p.required && !params[p.name]);
  return (
    <GlassCard title={`Install: ${t.title}`} action={<button className="btn" onClick={onClose}>Close</button>} className="mt-4">
      <ol className="mb-3 flex gap-2 text-xs"><li className="pill">1 Details</li><li className="pill">2 Requirements</li><li className="pill">3 Create draft</li></ol>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm">Agent id<input className="field mt-1" value={agentId} onChange={(e) => setAgentId(e.target.value)} aria-describedby="hub-id-help" />
          <span id="hub-id-help" className="mt-1 block text-xs text-muted">2 to 40 characters. {installed ? "An agent with this id already exists: a new version is added to it." : "A new agent with this id is created as a draft."}</span></label>
        {t.parameters.map((p) => (
          <label key={p.name} className="text-sm">{p.description}{p.required ? " *" : ""}
            <input className="field mt-1" value={params[p.name] ?? ""} onChange={(e) => setParams({ ...params, [p.name]: e.target.value })} /></label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn" disabled={busy || missingRequired || !can("versions:create")} onClick={() => run(async () => { setDone(null); setCheck(await renderTemplate(t.id, agentId, params)); })}>Check requirements</button>
        <button className="btn btn-primary" disabled={busy || missingRequired || !check || check.missingTools.length > 0 || !can("versions:create")}
          onClick={() => run(async () => setDone(await createFromTemplate(t.id, agentId, params, true)))}>Create draft with its tests</button>
        {!can("versions:create") && <span className="text-xs text-muted">Your role cannot create versions.</span>}
      </div>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      {check && (
        <div className="mt-3 text-sm">
          <p className="font-semibold">Requirements</p>
          <ul className="mt-1 space-y-1">
            <li>{check.missingTools.length === 0 ? "✓ Every tool it needs is available in this deployment." : <span className="text-[var(--bad)]">✗ Missing tools: {check.missingTools.join(", ")}. Add them (or change the tool names above) before installing.</span>}</li>
            <li>✓ It comes with {check.scenarios} test scenario{check.scenarios === 1 ? "" : "s"}, which are saved with the draft.</li>
            {check.warnings.map((w) => <li key={w} className="text-[var(--warn)]">! {w}</li>)}
          </ul>
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-xl border border-border bg-[var(--ok-bg)] p-3 text-sm" role="status">
          Created <strong>{done.agentId}</strong> version {done.number} as a draft. It is not live. {done.scenariosSaved.length} scenario(s) saved{done.scenariosSkipped.length ? `, ${done.scenariosSkipped.length} already existed` : ""}.{" "}
          <Link href={`/agents/${done.agentId}`} className="underline">Open the agent</Link> to run its tests and release it.
        </div>
      )}
    </GlassCard>
  );
}

export default function Hub() {
  const { data, error, loading, reload } = useLoad(async () => ({ templates: await listTemplates(), agents: await listAgents() }));
  const [open, setOpen] = useState<string | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const { templates, agents } = data!;
  const ids = new Set(agents.map((a) => a.id));
  const selected = templates.find((t) => t.id === open) ?? null;
  return (
    <>
      <PageHeader title="Agent Hub" subtitle="Predefined agents you can install, test and release. Installing creates a draft only; nothing goes live from here." />
      {templates.length === 0 ? <Empty>No templates are available on this server.</Empty> : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {templates.map((t) => (
            <li key={t.id} className="glass flex flex-col p-4">
              <div className="flex items-start justify-between gap-2"><h2 className="font-semibold">{t.title}</h2>{ids.has(t.id) && <span className="pill">Agent exists</span>}</div>
              <p className="mt-1 text-xs text-muted">Customer-facing · built in</p>
              <p className="mt-2 flex-1 text-sm">{t.description}</p>
              <p className="mt-2 text-xs text-muted">Tools: {t.requiresTools.join(", ") || "none"} · {t.scenarios} test scenario{t.scenarios === 1 ? "" : "s"}</p>
              <button className="btn mt-3 self-start" onClick={() => setOpen(t.id)}>{ids.has(t.id) ? "Add a version" : "Install"}</button>
            </li>
          ))}
        </ul>
      )}
      {selected && <Install key={selected.id} t={selected} installed={ids.has(selected.id)} onClose={() => setOpen(null)} />}
      <p className="mt-4 text-xs text-muted">Built-in templates only for now. Publishing your own and updates to installed templates are planned (see the Agent Hub design).</p>
    </>
  );
}
