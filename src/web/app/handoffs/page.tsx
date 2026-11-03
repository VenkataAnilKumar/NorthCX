"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { formatTime, getHandoff, getRouting, listHandoffs, resolveHandoff, type HandoffSummary } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { useMe } from "@/lib/me";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

const triggerLabel: Record<string, string> = {
  budget_exceeded: "Model budget used up", agent_handoff: "Agent handed off", forced_topic: "Always-to-a-person topic", input_blocked: "Input blocked",
  supervisor_rejections: "Replies rejected", step_limit: "Step limit", model_error: "Model unavailable", approval_expired: "Approval expired",
};
const who: Record<string, string> = { customer: "Customer", agent: "Agent", platform: "Platform" };

function Detail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { data, error, loading, reload } = useLoad(() => getHandoff(id), [id]);
  const { can, askForName } = useMe();
  const [by, setBy] = useState("jo");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const h = data!, p = h.package;

  async function resolve() {
    setErr(null);
    try { await resolveHandoff(h.id, askForName ? by.trim() || "agent" : undefined, note.trim() || undefined); setNote(""); reload(); onChanged(); }
    catch (e) { setErr((e as Error).message); reload(); onChanged(); }
  }

  return (
    <section aria-label="Handoff detail" className="space-y-5 rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{triggerLabel[h.trigger] ?? h.trigger}</h2>
        <StatusBadge status={h.state} />
      </div>
      <p className="text-sm">{p.summary}</p>
      {p.topics.length > 0 && <p className="text-sm text-muted">Topics: {p.topics.join(", ")}</p>}
      <div>
        <h3 className="mb-1 text-sm font-medium">Conversation</h3>
        <ol aria-label="Transcript" className="space-y-2">
          {p.transcript.map((m, i) => (
            <li key={i} className={`max-w-[90%] rounded-lg px-3 py-2 text-sm ${m.from === "customer" ? "bg-primary text-primary-text" : m.from === "platform" ? "border border-dashed border-border text-muted" : "border border-border"}`}>
              <span className="mr-2 text-xs opacity-75">{who[m.from]}</span>{m.text}
            </li>
          ))}
        </ol>
      </div>
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <h3 className="mb-1 text-sm font-medium">Actions taken</h3>
          {!p.actions.length ? <p className="text-sm text-muted">None.</p> : (
            <ul className="space-y-1 text-sm">{p.actions.map((a, i) => (
              <li key={i}><code>{a.tool}</code> <span className="text-muted">— {a.outcome}</span></li>))}</ul>
          )}
          {p.approvals.length > 0 && (<>
            <h3 className="mb-1 mt-3 text-sm font-medium">Approvals</h3>
            <ul className="space-y-1 text-sm">{p.approvals.map((a) => (
              <li key={a.id} className="flex items-center gap-2"><code>{a.tool}</code><StatusBadge status={a.state} /></li>))}</ul>
          </>)}
        </div>
        <div>
          <h3 className="mb-1 text-sm font-medium">Customer</h3>
          <p className="text-sm text-muted">{h.customerId ?? "Not identified"}</p>
          {p.language && <p className="text-sm text-muted">Writing in: {p.language}</p>}
          {Object.keys(p.customerFacts).length > 0 && (
            <dl className="mt-1 text-sm">{Object.entries(p.customerFacts).map(([k, v]) => (
              <div key={k} className="flex gap-2"><dt className="text-muted">{k}</dt><dd>{v}</dd></div>))}</dl>
          )}
          <p className="mt-3 text-sm"><Link className="text-primary underline" href={`/conversations/${h.traceId}`}>Open the trace</Link></p>
        </div>
      </div>
      {h.state === "open" ? (
        <div className="flex flex-wrap items-end gap-2 border-t border-border pt-4">
          {askForName && <label className="text-sm">Your name <input value={by} onChange={(e) => setBy(e.target.value)} className="ml-1 w-32 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>}
          <label className="text-sm">Note <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" className="ml-1 w-56 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
          <button onClick={resolve} disabled={!can("handoffs:resolve")} title={can("handoffs:resolve") ? undefined : "Your role cannot resolve handoffs"} className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text disabled:opacity-50">Mark resolved</button>
          {err && <ErrorBox message={err} />}
        </div>
      ) : (
        <p className="border-t border-border pt-3 text-sm text-muted">Resolved by {h.resolvedBy} {formatTime(h.resolvedAt)}{h.note ? ` — “${h.note}”` : ""}</p>
      )}
    </section>
  );
}

function Queue() {
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("open"));
  const [state, setState] = useState<"open" | "resolved">("open");
  const [queue, setQueue] = useState("");
  const routing = useLoad(getRouting, []);
  const queues = routing.data?.queues ?? [];
  const { data, error, loading, reload } = useLoad(() => listHandoffs(state, queue || undefined), [state, queue]);
  return (
    <>
      <PageHeader title="Handoffs" subtitle="Conversations passed to a person, with everything they need to carry on.">
        <div role="group" aria-label="Filter by state" className="flex gap-1">
          {(["open", "resolved"] as const).map((s) => (
            <button key={s} aria-pressed={state === s} onClick={() => setState(s)}
              className={`rounded-lg px-3 py-1.5 text-sm ${state === s ? "bg-primary text-primary-text" : "border border-border hover:bg-border/40"}`}>{s === "open" ? "Open" : "Resolved"}</button>
          ))}
        </div>
        {queues.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-muted">Queue
            <select value={queue} onChange={(e) => setQueue(e.target.value)} className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-text">
              <option value="">All</option>
              {queues.map((q) => <option key={q.name} value={q.name}>{q.name}{q.open ? "" : " (closed)"}</option>)}
            </select>
          </label>)}
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <div>
          {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? <Empty>No {state} handoffs.</Empty> : (
            <ul className="space-y-2">{data.map((h: HandoffSummary) => (
              <li key={h.id}>
                <button onClick={() => setSelected(h.id)} aria-current={selected === h.id ? "true" : undefined}
                  className={`block w-full rounded-xl border bg-surface p-3 text-left text-sm hover:border-primary ${selected === h.id ? "border-primary" : "border-border"}`}>
                  <div className="flex items-center justify-between gap-2"><span className="font-medium">{triggerLabel[h.trigger] ?? h.trigger}</span><span className="text-xs text-muted">{formatTime(h.createdAt)}</span></div>
                  {(h.queue && queues.length > 1) || h.afterHours ? (
                    <div className="mt-1 flex gap-2 text-xs">
                      {h.queue && queues.length > 1 && <span className="rounded bg-border/60 px-1.5 py-0.5">{h.queue}</span>}
                      {h.afterHours && <span className="rounded bg-[var(--warn-bg)] px-1.5 py-0.5 text-[var(--warn)]">Arrived after hours</span>}
                    </div>) : null}
                  <p className="mt-1 line-clamp-2 text-muted">{h.summary}</p>
                </button>
              </li>))}
            </ul>
          )}
        </div>
        <div>{selected ? <Detail id={selected} onChanged={reload} /> : <Empty>Select a handoff to see its package.</Empty>}</div>
      </div>
    </>
  );
}

export default function Handoffs() {
  return <Suspense fallback={<Loading />}><Queue /></Suspense>;
}
