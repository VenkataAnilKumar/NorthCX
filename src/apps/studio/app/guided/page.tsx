"use client";
import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { type Catalog, getCatalog, getLive, listAgents, previewSpec, saveSpec, type SpecPreview, useLoad, useMe } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader } from "@northcx/ui";
import { ToolPicker } from "@/components/tool-picker";
import { TryPanel } from "@/components/try-panel";
import { guidedSteps, type StepState } from "@/lib/guided";

type Spec = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const card = "rounded-xl border border-border bg-surface p-4";
const PILL: Record<StepState, string> = { done: "bg-[var(--ok-bg)] text-[var(--ok)]", next: "bg-[var(--info-bg)] text-[var(--info)]", blocked: "bg-border/60 text-muted" };
const PILL_TEXT: Record<StepState, string> = { done: "Done", next: "Next", blocked: "Waiting" };

function Choose() {
  const router = useRouter();
  const agents = useLoad(listAgents, []);
  const [pick, setPick] = useState("");
  if (agents.loading && !agents.data) return <Loading />;
  if (agents.error) return <ErrorBox message={agents.error} onRetry={agents.reload} />;
  return (
    <section aria-label="Choose the agent" className={card}>
      <h2 className="font-medium">Step 1: Choose the agent</h2>
      <p className="mb-3 text-sm text-muted">Work on an agent you already have, or start a new one from a ready-made template or from your own procedures and conversations.</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">Agent
          <select className="field ml-2" value={pick} onChange={(e) => setPick(e.target.value)}><option value="">Choose…</option>{agents.data?.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}</select></label>
        <button className="btn btn-primary" disabled={!pick} onClick={() => router.push(`/guided?agent=${encodeURIComponent(pick)}`)}>Continue</button>
        <Link className="btn" href="/hub">Start from a template</Link>
        <Link className="btn" href="/agents/build">Start from my own material</Link>
      </div>
    </section>
  );
}

function Guide({ id, initial, catalog }: { id: string; initial: Spec; catalog: Catalog }) {
  const { can, askForName } = useMe();
  const [spec, setSpec] = useState<Spec>(initial);
  const [noTools, setNoTools] = useState(false);
  const [preview, setPreview] = useState<SpecPreview | null>(null);
  const [saved, setSaved] = useState<number | null>(null);
  const [tried, setTried] = useState(false);
  const [changed, setChanged] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [by, setBy] = useState("dev");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const editable = can("versions:create");
  const tools: string[] = spec.tools ?? [];
  const always: string[] = spec.approvals?.always ?? [];
  const change = (n: Spec) => { setSpec(n); setChanged(true); setTried(false); setMsg(null); };  // a changed draft is tried again
  const pick = (c: { tools: string[]; always: string[] }) => {
    const n: Spec = { ...spec, tools: c.tools };
    if (!c.tools.length) delete n.tools;
    if (c.always.length) n.approvals = { always: c.always }; else delete n.approvals;
    change(n);
  };

  useEffect(() => {
    clearTimeout(timer.current);
    setPreview(null);
    timer.current = setTimeout(() => { previewSpec(id, spec).then(setPreview).catch((e) => setPreview({ valid: false, problems: [(e as Error).message] })); }, 400);
    return () => clearTimeout(timer.current);
  }, [id, spec]);

  async function save() {
    setMsg(null);
    try { const v = await saveSpec(id, spec, askForName ? by.trim() || "dev" : undefined); setSaved(v.number); setChanged(false); }
    catch (e) { setMsg((e as Error).message); }
  }

  const steps = guidedSteps({ agent: id, tools: tools.length, noTools, instructions: String(spec.instructions ?? ""), valid: preview ? preview.valid : null, problems: preview?.problems.length ?? 0, tried, saved, changed });
  const state = (k: string) => steps.find((s) => s.key === k)!.state;
  return (
    <div className="space-y-4">
      <ol aria-label="Steps" className="grid gap-2 sm:grid-cols-6">
        {steps.map((s, i) => (
          <li key={s.key} aria-current={s.state === "next" ? "step" : undefined} className={`rounded-lg border p-2 text-xs ${s.state === "next" ? "border-primary" : "border-border"}`}>
            <span className={`rounded px-1.5 py-0.5 font-medium ${PILL[s.state]}`}>{PILL_TEXT[s.state]}</span>
            <p className="mt-1 font-medium">{i + 1}. {s.title}</p><p className="text-muted">{s.note}</p></li>))}
      </ol>

      <fieldset disabled={!editable} className="space-y-4 border-0 p-0">
        <section aria-label="Connect what it can do" className={card}>
          <h2 className="font-medium">Step 2: Connect what it can do</h2>
          <p className="mb-2 text-sm text-muted">The tools your administrator has connected. Tools that change things start out needing a person's OK.</p>
          <div className="space-y-2"><ToolPicker catalog={catalog} tools={tools} always={always} audience={spec.audience === "staff" ? "staff" : "customer"} onChange={pick} /></div>
          {tools.length === 0 && <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={noTools} onChange={(e) => setNoTools(e.target.checked)} /> This agent does not need any tools</label>}
        </section>

        <section aria-label="Write its procedures" className={card}>
          <h2 className="font-medium">Step 3: Write its procedures</h2>
          <p className="mb-2 text-sm text-muted">What the agent should do, in your own words: when to look something up, what to offer, when to hand over to a person.</p>
          <label className="block text-sm">Instructions
            <textarea className="field mt-1 min-h-40 w-full" value={String(spec.instructions ?? "")} onChange={(e) => change({ ...spec, instructions: e.target.value })} /></label>
          <p className="mt-2 text-xs text-muted">Journeys, topics that always go to a person, languages and checks are in <Link className="text-primary underline" href={`/agents/${id}/edit`}>the full editor</Link> (Advanced).</p>
        </section>
      </fieldset>

      <section aria-label="What this agent will do" className={card} aria-live="polite">
        <h2 className="font-medium">Step 4: Check what it will do</h2>
        {state("summary") === "blocked" ? <p className="text-sm text-muted">Write the procedures first.</p>
          : !preview ? <p className="text-sm text-muted">Checking…</p>
          : !preview.valid ? <><p className="text-sm font-medium text-[var(--bad)]">Fix these first:</p><ul className="list-disc space-y-1 pl-5 text-sm text-[var(--bad)]">{preview.problems.map((p) => <li key={p}>{p}</li>)}</ul></>
          : <ul className="list-disc space-y-1 pl-5 text-sm">{(preview.summary ?? []).map((s) => <li key={s}>{s}</li>)}</ul>}
      </section>

      <TryPanel agent={id} spec={spec} ready={state("summary") === "done"} onTried={() => setTried(true)} />

      <section aria-label="Save and release" className={card}>
        <h2 className="font-medium">Step 6: Save it and get it ready to release</h2>
        {askForName && <label className="mt-2 block text-sm">Your name<input className="field mt-1" value={by} onChange={(e) => setBy(e.target.value)} /></label>}
        <button className="btn btn-primary mt-2" disabled={!editable || state("save") === "blocked" || (saved !== null && !changed) || preview?.unchangedSinceLatest === true} onClick={save}>Save a version</button>
        {preview?.unchangedSinceLatest && saved === null && <p className="mt-1 text-xs text-muted">Nothing has changed since the latest saved version.</p>}
        {!editable && <p className="mt-1 text-xs text-muted">Your role can look but not change.</p>}
        {msg && <p role="alert" className="mt-2 text-sm text-[var(--bad)]">{msg}</p>}
        {saved !== null && !changed && (
          <p role="status" className="mt-2 text-sm text-[var(--ok)]">Saved as version {saved}. <Link className="text-primary underline" href={`/agents/${id}`}>Run its tests and release it →</Link></p>)}
      </section>
    </div>
  );
}

function Loaded({ id }: { id: string }) {
  const live = useLoad(() => getLive(id), [id]);
  const catalog = useLoad(getCatalog, []);
  if ((live.loading && !live.data) || (catalog.loading && !catalog.data)) return <Loading />;
  if (live.error) return <ErrorBox message={live.error} onRetry={live.reload} />;
  if (catalog.error) return <ErrorBox message={catalog.error} onRetry={catalog.reload} />;
  return <Guide key={`${id}-${live.data!.digest}`} id={id} initial={live.data!.spec as Spec} catalog={catalog.data!} />;
}

function Page() {
  const id = useSearchParams().get("agent");
  return (
    <>
      <PageHeader title="Guided setup" subtitle="Set up an agent step by step, in plain words. Nothing goes live until it has passed its tests and you release it." />
      {id ? <Loaded id={id} /> : <><Choose /><Empty>The steps appear here once you choose an agent.</Empty></>}
    </>
  );
}

export default function Guided() {
  return <Suspense fallback={<Loading />}><Page /></Suspense>;
}
