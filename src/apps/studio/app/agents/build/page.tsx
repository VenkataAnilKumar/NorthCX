"use client";
import Link from "next/link";
import { useState } from "react";
import { type AgentDraft, draftAgent, draftScenarios, refineAgent, type ScenarioDraft, transcribeRecording } from "@northcx/api-client";
import { ErrorBox, PageHeader } from "@northcx/ui";

type Src = { kind: "procedure" | "transcript"; name: string; text: string };
const input = "w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm";

export default function BuildAgent() {
  const [agentId, setAgentId] = useState("");
  const [goal, setGoal] = useState("");
  const [sources, setSources] = useState<Src[]>([{ kind: "procedure", name: "", text: "" }]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<AgentDraft | null>(null);
  const [copied, setCopied] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [changes, setChanges] = useState<string[] | null>(null);
  const [tests, setTests] = useState<ScenarioDraft | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const set = (i: number, p: Partial<Src>) => setSources((s) => s.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const ready = /^[A-Za-z0-9_.-]+$/.test(agentId) && goal.trim().length >= 10 && sources.some((s) => s.text.trim());

  async function load(i: number, f: File | undefined) {
    if (!f) return;
    if (f.size > 20000) { setErr(`${f.name} is longer than 20,000 characters; paste the relevant part instead.`); return; }
    set(i, { text: await f.text(), name: sources[i].name || f.name });
  }
  async function hear(i: number, f: File | undefined) {
    if (!f) return;
    setErr(null); setWorking("Transcribing the recording…");
    try { const r = await transcribeRecording(f); set(i, { kind: "transcript", text: r.text, name: sources[i].name || f.name }); }
    catch (x) { setErr((x as Error).message); } finally { setWorking(null); }
  }
  async function revise(e: React.FormEvent) {
    e.preventDefault(); if (!draft) return;
    setErr(null); setWorking("Revising…");
    try { const r = await refineAgent(draft.specYaml, instruction.trim()); setDraft({ ...draft, specYaml: r.specYaml, spec: r.spec, warnings: r.warnings, notes: r.notes }); setChanges(r.changes); setTests(null); setInstruction(""); }
    catch (x) { setErr((x as Error).message); } finally { setWorking(null); }
  }
  async function makeTests() {
    if (!draft) return;
    setErr(null); setWorking("Drafting tests…");
    try { setTests(await draftScenarios(draft.specYaml, draft.examples)); } catch (x) { setErr((x as Error).message); } finally { setWorking(null); }
  }
  async function go(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null); setDraft(null);
    try { setDraft(await draftAgent({ agentId, goal: goal.trim(), sources: sources.filter((s) => s.text.trim()).map((s) => ({ ...s, text: s.text.trim() })) })); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  return (
    <>
      <PageHeader title="Build an agent from your material" subtitle="Give it your procedures and transcripts of real conversations and the model drafts an agent for you to review. Nothing is saved or made live." />
      <form onSubmit={go} className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div><label htmlFor="aid" className="text-sm font-medium">Agent id</label><input id="aid" value={agentId} onChange={(e) => setAgentId(e.target.value)} placeholder="orders-bot" className={input} /></div>
          <div className="md:col-span-2"><label htmlFor="goal" className="text-sm font-medium">What is it for?</label><input id="goal" value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={2000} placeholder="Answer order status and return questions for our webshop" className={input} /></div>
        </div>
        {sources.map((s, i) => (
          <fieldset key={i} className="rounded-xl border border-border bg-surface p-3">
            <legend className="px-1 text-sm font-medium">Material {i + 1}</legend>
            <div className="flex flex-wrap gap-2">
              <label className="sr-only" htmlFor={`k${i}`}>Kind</label>
              <select id={`k${i}`} value={s.kind} onChange={(e) => set(i, { kind: e.target.value as Src["kind"] })} className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"><option value="procedure">Procedure or policy</option><option value="transcript">Conversation or call transcript</option></select>
              <label className="sr-only" htmlFor={`n${i}`}>Name</label>
              <input id={`n${i}`} value={s.name} onChange={(e) => set(i, { name: e.target.value })} maxLength={80} placeholder="Name (optional)" className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm" />
              <label className="text-sm text-primary underline"><input type="file" accept=".txt,.md,.vtt,.srt,text/plain" className="sr-only" onChange={(e) => load(i, e.target.files?.[0])} />Load a text file</label>
              <label className="text-sm text-primary underline"><input type="file" accept="audio/*,.mp3,.wav,.m4a,.ogg,.flac,.webm" className="sr-only" onChange={(e) => { void hear(i, e.target.files?.[0]); e.target.value = ""; }} />Transcribe a recording</label>
              {sources.length > 1 && <button type="button" onClick={() => setSources((x) => x.filter((_, j) => j !== i))} className="text-sm text-muted underline">Remove</button>}
            </div>
            <label className="sr-only" htmlFor={`t${i}`}>Text</label>
            <textarea id={`t${i}`} value={s.text} onChange={(e) => set(i, { text: e.target.value })} maxLength={20000} rows={6} className={`${input} mt-2 font-mono`} placeholder="Paste the text here (up to 20,000 characters)" />
          </fieldset>))}
        <p className="text-xs text-muted">Email addresses, phone numbers, card numbers and similar personal details are masked before anything is sent to the model. A recording is sent to the transcription service your administrator configured (if any) and comes back as text you can read and correct before drafting.</p>
        <div className="flex gap-2">
          {sources.length < 8 && <button type="button" onClick={() => setSources((x) => [...x, { kind: "procedure", name: "", text: "" }])} className="rounded-lg border border-border px-3 py-1.5 text-sm">Add more material</button>}
          <button disabled={!ready || busy} className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text disabled:opacity-50">{busy ? "Drafting…" : "Draft the agent"}</button>
        </div>
      </form>
      {working && <p role="status" className="mt-3 text-sm text-muted">{working}</p>}
      {err && <div className="mt-4"><ErrorBox message={err} /></div>}
      {draft && (
        <section aria-label="Draft" className="mt-6 space-y-4">
          {draft.warnings.length > 0 && <div role="status" className="rounded-xl border border-[var(--warn)] bg-[var(--warn-bg)] p-3 text-sm text-[var(--warn)]"><p className="font-medium">Check these</p><ul className="list-disc pl-5">{draft.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
          {draft.notes.length > 0 && <div className="rounded-xl border border-border bg-surface p-3 text-sm"><p className="font-medium">The model’s notes for you</p><ul className="list-disc pl-5">{draft.notes.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
          <div className="rounded-xl border border-border bg-surface p-3">
            <div className="flex items-center justify-between"><h2 className="font-medium">Draft definition</h2>
              <button type="button" onClick={async () => { await navigator.clipboard?.writeText(draft.specYaml); setCopied(true); }} className="text-sm text-primary underline">{copied ? "Copied" : "Copy"}</button></div>
            <pre className="mt-2 max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-xs">{draft.specYaml}</pre>
          </div>
          <form onSubmit={revise} className="rounded-xl border border-border bg-surface p-3 text-sm" aria-label="Change the draft">
            <label htmlFor="ins" className="font-medium">Change something</label>
            <div className="mt-1 flex gap-2"><input id="ins" value={instruction} onChange={(e) => setInstruction(e.target.value)} maxLength={1000} placeholder="Never promise delivery dates, and hand over anything about chargebacks" className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-1.5" />
              <button disabled={instruction.trim().length < 5 || !!working} className="rounded-lg border border-border px-3 py-1.5 disabled:opacity-50">Revise</button></div>
            {changes && <ul className="mt-2 list-disc pl-5 text-muted">{changes.map((c, i) => <li key={i}>{c}</li>)}</ul>}
          </form>
          <div className="rounded-xl border border-border bg-surface p-3 text-sm">
            <button type="button" onClick={makeTests} disabled={!!working} className="rounded-lg border border-border px-3 py-1.5 disabled:opacity-50">Draft test scenarios</button>
            {tests && <div className="mt-2 space-y-2"><p className="text-muted">{tests.note}</p>
              {tests.warnings.length > 0 && <ul className="list-disc pl-5 text-[var(--warn)]">{tests.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
              <p>Checked against the draft: {tests.checked.length ? tests.checked.join(", ") : "none"}. Need a live model: {tests.needLiveModel.length ? tests.needLiveModel.length : "none"}.</p>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-xs">{tests.scenariosYaml}</pre></div>}
          </div>
          {draft.examples.length > 0 && <div className="rounded-xl border border-border bg-surface p-3 text-sm"><p className="font-medium">Typical questions seen (use them to write test scenarios)</p><ul className="list-disc pl-5">{draft.examples.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
          <p className="text-sm text-muted">{draft.note} Next: <Link href="/agents" className="text-primary underline">Agents</Link> → create a version with this definition, add scenarios, and release it through the usual checks.</p>
        </section>)}
    </>
  );
}
