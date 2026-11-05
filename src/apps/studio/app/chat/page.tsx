"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { type AttachmentInfo, chatStream, type EnvName, getTrace, listAgents, listOutbox, statusLabel, type Trace, uploadAttachment, useLoad, useMe } from "@northcx/api-client";
import { ErrorBox, Loading, PageHeader, StatusBadge, TraceTimeline } from "@northcx/ui";

interface Turn { from: "user" | "agent"; text: string; status?: string; late?: boolean; handoffId?: string | null }

export default function TestConsole() {
  const agents = useLoad(listAgents);
  const [agentId, setAgentId] = useState("");
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const [environment, setEnvironment] = useState<EnvName>("production");
  const { can } = useMe();
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [version, setVersion] = useState<number | null | undefined>(undefined);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!agents.data?.length || agentId) return;
    const q = new URLSearchParams(window.location.search);
    const wanted = q.get("agent");
    setAgentId(wanted && agents.data.some((a) => a.id === wanted) ? wanted : agents.data[0].id);
    const e = q.get("env");
    if (e === "dev" || e === "staging") setEnvironment(e);
  }, [agents.data, agentId]);
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

  const [pending, setPending] = useState<AttachmentInfo[]>([]);
  async function attach(list: FileList | null) {
    if (!list?.length) return;
    setError(null);
    try { const added: AttachmentInfo[] = []; for (const f of Array.from(list).slice(0, 5)) added.push(await uploadAttachment(sessionId, f)); setPending((p) => [...p, ...added].slice(0, 5)); }
    catch (err) { setError((err as Error).message); }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    const files = pending;
    setInput(""); setPending([]); setError(null); setBusy(true);
    setTurns((t) => [...t, { from: "user", text: files.length ? `${message}\n📎 ${files.map((f) => f.name).join(", ")}` : message }]);
    setWorking("Thinking…");
    let started = false;
    try {
      const r = await chatStream(agentId, sessionId, message, {
        onProgress: (tool) => setWorking(`Using ${tool.replace(/_/g, " ")}…`),
        onDelta: (piece) => {
          setWorking(null);
          setTurns((t) => started
            ? t.map((x, i) => (i === t.length - 1 ? { ...x, text: x.text + piece } : x))
            : [...t, { from: "agent", text: piece }]);
          started = true;
        },
      }, environment, files.map((f) => f.id));
      setTurns((t) => {
        const turn: Turn = { from: "agent", text: r.reply, status: r.status, handoffId: r.handoffId };
        return started ? [...t.slice(0, -1), turn] : [...t, turn];
      });
      setTrace(await getTrace(r.traceId));
      setVersion(r.agentVersion);
    } catch (err) {
      setError((err as Error).message);
    } finally { setBusy(false); setWorking(null); }
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
          {can("simulations:run") && (<>
            <label htmlFor="env" className="text-sm text-muted">Environment</label>
            <select id="env" value={environment} onChange={(e) => { setEnvironment(e.target.value as EnvName); reset(); }} className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm">
              <option value="production">production</option><option value="staging">staging</option><option value="dev">dev</option>
            </select>
          </>)}
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
                {t.status && t.status !== "completed" && (
                  <div className="mt-1 flex items-center gap-2"><StatusBadge status={t.status} />
                    {t.handoffId && <Link href={`/handoffs?open=${t.handoffId}`} className="text-xs text-primary underline">View handoff</Link>}</div>)}
              </div>
            ))}
            {busy && working && <p className="text-sm text-muted" role="status">{working}</p>}
            <div ref={endRef} />
          </div>
          {error && <div className="px-4 pb-2"><ErrorBox message={error} /></div>}
          {pending.length > 0 && <p className="px-4 pb-1 text-xs text-muted" role="status">Attached: {pending.map((f) => f.name).join(", ")}</p>}
          <form onSubmit={send} className="flex gap-2 border-t border-border p-3">
            <label className="cursor-pointer self-center rounded-lg border border-border px-2 py-2 text-sm hover:bg-border/40" title="Attach a picture, PDF or text file (if the agent accepts them)">
              <span aria-hidden>📎</span><span className="sr-only">Attach a file</span>
              <input type="file" className="sr-only" multiple accept="image/png,image/jpeg,image/gif,image/webp,application/pdf,text/plain" onChange={(e) => { void attach(e.target.files); e.target.value = ""; }} /></label>
            <label htmlFor="msg" className="sr-only">Message</label>
            <input id="msg" value={input} onChange={(e) => setInput(e.target.value)} autoComplete="off" placeholder="Type a message"
              className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
            <button disabled={busy || !input.trim() || !agentId} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-text disabled:opacity-50">Send</button>
          </form>
        </section>
        <section aria-label="Trace">
          <h2 className="mb-2 text-sm font-medium text-muted">Latest trace {trace && <span>· {statusLabel[trace.events.at(-1)?.data.status as string] ?? ""}{version !== undefined && ` · agent ${version ? `version ${version}` : "from spec file"}`}</span>}</h2>
          {trace ? <TraceTimeline events={trace.events} /> : <p className="text-sm text-muted">The trace for the latest reply appears here.</p>}
        </section>
      </div>
    </>
  );
}
