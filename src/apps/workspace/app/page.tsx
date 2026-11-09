"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { listAgents, listApprovals, listHandoffs, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, StatusBadge } from "@northcx/ui";

export default function Home() {
  const { me } = useMe();
  const router = useRouter();
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useLoad(async () => {
    const [handoffs, approvals, agents] = await Promise.all([listHandoffs("open"), listApprovals("pending"), listAgents()]);
    return { handoffs, approvals, agents };
  });
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const first = me && !me.openMode ? me.name.split(/[ @]/)[0] : "";
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const { handoffs, approvals, agents } = data!;
  const needs = handoffs.length + approvals.length;
  return (
    <div className="mx-auto max-w-4xl pt-4">
      <h1 className="text-3xl font-semibold">{greeting}{first ? `, ${first}` : ""}</h1>
      <p className="mt-1 text-sm text-muted">{needs ? `${needs} thing${needs === 1 ? "" : "s"} need${needs === 1 ? "s" : ""} you.` : "Nothing is waiting for you."}</p>
      <form className="glass mt-5 p-4" onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`); }}>
        <label htmlFor="home-q" className="sr-only">Search knowledge</label>
        <input id="home-q" className="field text-base" placeholder="Search the knowledge base…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn btn-primary" type="submit">Search</button>
          <Link href="/pilot" className="btn">Start a task</Link>
        </div>
      </form>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <GlassCard title={`Hand-offs (${handoffs.length})`} action={<Link href="/inbox" className="text-xs text-primary underline">Open Inbox</Link>}>
          {handoffs.length === 0 ? <Empty>No conversations are waiting for a person.</Empty> : (
            <ul className="divide-y divide-border text-sm">{handoffs.slice(0, 4).map((h) => (
              <li key={h.id} className="py-2"><Link href={`/inbox?id=${h.id}`} className="font-medium hover:underline">{h.summary || h.reason || h.trigger}</Link><span className="ml-2 text-xs text-muted">{h.agentId}</span></li>
            ))}</ul>
          )}
        </GlassCard>
        <GlassCard title={`Approvals (${approvals.length})`} action={<Link href="/approvals" className="text-xs text-primary underline">Open Approvals</Link>}>
          {approvals.length === 0 ? <Empty>No approvals are waiting.</Empty> : (
            <ul className="divide-y divide-border text-sm">{approvals.slice(0, 4).map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 py-2"><span><span className="font-medium">{a.tool}</span> <span className="text-muted">{a.reason}</span></span><StatusBadge status={a.state} /></li>
            ))}</ul>
          )}
        </GlassCard>
      </div>
      <GlassCard title="Assistants" className="mt-4" action={<Link href="/assistants" className="text-xs text-primary underline">All</Link>}>
        <ul className="flex flex-wrap gap-2">{agents.map((a) => <li key={a.id}><Link className="pill" href={`/pilot?agent=${a.id}`}>{a.id}</Link></li>)}</ul>
      </GlassCard>
    </div>
  );
}
