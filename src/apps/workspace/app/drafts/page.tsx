"use client";
import { useState } from "react";
import { decideShadowDraft, formatTime, getShadowSummary, listShadowDrafts, SHADOW_REASONS, type ShadowDraft, type ShadowState, type ShadowSummary, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, StatusBadge } from "@northcx/ui";

const TABS: [ShadowState, string][] = [["pending", "Waiting"], ["sent", "Sent"], ["edited", "Edited"], ["rejected", "Rejected"], ["expired", "Expired"]];
const REASON: Record<string, string> = { wrong: "It is wrong", tone: "The tone is off", incomplete: "It leaves something out", unsafe: "It is not safe to send", other: "Another reason" };

function Summary({ s }: { s: ShadowSummary }) {
  const pct = s.agreement.value === null ? null : Math.round(s.agreement.value * 100);
  return (
    <p className="mb-4 rounded-xl border border-border bg-surface p-3 text-sm" role="status">
      {s.decided === 0 ? `No drafts have been decided in the last ${s.days} days.` : (
        <>Last {s.days} days: {s.decided} drafts decided. You sent <b>{s.sent}</b> unchanged ({pct}%), edited <b>{s.edited}</b>, rejected <b>{s.rejected}</b>; <b>{s.expired}</b> expired.</>)}{" "}
      <span className="text-muted">{s.note}</span>
    </p>
  );
}

function Card({ d, onDone }: { d: ShadowDraft; onDone: () => void }) {
  const { askForName, me, can } = useMe();
  const [text, setText] = useState(d.draft);
  const [reasons, setReasons] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const may = can("shadow:review");
  const changed = text.trim() !== d.draft.trim();
  const decide = async (action: "send" | "edit" | "reject") => {
    setBusy(true); setErr(null);
    try {
      await decideShadowDraft(d.id, { action, ...(action === "edit" ? { text } : {}), ...(reasons.length ? { reasons } : {}), ...(note ? { note } : {}), ...(askForName ? {} : { by: me?.name }) });
      onDone();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <GlassCard title={`${d.agentId} · ${formatTime(d.createdAt)}`} action={<StatusBadge status={d.state} />}>
      <p className="text-xs text-muted">The customer wrote</p>
      <blockquote className="mb-3 whitespace-pre-wrap border-l-2 border-border pl-3 text-sm">{d.customerMessage}</blockquote>
      {d.state === "pending" ? (
        <>
          <label className="block text-sm">The agent's reply, to send or change<textarea className="field mt-1 min-h-28 w-full" value={text} onChange={(e) => setText(e.target.value)} /></label>
          <fieldset className="mt-3 text-sm"><legend className="text-muted">Why change or reject it? (optional)</legend>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">{SHADOW_REASONS.map((r) => (
              <label key={r} className="inline-flex items-center gap-1"><input type="checkbox" checked={reasons.includes(r)} onChange={(e) => setReasons(e.target.checked ? [...reasons, r] : reasons.filter((x) => x !== r))} />{REASON[r]}</label>))}</div>
          </fieldset>
          <label className="mt-3 block text-sm">Note (optional)<input className="field mt-1" value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn btn-primary" disabled={busy || !may || !text.trim()} onClick={() => decide(changed ? "edit" : "send")}>{changed ? "Send my edit" : "Send as is"}</button>
            <button className="btn btn-danger" disabled={busy || !may} onClick={() => decide("reject")}>Reject: send nothing</button>
          </div>
          {!may && <p className="mt-2 text-xs text-muted">Your role cannot review drafts. Ask someone with the reviewer role.</p>}
          {err && <div className="mt-2"><ErrorBox message={err} /></div>}
        </>
      ) : (
        <>
          <p className="text-xs text-muted">The agent wrote</p>
          <p className="mb-2 whitespace-pre-wrap text-sm">{d.draft}</p>
          {d.finalText && d.finalText !== d.draft && (<><p className="text-xs text-muted">Sent instead</p><p className="whitespace-pre-wrap text-sm">{d.finalText}</p></>)}
          <p className="mt-2 text-xs text-muted">{d.decidedBy ? `Decided by ${d.decidedBy}` : "Nobody decided it in time; the conversation went to a person"}{d.reasons.length ? ` · ${d.reasons.map((r) => REASON[r] ?? r).join(", ")}` : ""}{d.note ? ` · ${d.note}` : ""}</p>
        </>
      )}
    </GlassCard>
  );
}

export default function Drafts() {
  const [state, setState] = useState<ShadowState>("pending");
  const list = useLoad(() => listShadowDrafts(state), [state]);
  const summary = useLoad(() => getShadowSummary(30), []);
  const reload = () => { list.reload(); summary.reload(); };
  return (
    <>
      <PageHeader title="Drafts" subtitle="Replies the agent wrote in shadow mode. Nothing reaches the customer until you send it." />
      {summary.data && <Summary s={summary.data} />}
      <div className="mb-3 inline-flex gap-1 rounded-xl border border-border p-1" role="tablist" aria-label="State">
        {TABS.map(([s, label]) => <button key={s} role="tab" aria-selected={state === s} onClick={() => setState(s)} className={`rounded-lg px-3 py-1 text-sm ${state === s ? "bg-primary text-primary-text" : ""}`}>{label}</button>)}
      </div>
      {list.loading && !list.data ? <Loading /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> : list.data && list.data.length === 0
        ? <Empty>{state === "pending" ? "No drafts are waiting. When an agent in shadow mode answers a customer, its reply appears here." : `No ${TABS.find((t) => t[0] === state)?.[1].toLowerCase()} drafts.`}</Empty>
        : <ul className="grid gap-4 lg:grid-cols-2">{list.data?.map((d) => <li key={d.id}><Card d={d} onDone={reload} /></li>)}</ul>}
    </>
  );
}
