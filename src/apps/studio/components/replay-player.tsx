"use client";
import { useEffect, useState } from "react";
import { type Rerun, rerunTurn } from "@northcx/api-client";
import { ErrorBox, StatusBadge } from "@northcx/ui";
import { plainSteps, toolCards } from "@/lib/console-steps";
import { conversationAt, type Frame } from "@/lib/replay";

const STEP_MS = 900;

function RerunPanel({ sessionId, turn, message, original, onClose }: { sessionId: string; turn: number; message: string; original: string | null; onClose: () => void }) {
  const [text, setText] = useState(message);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [out, setOut] = useState<Rerun | null>(null);
  async function go() {
    setBusy(true); setErr(null);
    try { setOut(await rerunTurn(sessionId, turn, text.trim())); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div role="group" aria-label={`Edit and run again: message ${turn}`} className="mt-2 rounded-lg border border-border bg-bg p-3 text-sm">
      <label className="block">What the customer would say instead<textarea className="field mt-1 min-h-20 w-full" value={text} onChange={(e) => setText(e.target.value)} /></label>
      <div className="mt-2 flex gap-2">
        <button className="btn btn-primary" disabled={busy || !text.trim()} onClick={go}>{busy ? "Running…" : "Run again"}</button>
        <button className="btn" onClick={onClose}>Close</button>
      </div>
      <p className="mt-1 text-xs text-muted">Nothing is saved or sent, and actions are only simulated.</p>
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}
      {out && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2" aria-label="Result">
          <div><h4 className="text-xs font-medium text-muted">What happened</h4><p className="whitespace-pre-wrap">{original ?? "No reply was recorded."}</p></div>
          <div>
            <h4 className="text-xs font-medium text-muted">What would happen now <StatusBadge status={out.rerun.status} /></h4>
            <p className="whitespace-pre-wrap">{out.rerun.reply || "(no reply)"}</p>
            {toolCards(out.rerun.events).map((c, i) => <p key={i} className="mt-1 text-xs text-muted">Used {c.label} ({c.input}){c.outcome === "done" ? `: ${c.detail}` : c.outcome === "held" ? `: held for a person (${c.detail})` : ""}</p>)}
            <details className="mt-2"><summary className="cursor-pointer text-xs text-muted">Steps</summary>
              <ol className="mt-1 list-decimal space-y-1 pl-5 text-xs">{plainSteps(out.rerun.events).map((s, i) => <li key={i}>{s}</li>)}</ol></details>
          </div>
          <p className="text-xs text-muted sm:col-span-2">{out.note}</p>
        </div>
      )}
    </div>
  );
}

/** Steps through a stored conversation. Reading only: nothing here calls the agent except the Edit and run again button, which uses a sandbox. */
export function ReplayPlayer({ sessionId, frames, originals, canRerun }: { sessionId: string; frames: Frame[]; originals: Record<number, string | null>; canRerun: boolean }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const last = frames.length - 1;
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setIndex((i) => { if (i >= last) { setPlaying(false); return i; } return i + 1; }), STEP_MS);
    return () => clearInterval(id);
  }, [playing, last]);
  if (!frames.length) return <p className="text-sm text-muted">This conversation has no steps to replay.</p>;
  const lines = conversationAt(frames, index);
  const here = frames[index];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section aria-label="Conversation so far" className="rounded-xl border border-border bg-surface p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Replay controls">
          <button className="btn" disabled={index === 0} onClick={() => { setPlaying(false); setIndex(index - 1); }}>Previous</button>
          <button className="btn btn-primary" onClick={() => { if (!playing && index >= last) setIndex(0); setPlaying(!playing); }}>{playing ? "Pause" : "Play"}</button>
          <button className="btn" disabled={index >= last} onClick={() => { setPlaying(false); setIndex(index + 1); }}>Next</button>
          <label className="flex flex-1 items-center gap-2 text-sm">Step
            <input type="range" min={0} max={last} value={index} onChange={(e) => { setPlaying(false); setIndex(Number(e.target.value)); }} aria-valuetext={`Step ${index + 1} of ${frames.length}`} className="flex-1" /></label>
          <span className="text-sm text-muted" role="status">Step {index + 1} of {frames.length}</span>
        </div>
        <div className="space-y-2" aria-live="polite">
          {lines.map((l, i) => l.kind === "customer" ? (
            <div key={i}>
              <div className="ml-auto max-w-[85%] rounded-xl bg-primary px-3 py-2 text-sm text-primary-text">
                <p className="whitespace-pre-wrap">{l.text}</p>
                {l.turn !== null && canRerun && editing !== l.turn && <button className="mt-1 text-xs underline" aria-label={`Edit and run again: message ${l.turn}`} onClick={() => setEditing(l.turn)}>Edit and run again</button>}
              </div>
              {l.turn !== null && editing === l.turn && <RerunPanel sessionId={sessionId} turn={l.turn} message={l.text} original={originals[l.turn] ?? null} onClose={() => setEditing(null)} />}
            </div>
          ) : l.kind === "agent" ? (
            <div key={i} className="max-w-[85%] rounded-xl border border-border px-3 py-2 text-sm"><p className="whitespace-pre-wrap">{l.text}</p></div>
          ) : l.kind === "tool" ? (
            <div key={i} className="rounded-lg border border-border bg-bg px-3 py-2 text-xs"><p>{l.text}</p>{l.answer && <p className="text-muted">{l.answer}</p>}</div>
          ) : <p key={i} className="text-center text-xs text-muted">{l.text}</p>)}
        </div>
      </section>
      <section aria-label="Steps">
        <h2 className="mb-2 text-sm font-medium text-muted">This step</h2>
        <p className="mb-3 rounded-lg border border-border bg-surface p-3 text-sm" aria-live="polite">{here.sentence}</p>
        <ol className="max-h-[28rem] space-y-1 overflow-y-auto text-sm" aria-label="Every step">
          {frames.map((f, i) => (
            <li key={i}><button onClick={() => { setPlaying(false); setIndex(i); }} aria-current={i === index ? "step" : undefined}
              className={`w-full rounded px-2 py-1 text-left ${i === index ? "bg-primary/15 font-medium" : "hover:bg-border/40"} ${i > index ? "text-muted" : ""}`}>{f.sentence}</button></li>))}
        </ol>
      </section>
    </div>
  );
}
