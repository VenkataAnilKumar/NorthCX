"use client";
import { useRef, useState } from "react";
import type { AutomationCatalog } from "@northcx/api-client";
import { NewKindFields } from "./StepFields";
import { addStep, hints, KIND_LABEL, moveStep, removeStep, summary, toGraph, updateStep, type Definition, type Step } from "./flow";

/** The routine as a line of cards: the trigger, then each step, joined by arrows. It edits the same definition the YAML view edits.
 *  Everything works from the keyboard: Up and Down move between cards, Alt+Up and Alt+Down reorder, Delete removes, Enter opens the card. A list view shows the same thing as plain text. */
export function FlowEditor({ value, onChange, catalog, readOnly = false }: { value: Definition; onChange: (d: Definition) => void; catalog: AutomationCatalog | null; readOnly?: boolean }) {
  const [selected, setSelected] = useState<string>("trigger");
  const [view, setView] = useState<"canvas" | "list">("canvas");
  const [add, setAdd] = useState("assistant");
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const graph = toGraph(value);
  const ids = graph.nodes.map((n) => n.id);
  const focusId = (id: string) => { setSelected(id); refs.current[id]?.focus(); };
  const onKey = (e: React.KeyboardEvent, id: string) => {
    const i = ids.indexOf(id);
    if (e.key === "ArrowDown" && !e.altKey && i < ids.length - 1) { e.preventDefault(); focusId(ids[i + 1]); }
    else if (e.key === "ArrowUp" && !e.altKey && i > 0) { e.preventDefault(); focusId(ids[i - 1]); }
    else if (!readOnly && id !== "trigger" && e.altKey && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); onChange(moveStep(value, id, e.key === "ArrowDown" ? 1 : -1)); setTimeout(() => refs.current[id]?.focus(), 0); }
    else if (!readOnly && id !== "trigger" && e.key === "Delete") { e.preventDefault(); const next = ids[Math.max(0, i - 1)]; onChange(removeStep(value, id)); setSelected(next); setTimeout(() => refs.current[next]?.focus(), 0); }
  };
  const step = value.steps.find((s) => s.id === selected);
  const problems = hints(value, catalog?.tools?.filter((t) => t.effect === "read").map((t) => t.name));
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <div className="seg" role="group" aria-label="View"><button aria-pressed={view === "canvas"} onClick={() => setView("canvas")}>Canvas</button><button aria-pressed={view === "list"} onClick={() => setView("list")}>List</button></div>
        {!readOnly && <><label className="ml-2">Add a step <select className="field ml-1" value={add} onChange={(e) => setAdd(e.target.value)}>{(catalog?.kinds ?? ["report", "assistant", "tool", "branch", "foreach", "simulate", "criteria", "alert", "person", "tag", "notify", "output"]).map((k) => <option key={k} value={k}>{KIND_LABEL[k] ?? k}</option>)}</select></label>
          <button className="btn" onClick={() => { const d = addStep(value, add, step?.id); const made = d.steps.find((s) => !value.steps.some((o) => o.id === s.id)); onChange(d); if (made) setSelected(made.id); }}>Add after {step ? `'${step.id}'` : "the last step"}</button></>}
        <span className="text-xs text-muted">Up and Down move between cards. Alt with Up or Down reorders. Delete removes the step.</span>
      </div>
      {problems.length > 0 && <ul className="mb-2 text-sm text-[var(--warn)]" aria-label="Things to fix">{problems.map((p) => <li key={p}>! {p}</li>)}</ul>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {view === "canvas" ? (
          <ol aria-label="Routine steps" className="flex flex-col items-stretch">
            {graph.nodes.map((n, i) => (
              <li key={n.id} className="flex flex-col items-center">
                {i > 0 && <svg width="20" height="26" aria-hidden="true" className="text-muted"><line x1="10" y1="0" x2="10" y2="20" stroke="currentColor" strokeWidth="2" /><polygon points="4,18 16,18 10,26" fill="currentColor" /></svg>}
                <button ref={(el) => { refs.current[n.id] = el; }} onClick={() => setSelected(n.id)} onKeyDown={(e) => onKey(e, n.id)} aria-pressed={selected === n.id} aria-label={`${i === 0 ? "Trigger" : `Step ${i}`}: ${KIND_LABEL[n.kind] ?? n.kind}. ${summary(n.kind, n.data)}`}
                  className={`glass w-full max-w-md rounded-xl border p-3 text-left ${selected === n.id ? "border-[var(--accent)]" : "border-border"}`}>
                  <span className="block text-xs text-muted">{i === 0 ? "Trigger" : `Step ${i} · ${n.id}`}</span>
                  <span className="block font-medium">{KIND_LABEL[n.kind] ?? n.kind}</span>
                  <span className="block truncate text-sm text-muted">{summary(n.kind, n.data)}</span>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <ol aria-label="Routine steps as a list" className="list-decimal space-y-1 pl-6 text-sm">
            {graph.nodes.map((n) => <li key={n.id}><button className="underline" onClick={() => setSelected(n.id)}>{KIND_LABEL[n.kind] ?? n.kind}</button> <span className="text-muted">({n.id}) {summary(n.kind, n.data)}</span></li>)}
          </ol>
        )}
        <div className="rounded-xl border border-border p-3" aria-live="polite">
          {selected === "trigger" ? <TriggerForm value={value} onChange={onChange} catalog={catalog} readOnly={readOnly} /> : step ? <StepForm key={step.id} step={step} catalog={catalog} readOnly={readOnly} onPatch={(p) => onChange(updateStep(value, step.id, p))}
            onMove={(d) => onChange(moveStep(value, step.id, d))} onRemove={() => { onChange(removeStep(value, step.id)); setSelected("trigger"); }} /> : <p className="text-sm text-muted">Choose a card to edit it.</p>}
        </div>
      </div>
    </div>
  );
}

function TriggerForm({ value, onChange, catalog, readOnly }: { value: Definition; onChange: (d: Definition) => void; catalog: AutomationCatalog | null; readOnly: boolean }) {
  const t = value.trigger;
  const set = (patch: Record<string, unknown>) => onChange({ ...value, trigger: { ...t, ...patch } });
  return (
    <div className="space-y-2 text-sm">
      <h3 className="font-semibold">Trigger</h3>
      <label className="block">Starts<select className="field mt-1 w-full" disabled={readOnly} value={t.type} onChange={(e) => onChange({ ...value, trigger: { type: e.target.value, ...(e.target.value === "schedule" ? { everyHours: 24 } : {}), ...(e.target.value === "event" ? { event: catalog?.events[0] ?? "" } : {}) } })}>
        {(catalog?.triggers ?? ["manual", "schedule", "webhook", "event"]).map((k) => <option key={k} value={k}>{KIND_LABEL[k] ?? k}</option>)}</select></label>
      <p className="text-xs text-muted">{catalog?.triggerInfo.find((i) => i.type === t.type)?.description}</p>
      {t.type === "schedule" && <label className="block">Every (hours)<input type="number" min={1} max={720} className="field mt-1 w-full" disabled={readOnly} value={t.everyHours ?? 24} onChange={(e) => set({ everyHours: Number(e.target.value) })} /></label>}
      {t.type === "event" && <label className="block">When this happens<select className="field mt-1 w-full" disabled={readOnly} value={t.event ?? ""} onChange={(e) => set({ event: e.target.value })}><option value="">Choose…</option>{(catalog?.events ?? []).map((k) => <option key={k}>{k}</option>)}</select></label>}
      {(t.type === "webhook" || t.type === "event") && <label className="block">Only when (optional), such as <code>input.priority == &apos;urgent&apos;</code>
        <input className="field mt-1 w-full" disabled={readOnly} value={typeof t.when === "string" ? t.when : ""} onChange={(e) => set({ when: e.target.value || undefined })} /></label>}
      <label className="block">Name<input className="field mt-1 w-full" disabled={readOnly} value={value.name ?? ""} onChange={(e) => onChange({ ...value, name: e.target.value })} /></label>
      <label className="block">Id<input className="field mt-1 w-full" disabled={readOnly} value={value.id ?? ""} onChange={(e) => onChange({ ...value, id: e.target.value })} /></label>
    </div>
  );
}

function StepForm({ step, catalog, onPatch, onMove, onRemove, readOnly }: { step: Step; catalog: AutomationCatalog | null; onPatch: (p: Record<string, unknown>) => void; onMove: (d: -1 | 1) => void; onRemove: () => void; readOnly: boolean }) {
  const str = (k: string) => (typeof step[k] === "string" ? (step[k] as string) : "");
  const pick = (k: string, options: string[]) => <select className="field mt-1 w-full" disabled={readOnly} value={str(k)} onChange={(e) => onPatch({ [k]: e.target.value })}><option value="">Choose…</option>{options.map((o) => <option key={o}>{o}</option>)}</select>;
  return (
    <div className="space-y-2 text-sm">
      <h3 className="font-semibold">{KIND_LABEL[step.kind] ?? step.kind} <span className="font-normal text-muted">({step.id})</span></h3>
      {step.kind === "report" && <><label className="block">Report{pick("report", catalog?.reports ?? [])}</label><label className="block">Days<input type="number" min={1} max={90} className="field mt-1 w-full" disabled={readOnly} value={Number(step.days ?? 7)} onChange={(e) => onPatch({ days: Number(e.target.value) })} /></label></>}
      {step.kind === "assistant" && <><label className="block">Staff assistant{pick("assistant", catalog?.assistants ?? [])}</label><label className="block">What to ask. <code>{"{{previous}}"}</code> is the step before, <code>{"{{input}}"}</code> is what the trigger sent.<textarea className="field mt-1 h-28 w-full" disabled={readOnly} value={str("prompt")} onChange={(e) => onPatch({ prompt: e.target.value })} /></label></>}
      {step.kind === "person" && <><label className="block">Question for the person<textarea className="field mt-1 h-20 w-full" disabled={readOnly} value={str("ask")} onChange={(e) => onPatch({ ask: e.target.value })} /></label><label className="block">Wait up to (hours)<input type="number" min={1} max={72} className="field mt-1 w-full" disabled={readOnly} value={Number(step.maxWaitHours ?? 24)} onChange={(e) => onPatch({ maxWaitHours: Number(e.target.value) })} /></label>
        <ApproverFields step={step} readOnly={readOnly} onPatch={onPatch} /></>}
      {step.kind === "tag" && <label className="block">Tag (saved as auto-…)<input className="field mt-1 w-full" disabled={readOnly} value={str("tag")} onChange={(e) => onPatch({ tag: e.target.value })} /></label>}
      {step.kind === "notify" && <label className="block">Send to{pick("to", catalog?.destinations ?? [])}</label>}
      {step.kind === "output" && <label className="block">Title. <code>{"{date}"}</code> becomes the day.<input className="field mt-1 w-full" disabled={readOnly} value={str("title")} onChange={(e) => onPatch({ title: e.target.value })} /></label>}
      <NewKindFields step={step} catalog={catalog} readOnly={readOnly} onPatch={onPatch} />
      {!readOnly && <div className="flex gap-2 pt-1"><button className="btn" onClick={() => onMove(-1)}>Move up</button><button className="btn" onClick={() => onMove(1)}>Move down</button><button className="btn" onClick={onRemove}>Remove</button></div>}
    </div>
  );
}

/** Who may answer a person step: anyone allowed to decide approvals, a role, or a team. */
function ApproverFields({ step, readOnly, onPatch }: { step: Step; readOnly: boolean; onPatch: (p: Record<string, unknown>) => void }) {
  const cur = (step.approver ?? null) as { role?: string; group?: string } | null;
  const kind = cur?.role !== undefined ? "role" : cur?.group !== undefined ? "group" : "any";
  const value = cur?.role ?? cur?.group ?? "";
  const set = (k: string, v: string) => onPatch({ approver: k === "any" ? undefined : { [k]: v } });
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <label className="block">Who may answer<select className="field mt-1 w-full" disabled={readOnly} value={kind} onChange={(e) => set(e.target.value, e.target.value === "role" ? "admin" : "")}><option value="any">Anyone who may decide approvals</option><option value="role">A role</option><option value="group">A team</option></select></label>
      {kind !== "any" && <label className="block">{kind === "role" ? "Role" : "Team name"}<input className="field mt-1 w-full" disabled={readOnly} value={value} onChange={(e) => set(kind, e.target.value)} /></label>}
    </div>
  );
}
