"use client";
import Link from "next/link";
import { getAlerts, getOverview, listApprovals, listHandoffs, listAgents, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, StatTile } from "@northcx/ui";

const pct = (r?: { value: number | null }) => (r && r.value !== null ? `${Math.round(r.value * 100)}%` : "–");

export default function Overview() {
  const { can } = useMe();
  const { data, error, loading, reload } = useLoad(async () => {
    const [approvals, handoffs, agents] = await Promise.all([listApprovals("pending"), listHandoffs("open"), listAgents()]);
    // Insights and alerts need their own permissions; without them the page still works with what it can read.
    const overview = await getOverview(24 * 7).catch(() => null);
    const alerts = await getAlerts().catch(() => null);
    return { approvals, handoffs, agents, overview, alerts };
  });
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const { approvals, handoffs, agents, overview, alerts } = data!;
  const firing = alerts?.active ?? [];
  const attention = [
    ...firing.map((a) => ({ key: `a-${a.rule}`, kind: "Alert", text: `${a.rule}: value ${Number(a.value).toPrecision(3)} over ${a.samples} samples`, href: "/monitoring", tone: "bad" as const })),
    ...approvals.slice(0, 5).map((a) => ({ key: `p-${a.id}`, kind: "Approval", text: `${a.tool} is waiting: ${a.reason}`, href: "/approvals", tone: "warn" as const })),
    ...handoffs.slice(0, 5).map((h) => ({ key: `h-${h.id}`, kind: "Hand-off", text: `${h.reason || h.trigger} (${h.agentId})`, href: "/handoffs", tone: "warn" as const })),
  ];
  return (
    <>
      <PageHeader title="Overview" subtitle="What needs attention across your agents. Figures are for the last 7 days and your selected environment." />
      <ul className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <li><StatTile label="Conversations" value={overview?.conversations ?? "–"} hint={overview ? `${overview.turns} turns` : "Insights not available to your role"} /></li>
        <li><StatTile label="Resolved (provisional)" value={pct(overview?.resolutionRate)} hint={overview ? `contained ${pct(overview.containmentRate)} · ${overview.resolutionRate.pending} pending` : undefined} /></li>
        <li><StatTile label="Open hand-offs" value={handoffs.length} tone={handoffs.length ? "warn" : undefined} hint={handoffs.length ? "people are needed" : "none waiting"} /></li>
        <li><StatTile label="Pending approvals" value={approvals.length} tone={approvals.length ? "warn" : undefined} hint={approvals.length ? "agents are waiting" : "none waiting"} /></li>
      </ul>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <GlassCard title="Needs attention" className="lg:col-span-2">
          {attention.length === 0 ? <Empty>Nothing needs you right now.</Empty> : (
            <ul className="divide-y divide-border">
              {attention.map((a) => (
                <li key={a.key} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span><span className={`mr-2 rounded-full px-2 py-0.5 text-xs ${a.tone === "bad" ? "bg-[var(--bad-bg)] text-[var(--bad)]" : "bg-[var(--warn-bg)] text-[var(--warn)]"}`}>{a.kind}</span>{a.text}</span>
                  <Link href={a.href} className="btn">Open</Link>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
        <GlassCard title={`Agents (${agents.length})`} action={<Link href="/agents" className="text-xs text-primary underline">All agents</Link>}>
          <ul className="space-y-2 text-sm">
            {agents.slice(0, 8).map((a) => (
              <li key={a.id} className="flex items-center justify-between"><Link href={`/agents/${a.id}`} className="font-medium hover:underline">{a.id}</Link>
                <span className="text-xs text-muted">{a.version ? `v${a.version}` : "from file"}{a.model ? ` · ${a.model}` : ""}</span></li>
            ))}
          </ul>
        </GlassCard>
      </div>
      {overview && (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <GlassCard title="Hand-offs by trigger">
            {Object.keys(overview.handoffs.byTrigger).length === 0 ? <Empty>No hand-offs in this period.</Empty> : (
              <ul className="space-y-1 text-sm">{Object.entries(overview.handoffs.byTrigger).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span className="text-muted">{v}</span></li>)}</ul>
            )}
          </GlassCard>
          <GlassCard title="Tools used">
            {Object.keys(overview.tools.used).length === 0 ? <Empty>No tool calls in this period.</Empty> : (
              <ul className="space-y-1 text-sm">{Object.entries(overview.tools.used).slice(0, 6).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span className="text-muted">{v}{overview.tools.errors[k] ? ` · ${overview.tools.errors[k]} failed` : ""}</span></li>)}</ul>
            )}
          </GlassCard>
          <GlassCard title="Satisfaction" action={can("insights:read") ? <Link href="/insights" className="text-xs text-primary underline">Insights</Link> : undefined}>
            <p className="text-3xl font-bold">{overview.satisfaction.average ?? "–"}</p>
            <p className="text-xs text-muted">{overview.satisfaction.responses} ratings · response rate {pct(overview.satisfaction.responseRate)}</p>
          </GlassCard>
        </div>
      )}
      <p className="mt-4 text-xs text-muted">{overview?.note}</p>
    </>
  );
}
