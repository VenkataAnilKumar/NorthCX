"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { chatStream, listAgents, useLoad, type ChatReply } from "@northcx/api-client";
import { ErrorBox, Loading, PageHeader, StatusBadge } from "@northcx/ui";

interface Turn { from: "you" | "agent"; text: string; reply?: ChatReply; live?: boolean }

function Chat() {
  const params = useSearchParams();
  const agents = useLoad(() => listAgents());
  const [agent, setAgent] = useState(params.get("agent") ?? "");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const session = useRef(`ws-${Math.random().toString(36).slice(2, 10)}`);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!agent && agents.data?.length) setAgent(agents.data[0].id); }, [agents.data, agent]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [turns]);
  const send = async () => {
    const message = text.trim();
    if (!message || !agent) return;
    setText(""); setError(null); setBusy(true);
    setTurns((t) => [...t, { from: "you", text: message }, { from: "agent", text: "", live: true }]);
    try {
      const reply = await chatStream(agent, session.current, message, {
        onProgress: (tool) => setProgress(`Using ${tool}…`),
        onDelta: (d) => setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, text: x.text + d } : x))),
      });
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { from: "agent", text: reply.reply, reply } : x)));
    } catch (e) {
      setError((e as Error).message);
      setTurns((t) => t.slice(0, -1));
    } finally { setBusy(false); setProgress(null); }
  };
  return (
    <>
      <PageHeader title="Pilot" subtitle="A first, simple version: try an agent the way a customer would. Plans, steps and results arrive with the staff backend (E5). This is a test conversation, kept apart from real customers." />
      {agents.loading && !agents.data ? <Loading /> : agents.error ? <ErrorBox message={agents.error} onRetry={agents.reload} /> : (
        <div className="glass flex h-[calc(100vh-13rem)] min-h-[24rem] flex-col p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="text-sm" htmlFor="agent">Agent</label>
            <select id="agent" className="field w-auto" value={agent} onChange={(e) => { setAgent(e.target.value); setTurns([]); session.current = `ws-${Math.random().toString(36).slice(2, 10)}`; }}>
              {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.id}{a.version ? ` v${a.version}` : ""}</option>)}
            </select>
            <button className="btn" onClick={() => { setTurns([]); session.current = `ws-${Math.random().toString(36).slice(2, 10)}`; }}>New chat</button>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto pr-1" role="log" aria-live="polite" aria-label="Conversation">
            {turns.length === 0 && <p className="mt-10 text-center text-sm text-muted">Say hello to {agent || "an agent"}.</p>}
            {turns.map((t, i) => (
              <div key={i} className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${t.from === "you" ? "ml-auto bg-[var(--info-bg)]" : "glass-strong border border-border"}`}>
                {t.text || (t.live ? <span className="text-muted">{progress ?? "Thinking…"}</span> : "")}
                {t.reply && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <StatusBadge status={t.reply.status} />
                    {t.reply.pendingApprovals.length > 0 && <span>{t.reply.pendingApprovals.length} approval(s) waiting: see Approvals</span>}
                    {t.reply.handoffId && <span>Handed to a person: see Threads</span>}
                  </div>
                )}
              </div>
            ))}
            <div ref={end} />
          </div>
          {error && <div className="mt-2"><ErrorBox message={error} /></div>}
          <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(); }}>
            <label htmlFor="msg" className="sr-only">Message</label>
            <input id="msg" className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a message" disabled={busy || !agent} autoComplete="off" />
            <button className="btn btn-primary" disabled={busy || !text.trim() || !agent}>Send</button>
          </form>
        </div>
      )}
    </>
  );
}
export default function Page() { return <Suspense fallback={<Loading />}><Chat /></Suspense>; }
