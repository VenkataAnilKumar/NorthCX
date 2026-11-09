"use client";
import { useState } from "react";
import { deleteOutput, downloadOutput, editOutput, getOutput, listOutputs, listSpaces, saveOutput, useLoad, type OutputItem } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const when = (t: number) => new Date(t * 1000).toLocaleString();

function Editor({ id, onClose, onSaved }: { id: string | null; onClose: () => void; onSaved: () => void }) {
  const spaces = useLoad(() => listSpaces());
  const [loaded, setLoaded] = useState<OutputItem | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("note");
  const [visibility, setVisibility] = useState("private");
  const [space, setSpace] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [ready, setReady] = useState(id === null);
  useLoad(async () => { if (id) { const o = await getOutput(id); setLoaded(o); setTitle(o.title); setBody(o.body ?? ""); setKind(o.kind); setVisibility(o.visibility); setReady(true); } return null; }, [id]);
  const save = async () => {
    setErr(null);
    try { if (id) await editOutput(id, { title, body, visibility }); else await saveOutput({ title, body, kind, visibility, ...(space ? { spaceId: space } : {}) }); onSaved(); onClose(); } catch (e) { setErr((e as Error).message); }
  };
  if (!ready) return <Loading />;
  return (
    <GlassCard title={id ? `Edit: ${loaded?.title ?? ""}` : "New output"} action={<button className="btn" onClick={onClose}>Close</button>} className="mb-4">
      <div className="grid gap-3 md:grid-cols-4">
        <label className="text-sm md:col-span-2">Title<input className="field mt-1 w-full" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label className="text-sm">Type<select className="field mt-1 w-full" disabled={!!id} value={kind} onChange={(e) => setKind(e.target.value)}>{["note", "answer", "report", "table", "digest"].map((k) => <option key={k}>{k}</option>)}</select></label>
        <label className="text-sm">Who can see it<select className="field mt-1 w-full" value={visibility} onChange={(e) => setVisibility(e.target.value)}><option value="private">Only me</option><option value="shared">Everyone using the Workspace</option></select></label>
        {!id && <label className="text-sm">Space<select className="field mt-1 w-full" value={space} onChange={(e) => setSpace(e.target.value)}><option value="">None</option>{(spaces.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
      </div>
      <label className="mt-3 block text-sm">Content{kind === "table" ? " (CSV)" : ""}. Customer personal data is masked when you save.<textarea className="field mt-1 h-56 w-full font-mono text-xs" value={body} onChange={(e) => setBody(e.target.value)} /></label>
      {loaded && <p className="mt-1 text-xs text-muted">Version {loaded.version}; every change keeps the earlier version (the last 20).</p>}
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}
      <button className="btn btn-primary mt-3" disabled={title.trim().length < 2 || !body.trim()} onClick={() => void save()}>{id ? "Save a new version" : "Save"}</button>
    </GlassCard>
  );
}

export default function Page() {
  const [kind, setKind] = useState("");
  const [mine, setMine] = useState(false);
  const { data, error, loading, reload } = useLoad(() => listOutputs({ kind: kind || undefined, mine }), [kind, mine]);
  const [editing, setEditing] = useState<string | null | undefined>(undefined);
  const [err, setErr] = useState<string | null>(null);
  return (
    <>
      <PageHeader title="Outputs" subtitle="Results you kept: answers, reports, tables and notes. Customer personal data is masked, each change keeps the earlier version, and outputs expire after 90 days unless you set otherwise." />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <button className="btn btn-primary" onClick={() => setEditing(null)}>New output</button>
        <label>Type <select className="field ml-1" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">All</option>{["note", "answer", "report", "table", "digest"].map((k) => <option key={k}>{k}</option>)}</select></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only mine</label>
      </div>
      {editing !== undefined && <Editor key={editing ?? "new"} id={editing} onClose={() => setEditing(undefined)} onSaved={reload} />}
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? <Empty>No outputs yet. Save an answer from the Pilot, or write one here.</Empty> : (
        <ul className="space-y-3">{data.map((o) => (
          <li key={o.id} className="glass p-4">
            <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="font-semibold">{o.title}</h2><span className="pill">{o.visibility === "shared" ? "Shared" : "Private"}</span></div>
            <p className="mt-1 text-xs text-muted">{o.kind} · version {o.version} · {o.owner} · from {o.source} · updated {when(o.updatedAt)} · expires {when(o.expiresAt)}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn" onClick={() => setEditing(o.id)}>Open</button>
              {["md", "html", ...(o.kind === "table" ? ["csv"] : [])].map((f) => <button key={f} className="btn" onClick={() => void downloadOutput(o.id, f, o.title).catch((e) => setErr(e.message))}>Download .{f}</button>)}
              <button className="btn" onClick={() => { if (confirm("Delete this output and all its versions?")) void deleteOutput(o.id).then(reload).catch((e) => setErr(e.message)); }}>Delete</button>
            </div>
          </li>))}
        </ul>)}
    </>
  );
}
