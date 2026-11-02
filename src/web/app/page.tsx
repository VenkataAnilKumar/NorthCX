"use client";
import Link from "next/link";
import { listApprovals, listTraces } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { ErrorBox, Loading, PageHeader } from "@/components/states";

export default function Overview() {
  const { data, error, loading, reload } = useLoad(async () => {
    const [traces, pending] = await Promise.all([listTraces(), listApprovals("pending")]);
    return { traces, pending };
  });
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const { traces, pending } = data!;
  const total = traces.length;
  const count = (s: string) => traces.filter((t) => t.status === s).length;
  const rate = (n: number) => (total ? `${Math.round((n / total) * 100)}%` : "–");
  const cards = [
    { label: "Conversations", value: String(total), href: "/conversations" },
    { label: "Completed", value: rate(count("completed")), href: "/conversations?status=completed" },
    { label: "Escalated", value: rate(count("escalated")), href: "/conversations?status=escalated" },
    { label: "Pending approvals", value: String(pending.length), href: "/approvals" },
  ];
  return (
    <>
      <PageHeader title="Overview" subtitle="Runs since the backend started (in-memory storage)." />
      <ul className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {cards.map((c) => (
          <li key={c.label}>
            <Link href={c.href} className="block rounded-xl border border-border bg-surface p-4 shadow-sm hover:border-primary">
              <div className="text-sm text-muted">{c.label}</div>
              <div className="mt-1 text-3xl font-semibold">{c.value}</div>
            </Link>
          </li>
        ))}
      </ul>
      {total === 0 && <p className="mt-6 text-sm text-muted">No conversations yet. Try the <Link className="underline" href="/chat">test console</Link>.</p>}
    </>
  );
}
