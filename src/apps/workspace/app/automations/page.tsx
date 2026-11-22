"use client";
import { useState } from "react";
import { FlowEditor } from "../../components/FlowEditor";
import type { Definition } from "../../components/flow";
import { automationCatalog, convertAutomation, draftAutomation, type AutomationDraft } from "@northcx/api-client";
import { decideRun, waitingRuns, automation, automationAction, automationRuns, automations, createAutomation, reviseAutomation, setAutomationsEnabled, useLoad, useMe, type Automation, type AutoRun } from "@northcx/api-client";
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
const DIGEST = `id: weekly-digest
name: Weekly digest
description: A weekly summary of how the team and the agents did, saved to Outputs.
trigger: {type: schedule, everyHours: 168}
limits: {maxSeconds: 180}
steps:
  - {id: team, kind: report, report: performance, days: 7}
  - {id: quality, kind: report, report: quality, days: 7}
  - id: write
    kind: assistant
    assistant: shift-briefing
    prompt: "Write a short weekly digest for the team lead from these figures: {{previous}}"
  - {id: keep, kind: output, title: "Weekly digest {date}"}
`;
const EVENT = `id: note-handoffs
name: Note new hand-offs
description: When a conversation is handed to a person, write a one-line note.
trigger: {type: event, event: handoff.created}
steps:
  - id: note
    kind: assistant
    assistant: shift-briefing
    prompt: "Write one line about this event: {{input}}"
  - {id: keep, kind: output, title: "Hand-off note {date}"}
`;
const REVIEWED = `id: reviewed-digest
name: Reviewed digest
description: Writes the weekly digest, asks a person to approve it, then sends it to a destination the administrator set up.
trigger: {type: schedule, everyHours: 168}
steps:
  - {id: team, kind: report, report: performance, days: 7}
  - id: write
    kind: assistant
    assistant: shift-briefing
    prompt: "Write a short weekly digest from these figures: {{previous}}"
  - {id: approve, kind: person, ask: "Is this digest ready to send?", maxWaitHours: 24}
  - {id: send, kind: notify, to: ops-chat}
  - {id: keep, kind: output, title: "Weekly digest {date}"}
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
  const waiting = useLoad(() => waitingRuns().catch(() => [] as AutoRun[]));
  const [text, setText] = useState(STARTER);
  const [editing, setEditing] = useState<string | null>(null);
  const [mode, setMode] = useState<"canvas" | "yaml" | "describe">("yaml");
  const [def, setDef] = useState<Definition | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [wish, setWish] = useState("");
  const [drafted, setDrafted] = useState<AutomationDraft | null>(null);
  const catalog = useLoad(() => automationCatalog().catch(() => null));
  // the two views edit one routine: moving between them converts through the server, which also reports what is wrong
  const toCanvas = async () => { const r = await convertAutomation(text); setDef(r.definition as unknown as Definition); setProblems(r.problems); setMode("canvas"); };
  const toYaml = async () => { if (def) { const r = await convertAutomation(def); setText(r.yaml); setProblems(r.problems); } setMode("yaml"); };
  const load = (yaml: string) => { setText(yaml); setDef(null); setDrafted(null); if (mode === "canvas") void convertAutomation(yaml).then((r) => setDef(r.definition as unknown as Definition)); };
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = async (f: () => Promise<unknown>, ok?: string) => { setErr(null); setNote(null); try { await f(); if (ok) setNote(ok); reload(); } catch (e) { setErr((e as Error).message); } };
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const list = data!.automations;
  return (
    <>
      <PageHeader title="Automations" subtitle="Routines that run by themselves. A step can ask a staff assistant (read-only), get a report, call a tool, check a condition, go through a list, check an agent, judge conversations, raise an alert, ask a person, tag a conversation, send a result to a destination your administrator set up, or save it to Outputs. Anything that changes something or sends something out comes after a step that asks a person. Nothing is ever sent to customers. A routine starts by hand, on a schedule, by a signed webhook, or when an event happens. A second person approves each routine before it runs." />
      {!data!.enabled && <p role="alert" className="mb-3 rounded-xl border border-border p-3 text-sm">All routines are stopped for your organization. {can("keys:manage") && <button className="btn ml-2" onClick={() => void go(() => setAutomationsEnabled(true))}>Turn them back on</button>}</p>}
      {can("keys:manage") && data!.enabled && <p className="mb-3 text-xs"><button className="underline" onClick={() => { if (confirm("Stop every routine in the organization? Running ones stop at their next step.")) void go(() => setAutomationsEnabled(false)); }}>Stop all routines</button></p>}
      {note && <p className="mb-2 text-sm" role="status">{note}</p>}{err && <div className="mb-3"><ErrorBox message={err} /></div>}
      {(waiting.data ?? []).length > 0 && (
        <GlassCard title="Waiting for a person" className="mb-4">
          <ul className="space-y-3 text-sm">{waiting.data!.map((r) => (
            <li key={r.id} className="rounded-xl border border-border p-3"><strong>{r.automationId}</strong> · started by {r.by} · answer by {when(r.waiting?.until ?? null)}
              <p className="mt-1">{r.waiting?.ask}</p>{r.waiting?.preview && <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-xs">{r.waiting.preview}</pre>}
              <div className="mt-2 flex gap-2"><button className="btn btn-primary" disabled={!can("approvals:decide")} onClick={() => void go(async () => { await decideRun(r.id, true); waiting.reload(); }, "Approved. The routine carries on.")}>Approve</button>
                <button className="btn" disabled={!can("approvals:decide")} onClick={() => void go(async () => { await decideRun(r.id, false); waiting.reload(); }, "Refused. The routine stopped.")}>Refuse</button></div>
              {r.by && <p className="mt-1 text-xs text-muted">You cannot answer a run you started yourself.</p>}</li>))}</ul>
        </GlassCard>)}
      {list.length === 0 ? <Empty>No routines yet. Write one below.</Empty> : (
        <ul className="mb-6 space-y-3">
          {list.map((a: Automation) => (
            <li key={a.id} className="glass p-4">
              <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="font-semibold">{a.name} <span className="text-xs font-normal text-muted">{a.id} · version {a.version}</span></h2>
                <span className="pill">{a.paused ? "Paused" : LABEL[a.status]}</span></div>
              <p className="mt-1 text-xs text-muted">Starts by {a.trigger.type}{a.trigger.everyHours ? ` every ${a.trigger.everyHours} h` : ""} · {a.steps} step{a.steps === 1 ? "" : "s"} · next {when(a.nextRun)} · last run {a.lastRun ? `${a.lastRun.status}, ${when(a.lastRun.startedAt)}` : "never"}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button className="btn" onClick={() => setOpen(open === a.id ? null : a.id)}>{open === a.id ? "Hide runs" : "Runs"}</button>
                <button className="btn" onClick={() => void go(async () => { const full = await automation(a.id); setText(full.yaml ?? ""); setDef(null); setMode("yaml"); setEditing(a.id); })}>Edit</button>
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
        <div className="seg mb-3" role="group" aria-label="How to edit">
          <button aria-pressed={mode === "describe"} onClick={() => setMode("describe")}>Describe it</button>
          <button aria-pressed={mode === "canvas"} onClick={() => void go(toCanvas)}>Canvas</button>
          <button aria-pressed={mode === "yaml"} onClick={() => void go(toYaml)}>YAML</button>
        </div>
        {mode === "describe" && (
          <div className="text-sm">
            <label>Say what you want in your own words. The assistant drafts a routine; nothing is saved until you save it, and a second person must approve it before it runs.
              <textarea className="field mt-1 h-24 w-full" maxLength={1500} value={wish} onChange={(e) => setWish(e.target.value)} placeholder="Every Monday morning, get last week's figures, have the briefing assistant write them up, ask a lead to check it, then keep it in Outputs." /></label>
            <button className="btn btn-primary mt-2" disabled={wish.trim().length < 10} onClick={() => void go(async () => { const r = await draftAutomation(wish); setDrafted(r); if (r.definition && r.yaml) { setText(r.yaml); setDef(r.definition as unknown as Definition); } })}>Draft it</button>
            {drafted && (
              <div className="mt-3 rounded-xl border border-border p-3">
                {drafted.problems.length > 0 && <ul className="text-[var(--bad)]">{drafted.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
                {drafted.dryRun && <><p className="font-medium">Starts {drafted.dryRun.startsWhen}. {drafted.dryRun.canRun ? "It could run." : "It cannot run yet."}{drafted.dryRun.needsApproval ? " A person is asked first." : ""}{drafted.dryRun.sendsOut ? " It sends a result out." : ""}</p>
                  <ol className="mt-1 list-decimal pl-5">{drafted.dryRun.steps.map((s) => <li key={s.id}>{s.does}{s.problem && <span className="text-[var(--bad)]"> — {s.problem}</span>}</li>)}</ol>
                  <p className="mt-2 text-xs text-muted">{drafted.note}</p>
                  <div className="mt-2 flex gap-2"><button className="btn" onClick={() => void go(toCanvas)}>Open in the canvas</button><button className="btn" onClick={() => setMode("yaml")}>Open as YAML</button></div></>}
              </div>)}
          </div>)}
        {mode === "canvas" && def && <FlowEditor value={def} onChange={setDef} catalog={catalog.data ?? null} />}
        {mode === "yaml" && (
          <label className="text-sm">Routine (YAML). Steps run in order; <code>{"{{previous}}"}</code> is the step before, <code>{"{{input}}"}</code> is what the trigger sent. Both reach the assistant as marked data, never as instructions.
            <textarea className="field mt-1 h-64 w-full font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} /></label>)}
        {problems.length > 0 && mode !== "describe" && <ul className="mt-2 text-sm text-[var(--warn)]" aria-label="Checks">{problems.map((p) => <li key={p}>! {p}</li>)}</ul>}
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn btn-primary" disabled={!can("versions:create")} onClick={() => void go(async () => {
            const body = mode === "canvas" && def ? def : text;
            if (editing) await reviseAutomation(editing, body); else { const r = await createAutomation(body); if (r.webhookSecret) setNote(`Saved. Webhook secret (shown once): ${r.webhookSecret}`); }
          }, editing ? "Saved." : undefined)}>{editing ? "Save changes" : "Save as draft"}</button>
          {editing && <button className="btn" onClick={() => { setEditing(null); load(STARTER); }}>Start a new one</button>}
          {!editing && <><button className="btn" onClick={() => load(DIGEST)}>Weekly digest example</button><button className="btn" onClick={() => load(EVENT)}>On an event example</button><button className="btn" onClick={() => load(REVIEWED)}>With approval example</button></>}
        </div>
      </GlassCard>
    </>
  );
}
