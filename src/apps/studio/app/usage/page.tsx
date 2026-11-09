"use client";
import { useState } from "react";
import { usageReport, useLoad } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, StatTile } from "@northcx/ui";

export default function Usage() {
  const [days, setDays] = useState(7);
  const { data, error, loading, reload } = useLoad(() => usageReport(days), [days]);
  return (
    <>
      <PageHeader title="Usage and billing" subtitle="Model tokens and spending per agent. Spending counts only answers from models that have a price in the budget currency." />
      <div className="mb-3 flex items-center gap-2 text-sm"><label htmlFor="days">Period</label>
        <select id="days" className="field w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))}>{[1, 7, 30, 90].map((d) => <option key={d} value={d}>{d === 1 ? "Today" : `Last ${d} days`}</option>)}</select></div>
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : data && (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <StatTile label="Tokens" value={data.totals.tokens.toLocaleString()} hint={`last ${data.days} day(s)`} />
            <StatTile label="Spent" value={`${data.totals.cost.toFixed(4)} ${data.currency}`} hint={data.limits.dailyMoneyLimit ? `daily limit ${data.limits.dailyMoneyLimit} ${data.currency}` : "no daily spending limit"} />
            <StatTile label="Agents with usage" value={data.byAgent.length} hint="of those that ran" />
          </div>
          {data.byAgent.length === 0 ? <Empty>No model usage in this period yet.</Empty> : (
            <GlassCard title="By agent">
              <table className="tbl"><caption className="sr-only">Tokens and spending by agent</caption>
                <thead><tr><th>Agent</th><th>Tokens</th><th>Spent ({data.currency})</th></tr></thead>
                <tbody>{data.byAgent.map((a) => <tr key={a.agent}><td>{a.agent}</td><td>{a.tokens.toLocaleString()}</td><td>{a.cost.toFixed(4)}</td></tr>)}</tbody></table>
              <details className="mt-3 text-sm"><summary className="cursor-pointer">By day</summary>
                <table className="tbl mt-2"><thead><tr><th>Day (UTC)</th><th>Agent</th><th>Tokens</th><th>Spent</th></tr></thead>
                  <tbody>{data.rows.map((r) => <tr key={`${r.day}-${r.agent}`}><td>{r.day}</td><td>{r.agent}</td><td>{r.tokens.toLocaleString()}</td><td>{r.cost.toFixed(4)}</td></tr>)}</tbody></table></details>
            </GlassCard>
          )}
        </>
      )}
    </>
  );
}
