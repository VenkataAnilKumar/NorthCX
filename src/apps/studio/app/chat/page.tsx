"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type AttachmentInfo, chatStream, decideApproval, type EnvName, getTrace, listAgents, listApprovals, listOutbox, statusLabel, type Trace, uploadAttachment, useLoad, useMe } from "@northcx/api-client";
import { ErrorBox, Loading, PageHeader, StatusBadge, TraceTimeline } from "@northcx/ui";
import { ApprovalCard, type Decision, type HeldAction, ToolCard } from "@/components/console-cards";
import { plainSteps, type ToolCardData, toolCards } from "@/lib/console-steps";

interface Turn { from: "user" | "agent"; text: string; status?: string; late?: boolean; handoffId?: string | null; cards?: ToolCardData[]; held?: HeldAction[] }

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
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [deciding, setDeciding] = useState<string | null>(null);
  const waiting = Object.entries(decisions).filter(([, d]) => d.state === "waiting").map(([id]) => id);
  const checkOutbox = useCallback(async () => {
    const msgs = await listOutbox(sessionId, lastOutbox.current);
    if (!msgs.length) return;
    lastOutbox.current = msgs[msgs.length - 1].id;
    setTurns((t) => [...t, ...msgs.map((m) => ({ from: "agent" as const, text: m.reply, status: m.status, late: true }))]);
    const last = msgs[msgs.length - 1];
    if (last.traceId) setTrace(await getTrace(last.traceId));
  }, [sessionId]);
  const canRef = useRef(can);
  canRef.current = can;
  const waitingKey = waiting.join(",");
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        await checkOutbox();
        if (stop || !waitingKey || !canRef.current("approvals:read")) return;
        const still = new Set((await listApprovals("pending")).map((a) => a.id));  // a held action that is no longer pending was decided elsewhere or has expired
        if (!stop) setDecisions((d) => Object.fromEntries(Object.entries(d).map(([id, x]) => [id, x.state === "waiting" && !still.has(id) ? { state: "gone" as const } : x])));
      } catch { /* the next tick retries */ }
    };
    const id = setInterval(tick, 2000);
    return () => { stop = true; clearInterval(id); };
  }, [checkOutbox, waitingKey]);

  async function decide(a: HeldAction, approved: boolean) {
    setDeciding(a.id); setError(null);
    try {
      const r = await decideApproval(a.id, approved);
      setDecisions((d) => ({ ...d, [a.id]: { state: approved ? "approved" : "rejected", by: r.decided_by } }));
      if (r.resume?.traceId) setTrace(await getTrace(r.resume.traceId));
      await checkOutbox();
      if (r.resume?.error) setError(r.resume.error);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setDecisions((d) => ({ ...d, [a.id]: { state: "gone" } }));
      else setError((err as Error).message);
    } finally { setDeciding(null); }
  }

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
      const done = await getTrace(r.traceId);
      const cards = toolCards(done.events);
      const held: HeldAction[] = r.pendingApprovals.map((a) => ({ id: a.id, tool: a.tool, reason: a.reason, input: [...cards].reverse().find((c) => c.outcome === "held")?.input ?? "no inputs" }));
      setTurns((t) => {
        const turn: Turn = { from: "agent", text: r.reply, status: r.status, handoffId: r.handoffId, cards, held };
        return started ? [...t.slice(0, -1), turn] : [...t, turn];
      });
      setDecisions((d) => ({ ...d, ...Object.fromEntries(held.map((h) => [h.id, { state: "waiting" as const }])) }));
      setTrace(done);
      setVersion(r.agentVersion);
    } catch (err) {
      setError((err as Error).message);
    } finally { setBusy(false); setWorking(null); }
  }

  function reset() { setTurns([]); setTrace(null); setDecisions({}); setError(null); setSessionId(crypto.randomUUID()); }

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
                {t.cards?.length ? <div className="mb-2 space-y-1">{t.cards.map((c, k) => <ToolCard key={k} card={c} />)}</div> : null}
                <p className="whitespace-pre-wrap">{t.text}</p>
                {t.held?.map((h) => <div key={h.id} className="mt-2"><ApprovalCard action={h} decision={decisions[h.id] ?? { state: "gone" }} canDecide={can("approvals:decide")} busy={deciding === h.id} onDecide={(ok) => void decide(h, ok)} /></div>)}
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
          {trace ? (<>
            <h3 className="mb-1 text-sm font-medium">What happened</h3>
            <ol className="mb-3 list-decimal space-y-1 pl-5 text-sm" aria-label="What happened, in words">{plainSteps(trace.events).map((x, i) => <li key={i}>{x}</li>)}</ol>
            <details><summary className="cursor-pointer text-sm text-muted">Every event</summary><div className="mt-2"><TraceTimeline events={trace.events} /></div></details>
          </>) : <p className="text-sm text-muted">The trace for the latest reply appears here.</p>}
        </section>
      </div>
    </>
  );
}
