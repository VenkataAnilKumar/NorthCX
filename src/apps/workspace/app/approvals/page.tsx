"use client";
import { useState } from "react";
import { decideApproval, listApprovals, useLoad, useMe, type Approval } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, StatusBadge } from "@northcx/ui";

function Card({ a, onDone }: { a: Approval; onDone: () => void }) {
  const { askForName, me, can } = useMe();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const decide = async (ok: boolean) => { setBusy(true); setErr(null); try { await decideApproval(a.id, ok, askForName ? undefined : me?.name, note || undefined); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  return (
    <GlassCard title={a.tool} action={<StatusBadge status={a.state} />}>
      <p className="text-sm">{a.reason}</p>
      <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-[var(--info-bg)] p-2 text-xs">{JSON.stringify(a.input, null, 2)}</pre>
      {a.state === "pending" && (
        <>
          <label className="mt-3 block text-sm">Note (optional)<input className="field mt-1" value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="mt-3 flex gap-2">
            <button className="btn btn-primary" disabled={busy || !can("approvals:decide")} onClick={() => decide(true)}>Approve</button>
            <button className="btn btn-danger" disabled={busy || !can("approvals:decide")} onClick={() => decide(false)}>Reject</button>
          </div>
          {!can("approvals:decide") && <p className="mt-2 text-xs text-muted">Your role cannot decide approvals.</p>}
          {err && <div className="mt-2"><ErrorBox message={err} /></div>}
        </>
      )}
    </GlassCard>
  );
}

export default function Approvals() {
  const [state, setState] = useState("pending");
  const { data, error, loading, reload } = useLoad(() => listApprovals(state), [state]);
  return (
    <>
      <PageHeader title="Approvals" subtitle="Actions an agent asked a person to approve before it runs them." />
      <div className="mb-3 inline-flex gap-1 rounded-xl border border-border p-1" role="tablist" aria-label="State">
        {["pending", "approved", "rejected", "expired"].map((s) => <button key={s} role="tab" aria-selected={state === s} onClick={() => setState(s)} className={`rounded-lg px-3 py-1 text-sm capitalize ${state === s ? "bg-primary font-semibold text-primary-text" : "text-muted"}`}>{s}</button>)}
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : data && data.length === 0 ? <Empty>No {state} approvals.</Empty> : (
        <ul className="grid gap-4 lg:grid-cols-2">{data?.map((a) => <li key={a.id}><Card a={a} onDone={reload} /></li>)}</ul>
      )}
    </>
  );
}
