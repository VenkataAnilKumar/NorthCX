"use client";
import Link from "next/link";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { formatTime, listTraces } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

const filters = [["", "All"], ["completed", "Completed"], ["escalated", "Escalated"], ["needs_approval", "Needs approval"]];

function List() {
  const params = useSearchParams();
  const router = useRouter();
  const status = params.get("status") ?? "";
  const { data, error, loading, reload } = useLoad(() => listTraces(status || undefined), [status]);
  return (
    <>
      <PageHeader title="Conversations" subtitle="Every run, with its trace.">
        <div role="group" aria-label="Filter by status" className="flex gap-1">
          {filters.map(([v, l]) => (
            <button key={v} aria-pressed={status === v} onClick={() => router.push(v ? `/conversations?status=${v}` : "/conversations")}
              className={`rounded-lg px-3 py-1.5 text-sm ${status === v ? "bg-primary text-primary-text" : "border border-border hover:bg-border/40"}`}>{l}</button>
          ))}
        </div>
      </PageHeader>
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? <Empty>No conversations match.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-muted"><tr>
              <th className="p-3 font-medium">Started</th><th className="p-3 font-medium">Agent</th><th className="p-3 font-medium">Version</th><th className="p-3 font-medium">Session</th>
              <th className="p-3 font-medium">Tools</th><th className="p-3 font-medium">Status</th><th className="p-3"><span className="sr-only">Open</span></th>
            </tr></thead>
            <tbody>{data.map((t) => (
              <tr key={t.id} className="border-b border-border last:border-0">
                <td className="p-3 whitespace-nowrap">{formatTime(t.startedAt)}</td>
                <td className="p-3">{t.agentId}</td><td className="p-3">{t.agentVersion ? `v${t.agentVersion}` : "file"}</td>
                <td className="p-3 font-mono text-xs">{t.sessionId.slice(0, 8)}</td>
                <td className="p-3">{t.tools.join(", ") || "–"}</td>
                <td className="p-3"><StatusBadge status={t.status} /></td>
                <td className="p-3"><Link className="text-primary underline" href={`/conversations/${t.id}`}>View trace</Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function Conversations() {
  return <Suspense fallback={<Loading />}><List /></Suspense>;
}
