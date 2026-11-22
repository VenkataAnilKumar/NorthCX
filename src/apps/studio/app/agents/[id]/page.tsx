"use client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { type AgentVersion, ApiError, type Checklist, createVersion, diffVersions, formatTime, type Gate, getChecklist, getEnvironments, getLive, getVersionDetail, listReleases, listVersions, promoteAgent, publishVersion, rollbackAgent, runForVersion, useLoad, useMe, type VersionDiff, versionGate } from "@northcx/api-client";
import { DiffView } from "@/components/diff-view";
import { RolloutPanel } from "@/components/rollout-panel";
import { improveAgent, type ImproveResult } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "@northcx/ui";

function Improve({ agentId, onSaved }: { agentId: string; onSaved: () => void }) {
  const [focus, setFocus] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<ImproveResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (createDraft: boolean) => {
    setBusy(true); setErr(null);
    try { const r = await improveAgent(agentId, { focus: focus.trim() || undefined, createDraft }); setRes(r); if (createDraft) onSaved(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <section className="rounded-xl border border-border bg-surface p-4">
      <h2 className="mb-1 font-medium">Improve this agent</h2>
      <p className="text-sm text-muted">Looks at the last 14 days (hand-offs, failed tools, blocked replies, reviewer marks), proposes a change, tests it next to the live version, and can save it as a draft. Nothing is released from here.</p>
      <label className="mt-2 block text-sm">Anything specific? (optional)<input className="field mt-1 w-full" maxLength={300} value={focus} onChange={(e) => setFocus(e.target.value)} /></label>
      <button className="btn mt-2" disabled={busy} onClick={() => void run(false)}>{busy ? "Working…" : "Investigate and propose"}</button>
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}
      {res && (
        <div className="mt-3 space-y-2 text-sm">
          <p><strong>What is going wrong:</strong> {res.findings.causes.length ? res.findings.causes.slice(0, 4).map((c) => `${c.cause} (${c.count})`).join("; ") : "nothing specific found"}.</p>
          <p><strong>Proposed changes:</strong></p><ul className="list-disc pl-5">{res.proposal.changes.map((c) => <li key={c}>{c}</li>)}</ul>
          {res.proposal.warnings.length > 0 && <ul className="list-disc pl-5 text-[var(--warn)]">{res.proposal.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
          <p><strong>Tests:</strong> {res.tests.verdict}{res.tests.before?.counts ? ` (live: ${res.tests.before.counts.total - res.tests.before.counts.failed}/${res.tests.before.counts.total} pass; proposal: ${res.tests.after?.counts ? res.tests.after.counts.total - res.tests.after.counts.failed : "?"}/${res.tests.after?.counts?.total ?? "?"})` : ""}</p>
          <details><summary className="cursor-pointer">The proposed agent</summary><pre className="mt-1 max-h-72 overflow-auto rounded-lg bg-bg p-3 text-xs">{res.proposal.specYaml}</pre></details>
          {res.draftVersion ? <p role="status">Saved as draft version {res.draftVersion}. It goes through the usual release checks and a second person.</p>
            : <button className="btn btn-primary" disabled={busy || !res.tests.safe && res.tests.verdict.includes("breaks")} onClick={() => void run(true)}>Save as a draft version</button>}
        </div>)}
    </section>
  );
}

function VersionRow({ agent, v, liveNumber, by, note, tick, onChanged }: { agent: string; v: AgentVersion; liveNumber: number | null; by: string | undefined; note: string; tick: number; onChanged: () => void }) {
  const { can } = useMe();
  const [gate, setGate] = useState<Gate | null>(null);
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [spec, setSpec] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ message: string; reasons: string[] } | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [list, setList] = useState<Checklist | null>(null);
  const refreshGate = () => {
    getChecklist(agent, v.number).then(setList).catch(() => setList(null));
    return versionGate(agent, v.number).then(setGate).catch(() => setGate(null));
  };
  useEffect(() => { refreshGate(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [v.number, tick]);

  async function act(name: string, fn: () => Promise<unknown>, message: string) {
    setBusy(name); setErr(null); setDone(null);
    try { await fn(); setDone(message); onChanged(); }
    catch (e) { setErr({ message: (e as Error).message, reasons: e instanceof ApiError ? e.reasons : [] }); }
    finally { setBusy(null); refreshGate(); }
  }

  return (
    <li className="rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Version {v.number}{v.live && <span className="ml-2"><StatusBadge status="live" /></span>}</h3>
        <span className="text-xs text-muted">{v.author} · {formatTime(v.createdAt)} · {v.digest.slice(0, 8)}</span>
      </div>
      {v.note && <p className="mt-1 text-sm text-muted">{v.note}</p>}
      {gate && (
        <p className="mt-2 text-sm">Release gate: <StatusBadge status={gate.satisfied ? "satisfied" : "blocked"} />{" "}
          <span className="text-muted">{gate.covered} of {gate.required} required scenarios passed for this version</span></p>
      )}
      {list && !v.live && (
        <section aria-label={`Publish checklist for version ${v.number}`} className="mt-3 rounded-lg border border-border p-3 text-sm">
          <h4 className="font-medium">Before publishing to production <span className="text-muted">— {list.ready ? "ready" : "not ready"}</span></h4>
          <ul className="mt-2 space-y-1">
            {list.checks.map((c) => (
              <li key={c.key}>
                <span aria-label={c.status} className={c.status === "pass" ? "text-[var(--ok)]" : c.status === "fail" ? "text-[var(--bad)]" : "text-muted"}>{c.status === "pass" ? "✓" : c.status === "fail" ? "✗" : c.status === "warn" ? "!" : "·"}</span>{" "}
                {c.title}{c.detail && <span className="text-muted"> — {c.detail}</span>}
              </li>
            ))}
          </ul>
          {list.changes && !list.changes.identical && (
            <p className="mt-2 text-xs text-muted">Compared with v{list.liveVersion ?? "baseline"}: {[list.changes.instructionsChanged && "instructions", list.changes.toolsAdded.length > 0 && `tools added (${list.changes.toolsAdded.join(", ")})`, list.changes.toolsRemoved.length > 0 && `tools removed (${list.changes.toolsRemoved.join(", ")})`, list.changes.guardrailsChanged.length > 0 && `checks (${list.changes.guardrailsChanged.join(", ")})`, list.changes.otherChanged.length > 0 && `settings (${list.changes.otherChanged.join(", ")})`].filter(Boolean).join("; ") || "no visible change"}</p>
          )}
        </section>
      )}
      <div className="mt-3 flex flex-wrap gap-2 text-sm">
        <button disabled={busy !== null || !can("simulations:run")} onClick={() => act("run", () => runForVersion(agent, v.number), "Scenarios finished; the gate above is up to date.")}
          className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40 disabled:opacity-50">{busy === "run" ? "Running…" : "Run scenarios"}</button>
        {!v.live && <button disabled={busy !== null || !can("releases:publish") || (list !== null && !list.ready)} title={!can("releases:publish") ? "Your role cannot publish" : list && !list.ready ? "Some required checks have not passed" : undefined} onClick={() => act("publish", () => publishVersion(agent, v.number, by, note || undefined), `Version ${v.number} is now live.`)}
          className="rounded-lg bg-primary px-3 py-1.5 font-medium text-primary-text disabled:opacity-50">{busy === "publish" ? "Publishing…" : "Publish"}</button>}
        {!v.live && <Link href={`/agents/${agent}/compare?candidate=${v.number}`} className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Compare with live</Link>}
        <button disabled={busy !== null} onClick={async () => { setSpec(spec === null ? (await getVersionDetail(agent, v.number)).specYaml ?? "" : null); }}
          className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">{spec === null ? "View spec" : "Hide spec"}</button>
        {liveNumber !== null && liveNumber !== v.number && (
          <button disabled={busy !== null} onClick={async () => { setDiff(diff ? null : await diffVersions(agent, liveNumber, v.number)); }}
            className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">{diff ? "Hide changes" : `Changes from live (v${liveNumber})`}</button>
        )}
      </div>
      {done && <p role="status" className="mt-2 text-sm text-[var(--ok)]">{done}</p>}
      {err && (
        <div role="alert" className="mt-2 rounded-lg border border-[var(--bad)] bg-[var(--bad-bg)] p-3 text-sm text-[var(--bad)]">
          <p>{err.message}</p>
          {err.reasons.length > 0 && <ul className="mt-1 list-disc pl-5">{err.reasons.slice(0, 5).map((r) => <li key={r}>{r}</li>)}</ul>}
        </div>
      )}
      {diff && <div className="mt-3"><DiffView d={diff} /></div>}
      {spec !== null && <pre aria-label="Spec" className="mt-3 max-h-80 overflow-auto rounded-lg bg-bg p-3 text-xs">{spec}</pre>}
    </li>
  );
}

export default function AgentVersions({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [tick, setTick] = useState(0);
  const live = useLoad(() => getLive(id), [id, tick]);
  const versions = useLoad(() => listVersions(id), [id, tick]);
  const releases = useLoad(() => listReleases(id), [id, tick]);
  const envs = useLoad(() => getEnvironments(id), [id, tick]);
  const [envErr, setEnvErr] = useState<string | null>(null);
  const { can, askForName } = useMe();
  const [by, setBy] = useState("dev");
  const [note, setNote] = useState("");
  const [yamlText, setYamlText] = useState<string | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [rollErr, setRollErr] = useState<string | null>(null);
  const refresh = () => setTick((t) => t + 1);

  useEffect(() => { if (live.data && yamlText === null) setYamlText(live.data.specYaml); }, [live.data, yamlText]);
  if (live.loading && !live.data) return <Loading />;
  if (live.error) return <ErrorBox message={live.error} onRetry={live.reload} />;

  async function save(e: React.FormEvent) {
    e.preventDefault(); setFormErr(null); setCreated(null);
    try { const v = await createVersion(id, yamlText ?? "", askForName ? by.trim() || "dev" : undefined, note.trim() || undefined); setCreated(`Saved as version ${v.number}.`); setNote(""); refresh(); }
    catch (err) { setFormErr((err as Error).message); }
  }
  async function promote(to: "staging" | "production") {
    setEnvErr(null);
    try { await promoteAgent(id, to, askForName ? by.trim() || "dev" : undefined, note.trim() || undefined); refresh(); }
    catch (err) { setEnvErr((err as Error).message); }
  }
  async function rollback() {
    setRollErr(null);
    try { await rollbackAgent(id, askForName ? by.trim() || "on-call" : undefined, note.trim() || undefined); refresh(); }
    catch (err) { setRollErr((err as Error).message); }
  }

  const l = live.data!;
  return (
    <>
      <p className="mb-2 flex items-center justify-between text-sm"><Link className="text-primary underline" href="/agents">← Agents</Link>{can("versions:create") && <Link className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40" href={`/agents/${id}/edit`}>Edit in Studio</Link>}</p>
      <PageHeader title={`${id}: versions and releases`} subtitle="A version is a saved copy of the agent's spec. It can go live only after every required scenario has passed for that exact version.">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {askForName && (<>
            <label htmlFor="by">Your name</label>
            <input id="by" value={by} onChange={(e) => setBy(e.target.value)} className="w-28 rounded-lg border border-border bg-surface px-2 py-1.5" />
          </>)}
          <label htmlFor="note">Note</label>
          <input id="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" className="w-44 rounded-lg border border-border bg-surface px-2 py-1.5" />
        </div>
      </PageHeader>
      {envs.data && (
        <section aria-label="Environments" className="mb-6 rounded-xl border border-border bg-surface p-4">
          <h2 className="mb-2 text-sm font-medium text-muted">Environments{envs.data.strictPromotion ? " · production only takes versions that were live in staging" : ""}</h2>
          <ul className="grid gap-3 sm:grid-cols-3">
            {(["dev", "staging", "production"] as const).map((name, i, all) => {
              const e = envs.data!.environments[name];
              const next = all[i + 1];
              return (
                <li key={name} className="rounded-lg border border-border p-3 text-sm">
                  <p className="font-medium">{name}</p>
                  <p>{e.version ? `Version ${e.version}` : e.servedFrom !== name ? `Serves ${e.servedFrom}` : "Spec file"}</p>
                  {next && next !== "dev" && (
                    <button onClick={() => promote(next)} disabled={!can(next === "production" ? "releases:publish" : "versions:create") || !e.version}
                      title={!e.version ? "Nothing released here to promote" : undefined}
                      className="mt-2 rounded-lg border border-border px-2 py-1 text-xs hover:bg-border/40 disabled:opacity-50">Promote to {next}</button>)}
                </li>);
            })}
          </ul>
          {envErr && <p role="alert" className="mt-2 text-sm text-[var(--bad)]">{envErr}</p>}
        </section>)}
      <RolloutPanel agent={id} versions={(versions.data ?? []).map((v) => v.number)} tick={tick} onChanged={refresh} />

      <section aria-label="Live" className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface p-4">
        <div>
          <p className="text-sm text-muted">Serving customers now</p>
          <p className="text-lg font-semibold">{l.source === "release" ? `Version ${l.version}` : "The spec file (no version released yet)"}</p>
          {l.release && <p className="text-xs text-muted">{l.release.action === "rollback" ? "Rolled back" : "Published"} by {l.release.by} · {formatTime(l.release.createdAt)}{l.release.note ? ` · “${l.release.note}”` : ""}</p>}
        </div>
        <div>
          <button onClick={rollback} disabled={!l.release || !can("releases:rollback")} title={can("releases:rollback") ? undefined : "Your role cannot roll back"} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40 disabled:opacity-50">Roll back</button>
          {rollErr && <p role="alert" className="mt-1 text-sm text-[var(--bad)]">{rollErr}</p>}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <section aria-label="Versions">
          <h2 className="mb-2 font-medium">Versions</h2>
          {versions.loading && !versions.data ? <Loading /> : !versions.data?.length ? <Empty>No versions yet. Save one with the form.</Empty> : (
            <ul className="space-y-3">{versions.data.map((v) => (
              <VersionRow key={v.id} agent={id} v={v} liveNumber={l.version} by={askForName ? by.trim() || "release-manager" : undefined} note={note} tick={tick} onChanged={refresh} />))}</ul>
          )}
        </section>
        <div className="space-y-6">
          <form onSubmit={save} className="rounded-xl border border-border bg-surface p-4" aria-label="New version">
            <h2 className="mb-1 font-medium">New version</h2>
            <p className="mb-2 text-xs text-muted">Edit the spec below (it starts from what is live) and save it as the next version.</p>
            <label htmlFor="spec" className="sr-only">Agent spec</label>
            <textarea id="spec" value={yamlText ?? ""} onChange={(e) => setYamlText(e.target.value)} spellCheck={false} rows={14}
              className="w-full rounded-lg border border-border bg-bg p-2 font-mono text-xs" />
            <button disabled={!can("versions:create")} className="mt-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text disabled:opacity-50">Save as new version</button>
            {created && <p role="status" className="mt-2 text-sm text-[var(--ok)]">{created}</p>}
            {formErr && <p role="alert" className="mt-2 break-words text-sm text-[var(--bad)]">{formErr}</p>}
          </form>
          {can("versions:create") && live.data && <Improve agentId={id} onSaved={() => setTick((n) => n + 1)} />}
          <section aria-label="Release history">
            <h2 className="mb-2 font-medium">Release history</h2>
            {!releases.data?.length ? <Empty>Nothing released yet.</Empty> : (
              <ol className="space-y-2">{releases.data.map((r) => (
                <li key={r.id} className="rounded-lg border border-border bg-surface p-3 text-sm">
                  <div className="flex items-center justify-between gap-2"><StatusBadge status={r.action} /><span className="text-xs text-muted">{formatTime(r.createdAt)}</span></div>
                  <p className="mt-1">{r.toBaseline ? "Back to the spec file" : `Version ${r.version}`}{r.previousVersion ? ` (was ${r.previousVersion})` : ""} · {r.by}</p>
                  {r.note && <p className="text-muted">“{r.note}”</p>}
                  {r.action === "publish" && r.gate?.required ? <p className="text-xs text-muted">Gate: {r.gate.covered}/{r.gate.required} scenarios</p> : null}
                </li>))}
              </ol>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
