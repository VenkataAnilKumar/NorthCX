"use client";
import { useEffect, useRef, useState } from "react";
import { chat, getTrace, listAgents, listOutbox, statusLabel, type Trace } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { ErrorBox, Loading, PageHeader } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { TraceTimeline } from "@/components/trace-timeline";

interface Turn { from: "user" | "agent"; text: string; status?: string; late?: boolean }

export default function TestConsole() {
  const agents = useLoad(listAgents);
  const [agentId, setAgentId] = useState("");
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (agents.data?.length && !agentId) setAgentId(agents.data[0].id); }, [agents.data, agentId]);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "end" }); }, [turns]);

  // Messages that arrive later (for example after a reviewer decides an approval) appear in the conversation.
  const lastOutbox = useRef(0);
  useEffect(() => { lastOutbox.current = 0; }, [sessionId]);
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const msgs = await listOutbox(sessionId, lastOutbox.current);
        if (stop || !msgs.length) return;
        lastOutbox.current = msgs[msgs.length - 1].id;
        setTurns((t) => [...t, ...msgs.map((m) => ({ from: "agent" as const, text: m.reply, status: m.status, late: true }))]);
        const last = msgs[msgs.length - 1];
        if (last.traceId) setTrace(await getTrace(last.traceId));
      } catch { /* the next tick retries */ }
    };
    const id = setInterval(tick, 2000);
    return () => { stop = true; clearInterval(id); };
  }, [sessionId]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setInput(""); setError(null); setBusy(true);
    setTurns((t) => [...t, { from: "user", text: message }]);
    try {
      const r = await chat(agentId, sessionId, message);
      setTurns((t) => [...t, { from: "agent", text: r.reply, status: r.status }]);
      setTrace(await getTrace(r.traceId));
    } catch (err) {
      setError((err as Error).message);
    } finally { setBusy(false); }
  }

  function reset() { setTurns([]); setTrace(null); setError(null); setSessionId(crypto.randomUUID()); }

  if (agents.loading && !agents.data) return <Loading />;
  if (agents.error) return <ErrorBox message={agents.error} onRetry={agents.reload} />;

  return (
    <>
      <PageHeader title="Test console" subtitle="Chat with an agent and watch each step it takes.">
        <div className="flex items-center gap-2">
          <label htmlFor="agent" className="text-sm text-muted">Agent</label>
          <select id="agent" value={agentId} onChange={(e) => { setAgentId(e.target.value); reset(); }}
            className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm">
            {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}
          </select>
          <button onClick={reset} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40">New conversation</button>
        </div>
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label="Conversation" className="flex h-[32rem] flex-col rounded-xl border border-border bg-surface">
          <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
            {turns.length === 0 && <p className="text-sm text-muted">Say hello, or ask about an order (for example: where is order 1042?).</p>}
            {turns.map((t, i) => (
              <div key={i} className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${t.from === "user" ? "ml-auto bg-primary text-primary-text" : "border border-border"}`}>
                {t.late && <p className="mb-1 text-xs text-muted">Update from the team</p>}
                <p className="whitespace-pre-wrap">{t.text}</p>
                {t.status && t.status !== "completed" && <div className="mt-1"><StatusBadge status={t.status} /></div>}
              </div>
            ))}
            {busy && <p className="text-sm text-muted" role="status">Agent is working…</p>}
            <div ref={endRef} />
          </div>
          {error && <div className="px-4 pb-2"><ErrorBox message={error} /></div>}
          <form onSubmit={send} className="flex gap-2 border-t border-border p-3">
            <label htmlFor="msg" className="sr-only">Message</label>
            <input id="msg" value={input} onChange={(e) => setInput(e.target.value)} autoComplete="off" placeholder="Type a message"
              className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
            <button disabled={busy || !input.trim() || !agentId} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-text disabled:opacity-50">Send</button>
          </form>
        </section>
        <section aria-label="Trace">
          <h2 className="mb-2 text-sm font-medium text-muted">Latest trace {trace && <span>· {statusLabel[trace.events.at(-1)?.data.status as string] ?? ""}</span>}</h2>
          {trace ? <TraceTimeline events={trace.events} /> : <p className="text-sm text-muted">The trace for the latest reply appears here.</p>}
        </section>
      </div>
    </>
  );
}
