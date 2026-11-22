"use client";
import Link from "next/link";
import { Suspense, use, useState } from "react";
import { useSearchParams } from "next/navigation";
import { type Comparison, compareVersions, listVersions, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader } from "@northcx/ui";
import { DiffView } from "@/components/diff-view";

const WORDS = { same: "Same", fixed: "Fixed", regressed: "Now fails" } as const;
const TONE = { same: "text-muted", fixed: "text-[var(--ok)]", regressed: "text-[var(--bad)]" } as const;
const pass = (ok: boolean) => (ok ? "Passes" : "Fails");

function Compare({ id }: { id: string }) {
  const wanted = Number(useSearchParams().get("candidate")) || null;
  const { can } = useMe();
  const versions = useLoad(() => listVersions(id), [id]);
  const [picked, setPicked] = useState<number | null>(wanted);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [out, setOut] = useState<Comparison | null>(null);
  if (versions.loading && !versions.data) return <Loading />;
  if (versions.error) return <ErrorBox message={versions.error} onRetry={versions.reload} />;
  const list = versions.data ?? [];
  if (!list.length) return <Empty>This agent has no saved version yet. Save one from the guided setup or the editor, then compare it with what is live.</Empty>;
  const candidate = picked ?? list.find((v) => !v.live)?.number ?? list[0].number;
  async function run() {
    setBusy(true); setErr(null); setOut(null);
    try { setOut(await compareVersions(id, candidate)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-4">
        <label className="text-sm">Candidate version
          <select className="field ml-2" value={candidate} onChange={(e) => { setPicked(Number(e.target.value)); setOut(null); }}>
            {list.map((v) => <option key={v.number} value={v.number}>Version {v.number}{v.live ? " (live)" : ""}</option>)}</select></label>
        <button className="btn btn-primary" disabled={busy || !can("simulations:run")} onClick={run}>{busy ? "Running the tests…" : "Run the same tests on both"}</button>
        {!can("simulations:run") && <span className="text-xs text-muted">Your role cannot run tests.</span>}
      </div>
      {err && <ErrorBox message={err} />}
      {out && (
        <>
          <p role="status" className={`rounded-xl border p-3 text-sm ${out.scenarios.some((s) => s.change === "regressed") ? "border-[var(--bad)] text-[var(--bad)]" : "border-border"}`}>{out.verdict}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            {([["Live", out.live.number === null ? "the file this agent started from" : `version ${out.live.number}`, out.counts.live], ["Candidate", `version ${out.candidate.number}`, out.counts.candidate]] as const).map(([title, which, c]) => (
              <section key={title} aria-label={title} className="rounded-xl border border-border bg-surface p-4">
                <h2 className="font-medium">{title}: {which}</h2><p className="text-sm text-muted">{c.total - c.failed} of {c.total} tests pass</p></section>))}
          </div>
          <div className="overflow-x-auto rounded-xl border border-border bg-surface">
            <table className="w-full text-left text-sm" aria-label="Results on the same tests">
              <thead className="text-muted"><tr><th className="p-2">Test</th><th className="p-2">Live</th><th className="p-2">Candidate</th><th className="p-2">What changed</th></tr></thead>
              <tbody>{out.scenarios.map((s) => (
                <tr key={s.name} className="border-t border-border"><td className="p-2">{s.name}{s.required && <span className="ml-2 text-xs text-muted">required</span>}</td><td className="p-2">{pass(s.live)}</td><td className="p-2">{pass(s.candidate)}</td>
                  <td className={`p-2 ${TONE[s.change]}`}>{WORDS[s.change]}</td></tr>))}</tbody>
            </table>
          </div>
          <section aria-label="What differs" className="rounded-xl border border-border bg-surface p-4"><h2 className="mb-2 font-medium">What differs</h2><DiffView d={out.differences} /></section>
          <p className="text-sm"><Link className="text-primary underline" href={`/agents/${id}`}>Back to versions and releases</Link> to run the full checks and release it.</p>
        </>
      )}
    </div>
  );
}

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-primary underline" href={`/agents/${id}`}>← {id}: versions and releases</Link></p>
      <PageHeader title={`${id}: live and candidate side by side`} subtitle="Runs the same tests on what is live and on a saved version, and shows what is different. Nothing is released." />
      <Suspense fallback={<Loading />}><Compare id={id} /></Suspense>
    </>
  );
}
