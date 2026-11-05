"use client";
import Link from "next/link";
import { use } from "react";
import { getTrace, useLoad } from "@northcx/api-client";
import { ErrorBox, Loading, PageHeader, StatusBadge, TraceTimeline } from "@northcx/ui";

export default function TracePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading, reload } = useLoad(() => getTrace(id), [id]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const trace = data!;
  const reply = [...trace.events].reverse().find((e) => e.type === "reply");
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-primary underline" href="/conversations">← Conversations</Link></p>
      <PageHeader title="Trace" subtitle={`Agent ${trace.agent_id}${trace.agent_version ? ` v${trace.agent_version}` : " (spec file)"} · session ${trace.session_id.slice(0, 8)} · ${trace.events.length} events`}>
        {reply && <StatusBadge status={String(reply.data.status)} />}
      </PageHeader>
      <TraceTimeline events={trace.events} />
    </>
  );
}
