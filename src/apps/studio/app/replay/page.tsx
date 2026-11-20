"use client";
import Link from "next/link";
import { Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { getReviewContext, getSessionTurns, getTrace, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader } from "@northcx/ui";
import { ReplayPlayer } from "@/components/replay-player";
import { buildFrames } from "@/lib/replay";

function Replay() {
  const session = useSearchParams().get("session") ?? "";
  const { can } = useMe();
  const loaded = useLoad(async () => {
    if (!session) return null;
    const [context, turns] = await Promise.all([getReviewContext(session), getSessionTurns(session)]);
    const traces = await Promise.all(context.traces.map((t) => getTrace(t.id)));
    return { traces, turns };
  }, [session]);
  const frames = useMemo(() => (loaded.data ? buildFrames(loaded.data.traces, loaded.data.turns) : []), [loaded.data]);
  const originals = useMemo(() => Object.fromEntries((loaded.data?.turns ?? []).map((t) => [t.turn, t.reply])), [loaded.data]);
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-primary underline" href="/conversations">← Conversations</Link></p>
      <PageHeader title="Replay" subtitle="Step through a stored conversation, one event at a time. This only reads what was recorded." />
      {!session ? <Empty>Choose a conversation from the list and select Replay.</Empty>
        : loaded.loading && !loaded.data ? <Loading />
        : loaded.error ? <ErrorBox message={loaded.error} onRetry={loaded.reload} />
        : <ReplayPlayer sessionId={session} frames={frames} originals={originals} canRerun={can("simulations:run")} />}
    </>
  );
}

export default function ReplayPage() {
  return <Suspense fallback={<Loading />}><Replay /></Suspense>;
}
