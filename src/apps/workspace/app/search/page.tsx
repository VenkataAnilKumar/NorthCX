"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { workspaceSearch, type WorkspaceResult } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, PageHeader } from "@northcx/ui";

const KIND: Record<WorkspaceResult["kind"], string> = { knowledge: "Knowledge", conversation: "Conversation", handoff: "Hand-off" };
const HREF = (r: WorkspaceResult) => (r.kind === "handoff" ? `/inbox?id=${encodeURIComponent(r.id)}` : r.kind === "knowledge" ? "/library" : null);

function Search() {
  const params = useSearchParams();
  const router = useRouter();
  const initial = params.get("q") ?? "";
  const [q, setQ] = useState(initial);
  const [out, setOut] = useState<Awaited<ReturnType<typeof workspaceSearch>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (query: string) => {
    if (query.trim().length < 2) return;
    setBusy(true); setError(null);
    try { setOut(await workspaceSearch(query.trim())); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { if (initial) void run(initial); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [initial]);
  return (
    <>
      <PageHeader title="Search" subtitle="One search across your knowledge, conversations and hand-offs. You see only what your role allows, and customer details are masked." />
      <form onSubmit={(e) => { e.preventDefault(); router.replace(`/search?q=${encodeURIComponent(q)}`); void run(q); }} className="glass flex gap-2 p-3" role="search">
        <label htmlFor="s-q" className="sr-only">Search</label>
        <input id="s-q" className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="What do you want to find?" />
        <button className="btn btn-primary" disabled={busy}>Search</button>
      </form>
      <div className="mt-4 space-y-3" aria-live="polite">
        {error && <ErrorBox message={error} />}
        {out && out.skipped.length > 0 && <p className="text-sm text-muted" role="status">Not searched: {out.skipped.map((s) => `${s.source} (${s.reason})`).join(", ")}.</p>}
        {out && out.results.length === 0 && <Empty>Nothing found for “{initial || q}”. Try fewer or different words.</Empty>}
        {out?.results.map((r) => (
          <GlassCard key={`${r.kind}-${r.id}`} title={r.title} action={<span className="pill">{KIND[r.kind]}</span>}>
            <p className="text-sm">{r.snippet}</p>
            <p className="mt-2 text-xs text-muted">Why you can see this: {r.why}{HREF(r) ? <> · <a className="underline" href={HREF(r)!}>open</a></> : null}{r.url ? <> · <a className="underline" href={r.url} target="_blank" rel="noreferrer noopener">source page</a></> : null}</p>
          </GlassCard>
        ))}
      </div>
    </>
  );
}
export default function Page() { return <Suspense fallback={null}><Search /></Suspense>; }
