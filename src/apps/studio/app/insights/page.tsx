"use client";
import Link from "next/link";
import { useState } from "react";
import { type AskAnswer, askInsights, formatTime, getAlerts, getFailures, getGaps, getOverview, getReviewQuality, getSeries, type Ratio, type SeriesPoint, useLoad } from "@northcx/api-client";
import { BarList, ConversationList, Empty, ErrorBox, LineChart, Loading, PageHeader } from "@northcx/ui";

const PERIODS = [{ label: "24 hours", hours: 24 }, { label: "7 days", hours: 24 * 7 }, { label: "30 days", hours: 24 * 30 }];
const pct = (r: Ratio) => (r.value === null ? "–" : `${(r.value * 100).toFixed(r.value < 0.1 ? 1 : 0)}%`);

function AskBox({ env }: { env: string }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<AskAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function go(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null); setRes(null);
    try { setRes(await askInsights(q.trim(), env)); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  const p = res?.plan;
  return (
    <section aria-label="Ask a question" className="mb-4 rounded-xl border border-border bg-surface p-4">
      <h2 className="font-medium">Ask a question</h2>
      <p className="mb-2 text-sm text-muted">For example: “Did containment improve compared with last week?” The answer is calculated from the recorded figures; the model only works out which figure and period you mean.</p>
      <form onSubmit={go} className="flex gap-2">
        <label htmlFor="ask" className="sr-only">Question</label>
        <input id="ask" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} placeholder="How many conversations went to a person yesterday?" className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm" />
        <button disabled={busy || q.trim().length < 3} className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text disabled:opacity-50">{busy ? "Working…" : "Ask"}</button>
      </form>
      {err && <p role="alert" className="mt-2 text-sm text-[var(--bad)]">{err}</p>}
      {res && (
        <div role="status" className="mt-3 text-sm">
          <p className={res.answerable ? "" : "text-[var(--warn)]"}>{res.answer}</p>
          {res.series && <LineChart label={res.label ?? "Figure"} points={res.series.points} bucket={res.series.bucket} />}
          {res.rows && res.rows.length > 0 && <BarList label={res.label ?? "Breakdown"} rows={res.rows} />}
          {res.conversations && res.conversations.length > 0 && <ConversationList rows={res.conversations} />}
          {p && <p className="mt-1 text-xs text-muted">Read as: {p.find ? `find conversations${p.find.q ? ` about “${p.find.q}”` : ""}${p.find.status ? ` that ended ${p.find.status.replace("_", " ")}` : ""}` : (p.metric ?? "").replaceAll("_", " ")}, {p.days} day{p.days === 1 ? "" : "s"}{p.offsetDays ? `, ending ${p.offsetDays} days ago` : ""}{p.agent ? `, agent ${p.agent}` : ""}{p.filters && Object.keys(p.filters).length ? `, only ${Object.entries(p.filters).map(([k, v]) => `${k}=${v}`).join(", ")}` : ""}{p.compare ? ", compared with the period before" : ""}{p.trend ? ", over time" : ""}.</p>}
          {res.supported && <p className="mt-1 text-xs text-muted">Figures I can answer about: {res.supported.join(", ")}.</p>}
        </div>)}
    </section>
  );
}

function Stat({ title, ratio, hint }: { title: string; ratio: Ratio; hint: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-sm text-muted">{title}</p>
      <p className="mt-1 text-2xl font-semibold">{pct(ratio)}</p>
      <p className="mt-1 text-xs text-muted">{ratio.numerator} of {ratio.denominator} · {hint}</p>
    </div>
  );
}

function Spark({ points, pick, label }: { points: SeriesPoint[]; pick: (p: SeriesPoint) => number; label: string }) {
  const values = points.map(pick);
  const max = Math.max(1, ...values);
  const w = 280, h = 56;
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${(i / Math.max(1, values.length - 1)) * w},${h - (v / max) * (h - 6) - 3}`).join(" ");
  return (
    <figure className="rounded-xl border border-border bg-surface p-4">
      <figcaption className="text-sm text-muted">{label} <span className="text-text">(peak {max})</span></figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${label} over time`} className="mt-2 h-14 w-full">
        <path d={path} fill="none" stroke="var(--primary)" strokeWidth="2" />
      </svg>
    </figure>
  );
}

function Table({ title, rows, empty }: { title: string; rows: [string, string | number][]; empty: string }) {
  return (
    <section aria-label={title} className="rounded-xl border border-border bg-surface p-4">
      <h2 className="mb-2 text-sm font-medium text-muted">{title}</h2>
      {rows.length === 0 ? <p className="text-sm text-muted">{empty}</p> : (
        <ul className="space-y-1 text-sm">{rows.map(([k, v]) => <li key={k} className="flex justify-between gap-3"><span className="truncate">{k}</span><span className="tabular-nums text-muted">{v}</span></li>)}</ul>
      )}
    </section>
  );
}

export default function Insights() {
  const [hours, setHours] = useState(24 * 7);
  const [env, setEnv] = useState("production");
  const overview = useLoad(() => getOverview(hours, undefined, env), [hours, env]);
  const series = useLoad(() => getSeries(hours, undefined, env), [hours, env]);
  const failures = useLoad(() => getFailures(hours, undefined, env), [hours, env]);
  const gaps = useLoad(() => getGaps(hours, undefined, env), [hours, env]);
  const alerts = useLoad(getAlerts, []);
  const quality = useLoad(getReviewQuality, []);
  const o = overview.data;
  return (
    <>
      <PageHeader title="Insights" subtitle="How the agents are doing, from the conversations recorded in this period. Every figure shows what it is a share of.">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <div role="group" aria-label="Period" className="flex gap-1">
            {PERIODS.map((p) => (
              <button key={p.hours} aria-pressed={hours === p.hours} onClick={() => setHours(p.hours)}
                className={`rounded-lg px-3 py-1.5 ${hours === p.hours ? "bg-primary text-primary-text" : "border border-border hover:bg-border/40"}`}>{p.label}</button>))}
          </div>
          <label htmlFor="env" className="text-muted">Environment</label>
          <select id="env" value={env} onChange={(e) => setEnv(e.target.value)} className="rounded-lg border border-border bg-surface px-2 py-1.5">
            <option>production</option><option>staging</option><option>dev</option>
          </select>
        </div>
      </PageHeader>

      <AskBox env={env} />

      {quality.data && quality.data.reviewed > 0 && (
        <section aria-label="Human review" className="mb-4 grid gap-3 sm:grid-cols-3">
          <Stat title="Judged correct" ratio={quality.data.correctRate} hint="of reviewed conversations" />
          <Stat title="Hand-offs that were needed" ratio={quality.data.escalationCorrectness} hint="of reviewed hand-offs" />
          <Stat title="Unneeded hand-offs" ratio={quality.data.unneededEscalationRate} hint="of reviewed hand-offs" />
        </section>
      )}

      {alerts.data?.enabled && (alerts.data.active?.length ?? 0) > 0 && (
        <section aria-label="Active alerts" className="mb-4 rounded-xl border border-[var(--bad)] bg-[var(--bad-bg)] p-4 text-[var(--bad)]">
          <h2 className="font-semibold">Alerts firing now</h2>
          <ul className="mt-1 space-y-1 text-sm">{alerts.data.active!.map((a) => <li key={a.rule}><strong>{a.rule}</strong> since {formatTime(a.since)}: {a.samples} samples, value {Number(a.value).toPrecision(3)}</li>)}</ul>
        </section>)}

      {overview.loading && !o ? <Loading /> : overview.error ? <ErrorBox message={overview.error} onRetry={overview.reload} /> : o && (
        o.turns === 0 ? <Empty>No conversations were recorded in this period for {env}.</Empty> : (
          <div className="space-y-4">
            <p className="text-sm text-muted">{o.conversations} conversations · {o.turns} turns · {o.tokens.total.toLocaleString()} tokens{o.estimatedCost ? ` · about ${o.estimatedCost.amount} in model cost` : ""}{o.truncated ? " · showing the most recent turns only" : ""}</p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat title="Contained" ratio={o.containmentRate} hint="conversations that never reached a person" />
              <Stat title="Escalated turns" ratio={o.escalationRate} hint="of all turns" />
              <Stat title="Guardrail blocks" ratio={o.guardrailBlockRate} hint="of all turns" />
              <Stat title="Tool errors" ratio={o.toolErrorRate} hint="of turns that used tools" />
              <Stat title="Errors" ratio={o.errorRate} hint="of all turns" />
              <Stat title="Fallback model" ratio={o.fallbackModelRate} hint="of model calls" />
              <div className="rounded-xl border border-border bg-surface p-4"><p className="text-sm text-muted">Reply time</p>
                <p className="mt-1 text-2xl font-semibold">{o.latencySeconds.p95 ?? "–"}{o.latencySeconds.p95 !== null && " s"}</p><p className="mt-1 text-xs text-muted">95th percentile · median {o.latencySeconds.p50 ?? "–"} s</p></div>
              <div className="rounded-xl border border-border bg-surface p-4"><p className="text-sm text-muted">Customer rating</p>
                <p className="mt-1 text-2xl font-semibold">{o.satisfaction.average ?? "–"}{o.satisfaction.average !== null && " / 5"}</p><p className="mt-1 text-xs text-muted">{o.satisfaction.responses} ratings · {pct(o.satisfaction.responseRate)} of conversations</p></div>
            </div>
            {series.data && <div className="grid gap-4 md:grid-cols-3">
              <Spark points={series.data.points} pick={(p) => p.turns} label="Turns" />
              <Spark points={series.data.points} pick={(p) => p.escalated} label="Escalated turns" />
              <Spark points={series.data.points} pick={(p) => p.errors} label="Errors" />
            </div>}
            <div className="grid gap-4 md:grid-cols-2">
              <section aria-label="Why things went wrong" className="rounded-xl border border-border bg-surface p-4">
                <h2 className="mb-2 text-sm font-medium text-muted">Why things went wrong</h2>
                {failures.data?.length ? <ul className="space-y-2 text-sm">{failures.data.map((c) => (
                  <li key={c.cause}><div className="flex justify-between gap-3"><span>{c.cause}</span><span className="tabular-nums text-muted">{c.count} · {pct(c.share)}</span></div>
                    <div className="text-xs">{c.exampleTraceIds.map((id) => <Link key={id} className="mr-2 text-primary underline" href={`/conversations/${id}`}>example</Link>)}</div></li>))}</ul>
                  : <p className="text-sm text-muted">Nothing went wrong in this period.</p>}
              </section>
              {o.journeys && <Table title="Journeys" rows={Object.entries(o.journeys).map(([n, v]): [string, string] => [n, `${v.reached} reached · ${v.completed ? `${pct(v.completed)} completed` : "completion cannot be measured"} · ${v.handedOff} handed to a person`])} empty="" />}
              {o.languages && <Table title="Languages customers wrote in" rows={Object.entries(o.languages.byLanguage).map(([c, v]): [string, string] => [c, `${v.conversations} conversations · ${pct(v.containmentRate)} contained`])} empty="" />}
              <Table title="Handed to a person because" rows={Object.entries(o.handoffs.byTrigger)} empty="No hand-offs." />
              <Table title="What customers asked that the knowledge could not answer" rows={(gaps.data?.unansweredSearches ?? []).map((g) => [g.query, g.count])} empty="Every search found something." />
              <Table title="What customers said before a hand-off" rows={(gaps.data?.messagesBeforeHandoff ?? []).map((g) => [g.message, g.count])} empty="No agent-side hand-offs." />
              <Table title="Tools used" rows={Object.entries(o.tools.used)} empty="No tools were used." />
              <Table title="Guardrails that blocked something" rows={Object.entries(o.guardrails)} empty="No blocks." />
            </div>
            <p className="text-xs text-muted">{o.note}</p>
          </div>))}
    </>
  );
}
