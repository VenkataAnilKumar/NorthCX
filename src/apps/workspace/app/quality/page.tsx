"use client";
import { useState } from "react";
import { addCoachingNote, coachingNotes, deleteCoachingNote, getRubric, putRubric, qaCalibration, resetRubric, scorecards, useLoad, useMe, type Rubric } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const pct = (v: number | null) => (v === null ? "no data" : `${Math.round(v * 100)}%`);

function RubricEditor({ rubric, onSaved }: { rubric: Rubric; onSaved: () => void }) {
  const [text, setText] = useState(JSON.stringify({ criteria: rubric.criteria, passMark: rubric.passMark, sample: rubric.sample }, null, 2));
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const save = async () => { setErr(null); setNote(null); try { await putRubric(JSON.parse(text)); setNote("Saved as a new version."); onSaved(); } catch (e) { setErr((e as Error).message); } };
  return (
    <GlassCard title={`Scorecard rubric (${rubric.isDefault ? "default" : `version ${rubric.version}`})`}>
      <p className="text-sm text-muted">Each criterion is a check on facts already recorded about the conversation. Checks: {(rubric.checks?.kinds ?? []).join(", ")}. A change takes effect for the next scoring; earlier scores are not rewritten.</p>
      <textarea aria-label="Rubric (JSON)" className="field mt-2 h-64 w-full font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex gap-2"><button className="btn btn-primary" onClick={() => void save()}>Save rubric</button>
        {!rubric.isDefault && <button className="btn" onClick={() => { if (confirm("Go back to the default rubric?")) void resetRubric().then(onSaved); }}>Use the default</button>}</div>
      {note && <p className="mt-2 text-sm" role="status">{note}</p>}{err && <div className="mt-2"><ErrorBox message={err} /></div>}
    </GlassCard>
  );
}

function Coaching() {
  const [sid, setSid] = useState("");
  const [about, setAbout] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const { data, reload } = useLoad(() => coachingNotes());
  const add = async () => { setErr(null); try { await addCoachingNote(sid.trim(), about.trim(), note.trim()); setNote(""); reload(); } catch (e) { setErr((e as Error).message); } };
  return (
    <GlassCard title="Coaching notes">
      <p className="text-sm text-muted">Short notes on how a conversation went, for the person or agent it is about. No customer details: notes with personal data or card numbers are refused.</p>
      <div className="mt-2 grid gap-2 md:grid-cols-3">
        <input className="field" aria-label="Conversation id" placeholder="Conversation id" value={sid} onChange={(e) => setSid(e.target.value)} />
        <input className="field" aria-label="About" placeholder="Who or which agent" value={about} onChange={(e) => setAbout(e.target.value)} />
        <button className="btn btn-primary" disabled={!sid.trim() || about.trim().length < 2 || note.trim().length < 5} onClick={() => void add()}>Add note</button>
      </div>
      <textarea aria-label="Note" className="field mt-2 w-full" rows={2} maxLength={300} placeholder="What went well, and what to try next time" value={note} onChange={(e) => setNote(e.target.value)} />
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}
      <ul className="mt-3 space-y-2 text-sm">{(data ?? []).map((n) => <li key={n.id} className="rounded-xl border border-border p-2"><strong>{n.about}</strong> · {n.author} · conversation {n.sessionId.slice(0, 12)}<p>{n.note}</p>
        <button className="btn mt-1" onClick={() => void deleteCoachingNote(n.id).then(reload).catch((e) => setErr(e.message))}>Delete</button></li>)}</ul>
    </GlassCard>
  );
}

export default function Page() {
  const { can } = useMe();
  const [days, setDays] = useState(7);
  const card = useLoad(() => scorecards(days), [days]);
  const cal = useLoad(() => qaCalibration(30));
  const rub = useLoad(() => getRubric());
  if (card.loading && !card.data) return <Loading />;
  if (card.error) return <ErrorBox message={card.error} onRetry={card.reload} />;
  const c = card.data!;
  return (
    <>
      <PageHeader title="Quality" subtitle="Scores from recorded facts, checked against reviewers' verdicts, with coaching notes. Scores point you at conversations to read; they do not replace reading them." />
      <label className="mb-4 block text-sm">Period <select className="field ml-1" value={days} onChange={(e) => setDays(Number(e.target.value))}>{[7, 14, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select></label>
      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard title="Scorecards">
          {c.scored === 0 ? <Empty>No conversations to score in this period.</Empty> : (<>
            <p className="text-3xl font-semibold">{c.averageScore}<span className="text-base font-normal text-muted"> average of 100</span></p>
            <p className="text-sm">{pct(c.passRate.value)} at or above the pass mark of {c.passMark} ({c.passRate.numerator} of {c.passRate.denominator} scored conversations; {c.conversations - c.scored} had nothing to score). Rubric version {c.rubricVersion || "default"}.</p>
            <table className="mt-3 w-full text-sm"><caption className="sr-only">Pass and fail by check</caption><thead><tr className="text-left text-xs text-muted"><th>Check</th><th>Passed</th><th>Failed</th></tr></thead>
              <tbody>{c.byCheck.map((k) => <tr key={k.id}><td>{k.label}</td><td>{k.passed}</td><td>{k.failed}</td></tr>)}</tbody></table>
            {c.byAgent.length > 0 && <p className="mt-2 text-sm">By agent: {c.byAgent.map((a) => `${a.agent} ${a.average} (${a.scored})`).join(", ")}</p>}
          </>)}
          <p className="mt-2 text-xs text-muted">{c.note}</p>
        </GlassCard>
        <GlassCard title="Calibration">
          {!cal.data ? <Loading /> : cal.data.compared === 0 ? <Empty>No conversation has both a score and a reviewer's verdict yet. Review some in the sample below.</Empty> : (<>
            <p className="text-3xl font-semibold">{pct(cal.data.agreement.value)}<span className="text-base font-normal text-muted"> agreement</span></p>
            <p className="text-sm">{cal.data.agreement.numerator} of {cal.data.compared} compared conversations. Score said good, reviewer said wrong: {cal.data.scoreSaidGoodReviewerSaidWrong}. Score said poor, reviewer said correct: {cal.data.scoreSaidBadReviewerSaidCorrect}.</p>
            {cal.data.disagreements.length > 0 && <ul className="mt-2 text-xs">{cal.data.disagreements.map((d) => <li key={d.sessionId}>{d.sessionId.slice(0, 14)}: score {d.score}, reviewer {d.verdict}</li>)}</ul>}
          </>)}
          {cal.data && <p className="mt-2 text-xs text-muted">{cal.data.note}</p>}
        </GlassCard>
        <GlassCard title="Lowest scores">
          {c.lowest.length === 0 ? <Empty>Nothing scored.</Empty> : <ul className="space-y-2 text-sm">{c.lowest.slice(0, 10).map((l) => <li key={l.sessionId}><strong>{l.score}</strong> · {l.agentId} · {l.sessionId.slice(0, 14)}<br /><span className="text-xs text-muted">{l.criteria.filter((x) => x.result === "fail").map((x) => `${x.label}: ${x.reason}`).join("; ")}</span></li>)}</ul>}
        </GlassCard>
        <GlassCard title="Sample to review">
          {c.sampleToReview.length === 0 ? <Empty>No unreviewed conversations in the sample.</Empty> : <ul className="space-y-1 text-sm">{c.sampleToReview.slice(0, 15).map((s) => <li key={s}>{s.slice(0, 18)}</li>)}</ul>}
          <p className="mt-2 text-xs text-muted">A fixed share of conversations chosen by their id, so the same ones always come up. Open them from Admin → Review and QA.</p>
        </GlassCard>
        {can("reviews:write") && <div className="lg:col-span-2"><Coaching /></div>}
        {can("releases:publish") && rub.data && <div className="lg:col-span-2"><RubricEditor key={rub.data.version} rubric={rub.data} onSaved={() => { rub.reload(); card.reload(); }} /></div>}
      </div>
    </>
  );
}
