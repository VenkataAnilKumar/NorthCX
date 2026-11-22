"use client";
import { type HealthCheck, systemHealth, useLoad } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const WORD: Record<HealthCheck["status"], string> = { ok: "Working", failing: "Not working", not_set_up: "Not set up" };
const TONE: Record<HealthCheck["status"], string> = { ok: "text-[var(--good)]", failing: "text-[var(--bad)]", not_set_up: "text-muted" };

function Row({ c }: { c: HealthCheck }) {
  return (
    <li className="py-3 text-sm">
      <p className="flex items-baseline gap-2"><strong>{c.name}</strong><span className={`font-medium ${TONE[c.status]}`}>{WORD[c.status]}</span></p>
      <p className="text-muted">{c.detail}</p>
      {c.action && <p className="mt-1">What to do: {c.action}</p>}
    </li>
  );
}

export default function SystemHealth() {
  const { data, error, loading, reload } = useLoad(() => systemHealth());
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const checks = data!.checks;
  const broken = checks.filter((c) => c.status === "failing");
  return (
    <>
      <PageHeader title="System health" subtitle="What is working, what is not, and what to do about it. Nothing here calls a model or sends a message, so opening this page costs nothing.">
        <button className="btn mt-2" onClick={reload}>Check again</button>
      </PageHeader>
      <p role="status" className={`mb-4 text-sm font-medium ${broken.length ? "text-[var(--bad)]" : "text-[var(--good)]"}`}>
        {broken.length ? `${broken.length} thing${broken.length === 1 ? " is" : "s are"} not working: ${broken.map((c) => c.name).join(", ")}.` : "Everything that is set up is working."}
      </p>
      <GlassCard title="Checks">
        <ul className="divide-y divide-border" aria-label="Checks">{checks.map((c) => <Row key={c.name} c={c} />)}</ul>
      </GlassCard>
    </>
  );
}
