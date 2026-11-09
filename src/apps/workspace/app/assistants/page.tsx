"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { assistantChat, listAgents, staffAssistants, useLoad, type PilotSource, type StaffAssistant } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

interface Turn { from: "you" | "assistant"; text: string; sources?: PilotSource[] }

function Chat({ a, onClose }: { a: StaffAssistant; onClose: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [temporary, setTemporary] = useState(false);
  const chat = useRef<string | undefined>(undefined);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [turns]);
  const send = async () => {
    const message = text.trim();
    if (!message) return;
    setText(""); setError(null); setBusy(true);
    setTurns((t) => [...t, { from: "you", text: message }]);
    try {
      const r = await assistantChat(a.id, message, { chatId: chat.current, temporary });
      chat.current = r.chatId;
      setTurns((t) => [...t, { from: "assistant", text: r.reply, sources: r.sources }]);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <GlassCard title={a.id} action={<button className="btn" onClick={onClose}>Close</button>} className="mt-4">
      <p className="mb-2 text-xs text-muted">It works with your permissions and can use: {a.tools.map((t) => t.name).join(", ")}.{a.unavailableTools.length ? ` Not available to you: ${a.unavailableTools.join(", ")}.` : ""} It cannot send, approve or change anything.</p>
      <label className="mb-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={temporary} onChange={(e) => setTemporary(e.target.checked)} /> Temporary chat (nothing is kept)</label>
      <div role="log" aria-label="Conversation" className="max-h-96 space-y-2 overflow-auto">
        {turns.map((t, i) => <div key={i} className={`rounded-xl p-3 text-sm ${t.from === "you" ? "bg-[var(--surface-2)]" : "border border-border"}`}><p className="whitespace-pre-wrap">{t.text}</p>
          {t.sources && t.sources.length > 0 && <ol className="mt-1 list-decimal pl-5 text-xs text-muted">{t.sources.map((s, j) => <li key={j}>{s.title ?? "Untitled"}</li>)}</ol>}</div>)}
        <div ref={end} />
      </div>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <input className="field flex-1" aria-label="Message" value={text} onChange={(e) => setText(e.target.value)} placeholder={`Ask ${a.id}`} />
        <button className="btn btn-primary" disabled={busy || !text.trim()}>{busy ? "Working…" : "Send"}</button>
      </form>
    </GlassCard>
  );
}

export default function Assistants() {
  const mine = useLoad(() => staffAssistants().catch(() => [] as StaffAssistant[]));
  const agents = useLoad(() => listAgents());
  const [open, setOpen] = useState<string | null>(null);
  const selected = mine.data?.find((a) => a.id === open) ?? null;
  return (
    <>
      <PageHeader title="Assistants" subtitle="Assistants your administrator has made live for staff. Each works with your own permissions and only reads: it never sends, approves or changes anything." />
      {mine.loading && !mine.data ? <Loading /> : mine.error ? <ErrorBox message={mine.error} onRetry={mine.reload} /> : (mine.data ?? []).length === 0 ? <Empty>No staff assistants are live yet. An administrator can install one from the Agent Hub and release it; the Pilot is always available.</Empty> : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {mine.data!.map((a) => (
            <li key={a.id} className="glass flex flex-col p-4">
              <div className="flex items-start justify-between gap-2"><h2 className="font-semibold">{a.id}</h2><span className="pill">{a.version ? `v${a.version}` : "from file"}</span></div>
              <p className="mt-1 line-clamp-3 flex-1 text-sm text-muted">{a.description}</p>
              <p className="mt-2 text-xs text-muted">Uses {a.tools.length} tool{a.tools.length === 1 ? "" : "s"}{a.unavailableTools.length ? `; ${a.unavailableTools.length} not available to you` : ""}</p>
              <button className="btn mt-3 self-start" onClick={() => setOpen(a.id)}>Open</button>
            </li>
          ))}
        </ul>
      )}
      {selected && <Chat key={selected.id} a={selected} onClose={() => setOpen(null)} />}
      <h2 className="mb-2 mt-8 text-lg font-semibold">Customer-facing agents</h2>
      <p className="mb-3 text-sm text-muted">For trying out what customers talk to.</p>
      {agents.loading && !agents.data ? <Loading /> : agents.error ? <ErrorBox message={agents.error} onRetry={agents.reload} /> : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {agents.data?.filter((a) => !mine.data?.some((m) => m.id === a.id)).map((a) => (
            <li key={a.id} className="glass flex items-center justify-between gap-2 p-3"><span className="text-sm font-medium">{a.id}</span><Link className="btn" href={`/pilot?agent=${a.id}`}>Start a test chat</Link></li>
          ))}
        </ul>
      )}
    </>
  );
}
