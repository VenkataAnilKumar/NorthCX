"use client";
import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { getHandoff, listHandoffs, resolveHandoff, suggestHelp, suggestLibraryItems, takeLibraryItem, type LibraryItem, useLoad, useMe, type Assist } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, StatusBadge } from "@northcx/ui";

const when = (t: number) => new Date(t * 1000).toLocaleString();

function Detail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { askForName, me } = useMe();
  const { data, error, loading, reload } = useLoad(() => getHandoff(id), [id]);
  const [note, setNote] = useState("");
  const [back, setBack] = useState(true);
  const [assist, setAssist] = useState<Assist | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const h = data!;
  const by = askForName ? undefined : me?.name;
  const act = async (fn: () => Promise<void>) => { setBusy(true); setMsg(null); try { await fn(); } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); } };
  return (
    <div className="space-y-4">
      <GlassCard title={h.package.summary || "Hand-off"} action={<StatusBadge status={h.state} />}>
        <p className="text-sm text-muted">{h.package.triggerDescription}</p>
        <p className="mt-1 text-xs text-muted">Agent {h.agentId} · {when(h.createdAt)}{h.queue ? ` · queue ${h.queue}` : ""}{h.package.topics.length ? ` · ${h.package.topics.join(", ")}` : ""}</p>
        {h.package.language && <p className="mt-1 text-xs text-muted">Customer wrote in {h.package.language}</p>}
      </GlassCard>
      <GlassCard title="Conversation">
        <ol className="space-y-2" aria-label="Transcript">
          {h.package.transcript.map((m, i) => (
            <li key={i} className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${m.from === "customer" ? "ml-auto bg-[var(--info-bg)]" : "glass"}`}><span className="block text-[0.65rem] tracking-wide text-muted uppercase">{m.from}</span>{m.text}</li>
          ))}
        </ol>
      </GlassCard>
      {h.package.approvals.length > 0 && (
        <GlassCard title="Approvals in this conversation"><ul className="space-y-1 text-sm">{h.package.approvals.map((a) => <li key={a.id}><span className="font-medium">{a.tool}</span> <StatusBadge status={a.state} /> <span className="text-muted">{a.reason}</span></li>)}</ul></GlassCard>
      )}
      {Object.keys(h.package.customerFacts).length > 0 && (
        <GlassCard title="What the agent knew"><dl className="grid grid-cols-[10rem_1fr] gap-y-1 text-sm">{Object.entries(h.package.customerFacts).map(([k, v]) => <><dt key={k} className="text-muted">{k}</dt><dd key={k + "v"}>{String(v)}</dd></>)}</dl></GlassCard>
      )}
      {h.state === "open" && (
        <GlassCard title="Your reply and next step">
          <div className="flex flex-wrap gap-2">
            <button className="btn" disabled={busy} onClick={() => act(async () => setAssist(h.package.assist ?? (await suggestHelp(h.id))))}>Suggest a reply</button>
          </div>
          <Macros transcript={h.package.transcript} />
          {assist && (
            <div className="mt-3 rounded-xl border border-border p-3 text-sm" aria-live="polite">
              <p className="text-xs text-muted">{assist.note}</p>
              <p className="mt-2 font-medium">Suggested reply</p><p>{assist.suggestedReply}</p>
              {assist.nextSteps.length > 0 && <><p className="mt-2 font-medium">Next steps</p><ul className="list-disc pl-5">{assist.nextSteps.map((s) => <li key={s}>{s}</li>)}</ul></>}
              {assist.cautions.length > 0 && <><p className="mt-2 font-medium text-[var(--warn)]">Cautions</p><ul className="list-disc pl-5">{assist.cautions.map((s) => <li key={s}>{s}</li>)}</ul></>}
            </div>
          )}
          <label className="mt-3 block text-sm">Note for the record (optional)<textarea className="field mt-1" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={back} onChange={(e) => setBack(e.target.checked)} /> Return the conversation to the agent</label>
          <button className="btn btn-primary mt-3" disabled={busy} onClick={() => act(async () => { await resolveHandoff(h.id, by, note || undefined, back); await reload(); onChanged(); })}>Resolve</button>
          {msg && <div className="mt-3"><ErrorBox message={msg} /></div>}
        </GlassCard>
      )}
      {h.state === "resolved" && <p className="text-sm text-muted">Resolved by {h.resolvedBy}{h.resolvedAt ? ` · ${when(h.resolvedAt)}` : ""}{h.note ? ` · ${h.note}` : ""}</p>}
    </div>
  );
}

function Threads() {
  const params = useSearchParams();
  const router = useRouter();
  const selected = params.get("id");
  const [state, setState] = useState<"open" | "resolved">("open");
  const { data, error, loading, reload } = useLoad(() => listHandoffs(state), [state]);
  return (
    <>
      <PageHeader title="Inbox" subtitle="Customer conversations that need a person." />
      <div className="mb-3 inline-flex gap-1 rounded-xl border border-border p-1" role="tablist" aria-label="State">
        {(["open", "resolved"] as const).map((s) => <button key={s} role="tab" aria-selected={state === s} onClick={() => setState(s)} className={`rounded-lg px-3 py-1 text-sm ${state === s ? "bg-primary font-semibold text-primary-text" : "text-muted"}`}>{s === "open" ? "Needs a person" : "Resolved"}</button>)}
      </div>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <div>
          {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : data && data.length === 0 ? <Empty>{state === "open" ? "Nothing is waiting for a person." : "No resolved hand-offs yet."}</Empty> : (
            <ul className="space-y-2">{data?.map((h) => (
              <li key={h.id}><button onClick={() => router.push(`/inbox?id=${h.id}`)} aria-current={selected === h.id ? "true" : undefined}
                className={`glass block w-full p-3 text-left text-sm ${selected === h.id ? "ring-2 ring-primary" : ""}`}>
                <span className="font-medium">{h.summary || h.reason || h.trigger}</span><span className="mt-1 block text-xs text-muted">{h.agentId} · {when(h.createdAt)}</span></button></li>
            ))}</ul>
          )}
        </div>
        <div>{selected ? <Detail key={selected} id={selected} onChanged={reload} /> : <Empty>Choose a conversation to read it and decide what to do.</Empty>}</div>
      </div>
    </>
  );
}
function Macros({ transcript }: { transcript: { from: string; text: string }[] }) {
  const customerText = transcript.filter((m) => m.from === "customer").map((m) => m.text).join("\n").slice(-1500);
  const { data } = useLoad(() => (customerText.length > 1 ? suggestLibraryItems(customerText).catch(() => [] as LibraryItem[]) : Promise.resolve([] as LibraryItem[])), [customerText]);
  const [shown, setShown] = useState<LibraryItem | null>(null);
  if (!data?.length) return null;
  return (
    <div className="mt-3 rounded-xl border border-border p-3 text-sm">
      <p className="font-medium">Saved replies that fit</p>
      <ul className="mt-1 space-y-1">{data.map((m) => <li key={m.id}><button className="underline" onClick={() => void takeLibraryItem(m.id).then(setShown)}>{m.title}</button> <span className="text-xs text-muted">used {m.uses} times · {m.preview.slice(0, 80)}</span></li>)}</ul>
      {shown && <div className="mt-2"><p className="text-xs text-muted">Copy it, check it fits, and send it yourself from your usual tool. Nothing is sent from here.</p><textarea readOnly className="field mt-1 w-full" rows={4} value={shown.body ?? ""} onFocus={(e) => e.currentTarget.select()} /></div>}
    </div>
  );
}

export default function Page() { return <Suspense fallback={<Loading />}><Threads /></Suspense>; }
