"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { searchKnowledge, type Passage } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, PageHeader } from "@northcx/ui";

function Search() {
  const params = useSearchParams();
  const router = useRouter();
  const initial = params.get("q") ?? "";
  const [q, setQ] = useState(initial);
  const [results, setResults] = useState<Passage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (query: string) => {
    if (!query.trim()) return;
    setBusy(true); setError(null);
    try { setResults(await searchKnowledge(query.trim())); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { if (initial) void run(initial); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [initial]);
  return (
    <>
      <PageHeader title="Search" subtitle="Search your knowledge base. Conversations and hand-offs will join it later." />
      <form onSubmit={(e) => { e.preventDefault(); router.replace(`/search?q=${encodeURIComponent(q)}`); void run(q); }} className="glass flex gap-2 p-3" role="search">
        <label htmlFor="s-q" className="sr-only">Search</label>
        <input id="s-q" className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="What do you want to know?" />
        <button className="btn btn-primary" disabled={busy}>Search</button>
      </form>
      <div className="mt-4 space-y-3" aria-live="polite">
        {error && <ErrorBox message={error} />}
        {results && results.length === 0 && <Empty>Nothing found for “{initial || q}”. Try fewer or different words.</Empty>}
        {results?.map((p, i) => (
          <GlassCard key={`${p.documentId}-${i}`} title={p.title} action={<span className="text-xs text-muted">{p.stale ? "may be out of date · " : ""}{p.via ? `${p.via} · ` : ""}score {p.score.toFixed(2)}</span>}>
            {p.section && <p className="text-xs text-muted">{p.section}</p>}
            <p className="mt-1 text-sm">{p.text}</p>
            <p className="mt-2 text-xs text-muted">Source {p.sourceId}{p.url ? <> · <a className="underline" href={p.url} target="_blank" rel="noreferrer noopener">open the page</a></> : null}</p>
          </GlassCard>
        ))}
      </div>
    </>
  );
}
export default function Page() { return <Suspense fallback={null}><Search /></Suspense>; }
