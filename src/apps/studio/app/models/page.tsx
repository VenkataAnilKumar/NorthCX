"use client";
import { modelsOverview, useLoad } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader, StatTile } from "@northcx/ui";

const TIER: Record<string, string> = { local: "Local (your servers)", "private-cloud": "Private cloud (your account and region)", "public-cloud": "Public cloud (the provider's service)" };
const money = (n: number, c: string) => `${n.toFixed(4)} ${c}`;

export default function Models() {
  const { data, error, loading, reload } = useLoad(() => modelsOverview());
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const m = data!;
  const b = m.budget;
  return (
    <>
      <PageHeader title="Models and budgets" subtitle="Where text can go, which model answers, and what has been spent. Keys are never shown; providers, prices and rules are set in the providers and routing files." />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatTile label="Tokens today" value={b.tokensToday.toLocaleString()} hint={b.dailyTokenLimit ? `limit ${b.dailyTokenLimit.toLocaleString()} a day` : "no daily token limit"} />
        <StatTile label="Spent today" value={money(b.moneyToday, b.currency)} hint={b.dailyMoneyLimit ? `limit ${b.dailyMoneyLimit} ${b.currency} a day` : "no daily spending limit"} />
        <StatTile label="Fallback order" value={m.fallbacks?.length ? m.fallbacks.length : "none"} hint={m.fallbacks?.join(" → ") || "no fallback models"} />
      </div>
      {!m.configured ? <Empty>{m.note}</Empty> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <GlassCard title="Providers">
            <ul className="space-y-3">
              {m.providers.map((p) => (
                <li key={p.name} className="text-sm">
                  <p className="font-semibold">{p.name}{p.isDefault ? <span className="pill ml-2">default</span> : null}</p>
                  <p className="text-xs text-muted">{TIER[p.tier] ?? p.tier} · default model {p.defaultModel ?? "none"}</p>
                  <p className="text-xs text-muted">Tools {p.capabilities.tools ? "yes" : "no"} · images {p.capabilities.images ? "yes" : "no"} · documents {p.capabilities.documents ? "yes" : "no"}{p.capabilities.maxContextTokens ? ` · context ${p.capabilities.maxContextTokens.toLocaleString()} tokens` : ""}</p>
                  {Object.keys(p.prices).length ? <p className="text-xs text-muted">Prices per million tokens: {Object.entries(p.prices).map(([k, v]) => `${k} ${v.inputPerMillion} in / ${v.outputPerMillion} out ${v.currency}`).join("; ")}</p> : <p className="text-xs text-[var(--warn)]">No prices set: spending on this provider is not counted.</p>}
                </li>
              ))}
            </ul>
          </GlassCard>
          <GlassCard title="Data policy and routing">
            {m.routing ? (
              <div className="space-y-2 text-sm">
                <p><strong>Sensitive conversations</strong> may use: {m.routing.policy.sensitive.join(", ") || "no tier"}.</p>
                <p><strong>Other conversations</strong> may use: {m.routing.policy.normal.join(", ")}.</p>
                {m.routing.policy.publicCloudAllowedAgents.length > 0 && <p>Public cloud is allowed for: {m.routing.policy.publicCloudAllowedAgents.join(", ")} (every use is recorded).</p>}
                <p className="text-xs text-muted">A conversation is sensitive when the agent is marked sensitive, the customer is verified, personal data appears, or a topic word appears ({m.routing.sensitiveTopics.join(", ")}).</p>
                <p><strong>Rules</strong> (first match wins)</p>
                {m.routing.rules.length ? <ol className="list-decimal pl-5">{m.routing.rules.map((r) => <li key={r.name}>{r.name}: when {JSON.stringify(r.when)} use {r.use.tier ?? r.use.model}</li>)}</ol> : <p className="text-xs text-muted">No rules: the requested model, then the fallbacks.</p>}
                <p><strong>Qualification</strong>: {m.routing.qualification.required ? `a model serves an agent's customers only after it passes that agent's scenarios${m.routing.qualification.exempt.length ? `; trusted without a run: ${m.routing.qualification.exempt.join(", ")}` : ""}.` : "not required."}</p>
              </div>
            ) : <p className="text-sm text-muted">No routing rules file is set, so every conversation uses the default provider and its fallbacks. Set NORTHCX_ROUTING_RULES_FILE to keep sensitive conversations on private tiers.</p>}
          </GlassCard>
        </div>
      )}
    </>
  );
}
