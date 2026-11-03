"use client";
import { useState } from "react";
import { abortRollout, getRolloutComparison, listRollouts, promoteRollout, setRolloutPercent, startRollout, type ArmStats, type Ratio } from "@/lib/api";
import { useMe } from "@/lib/me";
import { useLoad } from "@/lib/use-load";

const pct = (r: Ratio) => (r.value === null ? "–" : `${(r.value * 100).toFixed(r.value < 0.1 ? 1 : 0)}% (${r.numerator}/${r.denominator})`);
const label = (v: number | null) => (v === null ? "spec file" : `v${v}`);

function Arm({ title, a }: { title: string; a: ArmStats }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <h4 className="font-medium">{title}</h4>
      <dl className="mt-1 space-y-0.5 text-sm">
        <div><dt className="inline text-muted">Conversations: </dt><dd className="inline">{a.conversations}</dd></div>
        <div><dt className="inline text-muted">Contained: </dt><dd className="inline">{pct(a.containmentRate)}</dd></div>
        <div><dt className="inline text-muted">Escalated turns: </dt><dd className="inline">{pct(a.escalationRate)}</dd></div>
        <div><dt className="inline text-muted">Tool errors: </dt><dd className="inline">{pct(a.toolErrorRate)}</dd></div>
        <div><dt className="inline text-muted">Rating: </dt><dd className="inline">{a.satisfaction === null ? "–" : `${a.satisfaction} (${a.ratings} ratings)`}</dd></div>
        <div><dt className="inline text-muted">Judged correct: </dt><dd className="inline">{pct(a.judgedCorrect)}</dd></div>
      </dl>
    </div>
  );
}

export function RolloutPanel({ agent, versions, tick, onChanged }: { agent: string; versions: number[]; tick: number; onChanged: () => void }) {
  const { can } = useMe();
  const rollouts = useLoad(() => listRollouts(agent), [agent, tick]);
  const active = rollouts.data?.find((r) => r.state === "active") ?? null;
  const cmp = useLoad(() => (active ? getRolloutComparison(agent, active.id) : Promise.resolve(null)), [agent, active?.id, tick]);
  const [candidate, setCandidate] = useState<number | "">("");
  const [percent, setPercent] = useState(10);
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); onChanged(); } catch (e) { setErr((e as Error).message); } };
  const canRun = can("releases:publish");
  if (rollouts.error) return null; // not configured on this server
  return (
    <section aria-label="Staged rollout" className="mb-6 rounded-xl border border-border bg-surface p-4">
      <h2 className="mb-2 font-semibold">Staged rollout</h2>
      {err && <p role="alert" className="mb-2 text-sm text-[var(--bad)]">{err}</p>}
      {active ? (
        <div className="space-y-3">
          <p className="text-sm">{active.percent}% of new conversations get <strong>{label(active.candidateVersion)}</strong>; the rest keep <strong>{label(active.controlVersion)}</strong>. Started by {active.startedBy}. A conversation keeps the version it started with.</p>
          {cmp.data && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Arm title={`Current (${label(cmp.data.versions.control)})`} a={cmp.data.arms.control} />
                <Arm title={`Candidate (${label(cmp.data.versions.candidate)})`} a={cmp.data.arms.candidate} />
              </div>
              <p className="text-xs text-muted">{cmp.data.note}</p>
            </>
          )}
          {canRun && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <label>Share <input type="number" min={1} max={99} value={percent} onChange={(e) => setPercent(Number(e.target.value))} className="w-16 rounded-lg border border-border bg-bg px-2 py-1" />%</label>
              <button className="rounded-lg border border-border px-3 py-1.5" onClick={() => run(() => setRolloutPercent(agent, active.id, percent))}>Change share</button>
              <button className="rounded-lg bg-primary px-3 py-1.5 text-primary-text" onClick={() => run(() => promoteRollout(agent, active.id))}>Promote to everyone</button>
              <button className="rounded-lg border border-[var(--bad)] px-3 py-1.5 text-[var(--bad)]" onClick={() => run(() => abortRollout(agent, active.id))}>Stop</button>
            </div>
          )}
        </div>
      ) : (
        <form className="flex flex-wrap items-end gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); if (candidate !== "") void run(() => startRollout(agent, candidate, percent)); }}>
          <label>Candidate version
            <select value={candidate} onChange={(e) => setCandidate(e.target.value === "" ? "" : Number(e.target.value))} className="ml-2 rounded-lg border border-border bg-bg px-2 py-1.5">
              <option value="">Choose…</option>{versions.map((n) => <option key={n} value={n}>v{n}</option>)}
            </select>
          </label>
          <label>Share <input type="number" min={1} max={99} value={percent} onChange={(e) => setPercent(Number(e.target.value))} className="w-16 rounded-lg border border-border bg-bg px-2 py-1.5" />%</label>
          <button type="submit" disabled={!canRun || candidate === ""} title={canRun ? undefined : "Your role cannot release to production"} className="rounded-lg bg-primary px-3 py-1.5 text-primary-text disabled:opacity-50">Start rollout</button>
          <span className="text-muted">Send a share of new conversations to a proven version before everyone gets it.</span>
        </form>
      )}
      {rollouts.data && rollouts.data.filter((r) => r.state !== "active").length > 0 && (
        <p className="mt-3 text-xs text-muted">Earlier: {rollouts.data.filter((r) => r.state !== "active").slice(0, 3).map((r) => `${label(r.candidateVersion)} at ${r.percent}% (${r.state})`).join(" · ")}</p>
      )}
    </section>
  );
}
