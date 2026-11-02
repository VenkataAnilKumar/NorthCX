"use client";
import { useState } from "react";
import { decideApproval, formatTime, listApprovals, type Approval } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { useMe } from "@/lib/me";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

export default function Approvals() {
  const { data, error, loading, reload } = useLoad(() => listApprovals());
  const { can, askForName } = useMe();
  const [by, setBy] = useState("reviewer");
  const [note, setNote] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);

  async function decide(a: Approval, approved: boolean) {
    setActionError(null); setOutcome(null); setDeciding(a.id);
    try {
      const res = await decideApproval(a.id, approved, askForName ? by.trim() || "reviewer" : undefined, note.trim() || undefined);
      setOutcome(res.resume?.error ? `Decision recorded, but the follow-up failed: ${res.resume.error}`
        : `${approved ? "Approved" : "Rejected"}. The customer was told: “${res.resume?.reply ?? ""}”`);
      setNote("");
    } catch (e) { setActionError((e as Error).message); }
    finally { setDeciding(null); reload(); }
  }

  const pending = data?.filter((a) => a.state === "pending") ?? [];
  const decided = data?.filter((a) => a.state !== "pending") ?? [];
  return (
    <>
      <PageHeader title="Approvals" subtitle="Actions held for a human decision. Approving runs the action once and the agent tells the customer; rejecting makes the agent explain.">
        <div className="flex flex-wrap items-center gap-2">
          {askForName && (<>
            <label htmlFor="by" className="text-sm text-muted">Reviewer</label>
            <input id="by" value={by} onChange={(e) => setBy(e.target.value)} className="w-32 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm" />
          </>)}
          <label htmlFor="note" className="text-sm text-muted">Note</label>
          <input id="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" className="w-48 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm" />
        </div>
      </PageHeader>
      {actionError && <div className="mb-4"><ErrorBox message={actionError} /></div>}
      {outcome && <p role="status" className="mb-4 rounded-lg border border-[var(--ok)] bg-[var(--ok-bg)] p-3 text-sm text-[var(--ok)]">{outcome}</p>}
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
                    <button disabled={deciding === a.id || !can("approvals:decide")} title={can("approvals:decide") ? undefined : "Your role cannot decide approvals"} onClick={() => decide(a, true)} className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text disabled:opacity-50">{deciding === a.id ? "Working…" : "Approve"}</button>
                    <button disabled={deciding === a.id || !can("approvals:decide")} title={can("approvals:decide") ? undefined : "Your role cannot decide approvals"} onClick={() => decide(a, false)} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40 disabled:opacity-50">Reject</button>
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
                  <span>{a.tool} · {a.reason}{a.note ? ` · “${a.note}”` : ""}</span>
                  <span className="flex items-center gap-2"><StatusBadge status={a.state} />{a.decided_by && <span className="text-muted">by {a.decided_by}</span>}</span>
                </li>))}
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  );
}
