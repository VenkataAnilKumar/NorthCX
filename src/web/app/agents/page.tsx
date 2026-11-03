"use client";
import Link from "next/link";
import { listAgents } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/states";

export default function Agents() {
  const { data, error, loading, reload } = useLoad(listAgents);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  return (
    <>
      <PageHeader title="Agents" subtitle="What is live for each agent. Create, test and release new versions from Versions and releases.">
        <Link href="/agents/build" className="text-sm text-primary underline">Build an agent from your material</Link>
      </PageHeader>
      {!data?.length ? <Empty>No agents are configured.</Empty> : (
        <ul className="space-y-4">{data.map((a) => (
          <li key={a.id} className="rounded-xl border border-border bg-surface p-4">
            <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">{a.id}{a.version ? <span className="ml-2 text-sm font-normal text-muted">version {a.version}</span> : <span className="ml-2 text-sm font-normal text-muted">spec file</span>}</h2>
              <Link href={`/agents/${a.id}`} className="text-sm text-primary underline">Versions and releases</Link></div>
            <p className="mt-1 text-xs text-muted">Model: {a.model ?? "default"} · Max steps: {a.maxSteps}</p>
            <h3 className="mt-4 text-sm font-medium">Instructions</h3>
            <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm">{a.instructions}</pre>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="text-sm font-medium">Tools</h3>
                <ul className="mt-1 space-y-1 text-sm">{a.tools.map((t) => (
                  <li key={t.name}><code>{t.name}</code>{t.approval && <span className="ml-2 text-xs text-[var(--info)]">approval rule</span>}<div className="text-muted">{t.description}</div></li>
                ))}</ul>
              </div>
              <div>
                <h3 className="text-sm font-medium">Guardrails</h3>
                <p className="mt-1 text-sm text-muted">Input: {a.inputGuardrails.join(", ") || "none"}</p>
                <p className="text-sm text-muted">Replies and tools: {a.guardrails.join(", ") || "none"}</p>
              </div>
            </div>
          </li>))}
        </ul>
      )}
    </>
  );
}
