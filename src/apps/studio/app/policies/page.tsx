"use client";
import { policyLibrary, useLoad } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

export default function Policies() {
  const { data, error, loading, reload } = useLoad(() => policyLibrary());
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  return (
    <>
      <PageHeader title="Policies" subtitle="Ready-made rules an agent can use. Each one ships with cases that show what it allows and what it blocks." />
      <p className="mb-3 text-sm text-muted">{data!.note} This page is read-only for now; organization-wide policy sets, review and locking are planned.</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {data!.policies.map((p) => (
          <GlassCard key={p.name} title={p.name}>
            <p className="text-sm">{p.description}</p>
            {Object.keys(p.exampleConfig).length > 0 && <p className="mt-2 text-xs text-muted">Example setting: <code>{JSON.stringify(p.exampleConfig)}</code></p>}
            <details className="mt-2 text-sm"><summary className="cursor-pointer">{p.cases.length} proof case{p.cases.length === 1 ? "" : "s"}</summary>
              <ul className="mt-2 space-y-1 text-xs">{p.cases.map((c, i) => <li key={i}><span className={`pill mr-2 ${c.expected === "allowed" ? "" : "font-semibold"}`}>{c.expected}</span><code>{typeof c.input === "string" ? c.input : JSON.stringify(c.input)}</code></li>)}</ul></details>
          </GlassCard>
        ))}
      </div>
    </>
  );
}
