"use client";
import { useState } from "react";
import { addSpaceFile, createSpace, deleteSpace, deleteSpaceFile, editSpace, getSpace, listSpaceFiles, listSpaces, useLoad, type SpaceItem } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

function Files({ space, canEdit }: { space: SpaceItem; canEdit: boolean }) {
  const { data, reload } = useLoad(() => listSpaceFiles(space.id), [space.id]);
  const [err, setErr] = useState<string | null>(null);
  const pick = async (file: File | undefined) => {
    if (!file) return;
    setErr(null);
    try {
      if (file.name.toLowerCase().endsWith(".pdf")) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        let bin = "";
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        await addSpaceFile(space.id, file.name, { dataBase64: btoa(bin) });
      } else await addSpaceFile(space.id, file.name, { text: await file.text() });
      reload();
    } catch (e) { setErr((e as Error).message); }
  };
  return (
    <div className="mt-3">
      <h3 className="text-sm font-semibold">Files</h3>
      <p className="text-xs text-muted">Plain text (.txt, .md, .csv, .json, .log) or a PDF with a text layer (only its text is kept; scans are not read), up to 10 files of 200,000 characters. Customer personal data is masked when a file is added. The Pilot reads them as data when you work in this space.</p>
      {err && <div className="my-2"><ErrorBox message={err} /></div>}
      {data?.length ? <ul className="mt-1 text-sm">{data.map((f) => <li key={f.id}>{f.name} <span className="text-xs text-muted">({f.size.toLocaleString()} characters)</span>{canEdit && <button className="btn ml-2" onClick={() => void deleteSpaceFile(space.id, f.id).then(reload).catch((e) => setErr(e.message))}>Remove</button>}</li>)}</ul> : <p className="text-sm text-muted">No files.</p>}
      {canEdit && <label className="mt-2 block text-sm">Add a file<input type="file" accept=".txt,.md,.csv,.json,.log,.pdf,text/plain,application/pdf" className="field mt-1 block" onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ""; }} /></label>}
    </div>
  );
}

export default function Page() {
  const { data, error, loading, reload } = useLoad(() => listSpaces());
  const [open, setOpen] = useState<SpaceItem | null>(null);
  const [form, setForm] = useState({ name: "", description: "", instructions: "", visibility: "private" });
  const [editing, setEditing] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (f: () => Promise<unknown>) => { setErr(null); try { await f(); reload(); } catch (e) { setErr((e as Error).message); } };
  return (
    <>
      <PageHeader title="Spaces" subtitle="One piece of work: instructions the Pilot follows when you work in the space, and the outputs that belong to it. Private unless you share it." />
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? <Empty>No spaces yet. Create one below.</Empty> : (
        <ul className="mb-6 grid gap-4 md:grid-cols-2">{data.map((s) => (
          <li key={s.id} className="glass p-4">
            <div className="flex items-start justify-between gap-2"><h2 className="font-semibold">{s.name}</h2><span className="pill">{s.visibility === "shared" ? "Shared" : "Private"}</span></div>
            <p className="mt-1 text-xs text-muted">{s.owner}</p>{s.description && <p className="mt-1 text-sm">{s.description}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn" onClick={() => void run(async () => setOpen(await getSpace(s.id)))}>Open</button>
              <button className="btn" onClick={() => { setEditing(s.id); setForm({ name: s.name, description: s.description, instructions: s.instructions, visibility: s.visibility }); }}>Edit</button>
              <button className="btn" onClick={() => { if (confirm("Delete this space? Its outputs are kept.")) void run(() => deleteSpace(s.id)); }}>Delete</button>
            </div>
          </li>))}
        </ul>)}
      {open && (
        <GlassCard title={`In ${open.name}`} action={<button className="btn" onClick={() => setOpen(null)}>Close</button>} className="mb-6">
          <p className="text-sm"><strong>Instructions:</strong> {open.instructions || "none"}</p>
          <p className="mt-1 text-xs text-muted">Open the Pilot and choose this space to work with these instructions.</p>
          <Files space={open} canEdit />
          <h3 className="mt-3 text-sm font-semibold">Outputs</h3>
          {open.outputs?.length ? <ul className="mt-1 text-sm">{open.outputs.map((o) => <li key={o.id}>{o.title} <span className="text-xs text-muted">({o.kind}, version {o.version})</span></li>)}</ul> : <Empty>No outputs you can see.</Empty>}
        </GlassCard>)}
      <GlassCard title={editing ? "Edit space" : "New space"}>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm">Name<input className="field mt-1 w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="text-sm">Who can see it<select className="field mt-1 w-full" value={form.visibility} onChange={(e) => setForm({ ...form, visibility: e.target.value })}><option value="private">Only me</option><option value="shared">Everyone using the Workspace</option></select></label>
          <label className="text-sm md:col-span-2">Description<input className="field mt-1 w-full" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <label className="text-sm md:col-span-2">Instructions for the Pilot (up to 2,000 characters). They guide it; they never give it more access.<textarea className="field mt-1 h-28 w-full" value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} /></label>
        </div>
        <div className="mt-3 flex gap-2">
          <button className="btn btn-primary" disabled={form.name.trim().length < 2} onClick={() => void run(async () => { if (editing) await editSpace(editing, form); else await createSpace(form); setEditing(null); setForm({ name: "", description: "", instructions: "", visibility: "private" }); })}>{editing ? "Save changes" : "Create space"}</button>
          {editing && <button className="btn" onClick={() => { setEditing(null); setForm({ name: "", description: "", instructions: "", visibility: "private" }); }}>Cancel</button>}
        </div>
      </GlassCard>
    </>
  );
}
