"use client";
import { useState } from "react";
import { listKnowledgeDocs, listKnowledgeSources, useLoad } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

export default function Knowledge() {
  const sources = useLoad(() => listKnowledgeSources());
  const [source, setSource] = useState<string | undefined>(undefined);
  const docs = useLoad(() => listKnowledgeDocs(source), [source]);
  return (
    <>
      <PageHeader title="Library" subtitle="The sources your agents and assistants answer from. Managing them happens in Admin (Build, Library)." />
      {sources.loading && !sources.data ? <Loading /> : sources.error ? <ErrorBox message={sources.error} onRetry={sources.reload} /> : (
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Source">
          <button className={`pill ${!source ? "font-semibold text-primary" : ""}`} aria-pressed={!source} onClick={() => setSource(undefined)}>All sources</button>
          {sources.data?.map((s) => <button key={s.id} className={`pill ${source === s.id ? "font-semibold text-primary" : ""}`} aria-pressed={source === s.id} onClick={() => setSource(s.id)}>{s.name}</button>)}
        </div>
      )}
      <GlassCard title="Documents">
        {docs.loading && !docs.data ? <Loading /> : docs.error ? <ErrorBox message={docs.error} onRetry={docs.reload} /> : docs.data && docs.data.length === 0 ? <Empty>No documents yet.</Empty> : (
          <table className="tbl"><thead><tr><th>Title</th><th>Source</th><th>Last updated</th><th></th></tr></thead>
            <tbody>{docs.data?.map((d) => (
              <tr key={`${d.sourceId}-${d.externalId}`}><td>{d.title}</td><td>{d.sourceId}</td><td>{d.sourceUpdatedAt ? new Date(d.sourceUpdatedAt * 1000).toLocaleDateString() : new Date(d.ingestedAt * 1000).toLocaleDateString()}</td><td>{d.stale ? <span className="pill">may be out of date</span> : null}</td></tr>
            ))}</tbody></table>
        )}
      </GlassCard>
    </>
  );
}
