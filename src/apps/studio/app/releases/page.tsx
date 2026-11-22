"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { announceWorkChanged, cancelReleaseRequest, decideReleaseRequest, formatTime, listReleaseRequests, type ReleaseRequestItem, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, StatusBadge } from "@northcx/ui";

const TABS: [string, string][] = [["pending", "Waiting"], ["approved", "Approved"], ["rejected", "Rejected"], ["cancelled", "Cancelled"], ["failed", "Did not go live"]];

function Card({ r, onDone }: { r: ReleaseRequestItem; onDone: () => void }) {
  const { can, me } = useMe();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setErr(null); try { await fn(); announceWorkChanged(); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const what = r.kind === "publish" ? `Version ${r.version} to ${r.environment}` : `Promote to ${r.environment}`;
  return (
    <GlassCard title={`${r.agent}: ${what}`} action={<StatusBadge status={r.status} />}>
      <p className="text-sm text-muted">Asked for by {r.requestedBy} · {formatTime(r.createdAt)}</p>
      {r.note && <p className="mt-1 text-sm">{r.note}</p>}
      {r.kind === "publish" && r.version !== null && <p className="mt-1 text-sm"><Link className="text-primary underline" href={`/agents/${r.agent}/compare?candidate=${r.version}`}>Compare with what is live</Link></p>}
      {r.status === "pending" ? (
        <>
          <label className="mt-3 block text-sm">Note (optional)<input className="field mt-1" value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn btn-primary" disabled={busy || !can("releases:publish")} onClick={() => act(() => decideReleaseRequest(r.id, true, note || undefined))}>Approve and release</button>
            <button className="btn btn-danger" disabled={busy || !can("releases:publish")} onClick={() => act(() => decideReleaseRequest(r.id, false, note || undefined))}>Reject</button>
            {me?.name === r.requestedBy && <button className="btn" disabled={busy} onClick={() => act(() => cancelReleaseRequest(r.id))}>Withdraw my request</button>}
          </div>
          {!can("releases:publish") && <p className="mt-2 text-xs text-muted">Your role cannot approve releases. Ask a release manager.</p>}
          <p className="mt-2 text-xs text-muted">A release needs a second person: you cannot approve what you asked for yourself.</p>
          {err && <div className="mt-2"><ErrorBox message={err} /></div>}
        </>
      ) : <p className="mt-2 text-sm text-muted">{r.decidedBy ? `Decided by ${r.decidedBy}${r.decidedAt ? ` · ${formatTime(r.decidedAt)}` : ""}` : "Not decided"}{r.decisionNote ? ` · ${r.decisionNote}` : ""}</p>}
    </GlassCard>
  );
}

function List() {
  const agent = useSearchParams().get("agent") ?? undefined;
  const [state, setState] = useState("pending");
  const { data, error, loading, reload } = useLoad(() => listReleaseRequests(state, agent), [state, agent]);
  return (
    <>
      <PageHeader title="Release requests" subtitle="In the environments your administrator chose, publishing a version is a request that a second person approves. Approving releases it, after the usual checks." />
      {data && data.required.length === 0 && (
        <p role="status" className="mb-4 rounded-xl border border-border bg-surface p-3 text-sm">The two-person rule is off on this server, so a release goes live straight after its checks. Ask your administrator to turn it on (<code>NORTHCX_RELEASE_APPROVALS</code>) for the environments that need it.</p>)}
      {data && data.required.length > 0 && <p className="mb-3 text-sm text-muted">Two people are needed for: {data.required.join(", ")}.</p>}
      <div className="mb-3 inline-flex gap-1 rounded-xl border border-border p-1" role="tablist" aria-label="State">
        {TABS.map(([s, label]) => <button key={s} role="tab" aria-selected={state === s} onClick={() => setState(s)} className={`rounded-lg px-3 py-1 text-sm ${state === s ? "bg-primary text-primary-text" : ""}`}>{label}</button>)}
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : data && data.requests.length === 0
        ? <Empty>{state === "pending" ? "Nothing is waiting for approval." : `No ${TABS.find((t) => t[0] === state)?.[1].toLowerCase()} requests.`}</Empty>
        : <ul className="grid gap-4 lg:grid-cols-2">{data?.requests.map((r) => <li key={r.id}><Card r={r} onDone={reload} /></li>)}</ul>}
    </>
  );
}

export default function Page() {
  return <Suspense fallback={<Loading />}><List /></Suspense>;
}
