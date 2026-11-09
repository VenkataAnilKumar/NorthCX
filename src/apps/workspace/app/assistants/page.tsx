"use client";
import Link from "next/link";
import { listAgents, useLoad } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader } from "@northcx/ui";

export default function Assistants() {
  const { data, error, loading, reload } = useLoad(() => listAgents());
  return (
    <>
      <PageHeader title="Assistants" subtitle="Agents available on this server. Staff assistants (drafting, summaries, reports) arrive with the staff backend; for now you can talk to the customer-facing agents as a test." />
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : data && data.length === 0 ? <Empty>No agents are available.</Empty> : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data?.map((a) => (
            <li key={a.id} className="glass flex flex-col p-4">
              <div className="flex items-start justify-between gap-2"><h2 className="font-semibold">{a.id}</h2><span className="pill">{a.version ? `v${a.version}` : "from file"}</span></div>
              <p className="mt-1 line-clamp-4 flex-1 text-sm text-muted">{a.instructions}</p>
              <p className="mt-2 text-xs text-muted">{a.tools.length} tool{a.tools.length === 1 ? "" : "s"}{a.tools.some((t) => t.approval) ? " · some need approval" : ""}{a.model ? ` · ${a.model}` : ""}</p>
              <Link className="btn mt-3 self-start" href={`/pilot?agent=${a.id}`}>Start a test chat</Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
