"use client";
import { useState } from "react";
import { deleteLibraryItem, editLibraryItem, getLibraryItem, listKnowledgeDocs, listKnowledgeSources, listLibraryItems, saveLibraryItem, takeLibraryItem, useLoad, type LibraryItem } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const KIND = { macro: "Macro (a reply)", canned: "Canned answer", playbook: "Playbook (steps)", prompt: "Prompt for the Pilot" } as const;

function Saved() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const { data, loading, error, reload } = useLoad(() => listLibraryItems({ q: q || undefined, kind: kind || undefined }), [q, kind]);
  const [editing, setEditing] = useState<string | null | undefined>(undefined);
  const [f, setF] = useState({ title: "", body: "", kind: "macro", visibility: "private", tags: "" });
  const [err, setErr] = useState<string | null>(null);
  const [shown, setShown] = useState<LibraryItem | null>(null);
  const run = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); reload(); } catch (e) { setErr((e as Error).message); } };
  const tags = () => f.tags.split(",").map((x) => x.trim()).filter(Boolean);
  return (
    <>
      <p className="mb-3 text-sm text-muted">Replies, playbooks and prompts you keep for reuse. Customer personal data is masked when you save, so nothing from one customer reaches the next. The Inbox suggests the macros and canned answers that fit a conversation.</p>
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <input className="field" aria-label="Search saved items" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <label>Type <select className="field ml-1" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">All</option>{Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <button className="btn btn-primary" onClick={() => { setEditing(null); setF({ title: "", body: "", kind: "macro", visibility: "private", tags: "" }); }}>New item</button>
      </div>
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      {editing !== undefined && (
        <GlassCard title={editing ? "Edit item" : "New item"} action={<button className="btn" onClick={() => setEditing(undefined)}>Close</button>} className="mb-4">
          <div className="grid gap-3 md:grid-cols-3">
            <label className="text-sm md:col-span-2">Title<input className="field mt-1 w-full" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
            <label className="text-sm">Type<select className="field mt-1 w-full" disabled={!!editing} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className="text-sm">Who can see it<select className="field mt-1 w-full" value={f.visibility} onChange={(e) => setF({ ...f, visibility: e.target.value })}><option value="private">Only me</option><option value="shared">Everyone using the Workspace</option></select></label>
            <label className="text-sm md:col-span-2">Tags (comma separated, up to 8)<input className="field mt-1 w-full" value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} /></label>
          </div>
          <label className="mt-3 block text-sm">Text<textarea className="field mt-1 h-40 w-full" value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></label>
          <button className="btn btn-primary mt-3" disabled={f.title.trim().length < 2 || !f.body.trim()} onClick={() => void run(async () => { if (editing) await editLibraryItem(editing, { title: f.title, body: f.body, visibility: f.visibility, tags: tags() }); else await saveLibraryItem({ ...f, tags: tags() }); setEditing(undefined); })}>{editing ? "Save a new version" : "Save"}</button>
        </GlassCard>)}
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? <Empty>No saved items yet.</Empty> : (
        <ul className="space-y-3">{data.map((i) => (
          <li key={i.id} className="glass p-4">
            <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="font-semibold">{i.title}</h2><span className="pill">{i.visibility === "shared" ? "Shared" : "Private"}</span></div>
            <p className="mt-1 text-xs text-muted">{KIND[i.kind]} · version {i.version} · {i.owner} · used {i.uses} times{i.tags.length ? ` · ${i.tags.join(", ")}` : ""}</p>
            <p className="mt-1 text-sm">{i.preview}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn" onClick={() => void run(async () => setShown(await takeLibraryItem(i.id)))}>Use</button>
              <button className="btn" onClick={() => void run(async () => { const full = await getLibraryItem(i.id); setF({ title: full.title, body: full.body ?? "", kind: full.kind, visibility: full.visibility, tags: full.tags.join(", ") }); setEditing(i.id); })}>Edit</button>
              <button className="btn" onClick={() => { if (confirm("Delete this item and its versions?")) void run(() => deleteLibraryItem(i.id)); }}>Delete</button>
            </div>
          </li>))}</ul>)}
      {shown && <GlassCard title={shown.title} action={<button className="btn" onClick={() => setShown(null)}>Close</button>} className="mt-4"><textarea readOnly className="field w-full" rows={6} value={shown.body ?? ""} onFocus={(e) => e.currentTarget.select()} /><p className="mt-1 text-xs text-muted">Copy it where you need it. This counts as one use.</p></GlassCard>}
    </>
  );
}

export default function Knowledge() {
  const [tab, setTab] = useState<"sources" | "saved">("sources");
  const sources = useLoad(() => listKnowledgeSources());
  const [source, setSource] = useState<string | undefined>(undefined);
  const docs = useLoad(() => listKnowledgeDocs(source), [source]);
  return (
    <>
      <PageHeader title="Library" subtitle="The sources your agents and assistants answer from, and the replies, playbooks and prompts you keep. Managing sources happens in Admin (Build, Library)." />
      <div className="seg mb-4" role="tablist" aria-label="Library"><button role="tab" aria-selected={tab === "sources"} onClick={() => setTab("sources")}>Sources</button><button role="tab" aria-selected={tab === "saved"} onClick={() => setTab("saved")}>Saved items</button></div>
      {tab === "saved" ? <Saved /> : <>
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
      </>}
    </>
  );
}
