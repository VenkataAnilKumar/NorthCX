"use client";
import Link from "next/link";
import { useState } from "react";
import { createScenario, tryDraft, type Tried, useMe } from "@northcx/api-client";
import { ErrorBox, StatusBadge } from "@northcx/ui";
import { plainSteps } from "@/lib/console-steps";

interface Exchange { message: string; result: Tried }

/** Save a test made from a conversation or a try. A test is not required, so it never blocks a release until someone marks it required. */
export function SaveTest({ yaml, label = "Save this as a test" }: { yaml: () => Promise<string>; label?: string }) {
  const { can } = useMe();
  const [saved, setSaved] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!can("scenarios:write")) return null;
  async function go() {
    setBusy(true); setErr(null);
    try { setSaved((await createScenario({ yaml: await yaml() })).name); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {saved ? <span role="status" className="text-xs text-[var(--ok)]">Saved as the test <Link className="underline" href={`/simulations/scenarios/${encodeURIComponent(saved)}`}>{saved}</Link>.</span>
        : <button className="btn text-xs" disabled={busy} onClick={go}>{busy ? "Saving…" : label}</button>}
      {err && <span role="alert" className="text-xs text-[var(--bad)]">{err}</span>}
    </span>
  );
}

/** Type a customer message and see how the draft answers, with the steps in words. Nothing is saved or sent; actions are only simulated. */
export function TryPanel({ agent, spec, ready, onTried }: { agent: string; spec: unknown; ready: boolean; onTried: () => void }) {
  const { can } = useMe();
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const allowed = can("simulations:run");
  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true); setErr(null);
    try {
      const history = turns.flatMap((t) => [{ role: "user" as const, text: t.message }, { role: "assistant" as const, text: t.result.reply }]);
      const result = await tryDraft(agent, spec, message, history);
      setTurns((t) => [...t, { message, result }]); setText(""); onTried();
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  return (
    <section aria-label="Try it" className="rounded-xl border border-border bg-surface p-4">
      <h2 className="font-medium">Step 5: Try it</h2>
      <p className="mb-2 text-sm text-muted">Type what a customer might write and see how this draft answers. Nothing is saved or sent, and actions are only simulated.</p>
      {!allowed && <p className="text-sm text-muted">Your role cannot try drafts. Ask someone who can run tests.</p>}
      {allowed && !ready && <p className="text-sm text-muted">Check what it will do first.</p>}
      {allowed && ready && (
        <>
          <ol aria-label="Conversation" className="space-y-3">
            {turns.map((t, i) => (
              <li key={i} className="text-sm">
                <p className="ml-auto w-fit max-w-[85%] rounded-xl bg-primary px-3 py-2 text-primary-text">{t.message}</p>
                <div className="mt-1 max-w-[85%] rounded-xl border border-border px-3 py-2"><p className="whitespace-pre-wrap">{t.result.reply || "(no reply)"}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted"><StatusBadge status={t.result.status} />{t.result.toolsCalled.length ? `Used ${t.result.toolsCalled.join(", ").replace(/_/g, " ")}` : "Used no tools"}</p></div>
                <details className="mt-1 text-xs"><summary className="cursor-pointer text-muted">What happened</summary>
                  <ol className="mt-1 list-decimal space-y-1 pl-5">{plainSteps(t.result.events).map((s, k) => <li key={k}>{s}</li>)}</ol></details>
                {t.result.testYaml && i === turns.length - 1 && <div className="mt-1"><SaveTest yaml={async () => t.result.testYaml as string} label="Save this exchange as a test" /></div>}
              </li>))}
          </ol>
          <form onSubmit={send} className="mt-3 flex gap-2">
            <label className="sr-only" htmlFor="try-msg">A customer message to try</label>
            <input id="try-msg" className="field flex-1" value={text} onChange={(e) => setText(e.target.value)} placeholder="Where is order 1042?" autoComplete="off" />
            <button className="btn btn-primary" disabled={busy || !text.trim()}>{busy ? "Trying…" : "Try it"}</button>
            {turns.length > 0 && <button type="button" className="btn" onClick={() => setTurns([])}>Start over</button>}
          </form>
          {err && <div className="mt-2"><ErrorBox message={err} /></div>}
        </>
      )}
    </section>
  );
}
