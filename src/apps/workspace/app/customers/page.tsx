"use client";
import { useState } from "react";
import { customerAddNote, customerDeleteNote, customerLookup, customerRemoveFact, customerReveal, customersEnabled, setCustomersEnabled, useLoad, useMe, type CustomerRecord } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const when = (t: number) => new Date(t * 1000).toLocaleString();

export default function Page() {
  const { can } = useMe();
  const enabled = useLoad(() => customersEnabled());
  const [q, setQ] = useState("");
  const [id, setId] = useState<string | null>(null);
  const [rec, setRec] = useState<CustomerRecord | null>(null);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (f: () => Promise<unknown>) => { setErr(null); setBusy(true); try { await f(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const open = (cid: string) => run(async () => { setRec(await customerLookup(cid)); setId(cid); setRevealed(null); });
  if (!can("customers:read")) return (<><PageHeader title="Customers" subtitle="Your role cannot open this view." /><Empty>Ask an administrator if you need it.</Empty></>);
  if (enabled.loading && !enabled.data) return <Loading />;
  if (enabled.data && !enabled.data.enabled) return (
    <>
      <PageHeader title="Customers" subtitle="This view is turned off for your organization." />
      {can("keys:manage") && <button className="btn" onClick={() => void setCustomersEnabled(true).then(enabled.reload)}>Turn it on</button>}
    </>
  );
  return (
    <>
      <PageHeader title="Customers" subtitle="One view of a person across every channel. Look someone up by the identifier your company uses for them. Personal data is masked and every open is recorded." />
      <form className="mb-4 flex gap-2" role="search" onSubmit={(e) => { e.preventDefault(); if (q.trim()) void open(q.trim()); }}>
        <input className="field flex-1" aria-label="Customer identifier" placeholder="Customer identifier" autoComplete="off" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn btn-primary" disabled={busy || !q.trim()}>Open</button>
      </form>
      {can("keys:manage") && <p className="mb-3 text-xs"><button className="underline" onClick={() => { if (confirm("Turn the Customers view off for everyone?")) void setCustomersEnabled(false).then(enabled.reload); }}>Turn this view off</button></p>}
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      {!rec ? <Empty>Nothing opened. There is no browsing here on purpose: you need the identifier.</Empty> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <GlassCard title={`Customer ${rec.ref}`}>
            <p className="text-sm">Identifier: <strong>{revealed ?? rec.id}</strong>{rec.idMasked && !revealed && (
              <button className="btn ml-2" onClick={() => { const reason = prompt("Why do you need to see it? This is recorded."); if (reason && reason.trim().length >= 10) void run(async () => setRevealed((await customerReveal(id!, reason.trim())).id)); }}>Show</button>)}</p>
            <p className="mt-2 text-sm">{rec.sessions} conversation{rec.sessions === 1 ? "" : "s"}; {rec.satisfaction.rated} rated{rec.satisfaction.average !== null ? `, average ${rec.satisfaction.average}` : ""}; {rec.satisfaction.handedOff} handed to a person.</p>
            <p className="mt-1 text-xs text-muted">{rec.satisfaction.counts}. {rec.note}</p>
          </GlassCard>
          <GlassCard title="Facts the agents may use">
            {rec.facts.length === 0 ? <Empty>None.</Empty> : <ul className="space-y-2 text-sm">{rec.facts.map((f) => (
              <li key={f.id} className="rounded-xl border border-border p-2">{f.text}<br /><span className="text-xs text-muted">Added by {f.addedBy}, {when(f.createdAt)}</span>
                {can("customers:write") && <button className="btn ml-2" onClick={() => { const reason = prompt("Reason for removing it (for example, the customer asked)?"); if (reason && reason.trim().length >= 5) void run(async () => { await customerRemoveFact(id!, f.id, reason.trim()); await open(id!); }); }}>Remove</button>}</li>))}</ul>}
          </GlassCard>
          <GlassCard title="Timeline">
            <ol className="space-y-2 text-sm">{rec.timeline.map((t) => (
              <li key={t.sessionId} className="rounded-xl border border-border p-2"><strong>{when(t.startedAt)}</strong> · {t.channel ?? "chat"} · {t.agentId} · {t.turns} message{t.turns === 1 ? "" : "s"}<br />
                <span className="text-muted">{t.firstMessage}</span><br /><span className="text-xs">{t.lastStatus}{t.handedOff ? ` · handed to a person (${t.handoffReasons.join(", ")})` : ""}{t.rating ? ` · rated ${t.rating}` : ""}{t.review ? ` · reviewed ${t.review}` : ""}</span></li>))}</ol>
          </GlassCard>
          <GlassCard title="Staff notes">
            {can("customers:write") && <div className="mb-2 flex gap-2"><input className="field flex-1" aria-label="New note" maxLength={300} placeholder="A short note for colleagues" value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn btn-primary" disabled={busy || note.trim().length < 5} onClick={() => void run(async () => { await customerAddNote(id!, note.trim()); setNote(""); await open(id!); })}>Add</button></div>}
            {rec.notes.length === 0 ? <Empty>No notes.</Empty> : <ul className="space-y-2 text-sm">{rec.notes.map((n) => <li key={n.id} className="rounded-xl border border-border p-2">{n.note}<br /><span className="text-xs text-muted">{n.author}, {when(n.createdAt)}</span>
              <button className="btn ml-2" onClick={() => void run(async () => { await customerDeleteNote(id!, n.id); await open(id!); })}>Delete</button></li>)}</ul>}
          </GlassCard>
        </div>
      )}
    </>
  );
}
