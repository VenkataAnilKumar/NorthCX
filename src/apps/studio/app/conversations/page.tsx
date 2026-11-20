"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { addTag, type ConversationRow, formatTime, listTraces, removeTag, searchConversations, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "@northcx/ui";

const filters = [["", "All"], ["completed", "Completed"], ["escalated", "Escalated"], ["needs_approval", "Needs approval"]];

function Found({ q, tag }: { q: string; tag: string }) {
  const { can } = useMe();
  const { data, error, loading, reload } = useLoad(() => searchConversations({ q: q || undefined, tag: tag || undefined }), [q, tag]);
  const [err, setErr] = useState<string | null>(null);
  async function change(fn: () => Promise<unknown>) { setErr(null); try { await fn(); reload(); } catch (e) { setErr((e as Error).message); } }
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data?.length) return <Empty>No conversations match.</Empty>;
  return (
    <div className="space-y-3">
      {err && <p role="alert" className="text-sm text-[var(--bad)]">{err}</p>}
      <ul className="space-y-2">{data.map((c: ConversationRow) => (
        <li key={c.sessionId} className="rounded-xl border border-border bg-surface p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">{c.firstMessage || "(no message)"}</span>
            <span className="flex items-center gap-2 text-xs text-muted">{formatTime(c.endedAt)} · {c.turns} turn{c.turns === 1 ? "" : "s"}{c.rating ? ` · rated ${c.rating}/5` : ""}</span>
          </div>
          <p className="mt-1 text-muted">{c.lastReply}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={c.lastStatus} />
            {c.handedOff && <span className="rounded bg-[var(--warn-bg)] px-1.5 py-0.5 text-xs text-[var(--warn)]">Handed to a person: {c.handoffTriggers.join(", ")}</span>}
            {c.tags.map((t) => (
              <span key={t} className="rounded bg-border/60 px-1.5 py-0.5 text-xs">{t}
                {can("conversations:tag") && <button aria-label={`Remove tag ${t}`} className="ml-1" onClick={() => change(() => removeTag(c.sessionId, t))}>×</button>}</span>))}
            {can("conversations:tag") && (
              <form onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const v = String(f.get("tag") ?? "").trim().toLowerCase(); if (v) change(() => addTag(c.sessionId, v)); e.currentTarget.reset(); }}>
                <label className="sr-only" htmlFor={`tag-${c.sessionId}`}>Add a tag</label>
                <input id={`tag-${c.sessionId}`} name="tag" placeholder="add tag" className="w-28 rounded border border-border bg-bg px-1.5 py-0.5 text-xs" />
              </form>)}
            <span className="ml-auto flex gap-3 text-xs">
              <Link className="text-primary underline" href={`/replay?session=${encodeURIComponent(c.sessionId)}`}>Replay</Link>
              {c.traceIds.length > 0 && <Link className="text-primary underline" href={`/conversations/${c.traceIds[c.traceIds.length - 1]}`}>View trace</Link>}
            </span>
          </div>
        </li>))}
      </ul>
    </div>
  );
}

function List() {
  const params = useSearchParams();
  const router = useRouter();
  const status = params.get("status") ?? "";
  const q = params.get("q") ?? "";
  const tag = params.get("tag") ?? "";
  const { data, error, loading, reload } = useLoad(() => listTraces(status || undefined), [status]);
  return (
    <>
      <PageHeader title="Conversations" subtitle="Every run, with its trace. Search what was said, or filter by tag.">
        <form role="search" className="flex items-center gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const p = new URLSearchParams(); if (f.get("q")) p.set("q", String(f.get("q"))); if (f.get("tag")) p.set("tag", String(f.get("tag"))); router.push(`/conversations${p.size ? `?${p}` : ""}`); }}>
          <label htmlFor="q" className="sr-only">Search conversations</label>
          <input id="q" name="q" defaultValue={q} placeholder="Search words" className="w-44 rounded-lg border border-border bg-surface px-2 py-1.5" />
          <label htmlFor="tagfilter" className="sr-only">Tag</label>
          <input id="tagfilter" name="tag" defaultValue={tag} placeholder="tag" className="w-24 rounded-lg border border-border bg-surface px-2 py-1.5" />
          <button className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Search</button>
        </form>
        <div role="group" aria-label="Filter by status" className="flex gap-1">
          {filters.map(([v, l]) => (
            <button key={v} aria-pressed={status === v} onClick={() => router.push(v ? `/conversations?status=${v}` : "/conversations")}
              className={`rounded-lg px-3 py-1.5 text-sm ${status === v ? "bg-primary text-primary-text" : "border border-border hover:bg-border/40"}`}>{l}</button>
          ))}
        </div>
      </PageHeader>
      {(q || tag) ? <Found q={q} tag={tag} /> : loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? <Empty>No conversations match.</Empty> : (
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
                <td className="p-3 whitespace-nowrap"><Link className="text-primary underline" href={`/conversations/${t.id}`}>View trace</Link> · <Link className="text-primary underline" href={`/replay?session=${encodeURIComponent(t.sessionId)}`}>Replay</Link></td>
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
