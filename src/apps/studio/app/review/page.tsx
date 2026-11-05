"use client";
import Link from "next/link";
import { useState } from "react";
import { FAILURE_KINDS, formatTime, getReviewContext, getReviewQueue, getScenarioDraft, type QueueRow, type ReviewContext, saveReview, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader } from "@northcx/ui";

function Reviewer({ ctx, onSaved }: { ctx: ReviewContext; onSaved: () => void }) {
  const { can } = useMe();
  const handed = ctx.handoffs.length > 0;
  const [verdict, setVerdict] = useState(ctx.review?.verdict ?? "correct");
  const [handoff, setHandoff] = useState(ctx.review?.handoff ?? (handed ? "needed" : "not_applicable"));
  const [failures, setFailures] = useState<string[]>(ctx.review?.failures ?? []);
  const [note, setNote] = useState(ctx.review?.note ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const toggle = (f: string) => setFailures((cur) => (cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]));
  const submit = async () => {
    try { await saveReview(ctx.sessionId, { verdict, handoff, failures: verdict === "correct" ? [] : failures, note }); setMsg("Saved."); onSaved(); }
    catch (e) { setMsg((e as Error).message); }
  };
  const makeDraft = async () => {
    try { setDraft((await getScenarioDraft(ctx.sessionId)).yaml); } catch (e) { setMsg((e as Error).message); }
  };
  return (
    <div className="space-y-4">
      <section aria-label="Transcript" className="space-y-2 rounded-xl border border-border bg-surface p-4">
        {ctx.transcript.map((m, i) => (
          <p key={i} className="text-sm"><span className="font-medium">{m.from}:</span> {m.text}</p>
        ))}
        <p className="pt-2 text-xs text-muted">
          {ctx.rating !== null && <>Customer rating {ctx.rating}/5 · </>}{ctx.handoffs.map((h) => `handed over (${h.trigger}${h.queue ? `, ${h.queue}` : ""})`).join(", ")}
          {ctx.traces.length > 0 && <> · Traces: {ctx.traces.map((t) => <Link key={t.id} className="underline" href={`/conversations/${encodeURIComponent(ctx.sessionId)}`}>{t.status}</Link>)}</>}
        </p>
      </section>
      {can("reviews:write") ? (
        <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="space-y-3 rounded-xl border border-border bg-surface p-4" aria-label="Review">
          <fieldset className="flex gap-4"><legend className="text-sm font-medium">Was the agent right?</legend>
            {["correct", "wrong"].map((v) => <label key={v} className="text-sm"><input type="radio" name="verdict" checked={verdict === v} onChange={() => setVerdict(v as "correct" | "wrong")} /> {v === "correct" ? "Yes" : "No"}</label>)}
          </fieldset>
          {handed && (
            <fieldset className="flex gap-4"><legend className="text-sm font-medium">Was the hand-off needed?</legend>
              {["needed", "unneeded"].map((v) => <label key={v} className="text-sm"><input type="radio" name="handoff" checked={handoff === v} onChange={() => setHandoff(v)} /> {v === "needed" ? "Yes" : "No"}</label>)}
            </fieldset>
          )}
          {verdict === "wrong" && (
            <fieldset><legend className="text-sm font-medium">What went wrong?</legend>
              <div className="mt-1 flex flex-wrap gap-3">{FAILURE_KINDS.map((f) => <label key={f} className="text-sm"><input type="checkbox" checked={failures.includes(f)} onChange={() => toggle(f)} /> {f.replaceAll("_", " ")}</label>)}</div>
            </fieldset>
          )}
          <label className="block text-sm font-medium">Note<textarea value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-bg p-2 text-sm font-normal" rows={3} /></label>
          <div className="flex gap-3">
            <button type="submit" className="rounded-lg bg-[var(--primary)] px-4 py-2 text-sm text-white">Save review</button>
            <button type="button" onClick={() => void makeDraft()} className="rounded-lg border border-border px-4 py-2 text-sm">Create scenario draft</button>
          </div>
          {msg && <p role="status" className="text-sm">{msg}</p>}
          {draft && <pre className="overflow-x-auto rounded-lg bg-bg p-3 text-xs">{draft}</pre>}
        </form>
      ) : <p className="text-sm text-muted">You can read this review but not change it.</p>}
    </div>
  );
}

export default function ReviewPage() {
  const [showDone, setShowDone] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const queue = useLoad(() => getReviewQueue(showDone), [showDone]);
  const ctx = useLoad(() => (open ? getReviewContext(open) : Promise.resolve(null)), [open]);
  return (
    <div>
      <PageHeader title="Review" subtitle="Conversations most worth a human look, plus a small random sample.">
        <label className="text-sm"><input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} /> Show reviewed</label>
      </PageHeader>
      {queue.error && <ErrorBox message={queue.error} onRetry={queue.reload} />}
      {queue.loading && !queue.data && <Loading />}
      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <ul aria-label="Review queue" className="space-y-2">
          {queue.data?.length === 0 && <Empty>Nothing to review right now.</Empty>}
          {queue.data?.map((r: QueueRow) => (
            <li key={r.sessionId}>
              <button onClick={() => setOpen(r.sessionId)} aria-current={open === r.sessionId} className="w-full rounded-xl border border-border bg-surface p-3 text-left text-sm">
                <span className="line-clamp-2">{r.firstMessage || "(no message)"}</span>
                <span className="mt-1 flex flex-wrap gap-1">{r.reasons.map((x) => <span key={x} className="rounded-full bg-bg px-2 py-0.5 text-xs text-muted">{x}</span>)}</span>
                <span className="mt-1 block text-xs text-muted">{formatTime(r.endedAt)}{r.review && ` · reviewed: ${r.review.verdict}`}</span>
              </button>
            </li>
          ))}
        </ul>
        <div>
          {!open && <Empty>Choose a conversation to review.</Empty>}
          {open && ctx.error && <ErrorBox message={ctx.error} />}
          {open && ctx.data && <Reviewer key={open} ctx={ctx.data} onSaved={queue.reload} />}
        </div>
      </div>
    </div>
  );
}
