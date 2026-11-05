"use client";
import { useState } from "react";
import { createScenario, draftJourney, type Journey, journeyScenarios } from "@northcx/api-client";

const input = "w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-sm";
const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);

function One({ agent, j, tools, onChange, onRemove }: { agent: string; j: Journey; tools: string[]; onChange: (j: Journey) => void; onRemove: () => void }) {
  const [msg, setMsg] = useState<string | null>(null);
  const set = (patch: Partial<Journey>) => onChange({ ...j, ...patch });
  const setStep = (i: number, patch: Record<string, unknown>) => set({ steps: j.steps.map((s, k) => (k === i ? { ...s, ...patch } : s)) });
  async function makeTests() {
    setMsg(null);
    try {
      const { scenarios } = await journeyScenarios(agent, j);
      for (const s of scenarios) await createScenario({ scenario: s });
      setMsg(`Saved ${scenarios.length} test scenario${scenarios.length === 1 ? "" : "s"} (not required to pass yet). Run them on the Simulations page with a live model.`);
    } catch (e) { setMsg((e as Error).message); }
  }
  return (
    <div className="space-y-2 rounded-lg border border-border p-3 text-sm">
      <div className="flex gap-2"><code className="self-center">{j.name}</code>
        <select aria-label={`How strictly for ${j.name}`} value={j.flexibility ?? "guided"} onChange={(e) => set({ flexibility: e.target.value })} className="rounded border border-border bg-bg px-1 py-0.5">
          <option value="strict">strict: steps enforced</option><option value="guided">guided</option><option value="free">free</option></select>
        <button type="button" onClick={onRemove} className="ml-auto rounded-lg border border-border px-2 hover:bg-border/40">Remove</button></div>
      <label className="block">Goal<input value={j.goal} onChange={(e) => set({ goal: e.target.value })} className={input} /></label>
      <label className="block">When it applies<input value={j.when ?? ""} onChange={(e) => set({ when: e.target.value })} className={input} /></label>
      <fieldset className="space-y-1"><legend className="font-medium">Steps</legend>
        {j.steps.map((s, i) => (
          <div key={i} className="flex flex-wrap gap-2">
            <input aria-label={`Step ${i + 1}`} value={s.purpose} onChange={(e) => setStep(i, { purpose: e.target.value })} className={`${input} flex-1`} />
            <select aria-label={`Tool for step ${i + 1}`} value={s.tool ?? ""} onChange={(e) => setStep(i, { tool: e.target.value || null })} className="rounded border border-border bg-bg px-1">
              <option value="">no tool</option>{tools.map((t) => <option key={t}>{t}</option>)}</select>
            <label><input type="checkbox" checked={s.required !== false} onChange={(e) => setStep(i, { required: e.target.checked })} /> required</label>
            <button type="button" aria-label={`Remove step ${i + 1}`} onClick={() => set({ steps: j.steps.filter((_, k) => k !== i) })} className="rounded-lg border border-border px-2">×</button>
          </div>))}
        <button type="button" onClick={() => set({ steps: [...j.steps, { purpose: "New step", required: true }] })} className="rounded-lg border border-border px-3 py-1">Add step</button>
      </fieldset>
      <label className="block">Rules, one per line<textarea value={(j.rules ?? []).join("\n")} onChange={(e) => set({ rules: lines(e.target.value) })} rows={2} className={input} /></label>
      <label className="block">Hand over to a person if, one per line<textarea value={(j.handoff_if ?? []).join("\n")} onChange={(e) => set({ handoff_if: lines(e.target.value) })} rows={2} className={input} /></label>
      <label className="block">Done when these tools have run<select multiple value={j.done_when ?? []} onChange={(e) => set({ done_when: Array.from(e.target.selectedOptions).map((o) => o.value) })} className={input}>
        {tools.map((t) => <option key={t}>{t}</option>)}</select></label>
      <label className="block">Example opening messages, one per line (used for tests)<textarea value={(j.samples ?? []).join("\n")} onChange={(e) => set({ samples: lines(e.target.value).slice(0, 3) })} rows={2} className={input} /></label>
      <button type="button" onClick={() => void makeTests()} className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Create test scenarios</button>
      {msg && <p role="status" className="text-xs text-muted">{msg}</p>}
    </div>
  );
}

export function JourneyEditor({ agent, journeys, tools, onChange }: { agent: string; journeys: Journey[]; tools: string[]; onChange: (j: Journey[]) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  async function draft() {
    setBusy(true); setNote(null);
    try {
      const r = await draftJourney(agent, text);
      if (journeys.some((j) => j.name === r.journey.name)) r.journey.name = `${r.journey.name}-2`.slice(0, 40);
      onChange([...journeys, r.journey]);
      setText("");
      setNote({ ok: true, text: ["Drafted. Read it through and fix anything wrong before saving a version.", ...r.warnings].join(" ") });
    } catch (e) { setNote({ ok: false, text: (e as Error).message }); }
    finally { setBusy(false); }
  }
  return (
    <>
      {journeys.map((j, i) => <One key={j.name + i} agent={agent} j={j} tools={tools} onChange={(n) => onChange(journeys.map((x, k) => (k === i ? n : x)))} onRemove={() => onChange(journeys.filter((_, k) => k !== i))} />)}
      <div className="space-y-2">
        <label className="block text-sm">Describe a journey in plain words
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="When a customer wants a refund, find their order, check it was delivered, then refund it. If they mention a lawyer, hand over to a person." className={input} /></label>
        <button type="button" disabled={busy || text.trim().length < 10} onClick={() => void draft()} className="rounded-lg bg-primary px-3 py-1.5 text-sm text-primary-text disabled:opacity-50">{busy ? "Drafting…" : "Draft a journey"}</button>
        <button type="button" onClick={() => onChange([...journeys, { name: `journey-${journeys.length + 1}`, goal: "Describe the goal", steps: [{ purpose: "First step", required: true }], flexibility: "guided" }])}
          className="ml-2 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40">Start from blank</button>
        {note && <p role={note.ok ? "status" : "alert"} className={`text-sm ${note.ok ? "text-muted" : "text-[var(--bad)]"}`}>{note.text}</p>}
      </div>
    </>
  );
}
