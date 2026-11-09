"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  addNote, answerTask, listSpaces, saveOutput, approveTask, controlTask, createTask, deleteNote, deleteTask, editTaskPlan, eraseNotes, getTask, listNotes, listTasks, pilotChat, useLoad,
  type PilotSource, type PilotTask,
} from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, Toggle } from "@northcx/ui";

type Mode = "quick" | "research";
interface Turn { from: "you" | "assistant"; text: string; sources?: PilotSource[] }

const LIVE: PilotTask["status"][] = ["approved", "running"];

function Sources({ items }: { items: { title: string | null; section?: string | null; stale?: boolean }[] }) {
  if (!items.length) return <p className="text-sm text-muted">No sources were used.</p>;
  return (
    <ol className="list-decimal space-y-1 pl-5 text-sm">
      {items.map((s, i) => <li key={i}>{s.title ?? "Untitled"}{s.section ? <span className="text-muted"> · {s.section}</span> : null}{s.stale ? <span className="text-muted"> · may be out of date</span> : null}</li>)}
    </ol>
  );
}

function Quick() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [memory, setMemory] = useState(true);
  const [temporary, setTemporary] = useState(false);
  const [space, setSpace] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const spaces = useLoad(() => listSpaces().catch(() => []));
  const chat = useRef<string | undefined>(undefined);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [turns]);
  const send = async () => {
    const message = text.trim();
    if (!message) return;
    setText(""); setError(null); setBusy(true);
    setTurns((t) => [...t, { from: "you", text: message }]);
    try {
      const r = await pilotChat(message, { chatId: chat.current, style: "quick", memory, temporary, ...(space ? { spaceId: space } : {}) });
      chat.current = r.chatId;
      setTurns((t) => [...t, { from: "assistant", text: r.reply, sources: r.sources }]);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="glass flex h-[calc(100vh-17rem)] min-h-[22rem] flex-col p-4">
      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <span className="flex items-center gap-2"><Toggle label="Use my saved notes" checked={memory && !temporary} onChange={setMemory} /><span>Use my saved notes</span></span>
        <span className="flex items-center gap-2"><Toggle label="Temporary chat: nothing is kept" checked={temporary} onChange={setTemporary} /><span>Temporary chat (nothing is kept)</span></span>
        <label className="flex items-center gap-2">Space <select className="field" value={space} onChange={(e) => { setSpace(e.target.value); chat.current = undefined; setTurns([]); }}><option value="">None</option>{(spaces.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <button className="btn" onClick={() => { setTurns([]); chat.current = undefined; }}>New chat</button>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto pr-1" role="log" aria-live="polite" aria-label="Conversation">
        {turns.length === 0 && <p className="mt-10 text-center text-sm text-muted">Ask about your knowledge base, conversations, hand-offs or how the agents are doing. Customer details are masked, and the assistant cannot send or change anything.</p>}
        {turns.map((t, i) => (
          <div key={i} className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${t.from === "you" ? "ml-auto bg-[var(--info-bg)]" : "glass-strong border border-border"}`}>
            <p className="whitespace-pre-wrap">{t.text}</p>
            {t.from === "assistant" && !temporary && <button className="btn mt-2" onClick={() => void saveOutput({ title: `Pilot answer ${new Date().toLocaleString()}`, body: t.text, kind: "answer", source: "pilot", ...(space ? { spaceId: space } : {}) }).then(() => setSaved(t.text)).catch((e) => setError((e as Error).message))}>{saved === t.text ? "Saved to Outputs" : "Save to Outputs"}</button>}
            {t.sources && t.sources.length > 0 && <details className="mt-2 text-xs text-muted"><summary className="cursor-pointer">Sources ({t.sources.length})</summary><div className="mt-1"><Sources items={t.sources} /></div></details>}
          </div>
        ))}
        {busy && <p className="text-sm text-muted" role="status">Thinking…</p>}
        <div ref={end} />
      </div>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <label htmlFor="msg" className="sr-only">Message</label>
        <input id="msg" className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a question" disabled={busy} autoComplete="off" />
        <button className="btn btn-primary" disabled={busy || !text.trim()}>Send</button>
      </form>
    </div>
  );
}

function TaskView({ task, onChange, onDeleted }: { task: PilotTask; onChange: (t: PilotTask) => void; onDeleted: () => void }) {
  const [answers, setAnswers] = useState<string[]>(task.questions.map((_, i) => task.answers[i] ?? ""));
  const [plan, setPlan] = useState(task.plan.map((p) => p.text));
  const [tab, setTab] = useState<"plan" | "steps" | "result" | "sources">(task.results.length ? "result" : "plan");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setPlan(task.plan.map((p) => p.text)); }, [task.plan]);
  const act = async (fn: () => Promise<PilotTask | { deleted: boolean }>) => {
    setBusy(true); setError(null);
    try { const r = await fn(); if ("deleted" in r) onDeleted(); else onChange(r); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const live = LIVE.includes(task.status);
  const result = task.results[task.results.length - 1];
  return (
    <GlassCard title={task.prompt} action={<span className="pill" role="status">{task.status.replace("_", " ")}</span>}>
      {task.note && <p className="mb-2 text-sm text-muted">{task.note}</p>}
      {error && <div className="mb-2"><ErrorBox message={error} /></div>}
      {task.status === "needs_answers" && (
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void act(() => answerTask(task.id, answers)); }}>
          {task.questions.map((q, i) => (
            <div key={i}>
              <label className="text-sm font-medium" htmlFor={`q${i}`}>{q.q}</label>
              <div className="mt-1 flex flex-wrap gap-2">{q.chips.map((c) => <button type="button" key={c} className="pill" onClick={() => setAnswers((a) => a.map((x, j) => (j === i ? c : x)))}>{c}</button>)}</div>
              <input id={`q${i}`} className="field mt-1" value={answers[i] ?? ""} onChange={(e) => setAnswers((a) => a.map((x, j) => (j === i ? e.target.value : x)))} placeholder="Your answer (or skip)" />
            </div>
          ))}
          <button className="btn btn-primary" disabled={busy}>Make the plan</button>
        </form>
      )}
      {task.status !== "needs_answers" && (
        <>
          <div className="seg mb-3" role="tablist" aria-label="Task">
            {(["plan", "steps", "result", "sources"] as const).map((t) => <a key={t} role="tab" aria-selected={tab === t} aria-current={tab === t ? "page" : undefined} href="#" onClick={(e) => { e.preventDefault(); setTab(t); }}>{t[0].toUpperCase() + t.slice(1)}</a>)}
          </div>
          {tab === "plan" && (
            <div className="space-y-2">
              <ol className="list-decimal space-y-2 pl-5 text-sm">
                {plan.map((p, i) => <li key={i}>{task.status === "planned" ? <input className="field" aria-label={`Step ${i + 1}`} value={p} onChange={(e) => setPlan((x) => x.map((y, j) => (j === i ? e.target.value : y)))} /> : p}</li>)}
              </ol>
              <p className="text-xs text-muted">Up to {task.limits.steps} steps. Research reads your own knowledge and conversations only, and never changes anything.</p>
              <div className="flex flex-wrap gap-2">
                {task.status === "planned" && <button className="btn" disabled={busy} onClick={() => void act(() => editTaskPlan(task.id, plan.map((text) => ({ text }))))}>Save plan</button>}
                {(task.status === "planned" || task.status === "paused" || task.status === "stopped") && <button className="btn btn-primary" disabled={busy} onClick={() => void act(() => approveTask(task.id))}>{task.status === "planned" ? "Approve and run" : task.status === "paused" ? "Resume" : "Run again"}</button>}
                {live && <><button className="btn" disabled={busy} onClick={() => void act(() => controlTask(task.id, "pause"))}>Pause</button><button className="btn" disabled={busy} onClick={() => void act(() => controlTask(task.id, "stop"))}>Stop</button></>}
                <button className="btn" disabled={busy} onClick={() => void act(() => deleteTask(task.id))}>Delete</button>
              </div>
            </div>
          )}
          {tab === "steps" && (task.steps.length === 0 ? <p className="text-sm text-muted">Nothing has run yet. Steps appear here as they finish.</p> : (
            <ul className="space-y-2 text-sm" aria-live="polite">
              {task.steps.map((s) => <li key={s.n}><strong>{s.n}. {s.text}</strong> <span className="text-muted">· {s.status}{s.tokens ? ` · ${s.tokens} tokens` : ""}{s.tools.length ? ` · ${s.tools.join(", ")}` : ""}</span></li>)}
              <li className="text-xs text-muted">{task.tokens} of {task.limits.tokens} tokens used</li>
            </ul>
          ))}
          {tab === "result" && (result ? <div><p className="whitespace-pre-wrap text-sm">{result.text}</p><p className="mt-2 text-xs text-muted">Version {result.v} · {result.tokens} tokens</p></div> : <p className="text-sm text-muted">{live ? "Working on it…" : "No result yet. Approve the plan to run it."}</p>)}
          {tab === "sources" && <Sources items={result?.sources ?? task.steps.flatMap((s) => s.sources)} />}
        </>
      )}
    </GlassCard>
  );
}

function Research() {
  const tasks = useLoad(() => listTasks());
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState<PilotTask | null>(null);
  const select = useCallback(async (id: string) => { setSelected(id); try { setCurrent(await getTask(id)); } catch (e) { setError((e as Error).message); } }, []);
  // poll a running task so its steps show as they finish; a task that is not running needs no polling
  useEffect(() => {
    if (!current || !LIVE.includes(current.status)) return;
    const t = setInterval(() => { void getTask(current.id).then((x) => { setCurrent(x); if (!LIVE.includes(x.status)) tasks.reload(); }).catch(() => undefined); }, 2000);
    return () => clearInterval(t);
  }, [current, tasks]);
  const start = async () => {
    if (!prompt.trim()) return;
    setBusy(true); setError(null);
    try { const t = await createTask(prompt.trim()); setPrompt(""); setCurrent(t); setSelected(t.id); tasks.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <div className="space-y-3">
        <form className="glass p-3" onSubmit={(e) => { e.preventDefault(); void start(); }}>
          <label htmlFor="task" className="text-sm font-medium">New research task</label>
          <textarea id="task" className="field mt-1" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="What should the assistant find out?" />
          <button className="btn btn-primary mt-2" disabled={busy || !prompt.trim()}>{busy ? "Asking…" : "Start"}</button>
        </form>
        {error && <ErrorBox message={error} />}
        <div className="glass p-3">
          <h3 className="mb-2 text-sm font-semibold">Recent</h3>
          {tasks.loading && !tasks.data ? <Loading /> : tasks.data?.length ? (
            <ul className="space-y-1">{tasks.data.map((t) => <li key={t.id}><button className={`w-full rounded-lg px-2 py-1 text-left text-sm ${selected === t.id ? "bg-[var(--accent-soft)]" : ""}`} onClick={() => void select(t.id)}>{t.prompt.slice(0, 60)}<span className="block text-xs text-muted">{t.status.replace("_", " ")}</span></button></li>)}</ul>
          ) : <p className="text-sm text-muted">No tasks yet.</p>}
        </div>
      </div>
      <div>{current ? <TaskView key={current.id} task={current} onChange={(t) => { setCurrent(t); tasks.reload(); }} onDeleted={() => { setCurrent(null); setSelected(null); tasks.reload(); }} /> : <Empty>Describe a task on the left, or pick a recent one.</Empty>}</div>
    </div>
  );
}

function Notes() {
  const notes = useLoad(() => listNotes());
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = async () => {
    setError(null);
    try { await addNote(text.trim()); setText(""); notes.reload(); } catch (e) { setError((e as Error).message); }
  };
  return (
    <GlassCard title="My notes" action={<span className="text-xs text-muted">Only you see these</span>}>
      <p className="mb-2 text-sm text-muted">Short working preferences the assistant uses in every chat (for example, “I prefer short answers with a table”). Never customer details.</p>
      {notes.error ? <ErrorBox message={notes.error} onRetry={notes.reload} /> : notes.data?.length ? (
        <ul className="mb-3 space-y-1 text-sm">{notes.data.map((n) => <li key={n.id} className="flex items-center justify-between gap-2"><span>{n.note}</span><button className="btn" aria-label={`Delete note: ${n.note}`} onClick={() => void deleteNote(n.id).then(notes.reload)}>Delete</button></li>)}</ul>
      ) : <p className="mb-3 text-sm text-muted">No notes yet.</p>}
      {error && <div className="mb-2"><ErrorBox message={error} /></div>}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void add(); }}>
        <label htmlFor="note" className="sr-only">New note</label>
        <input id="note" className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a note" />
        <button className="btn" disabled={text.trim().length < 5}>Add</button>
        {notes.data?.length ? <button type="button" className="btn" onClick={() => void eraseNotes().then(notes.reload)}>Erase all</button> : null}
      </form>
    </GlassCard>
  );
}

function PilotPage() {
  const [mode, setMode] = useState<Mode>("quick");
  const [showNotes, setShowNotes] = useState(false);
  return (
    <>
      <PageHeader title="Pilot" subtitle="Give the assistant a question or a research task. It reads what you are allowed to see, masks customer details, and never sends or changes anything." />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="seg" role="tablist" aria-label="Task style">
          <a role="tab" aria-selected={mode === "quick"} aria-current={mode === "quick" ? "page" : undefined} href="#" onClick={(e) => { e.preventDefault(); setMode("quick"); }}>Quick answer</a>
          <a role="tab" aria-selected={mode === "research"} aria-current={mode === "research" ? "page" : undefined} href="#" onClick={(e) => { e.preventDefault(); setMode("research"); }}>Research</a>
        </div>
        <button className="btn" aria-expanded={showNotes} onClick={() => setShowNotes((v) => !v)}>{showNotes ? "Hide my notes" : "My notes"}</button>
      </div>
      {showNotes && <div className="mb-3"><Notes /></div>}
      {mode === "quick" ? <Quick /> : <Research />}
    </>
  );
}
export default function Page() { return <Suspense fallback={<Loading />}><PilotPage /></Suspense>; }
