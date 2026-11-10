"use client";
import { useState } from "react";
import { eraseNotes, getTenantLimits, listNotes, useLoad } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

export default function Privacy() {
  const { data, error, loading, reload } = useLoad(async () => ({ notes: await listNotes(), limits: (await getTenantLimits()).limits }), []);
  const [msg, setMsg] = useState("");
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const days = data.limits.retentionDays;
  const save = () => {
    const blob = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), notes: data.notes }, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "my-northcx-notes.json"; a.click(); URL.revokeObjectURL(a.href);
  };
  return (
    <>
      <PageHeader title="Privacy and data" subtitle="What is kept about you, for how long, and how to take it with you or remove it." />
      {msg && <p role="status" className="mb-3 text-sm">{msg}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard title="Your assistant notes">
          <p className="text-sm">{data.notes.length} note{data.notes.length === 1 ? "" : "s"} stored, visible only to you.</p>
          <div className="mt-3 flex gap-2">
            <button className="btn" disabled={data.notes.length === 0} onClick={save}>Download my notes</button>
            <button className="btn" disabled={data.notes.length === 0} onClick={async () => { if (!confirm("Delete all your notes?")) return; const r = await eraseNotes(); setMsg(`Removed ${r.removed} note(s).`); reload(); }}>Delete my notes</button>
          </div>
        </GlassCard>
        <GlassCard title="How long things are kept">
          <p className="text-sm">{days?.value ? <>Outputs and automation run history are kept for <b>{days.value} days</b> ({days.source === "tenant" ? "set for your organization" : "platform default"}).</> : "No retention period is set for outputs and run history, so they stay until deleted."}</p>
          <p className="mt-2 text-xs text-muted">Customer conversations follow the customer-data retention rules on the Access page; erasing a customer is done by an administrator with the privacy permission.</p>
        </GlassCard>
      </div>
    </>
  );
}
