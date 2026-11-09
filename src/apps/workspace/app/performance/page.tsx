"use client";
import { useState } from "react";
import { performance, useLoad, useMe, type PerfSeries, type TimeStats } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const span = (s: number | null) => (s === null ? "no data" : s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

function Stat({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <div className="rounded-xl border border-border p-3"><p className="text-xs text-muted">{label}</p><p className="text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted">{note}</p></div>;
}

function Bars({ series, label }: { series: PerfSeries[]; label: string }) {
  const max = Math.max(1, ...series.map((s) => s.count));
  return (
    <figure aria-label={label} className="mt-3">
      <div className="flex h-20 items-end gap-1" role="img" aria-label={`${label}: ${series.map((s) => `${s.day} ${s.count}`).join(", ")}`}>
        {series.map((s) => <div key={s.day} title={`${s.day}: ${s.count}`} className="flex-1 rounded-t bg-[var(--accent)]" style={{ height: `${Math.max(4, (s.count / max) * 100)}%`, opacity: s.count ? 1 : 0.25 }} />)}
      </div>
      <figcaption className="mt-1 text-xs text-muted">{series[0]?.day} to {series[series.length - 1]?.day}, items per day</figcaption>
    </figure>
  );
}

const times = (t: TimeStats) => `${span(t.medianSeconds)} typical, ${span(t.p90Seconds)} slowest tenth (${t.count})`;

export default function Page() {
  const { can } = useMe();
  const [days, setDays] = useState(7);
  const [people, setPeople] = useState(false);
  const { data, error, loading, reload } = useLoad(() => performance(days, people && can("audit:read")), [days, people]);
  return (
    <>
      <PageHeader title="Performance" subtitle="Your numbers and the team's. Each figure says what it counts." />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <label>Period <select className="field ml-1" value={days} onChange={(e) => setDays(Number(e.target.value))}>{[7, 14, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select></label>
        {can("audit:read") && <label className="flex items-center gap-2"><input type="checkbox" checked={people} onChange={(e) => setPeople(e.target.checked)} /> Show people (recorded in the audit log)</label>}
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <GlassCard title="You">
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Hand-offs you resolved" value={data.mine.handoffsResolved} note={data.counts.handoffsResolved} />
              <Stat label="Approvals you decided" value={data.mine.approvalsDecided} note={`${data.mine.approved} approved, ${data.mine.rejected} rejected`} />
            </div>
            <p className="mt-3 text-sm">Hand-offs: {times(data.mine.handoffTime)}</p>
            <p className="text-sm">Approvals: {times(data.mine.approvalTime)}</p>
            <Bars series={data.mine.series} label="Your items per day" />
          </GlassCard>
          <GlassCard title="Team">
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Hand-offs resolved" value={data.team.handoffsResolved} note={`by ${data.team.handlers} people`} />
              <Stat label="Approvals decided" value={data.team.approvalsDecided} note={data.counts.approvalsDecided} />
              <Stat label="Waiting now" value={data.team.openNow} note={data.team.oldestOpenSeconds === null ? "nothing is waiting" : `oldest waiting ${span(data.team.oldestOpenSeconds)}`} />
              <Stat label="Arrived out of hours" value={data.team.afterHours} note="of the hand-offs resolved" />
            </div>
            <p className="mt-3 text-sm">Hand-offs: {times(data.team.handoffTime)}</p>
            <p className="text-sm">Approvals: {times(data.team.approvalTime)}</p>
            <Bars series={data.team.series} label="Team items per day" />
            {data.team.people && <ul className="mt-3 space-y-1 text-sm" aria-label="People">{data.team.people.map((p) => <li key={p.name}>{p.name}: {p.items}</li>)}</ul>}
          </GlassCard>
        </div>
      )}
    </>
  );
}
