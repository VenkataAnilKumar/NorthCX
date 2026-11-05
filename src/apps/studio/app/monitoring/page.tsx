"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { type AlertDelivery, type AlertEvent, formatTime, getAlerts, getFindings, getMonitorSummary, sendTestAlert, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader } from "@northcx/ui";

const SEVERITIES = ["critical", "warning", "info"];
const sevClass = (s: string) => (s === "critical" ? "border-[var(--bad)] text-[var(--bad)]" : s === "warning" ? "border-[var(--warn)] text-[var(--warn)]" : "border-border text-muted");

function Delivery({ d }: { d?: AlertDelivery }) {
  if (!d) return <span className="text-xs text-muted">–</span>;
  const text = { sent: `Delivered${d.attempts > 1 ? ` after ${d.attempts} tries` : ""}`, retrying: "Sending…", failed: `Not delivered after ${d.attempts} tries${d.error ? ` (${d.error})` : ""}`, not_configured: "No webhook set up" }[d.status];
  const tone = d.status === "sent" ? "text-[var(--ok)]" : d.status === "failed" ? "text-[var(--bad)]" : "text-muted";
  return <span className={`text-xs ${tone}`}>{text}</span>;
}

export default function Monitoring() {
  const { can } = useMe();
  const [tick, setTick] = useState(0);
  useEffect(() => { const t = setInterval(() => setTick((n) => n + 1), 30_000); return () => clearInterval(t); }, []);
  const [rule, setRule] = useState("");
  const [severity, setSeverity] = useState("");
  const alerts = useLoad(getAlerts, [tick]);
  const summary = useLoad(getMonitorSummary, [tick]);
  const findings = useLoad(() => getFindings({ rule: rule || undefined, severity: severity || undefined }), [rule, severity, tick]);
  const [test, setTest] = useState<AlertEvent | null>(null);
  const [testErr, setTestErr] = useState<string | null>(null);
  async function runTest() {
    setTestErr(null); setTest(null);
    try { setTest(await sendTestAlert()); alerts.reload(); } catch (e) { setTestErr((e as Error).message); }
  }
  const a = alerts.data;
  return (
    <>
      <PageHeader title="Monitoring" subtitle="What needs attention now: alerts on how the agents are doing, and what the always-on checks flagged. Refreshes every 30 seconds." />
      {alerts.error && <ErrorBox message={alerts.error} onRetry={alerts.reload} />}
      {alerts.loading && !a && <Loading />}
      {a && !a.enabled && <Empty>Alerts are switched off on this server (<code>NORTHCX_ALERTS=off</code>; remove it to switch them on). The checks below still run.</Empty>}
      {a?.enabled && (
        <>
          <section aria-label="Alert status" className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-1 rounded-xl border border-border bg-surface p-4 text-sm">
            <span>Last checked: {a.lastRun ? formatTime(a.lastRun) : "not yet"}</span>
            <span>Webhook: {a.webhook ? "set up" : "not set up"}</span>
            {(a.undelivered ?? 0) > 0 && <span role="alert" className="text-[var(--bad)]">{a.undelivered} alert{a.undelivered === 1 ? "" : "s"} could not be delivered</span>}
            {can("keys:manage") && <button onClick={() => void runTest()} className="ml-auto rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Send a test alert</button>}
          </section>
          {test && <p role="status" className="mb-4 text-sm">Test alert: <Delivery d={test.delivery} /></p>}
          {testErr && <ErrorBox message={testErr} />}

          <section aria-label="Active alerts" className="mb-6">
            <h2 className="mb-2 font-semibold">Active alerts</h2>
            {(a.active ?? []).length === 0 ? <Empty>Nothing is wrong right now.</Empty> : (
              <ul className="space-y-2">{(a.active ?? []).map((x) => (
                <li key={x.rule} className={`rounded-xl border bg-surface p-3 text-sm ${sevClass(x.severity)}`}>
                  <strong>{x.rule}</strong> <span className="text-xs">({x.severity})</span> · since {formatTime(x.since)} · {x.samples} conversations in the window
                </li>))}
              </ul>
            )}
          </section>

          <section aria-label="Alert history" className="mb-6">
            <h2 className="mb-2 font-semibold">Recent alert events</h2>
            {(a.recent ?? []).length === 0 ? <Empty>No alerts have fired since the server started. (This history is kept in memory; the findings below are permanent.)</Empty> : (
              <div className="overflow-x-auto rounded-xl border border-border bg-surface">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-muted"><tr><th className="p-2">When</th><th className="p-2">Event</th><th className="p-2">Rule</th><th className="p-2">Detail</th><th className="p-2">Delivery</th></tr></thead>
                  <tbody>{(a.recent ?? []).map((e, i) => (
                    <tr key={i} className="border-t border-border align-top">
                      <td className="p-2 whitespace-nowrap">{formatTime(e.at)}</td><td className="p-2">{e.event.replace("alert.", "")}</td><td className="p-2">{e.rule}</td>
                      <td className="p-2">{e.detail}</td><td className="p-2"><Delivery d={e.delivery} /></td>
                    </tr>))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section aria-label="Alert rules" className="mb-6">
            <h2 className="mb-2 font-semibold">Rules</h2>
            <ul className="grid gap-2 sm:grid-cols-2">{(a.rules ?? []).map((r) => (
              <li key={r.name} className="rounded-xl border border-border bg-surface p-3 text-sm">
                <strong>{r.name}</strong> <span className={`rounded-full border px-2 py-0.5 text-xs ${sevClass(r.severity)}`}>{r.severity}</span>
                <p className="text-xs text-muted">{r.metric.replaceAll("_", " ")} above {r.threshold} over {r.windowMinutes} min{r.minSamples ? `, at least ${r.minSamples} conversations` : ""}</p>
              </li>))}
            </ul>
          </section>
        </>
      )}

      <section aria-label="Flagged conversations">
        <h2 className="mb-2 font-semibold">Flagged by the always-on checks {summary.data && <span className="text-sm font-normal text-muted">({summary.data.total} so far)</span>}</h2>
        <div className="mb-3 flex flex-wrap gap-3 text-sm">
          <label>Check <select value={rule} onChange={(e) => setRule(e.target.value)} className="ml-1 rounded-lg border border-border bg-surface px-2 py-1">
            <option value="">All</option>{(summary.data?.rules ?? []).map((r) => <option key={r}>{r}</option>)}</select></label>
          <label>Severity <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="ml-1 rounded-lg border border-border bg-surface px-2 py-1">
            <option value="">All</option>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}</select></label>
        </div>
        {summary.data && Object.keys(summary.data.counts).length > 0 && (
          <p className="mb-3 flex flex-wrap gap-2 text-xs">{Object.entries(summary.data.counts).map(([r, by]) => (
            <span key={r} className="rounded-full border border-border px-2 py-0.5">{r}: {Object.values(by).reduce((x, y) => x + y, 0)}</span>))}</p>
        )}
        {findings.error && <ErrorBox message={findings.error} onRetry={findings.reload} />}
        {findings.data && findings.data.length === 0 && <Empty>Nothing flagged.</Empty>}
        <ul className="space-y-2">{(findings.data ?? []).map((f) => (
          <li key={f.id} className="rounded-xl border border-border bg-surface p-3 text-sm">
            <span className={`mr-2 rounded-full border px-2 py-0.5 text-xs ${sevClass(f.severity)}`}>{f.severity}</span><strong>{f.rule}</strong> · {f.detail}
            <span className="block text-xs text-muted">{formatTime(f.created_at)}{f.agent_id && f.agent_id !== "-" ? ` · ${f.agent_id}` : ""}
              {f.trace_id && f.trace_id !== "-" && <> · <Link className="underline" href={`/conversations/${f.trace_id}`}>open the trace</Link></>}</span>
          </li>))}
        </ul>
      </section>
    </>
  );
}
