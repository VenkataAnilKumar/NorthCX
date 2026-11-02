"use client";
import { useState } from "react";
import { decideApproval, formatTime, listApprovals, type Approval } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

export default function Approvals() {
  const { data, error, loading, reload } = useLoad(() => listApprovals());
  const [by, setBy] = useState("reviewer");
  const [actionError, setActionError] = useState<string | null>(null);

  async function decide(a: Approval, approved: boolean) {
    setActionError(null);
    try { await decideApproval(a.id, approved, by.trim() || "reviewer"); reload(); }
    catch (e) { setActionError((e as Error).message); reload(); }
  }

  const pending = data?.filter((a) => a.state === "pending") ?? [];
  const decided = data?.filter((a) => a.state !== "pending") ?? [];
  return (
    <>
      <PageHeader title="Approvals" subtitle="Actions held for a human decision. Deciding records the outcome; resuming the conversation is not built yet.">
        <div className="flex items-center gap-2">
          <label htmlFor="by" className="text-sm text-muted">Reviewer</label>
          <input id="by" value={by} onChange={(e) => setBy(e.target.value)} className="w-36 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm" />
        </div>
      </PageHeader>
      {actionError && <div className="mb-4"><ErrorBox message={actionError} /></div>}
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : (
        <div className="space-y-8">
          <section aria-label="Pending">
            <h2 className="mb-2 font-medium">Pending ({pending.length})</h2>
            {!pending.length ? <Empty>Nothing waiting for approval.</Empty> : (
              <ul className="space-y-3">{pending.map((a) => (
                <li key={a.id} className="rounded-xl border border-border bg-surface p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div><span className="font-medium">{a.tool}</span> <span className="text-sm text-muted">· {formatTime(a.created_at)}</span></div>
                    <StatusBadge status="pending" />
                  </div>
                  <p className="mt-2 text-sm">{a.reason}</p>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-bg p-3 text-xs">{JSON.stringify(a.input, null, 2)}</pre>
                  <div className="mt-3 flex gap-2">
                    <button onClick={() => decide(a, true)} className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text">Approve</button>
                    <button onClick={() => decide(a, false)} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40">Reject</button>
                  </div>
                </li>))}
              </ul>
            )}
          </section>
          <section aria-label="Decided">
            <h2 className="mb-2 font-medium">Decided ({decided.length})</h2>
            {!decided.length ? <Empty>No decisions yet.</Empty> : (
              <ul className="space-y-2">{decided.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface p-3 text-sm">
                  <span>{a.tool} · {a.reason}</span>
                  <span className="flex items-center gap-2"><StatusBadge status={a.state} /><span className="text-muted">by {a.decided_by}</span></span>
                </li>))}
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  );
}
