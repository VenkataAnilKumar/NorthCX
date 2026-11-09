"use client";
import { useState } from "react";
import { createOrgPolicy, decideOrgPolicy, editOrgPolicy, orgPolicies, policyLibrary, proposeOrgPolicy, proveOrgPolicy, useLoad } from "@northcx/api-client";
import type { OrgPolicy, OrgPolicyCase, OrgPolicyProof, PolicyInfo } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const STATUS_NOTE: Record<string, string> = {
  draft: "Draft: not in force", proposed: "Waiting for a second person", active: "In force and locked", rejected: "Rejected", superseded: "Replaced by a newer version", retired: "Retired",
};

function Editor({ lib, onDone }: { lib: PolicyInfo[]; onDone: () => void }) {
  const [name, setName] = useState("");
  const [policy, setPolicy] = useState(lib[0]?.name ?? "");
  const [config, setConfig] = useState(JSON.stringify(lib[0]?.exampleConfig ?? {}, null, 2));
  const [cases, setCases] = useState(JSON.stringify(lib[0]?.cases ?? [], null, 2));
  const [proof, setProof] = useState<OrgPolicyProof | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const parse = (): { c: Record<string, unknown>; k: OrgPolicyCase[] } | null => {
    try { return { c: JSON.parse(config), k: JSON.parse(cases) }; } catch { setErr("The setting and the cases must be valid JSON."); return null; }
  };
  const pick = (n: string) => { const l = lib.find((x) => x.name === n); setPolicy(n); if (l) { setConfig(JSON.stringify(l.exampleConfig, null, 2)); setCases(JSON.stringify(l.cases, null, 2)); setProof(null); } };
  const run = async (save: boolean) => {
    setErr(null); const p = parse(); if (!p) return;
    try { if (save) { await createOrgPolicy({ name, policy, config: p.c, cases: p.k }); onDone(); } else setProof(await proveOrgPolicy(policy, p.c, p.k)); } catch (e) { setErr(String((e as Error).message ?? e)); }
  };
  return (
    <GlassCard title="New organization policy">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm">Name<input className="input mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="Refund ceiling" /></label>
        <label className="text-sm">Policy<select className="input mt-1 w-full" value={policy} onChange={(e) => pick(e.target.value)}>{lib.map((l) => <option key={l.name}>{l.name}</option>)}</select></label>
        <label className="text-sm">Setting (JSON)<textarea className="input mt-1 h-32 w-full font-mono text-xs" value={config} onChange={(e) => setConfig(e.target.value)} /></label>
        <label className="text-sm">Proof cases (JSON): at least one allowed and one blocked<textarea className="input mt-1 h-32 w-full font-mono text-xs" value={cases} onChange={(e) => setCases(e.target.value)} /></label>
      </div>
      <div className="mt-3 flex gap-2"><button className="btn" onClick={() => run(false)}>Run the cases</button><button className="btn btn-primary" disabled={name.trim().length < 3} onClick={() => run(true)}>Save as draft</button></div>
      {err && <p role="alert" className="mt-2 text-sm text-red-600">{err}</p>}
      {proof && <p className="mt-2 text-sm" role="status">{proof.passed ? "All cases behave as expected." : "Not yet: " + proof.problems.join("; ")}</p>}
    </GlassCard>
  );
}

function Row({ p, reload }: { p: OrgPolicy; reload: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const act = async (f: () => Promise<unknown>) => { setBusy(true); setErr(null); try { await f(); reload(); } catch (e) { setErr(String((e as Error).message ?? e)); } finally { setBusy(false); } };
  return (
    <GlassCard title={`${p.name} (version ${p.version})`}>
      <p className="text-sm"><span className="pill mr-2">{STATUS_NOTE[p.status] ?? p.status}</span>{p.locked && <span aria-label="Locked" title="Locked: changing it needs a new version and a second person">🔒 locked</span>}</p>
      <p className="mt-2 text-xs text-muted">{p.policy}{p.appliesTo ? ` · only for ${p.appliesTo.join(", ")}` : " · every customer agent"} · <code>{JSON.stringify(p.config)}</code></p>
      <p className="mt-1 text-xs">{p.proof.passed ? "Cases pass." : "Cases do not pass: " + p.proof.problems.join("; ")}</p>
      {p.versions && p.versions.length > 1 && <p className="mt-1 text-xs text-muted">Versions: {p.versions.map((v) => `${v.version} ${v.status}`).join(", ")}</p>}
      <div className="mt-2 flex flex-wrap gap-2">
        {p.status === "draft" && <button className="btn" disabled={busy || !p.proof.passed} onClick={() => act(() => proposeOrgPolicy(p.id))}>Propose</button>}
        {p.status === "proposed" && <><button className="btn btn-primary" disabled={busy} onClick={() => act(() => decideOrgPolicy(p.id, "approve"))}>Approve (not the proposer)</button><button className="btn" disabled={busy} onClick={() => act(() => decideOrgPolicy(p.id, "reject"))}>Reject</button></>}
        {p.status === "active" && <>
          <button className="btn" disabled={busy} onClick={() => { const max = prompt("New setting (JSON). The cases stay as they are; edit them through the API if they change."); if (max) act(() => editOrgPolicy(p.id, { config: JSON.parse(max) })); }}>New version</button>
          <button className="btn" disabled={busy} onClick={() => { if (confirm("Take this policy out of force?")) act(() => decideOrgPolicy(p.id, "retire", "retired from the Admin app")); }}>Retire</button></>}
      </div>
      {err && <p role="alert" className="mt-2 text-sm text-red-600">{err}</p>}
    </GlassCard>
  );
}

export default function Policies() {
  const lib = useLoad(() => policyLibrary());
  const org = useLoad(() => orgPolicies().catch(() => [] as OrgPolicy[]));
  const [tab, setTab] = useState<"org" | "library">("org");
  const [adding, setAdding] = useState(false);
  if ((lib.loading && !lib.data) || (org.loading && !org.data)) return <Loading />;
  if (lib.error) return <ErrorBox message={lib.error} onRetry={lib.reload} />;
  return (
    <>
      <PageHeader title="Policies" subtitle="Rules for every customer agent. An organization policy is proven with its cases, approved by a second person, and then locked." />
      <div role="tablist" className="mb-3 flex gap-2">
        <button role="tab" aria-selected={tab === "org"} className={`btn ${tab === "org" ? "btn-primary" : ""}`} onClick={() => setTab("org")}>Organization</button>
        <button role="tab" aria-selected={tab === "library"} className={`btn ${tab === "library" ? "btn-primary" : ""}`} onClick={() => setTab("library")}>Library</button>
      </div>
      {tab === "library" ? (
        <>
          <p className="mb-3 text-sm text-muted">{lib.data!.note}</p>
          <div className="grid gap-4 lg:grid-cols-2">
            {lib.data!.policies.map((p) => (
              <GlassCard key={p.name} title={p.name}>
                <p className="text-sm">{p.description}</p>
                {Object.keys(p.exampleConfig).length > 0 && <p className="mt-2 text-xs text-muted">Example setting: <code>{JSON.stringify(p.exampleConfig)}</code></p>}
                <details className="mt-2 text-sm"><summary className="cursor-pointer">{p.cases.length} proof case{p.cases.length === 1 ? "" : "s"}</summary>
                  <ul className="mt-2 space-y-1 text-xs">{p.cases.map((c, i) => <li key={i}><span className={`pill mr-2 ${c.expected === "allowed" ? "" : "font-semibold"}`}>{c.expected}</span><code>{typeof c.input === "string" ? c.input : JSON.stringify(c.input)}</code></li>)}</ul></details>
              </GlassCard>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="mb-3"><button className="btn" onClick={() => setAdding(!adding)}>{adding ? "Close" : "New policy"}</button></div>
          {adding && <div className="mb-4"><Editor lib={lib.data!.policies} onDone={() => { setAdding(false); org.reload(); }} /></div>}
          {(org.data ?? []).length === 0 ? <p className="text-sm text-muted">No organization policies yet.</p> :
            <div className="grid gap-4 lg:grid-cols-2">{org.data!.map((p) => <Row key={p.id} p={p} reload={org.reload} />)}</div>}
        </>
      )}
    </>
  );
}
