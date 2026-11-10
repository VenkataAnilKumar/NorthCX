"use client";
import { automations, customersEnabled, getTenantLimits, getTenantProvider, useLoad, useMe } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const LIMITS: Record<string, { label: string; unit: string }> = {
  requestsPerMinute: { label: "Requests per minute", unit: "requests" },
  maxOutputs: { label: "Saved outputs", unit: "items" },
  retentionDays: { label: "Keep outputs and run history", unit: "days" },
};
const SOURCE = { tenant: "set for this organization", platform: "platform default", none: "no limit" } as const;

export default function Org() {
  const { me } = useMe();
  const { data, error, loading, reload } = useLoad(async () => {
    const [limits, provider, customers, autos] = await Promise.all([getTenantLimits(), getTenantProvider().catch(() => null), customersEnabled().catch(() => null), automations().catch(() => null)]);
    return { limits, provider, customers, autos };
  }, []);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const { limits, provider, customers, autos } = data;
  return (
    <>
      <PageHeader title="Organization settings" subtitle="What applies to your organization. Limits and the model provider are set by whoever operates the platform; the switches below are changed where they live." />
      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard title="Organization">
          <dl className="grid grid-cols-[10rem_1fr] gap-y-1 text-sm">
            <dt className="text-muted">Identifier</dt><dd><code>{limits.tenant}</code></dd>
            <dt className="text-muted">You are</dt><dd>{me ? `${me.name} (${me.role.replace("_", " ")})` : "n/a"}</dd>
            <dt className="text-muted">Model provider</dt>
            <dd>{provider ? (provider.own ? <>Own provider: {provider.defaultModel} at {provider.baseUrl} <span className="text-muted">(key stored encrypted, never shown)</span></> : "The platform's shared provider") : "n/a"}</dd>
          </dl>
        </GlassCard>
        <GlassCard title="Limits">
          <table className="tbl"><caption className="sr-only">Limits for this organization</caption>
            <thead><tr><th>Limit</th><th>Value</th><th>Where it comes from</th></tr></thead>
            <tbody>{Object.entries(limits.limits).map(([k, v]) => (
              <tr key={k}><td>{LIMITS[k]?.label ?? k}</td><td>{v.value === null ? "none" : `${v.value.toLocaleString()} ${LIMITS[k]?.unit ?? ""}`}</td><td>{SOURCE[v.source]}</td></tr>))}</tbody></table>
          <p className="mt-2 text-xs text-muted">Read-only here. The platform operator changes limits.</p>
        </GlassCard>
        <GlassCard title="Switches">
          <ul className="space-y-1 text-sm">
            <li>Customer view in the Workspace: <b>{customers ? (customers.enabled ? "on" : "off") : "n/a"}</b></li>
            <li>Automations: <b>{autos ? (autos.enabled ? "on" : "off (kill switch)") : "n/a"}</b></li>
          </ul>
          <p className="mt-2 text-xs text-muted">Change these in the Workspace (Customers and Automations).</p>
        </GlassCard>
        <GlassCard title="Budgets and spending">
          <p className="text-sm">Token and money budgets are set on <a className="underline" href="/models">Models and budgets</a>; spending is on <a className="underline" href="/usage">Usage and billing</a>.</p>
        </GlassCard>
      </div>
    </>
  );
}
