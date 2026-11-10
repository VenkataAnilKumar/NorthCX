"use client";
import { useState } from "react";
import { deleteNote, eraseNotes, listNotes, useLoad } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

export default function Memory() {
  const { data, error, loading, reload } = useLoad(listNotes, []);
  const [msg, setMsg] = useState("");
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  return (
    <>
      <PageHeader title="Memory" subtitle="What your assistants remember about you. Only you can see these notes; add them from the Workspace Pilot, and delete any of them here." />
      {msg && <p role="status" className="mb-3 text-sm">{msg}</p>}
      {!data || data.length === 0 ? <Empty>Nothing is remembered about you.</Empty> : (
        <GlassCard title={`${data.length} note${data.length === 1 ? "" : "s"}`}>
          <ul className="divide-y divide-border text-sm">
            {data.map((n) => (
              <li key={n.id} className="flex items-start justify-between gap-3 py-2">
                <span>{n.note}<span className="ml-2 text-xs text-muted">{new Date(n.updatedAt * 1000).toLocaleDateString()}</span></span>
                <button className="btn" onClick={async () => { await deleteNote(n.id); setMsg("Note deleted."); reload(); }}>Delete</button>
              </li>))}
          </ul>
          <button className="btn mt-3" onClick={async () => { if (!confirm("Delete everything remembered about you?")) return; const r = await eraseNotes(); setMsg(`Removed ${r.removed} note(s).`); reload(); }}>Delete all</button>
        </GlassCard>)}
    </>
  );
}
