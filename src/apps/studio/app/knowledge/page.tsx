"use client";
import { useEffect, useState } from "react";
import { type CrawlJob, createKnowledgeSource, createSchedule, deleteKnowledgeDoc, deleteKnowledgeSource, deleteSchedule, formatTime, getIndexStatus, getKnowledgeDoc, importKnowledgeFile, type KnowledgeDoc, listCrawls, listKnowledgeDocs, listKnowledgeSources, listSchedules, type Passage, putKnowledgeDoc, rebuildIndex, searchKnowledge, setScheduleEnabled, startCrawl, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader } from "@northcx/ui";

const input = "w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-sm";
const box = "rounded-xl border border-border bg-surface p-4";
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);

function Try({ source }: { source: string }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Passage[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function go(e: React.FormEvent) { e.preventDefault(); setErr(null); try { setFound(await searchKnowledge(q.trim(), source || undefined)); } catch (x) { setErr((x as Error).message); } }
  return (
    <section aria-label="Try a question" className={box}>
      <h2 className="font-medium">Try a question</h2>
      <p className="mb-2 text-sm text-muted">See what the agent would find for a customer’s question. Nothing found here means it would hand off or say it does not know.</p>
      <form onSubmit={go} className="flex gap-2"><label className="sr-only" htmlFor="kq">Question</label><input id="kq" value={q} onChange={(e) => setQ(e.target.value)} placeholder="How long do refunds take?" className={input} /><button disabled={q.trim().length < 2} className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text disabled:opacity-50">Search</button></form>
      {err && <p role="alert" className="mt-2 text-sm text-[var(--bad)]">{err}</p>}
      <MeaningStatus />
      {found && (found.length === 0 ? <p className="mt-3 text-sm text-[var(--warn)]">Nothing relevant was found. A customer asking this would not get an answer from the documents.</p> : (
        <ol className="mt-3 space-y-2 text-sm">{found.map((p, i) => (
          <li key={i} className="rounded-lg border border-border p-3"><p className="font-medium">[{i + 1}] {p.title}{p.section ? ` › ${p.section}` : ""} {p.stale && <span className="ml-1 rounded bg-[var(--warn-bg)] px-1.5 text-xs text-[var(--warn)]">out of date</span>}</p>
            <p className="mt-1 whitespace-pre-wrap text-muted">{p.text}</p><p className="mt-1 text-xs text-muted">Updated {formatTime(p.updatedAt)}{p.via ? ` · found by ${p.via === "both" ? "words and meaning" : p.via === "meaning" ? "meaning" : "words"}` : ""}</p></li>))}</ol>))}
    </section>
  );
}

function DocForm({ sources, initial, onDone }: { sources: { id: string; name: string }[]; initial?: { source: string; ext: string }; onDone: () => void }) {
  const [source, setSource] = useState(initial?.source ?? sources[0]?.id ?? "");
  const [ext, setExt] = useState(initial?.ext ?? "");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [reviewed, setReviewed] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(!initial);
  useLoad(async () => {
    if (!initial) return null;
    const d = await getKnowledgeDoc(initial.source, initial.ext);
    setTitle(d.title); setUrl(d.url ?? ""); setText(d.text); setLoaded(true);
    if (d.textRebuilt) setNote("This document was saved before the original text was kept, so the text below was put back together from its passages. Check it before saving.");
    return d;
  }, [initial?.source, initial?.ext]);
  async function pick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 500_000) { setMsg("That file is larger than 500,000 characters."); return; }
    setText(await f.text()); if (!title) setTitle(f.name.replace(/\.[^.]+$/, "")); if (!ext && !initial) setExt(slug(f.name.replace(/\.[^.]+$/, "")));
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try { const r = await putKnowledgeDoc(source, ext, { title, text, ...(url ? { url } : {}), ...(reviewed ? { sourceUpdatedAt: Date.now() / 1000 } : {}) }); setMsg(r.status === "unchanged" ? "Nothing changed." : `Saved (${r.status}).`); onDone(); }
    catch (x) { setMsg((x as Error).message); }
  }
  if (!loaded) return <Loading />;
  return (
    <form onSubmit={save} className={`${box} space-y-2`} aria-label={initial ? "Edit document" : "Add document"}>
      <h2 className="font-medium">{initial ? "Edit document" : "Add a document"}</h2>
      {note && <p className="text-sm text-[var(--warn)]">{note}</p>}
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-sm">Source<select value={source} disabled={!!initial} onChange={(e) => setSource(e.target.value)} className={input}>{sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label className="text-sm">Title<input required value={title} onChange={(e) => { setTitle(e.target.value); if (!initial && !ext) setExt(slug(e.target.value)); }} className={input} /></label>
        <label className="text-sm">Link (optional)<input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" className={input} /></label>
      </div>
      <label className="block text-sm">Text (plain text or Markdown; headings split it into passages)<textarea required value={text} onChange={(e) => setText(e.target.value)} rows={12} className={`${input} font-mono`} /></label>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label>Load from a file<input type="file" accept=".md,.txt,.markdown,text/plain,text/markdown" onChange={pick} className="ml-2" /></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} /> Mark as reviewed today</label>
        {!initial && <label>Id<input value={ext} onChange={(e) => setExt(e.target.value)} className="ml-2 w-44 rounded-lg border border-border bg-bg px-2 py-1" /></label>}
      </div>
      <div className="flex items-center gap-3"><button disabled={!source || !ext || !title || !text} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-text disabled:opacity-50">Save document</button>
        {msg && <span role="status" className="text-sm text-muted">{msg}</span>}</div>
    </form>
  );
}

function MeaningStatus() {
  const st = useLoad(getIndexStatus, []);
  const [msg, setMsg] = useState<string | null>(null);
  const s = st.data;
  if (!s) return null;
  if (!s.enabled) return <p className="mt-2 text-xs text-muted">Search matches words only. An administrator can switch on meaning-based search (see the Deployment Guide).</p>;
  return (
    <p className="mt-2 text-xs text-muted" role="status">
      Meaning-based search is on ({s.model}): {s.indexed} of {s.passages} passages ready{s.pending ? `, ${s.pending} still being prepared` : ""}.{s.lastError ? ` Last problem: ${s.lastError}. Search is using words only until it recovers.` : ""}{" "}
      <button type="button" className="underline" onClick={async () => { try { await rebuildIndex(); setMsg("Rebuilding."); st.reload(); } catch (x) { setMsg((x as Error).message); } }}>Rebuild</button>{msg ? ` ${msg}` : ""}
    </p>
  );
}

function BringIn({ sources, onDone }: { sources: { id: string; name: string }[]; onDone: () => void }) {
  const [source, setSource] = useState(sources[0]?.id ?? "");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [url, setUrl] = useState("");
  const [pages, setPages] = useState(50);
  const [include, setInclude] = useState("");
  const [prune, setPrune] = useState(false);
  const [every, setEvery] = useState(0);
  const schedules = useLoad(listSchedules, [msg]);
  const crawls = useLoad(listCrawls, [source, msg]);
  const running = crawls.data?.crawls.some((c) => c.state === "running");
  useEffect(() => { if (!running) return; const t = setInterval(() => { crawls.reload(); onDone(); }, 3000); return () => clearInterval(t); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [running]);
  const lines = (v: string) => v.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
  async function upload(list: FileList | null) {
    if (!list?.length || !source) return;
    const out: string[] = [];
    for (const f of Array.from(list).slice(0, 10)) {
      try { const r = await importKnowledgeFile(source, f); out.push(`${f.name}: ${r.status}`); } catch (e) { out.push(`${f.name}: ${(e as Error).message}`); }
    }
    setMsg({ ok: true, text: out.join(" · ") }); onDone();
  }
  async function crawl(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      const body = { url: url.trim(), maxPages: pages, maxDepth: 2, includePaths: lines(include), excludePaths: [], prune };
      await startCrawl(source, body);
      if (every > 0) { await createSchedule(source, { ...body, everyHours: every }); setMsg({ ok: true, text: `Crawl started, and it will repeat every ${every === 24 ? "day" : every === 168 ? "week" : `${every} hours`}.` }); }
      else setMsg({ ok: true, text: "Crawl started." });
      crawls.reload();
    }
    catch (err) { setMsg({ ok: false, text: (err as Error).message }); }
  }
  const mine: CrawlJob[] = (crawls.data?.crawls ?? []).filter((c) => c.sourceId === source).slice(0, 3);
  return (
    <section aria-label="Bring in content" className={box}>
      <h2 className="font-medium">Bring in content</h2>
      <p className="mb-2 text-sm text-muted">Upload PDF, HTML, Markdown or text files, or read a website. Pages are added as documents you can edit and keep up to date.</p>
      <label className="text-sm">Into source <select value={source} onChange={(e) => setSource(e.target.value)} className="ml-1 rounded-lg border border-border bg-bg px-2 py-1.5">{sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <div className="mt-3 text-sm"><label className="inline-block cursor-pointer rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Upload files
        <input type="file" multiple className="sr-only" accept=".pdf,.html,.htm,.md,.markdown,.txt,application/pdf,text/*" onChange={(e) => { void upload(e.target.files); e.target.value = ""; }} /></label></div>
      {crawls.data?.enabled ? (
        <form onSubmit={crawl} className="mt-3 space-y-2 text-sm" aria-label="Crawl a website">
          <label className="block">Website address<input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://help.example.com/" className="mt-1 w-full rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
          <div className="flex flex-wrap items-end gap-3">
            <label>Pages at most<input type="number" min={1} max={200} value={pages} onChange={(e) => setPages(Number(e.target.value))} className="ml-2 w-20 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
            <label>Only these paths (optional)<input value={include} onChange={(e) => setInclude(e.target.value)} placeholder="/help/, /faq/" className="ml-2 w-48 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={prune} onChange={(e) => setPrune(e.target.checked)} /> Remove pages that no longer exist</label>
          </div>
          <label className="block">Repeat <select value={every} onChange={(e) => setEvery(Number(e.target.value))} className="ml-2 rounded-lg border border-border bg-bg px-2 py-1.5"><option value={0}>Only this once</option><option value={6}>Every 6 hours</option><option value={24}>Every day</option><option value={168}>Every week</option></select></label>
          <button disabled={!url.trim() || !source || !!running} className="rounded-lg bg-primary px-3 py-1.5 font-medium text-primary-text disabled:opacity-50">{running ? "Crawling…" : "Crawl"}</button>
        </form>
      ) : <p className="mt-3 text-xs text-muted">Reading websites is switched off. The operator lists the sites that may be read in <code>NORTHCX_CRAWL_HOSTS</code>.</p>}
      {msg && <p role={msg.ok ? "status" : "alert"} className={`mt-2 text-sm ${msg.ok ? "text-muted" : "text-[var(--bad)]"}`}>{msg.text}</p>}
      {(schedules.data?.schedules ?? []).filter((s) => s.sourceId === source).map((s) => (
        <p key={s.id} className="mt-2 text-xs text-muted">Repeats every {s.everyHours} hours: {s.url}{s.enabled ? `, next ${formatTime(s.nextRun)}` : " (paused)"}{s.lastResult ? ` · last: ${s.lastResult}` : ""}{" "}
          <button type="button" className="underline" onClick={async () => { await setScheduleEnabled(s.id, !s.enabled); schedules.reload(); }}>{s.enabled ? "Pause" : "Resume"}</button>{" "}
          <button type="button" className="underline" onClick={async () => { await deleteSchedule(s.id); schedules.reload(); }}>Remove</button></p>))}
      {mine.map((c) => (
        <p key={c.jobId} className="mt-2 text-xs text-muted">{c.host}: {c.state === "running" ? "reading…" : c.state} · {c.fetched} pages read · {c.created} new, {c.updated} changed, {c.unchanged} the same{c.pruned ? `, ${c.pruned} removed` : ""}
          {Object.keys(c.skipped).length > 0 && ` · skipped: ${Object.entries(c.skipped).map(([k, n]) => `${n} ${k}`).join(", ")}`}{c.message && ` · ${c.message}`}</p>))}
    </section>
  );
}

export default function Knowledge() {
  const { can } = useMe();
  const [tick, setTick] = useState(0);
  const [source, setSource] = useState("");
  const [staleOnly, setStaleOnly] = useState(false);
  const [editing, setEditing] = useState<{ source: string; ext: string } | "new" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const sources = useLoad(listKnowledgeSources, [tick]);
  const docs = useLoad(() => listKnowledgeDocs(source || undefined, staleOnly), [source, staleOnly, tick]);
  const refresh = () => setTick((t) => t + 1);
  const write = can("knowledge:write");
  async function act(fn: () => Promise<unknown>) { setErr(null); try { await fn(); refresh(); } catch (e) { setErr((e as Error).message); } }

  if (sources.loading && !sources.data) return <Loading />;
  if (sources.error) return <ErrorBox message={sources.error} onRetry={sources.reload} />;
  const srcs = sources.data!;
  return (
    <>
      <PageHeader title="Knowledge" subtitle="The documents your agents answer from. Out-of-date sources are flagged so the agent says so, and so you can fix them." />
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
        <div className="space-y-4">
          <section aria-label="Sources" className={box}>
            <h2 className="font-medium">Sources</h2>
            {srcs.length === 0 ? <p className="text-sm text-muted">No sources yet. A source is a collection such as “Help centre”.</p> : (
              <ul className="mt-2 space-y-1 text-sm">{srcs.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2"><span><strong>{s.name}</strong> <span className="text-muted">· {s.staleAfterDays ? `out of date after ${s.staleAfterDays} days` : "never goes out of date"}</span></span>
                  {write && <button onClick={() => confirm(`Delete the source ${s.name} and all its documents?`) && act(() => deleteKnowledgeSource(s.id))} className="rounded-lg border border-border px-2 py-1 text-xs hover:bg-border/40">Delete</button>}</li>))}</ul>)}
            {write && (
              <form className="mt-3 flex flex-wrap items-end gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const name = String(f.get("name") ?? "").trim(); const days = Number(f.get("days") || 0); if (name) act(() => createKnowledgeSource(slug(name) || "source", name, days || undefined)); e.currentTarget.reset(); }}>
                <label>New source<input name="name" placeholder="Help centre" className="ml-2 w-44 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
                <label>Out of date after (days)<input name="days" type="number" min={1} max={3650} className="ml-2 w-20 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
                <button className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Add source</button></form>)}
          </section>

          {write && srcs.length > 0 && <BringIn sources={srcs} onDone={refresh} />}

          <section aria-label="Documents" className={box}>
            <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-medium">Documents</h2>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <label className="sr-only" htmlFor="srcf">Source</label><select id="srcf" value={source} onChange={(e) => setSource(e.target.value)} className="rounded-lg border border-border bg-bg px-2 py-1.5"><option value="">All sources</option>{srcs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
                <label className="flex items-center gap-2"><input type="checkbox" checked={staleOnly} onChange={(e) => setStaleOnly(e.target.checked)} /> Out of date only</label>
                {write && srcs.length > 0 && <button onClick={() => setEditing("new")} className="rounded-lg bg-primary px-3 py-1.5 font-medium text-primary-text">Add document</button>}</div></div>
            {docs.loading && !docs.data ? <Loading /> : docs.error ? <ErrorBox message={docs.error} onRetry={docs.reload} /> : !docs.data?.length ? <Empty>{staleOnly ? "Nothing is out of date." : "No documents yet."}</Empty> : (
              <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-sm">
                <thead className="border-b border-border text-muted"><tr><th className="p-2 font-medium">Title</th><th className="p-2 font-medium">Source</th><th className="p-2 font-medium">Passages</th><th className="p-2 font-medium">Last reviewed</th><th className="p-2"><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>{docs.data.map((d: KnowledgeDoc) => (
                  <tr key={d.id} className="border-b border-border last:border-0"><td className="p-2">{d.title} {d.stale && <span className="ml-1 rounded bg-[var(--warn-bg)] px-1.5 text-xs text-[var(--warn)]">out of date</span>}</td>
                    <td className="p-2">{d.sourceId}</td><td className="p-2 tabular-nums">{d.chunks}</td><td className="p-2 whitespace-nowrap">{formatTime(d.sourceUpdatedAt ?? d.ingestedAt)}</td>
                    <td className="p-2 whitespace-nowrap">{write ? (<><button onClick={() => setEditing({ source: d.sourceId, ext: d.externalId })} className="mr-2 text-primary underline">Edit</button>
                      <button onClick={() => confirm(`Delete ${d.title}?`) && act(() => deleteKnowledgeDoc(d.sourceId, d.externalId))} className="text-[var(--bad)] underline">Delete</button></>) : null}</td></tr>))}</tbody></table></div>)}
          </section>
          {editing && write && <DocForm key={editing === "new" ? "new" : `${editing.source}/${editing.ext}`} sources={srcs} initial={editing === "new" ? undefined : editing} onDone={refresh} />}
        </div>
        <Try source={source} />
      </div>
    </>
  );
}
