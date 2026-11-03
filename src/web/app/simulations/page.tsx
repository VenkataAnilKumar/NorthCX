"use client";
import Link from "next/link";
import { useState } from "react";
import { useMe } from "@/lib/me";
import { formatTime, getGates, getSimRun, listSimRuns, listSimScenarios, runSimulation, type SimRunSummary } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

function Gates({ refresh }: { refresh: number }) {
  const { data, error, loading, reload } = useLoad(getGates, [refresh]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  return (
    <section aria-label="Release gate" className="grid gap-4 md:grid-cols-2">
      {data!.map((g) => (
        <div key={g.agent} className="rounded-xl border border-border bg-surface p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">Release gate: {g.agent}</h2>
            <StatusBadge status={g.satisfied ? "satisfied" : "blocked"} />
          </div>
          <p className="mt-1 text-sm text-muted">{g.covered} of {g.required} required scenarios passed for this exact agent version{g.agentDigest ? ` (${g.agentDigest.slice(0, 8)})` : ""}.</p>
          {g.reasons.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm">{g.reasons.slice(0, 5).map((r) => <li key={r} className="text-[var(--bad)]">{r}</li>)}
              {g.reasons.length > 5 && <li className="text-muted">and {g.reasons.length - 5} more…</li>}</ul>
          )}
        </div>
      ))}
    </section>
  );
}

function RunDetail({ id }: { id: string }) {
  const { data, error, loading, reload } = useLoad(() => getSimRun(id), [id]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  return (
    <section aria-label="Run detail" className="rounded-xl border border-border bg-surface p-4">
      <h3 className="mb-2 font-medium">Scenarios in this run</h3>
      <ul className="space-y-2">
        {data!.results.map((r) => (
          <li key={r.name} className="rounded-lg border border-border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{r.name}{!r.required && <span className="ml-2 text-xs text-muted">not required</span>}</span>
              <StatusBadge status={r.passed ? "passed" : "failed"} />
            </div>
            {r.notes.map((n) => <p key={n} className="text-xs text-muted">{n}</p>)}
            {!r.passed && r.trials.flatMap((t) => t.failures).slice(0, 5).map((f, i) => (
              <p key={i} className="mt-1 break-words text-[var(--bad)]">{f.where}: {f.check} — expected {JSON.stringify(f.expected)}, got {JSON.stringify(f.actual)}</p>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function Simulations() {
  const [tick, setTick] = useState(0);
  const scenarios = useLoad(listSimScenarios);
  const runs = useLoad(listSimRuns, [tick]);
  const [mode, setMode] = useState("scripted");
  const [skipJudge, setSkipJudge] = useState(true);
  const [only, setOnly] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const { can } = useMe();

  async function start() {
    setRunning(true); setError(null);
    try { const r = await runSimulation(mode, skipJudge, only.trim() || undefined); setSelected(r.id); }
    catch (e) { setError((e as Error).message); }
    finally { setRunning(false); setTick((t) => t + 1); }
  }

  if (scenarios.loading && !scenarios.data) return <Loading />;
  if (scenarios.error) return <ErrorBox message={scenarios.error} onRetry={scenarios.reload} />;
  const list = scenarios.data!.scenarios;
  return (
    <>
      <PageHeader title="Simulations" subtitle="Scripted conversations that check an agent before it reaches customers. A release needs every required scenario to pass for its exact version." />
      <Gates refresh={tick} />
      <section aria-label="Scenarios" className="mt-6 rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-medium">Scenarios</h2>
          {can("scenarios:write") && <Link href="/simulations/scenarios/new" className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text">New scenario</Link>}</div>
        <ul className="mt-2 divide-y divide-border text-sm">{list.map((s) => (
          <li key={s.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span><Link className="text-primary underline" href={`/simulations/scenarios/${encodeURIComponent(s.name)}`}>{s.name}</Link> <span className="text-muted">· {s.agent} · {s.steps} step{s.steps === 1 ? "" : "s"}</span></span>
            <span className="flex gap-2 text-xs">{s.required && <span className="rounded bg-[var(--info-bg)] px-1.5 py-0.5 text-[var(--info)]">required</span>}<span className="rounded bg-border/60 px-1.5 py-0.5">{s.source ?? "file"}</span></span>
          </li>))}</ul>
      </section>
      <form onSubmit={(e) => { e.preventDefault(); start(); }} className="my-6 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-4">
        <label className="text-sm">Model
          <select value={mode} onChange={(e) => setMode(e.target.value)} className="ml-2 rounded-lg border border-border bg-bg px-2 py-1.5">
            {scenarios.data!.modes.map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        <label className="text-sm">Only names containing
          <input value={only} onChange={(e) => setOnly(e.target.value)} placeholder="all scenarios" className="ml-2 w-40 rounded-lg border border-border bg-bg px-2 py-1.5" />
        </label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={skipJudge} onChange={(e) => setSkipJudge(e.target.checked)} /> Skip judge checks</label>
        <button disabled={running} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-text disabled:opacity-50">{running ? "Running…" : "Run scenarios"}</button>
        <p className="text-xs text-muted">{list.length} scenarios · {list.filter((s) => s.required).length} required. “demo” results never count towards the gate.</p>
      </form>
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}
      <div className="grid gap-6 lg:grid-cols-[24rem_1fr]">
        <section aria-label="Runs">
          <h2 className="mb-2 font-medium">Recent runs</h2>
          {runs.loading && !runs.data ? <Loading /> : runs.error ? <ErrorBox message={runs.error} onRetry={runs.reload} /> : !runs.data?.length ? <Empty>No runs yet. Run the scenarios above.</Empty> : (
            <ul className="space-y-2">{runs.data.map((r: SimRunSummary) => (
              <li key={r.id}>
                <button onClick={() => setSelected(r.id)} aria-current={selected === r.id ? "true" : undefined}
                  className={`block w-full rounded-xl border bg-surface p-3 text-left text-sm hover:border-primary ${selected === r.id ? "border-primary" : "border-border"}`}>
                  <div className="flex items-center justify-between gap-2"><span>{formatTime(r.createdAt)}</span><StatusBadge status={r.passed ? "passed" : "failed"} /></div>
                  <p className="mt-1 text-muted">{r.counts.passed}/{r.counts.total} passed · {r.mode} · {r.source}{r.counts.required_failed ? ` · ${r.counts.required_failed} required failed` : ""}</p>
                </button>
              </li>))}
            </ul>
          )}
        </section>
        <div>{selected ? <RunDetail id={selected} /> : <Empty>Select a run to see its scenarios.</Empty>}</div>
      </div>
    </>
  );
}
