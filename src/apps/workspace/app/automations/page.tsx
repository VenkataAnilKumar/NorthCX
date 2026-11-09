"use client";
import { useState } from "react";
import { automation, automationAction, automationRuns, automations, createAutomation, reviseAutomation, setAutomationsEnabled, useLoad, useMe, type Automation, type AutoRun } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const STARTER = `id: morning-brief
name: Morning brief
description: A short briefing at the start of each day.
trigger: {type: schedule, everyHours: 24}
limits: {maxSeconds: 120}
steps:
  - {id: figures, kind: report, report: performance, days: 1}
  - id: write
    kind: assistant
    assistant: shift-briefing
    prompt: "Write a briefing of a few lines from this: {{previous}}"
`;
const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleString() : "never");
const LABEL: Record<string, string> = { draft: "Draft", proposed: "Waiting for a second person", published: "Published", rejected: "Rejected", superseded: "Replaced", retired: "Retired" };

function Runs({ id }: { id: string }) {
  const { data, loading, reload } = useLoad(() => automationRuns(id), [id]);
  if (loading && !data) return <Loading />;
  if (!data?.length) return <Empty>No runs yet.</Empty>;
  return (
    <div className="space-y-2 text-sm">
      <button className="btn" onClick={reload}>Refresh</button>
      {data.map((r: AutoRun) => (
        <details key={r.id} className="rounded-xl border border-border p-2"><summary className="cursor-pointer"><strong>{r.status}</strong> · {r.trigger} · {when(r.startedAt)} · by {r.by}</summary>
          {r.error && <p className="mt-1 text-[var(--bad)]">{r.error}</p>}
          <ol className="mt-1 list-decimal pl-5">{r.steps.map((s) => <li key={s.id}>{s.id} ({s.kind}): {s.status}{s.error ? ` — ${s.error}` : ""}{s.output ? <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-xs">{s.output}</pre> : null}</li>)}</ol>
          {r.outcome && <p className="mt-1"><strong>Result:</strong> {r.outcome}</p>}</details>
      ))}
    </div>
  );
}

export default function Page() {
  const { can } = useMe();
  const { data, error, loading, reload } = useLoad(() => automations());
  const [text, setText] = useState(STARTER);
  const [editing, setEditing] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = async (f: () => Promise<unknown>, ok?: string) => { setErr(null); setNote(null); try { await f(); if (ok) setNote(ok); reload(); } catch (e) { setErr((e as Error).message); } };
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const list = data!.automations;
  return (
    <>
      <PageHeader title="Automations" subtitle="Routines that run by themselves. In this release a step is a staff assistant (read-only) or a built-in report; nothing is sent to customers or outside systems. A second person approves each routine before it runs." />
      {!data!.enabled && <p role="alert" className="mb-3 rounded-xl border border-border p-3 text-sm">All routines are stopped for your organization. {can("keys:manage") && <button className="btn ml-2" onClick={() => void go(() => setAutomationsEnabled(true))}>Turn them back on</button>}</p>}
      {can("keys:manage") && data!.enabled && <p className="mb-3 text-xs"><button className="underline" onClick={() => { if (confirm("Stop every routine in the organization? Running ones stop at their next step.")) void go(() => setAutomationsEnabled(false)); }}>Stop all routines</button></p>}
      {note && <p className="mb-2 text-sm" role="status">{note}</p>}{err && <div className="mb-3"><ErrorBox message={err} /></div>}
      {list.length === 0 ? <Empty>No routines yet. Write one below.</Empty> : (
        <ul className="mb-6 space-y-3">
          {list.map((a: Automation) => (
            <li key={a.id} className="glass p-4">
              <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="font-semibold">{a.name} <span className="text-xs font-normal text-muted">{a.id} · version {a.version}</span></h2>
                <span className="pill">{a.paused ? "Paused" : LABEL[a.status]}</span></div>
              <p className="mt-1 text-xs text-muted">Starts by {a.trigger.type}{a.trigger.everyHours ? ` every ${a.trigger.everyHours} h` : ""} · {a.steps} step{a.steps === 1 ? "" : "s"} · next {when(a.nextRun)} · last run {a.lastRun ? `${a.lastRun.status}, ${when(a.lastRun.startedAt)}` : "never"}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button className="btn" onClick={() => setOpen(open === a.id ? null : a.id)}>{open === a.id ? "Hide runs" : "Runs"}</button>
                <button className="btn" onClick={() => void go(async () => { const full = await automation(a.id); setText(full.yaml ?? ""); setEditing(a.id); })}>Edit</button>
                {a.status === "draft" && <button className="btn" disabled={!can("versions:create")} onClick={() => void go(() => automationAction(a.id, "propose"), "Proposed. A second person must approve it.")}>Propose</button>}
                {a.status === "proposed" && <><button className="btn btn-primary" disabled={!can("releases:publish")} onClick={() => void go(() => automationAction(a.id, "approve"), "Published.")}>Approve (not the proposer)</button><button className="btn" disabled={!can("releases:publish")} onClick={() => void go(() => automationAction(a.id, "reject"))}>Reject</button></>}
                {a.status === "published" && <>
                  <button className="btn btn-primary" disabled={!can("automations:run") || a.paused} onClick={() => void go(() => automationAction(a.id, "run"), "Started. Open Runs to follow it.")}>Run now</button>
                  <button className="btn" disabled={!can("releases:publish")} onClick={() => void go(() => automationAction(a.id, a.paused ? "resume" : "pause"))}>{a.paused ? "Resume" : "Pause"}</button>
                  <button className="btn" disabled={!can("releases:publish")} onClick={() => { if (confirm("Retire this routine?")) void go(() => automationAction(a.id, "retire")); }}>Retire</button></>}
              </div>
              {open === a.id && <div className="mt-3"><Runs id={a.id} /></div>}
            </li>
          ))}
        </ul>
      )}
      <GlassCard title={editing ? `Editor: ${editing}` : "New routine"}>
        <label className="text-sm">Routine (YAML). Steps run in order; <code>{"{{previous}}"}</code> is the step before, <code>{"{{input}}"}</code> is what the trigger sent. Both reach the assistant as marked data, never as instructions.
          <textarea className="field mt-1 h-64 w-full font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} /></label>
        <div className="mt-2 flex gap-2">
          <button className="btn btn-primary" disabled={!can("versions:create")} onClick={() => void go(async () => { if (editing) await reviseAutomation(editing, text); else { const r = await createAutomation(text); if (r.webhookSecret) setNote(`Saved. Webhook secret (shown once): ${r.webhookSecret}`); } }, editing ? "Saved." : undefined)}>{editing ? "Save changes" : "Save as draft"}</button>
          {editing && <button className="btn" onClick={() => { setEditing(null); setText(STARTER); }}>Start a new one</button>}
        </div>
      </GlassCard>
    </>
  );
}
