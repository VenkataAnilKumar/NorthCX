"use client";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { createScenario, deleteScenario, getScenario, getSimRun, listAgents, runSimulation, updateScenario, validateScenario, type SimRunDetail } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { useMe } from "@/lib/me";
import { ErrorBox, Loading, PageHeader } from "@/components/states";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Def = Record<string, any>;
const input = "w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-sm";
const box = "rounded-xl border border-border bg-surface p-4";
const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);
const csv = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);
const STATUSES = ["", "completed", "escalated", "needs_approval"];
const BLANK: Def = { name: "", agent: "", description: "", model: [{ text: "" }], turns: [{ say: "", expect: { status: "completed" } }] };

function clean(d: Def): Def {
  const prune = (v: any): any => {
    if (Array.isArray(v)) return v.map(prune).filter((x) => x !== undefined);
    if (v && typeof v === "object") { const o: Def = {}; for (const [k, x] of Object.entries(v)) { const p = prune(x); if (p !== undefined && !(Array.isArray(p) && p.length === 0) && !(p && typeof p === "object" && !Array.isArray(p) && Object.keys(p).length === 0) && p !== "") o[k] = p; } return o; }
    return v;
  };
  return prune(d);
}

function Editor({ initial, isNew, editable, canRequire }: { initial: Def; isNew: boolean; editable: boolean; canRequire: boolean }) {
  const agents = useLoad(listAgents, []);
  const [d, setD] = useState<Def>(initial);
  const [advanced, setAdvanced] = useState(false);
  const [text, setText] = useState("");
  const [check, setCheck] = useState<{ valid: boolean; problems: string[] } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [run, setRun] = useState<SimRunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const set = (k: string, v: any) => setD((s) => ({ ...s, [k]: v }));
  const model: any[] = d.model ?? [];
  const turns: any[] = d.turns ?? [];
  const body = () => (advanced ? { yaml: text } : { scenario: clean(d) });

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => { validateScenario(body()).then(setCheck).catch((e) => setCheck({ valid: false, problems: [(e as Error).message] })); }, 400);
    return () => clearTimeout(timer.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, text, advanced]);

  function toggleAdvanced() {
    if (!advanced) { setText(JSON.stringify(clean(d), null, 2)); setAdvanced(true); return; }
    try { setD(JSON.parse(text)); setAdvanced(false); setMsg(null); } catch { setMsg("Advanced text must be JSON to switch back to the form; keep editing here, or save it as it is."); }
  }
  async function save() {
    setMsg(null); setBusy(true);
    try { isNew ? await createScenario(body()) : await updateScenario(d.name, body()); window.location.href = `/simulations/scenarios/${encodeURIComponent(d.name)}`; }
    catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  }
  async function remove() {
    if (!confirm(`Delete the scenario ${d.name}?`)) return;
    try { await deleteScenario(d.name); window.location.href = "/simulations"; } catch (e) { setMsg((e as Error).message); }
  }
  async function runIt() {
    setMsg(null); setRun(null); setBusy(true);
    try { const r = await runSimulation("scripted", true, d.name); setRun(await getSimRun(r.id)); } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  }
  const setTurn = (i: number, patch: Def) => set("turns", turns.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const setExpect = (i: number, patch: Def) => setTurn(i, { expect: { ...(turns[i].expect ?? {}), ...patch } });
  const setModel = (i: number, e: Def) => set("model", model.map((m, j) => (j === i ? e : m)));
  const fin = d.expect ?? {};
  const r0 = run?.results[0];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      {advanced ? (
        <section className={box} aria-label="Advanced"><h2 className="font-medium">Advanced: the scenario as text</h2><p className="mb-2 text-sm text-muted">JSON or YAML, exactly as a scenario file.</p>
          <label htmlFor="adv" className="sr-only">Scenario text</label><textarea id="adv" value={text} onChange={(e) => setText(e.target.value)} rows={28} className={`${input} font-mono text-xs`} disabled={!editable} /></section>
      ) : (
        <fieldset disabled={!editable} className="space-y-4 border-0 p-0">
          <section className={box} aria-label="About"><h2 className="font-medium">About this scenario</h2>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <label className="text-sm">Name<input value={d.name ?? ""} disabled={!isNew} onChange={(e) => set("name", e.target.value)} placeholder="refund-over-limit-waits" className={input} /></label>
              <label className="text-sm">Agent<select value={d.agent ?? ""} onChange={(e) => set("agent", e.target.value)} className={input}><option value="">choose…</option>{agents.data?.map((a) => <option key={a.id}>{a.id}</option>)}{d.agent && !agents.data?.some((a) => a.id === d.agent) && <option>{d.agent}</option>}</select></label>
            </div>
            <label className="mt-2 block text-sm">What it checks<input value={d.description ?? ""} onChange={(e) => set("description", e.target.value)} className={input} /></label>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={d.required ?? true} disabled={!canRequire} onChange={(e) => set("required", e.target.checked)} /> Required to release</label>
              {!canRequire && <span className="text-xs text-muted">Only release managers can change this.</span>}
              <label>Tags<input value={(d.tags ?? []).join(", ")} onChange={(e) => set("tags", csv(e.target.value))} className="ml-2 w-44 rounded-lg border border-border bg-bg px-2 py-1" /></label>
            </div>
          </section>
          <section className={box} aria-label="Conversation"><h2 className="font-medium">The conversation</h2><p className="mb-2 text-sm text-muted">What the customer says, and what should be true afterwards.</p>
            {turns.map((t, i) => (
              <div key={i} className="mb-3 rounded-lg border border-border p-3 text-sm">
                <div className="flex gap-2"><label className="flex-1">Customer says<input value={t.say ?? ""} onChange={(e) => setTurn(i, { say: e.target.value })} className={input} /></label>
                  <button type="button" onClick={() => set("turns", turns.filter((_, j) => j !== i))} disabled={turns.length === 1} className="self-end rounded-lg border border-border px-2 py-1.5 hover:bg-border/40 disabled:opacity-50">Remove</button></div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <label>Then the agent’s status is<select value={t.expect?.status ?? ""} onChange={(e) => setExpect(i, { status: e.target.value })} className={input}>{STATUSES.map((s) => <option key={s} value={s}>{s || "(anything)"}</option>)}</select></label>
                  <label>Tools called (comma separated)<input value={(t.expect?.tools_called ?? []).join(", ")} onChange={(e) => setExpect(i, { tools_called: csv(e.target.value) })} className={input} /></label>
                  <label>Reply must include (one per line)<textarea rows={2} value={(t.expect?.reply_includes ?? []).join("\n")} onChange={(e) => setExpect(i, { reply_includes: lines(e.target.value) })} className={input} /></label>
                  <label>Reply must not include (one per line)<textarea rows={2} value={(t.expect?.reply_excludes ?? []).join("\n")} onChange={(e) => setExpect(i, { reply_excludes: lines(e.target.value) })} className={input} /></label>
                </div>
              </div>))}
            <button type="button" onClick={() => set("turns", [...turns, { say: "", expect: { status: "completed" } }])} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40">Add a customer message</button>
          </section>
          <section className={box} aria-label="Whole conversation"><h2 className="font-medium">Across the whole conversation</h2>
            <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
              <label>Tools that must never be called<input value={(fin.tools_not_called ?? []).join(", ")} onChange={(e) => set("expect", { ...fin, tools_not_called: csv(e.target.value) })} className={input} /></label>
              <label>Most model calls<input type="number" min={0} value={fin.max_model_calls ?? ""} onChange={(e) => set("expect", { ...fin, max_model_calls: e.target.value === "" ? undefined : Number(e.target.value) })} className={input} /></label>
              <label className="sm:col-span-2">Text that must never reach the model (one per line)<textarea rows={2} value={(fin.model_input_excludes ?? []).join("\n")} onChange={(e) => set("expect", { ...fin, model_input_excludes: lines(e.target.value) })} className={input} /></label>
            </div>
          </section>
          <section className={box} aria-label="Model script"><h2 className="font-medium">What the model says (for offline runs)</h2><p className="mb-2 text-sm text-muted">Scripted runs replay these answers in order, so the test is repeatable. A tool call needs the tool name and its input as JSON.</p>
            {model.map((m, i) => (
              <div key={i} className="mb-2 flex flex-wrap gap-2 text-sm">
                <select aria-label={`Step ${i + 1} kind`} value={m.tool_call ? "tool" : "text"} onChange={(e) => setModel(i, e.target.value === "tool" ? { tool_call: { name: "", input: {} } } : { text: "" })} className="rounded-lg border border-border bg-bg px-2 py-1.5"><option value="text">replies</option><option value="tool">calls a tool</option></select>
                {m.tool_call ? (<>
                  <input aria-label={`Step ${i + 1} tool`} value={m.tool_call.name} placeholder="tool name" onChange={(e) => setModel(i, { tool_call: { ...m.tool_call, name: e.target.value } })} className="w-40 rounded-lg border border-border bg-bg px-2 py-1.5" />
                  <input aria-label={`Step ${i + 1} input`} defaultValue={JSON.stringify(m.tool_call.input)} placeholder='{"order_id": "1042"}' onChange={(e) => { try { setModel(i, { tool_call: { ...m.tool_call, input: JSON.parse(e.target.value || "{}") } }); } catch { /* keep the last valid input */ } }} className="min-w-0 flex-1 rounded-lg border border-border bg-bg px-2 py-1.5 font-mono text-xs" /></>
                ) : <input aria-label={`Step ${i + 1} reply`} value={m.text ?? ""} onChange={(e) => setModel(i, { text: e.target.value })} className="min-w-0 flex-1 rounded-lg border border-border bg-bg px-2 py-1.5" />}
                <button type="button" onClick={() => set("model", model.filter((_, j) => j !== i))} className="rounded-lg border border-border px-2 hover:bg-border/40">Remove</button>
              </div>))}
            <button type="button" onClick={() => set("model", [...model, { text: "" }])} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40">Add a step</button>
          </section>
        </fieldset>
      )}
      <aside aria-label="Check and save" className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <section className={box} aria-live="polite"><h2 className="font-medium">Checks</h2>
          {!check ? <p className="text-sm text-muted">Checking…</p> : check.valid ? <p className="text-sm text-[var(--ok)]">The scenario is valid.</p> : <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--bad)]">{check.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          <button type="button" onClick={toggleAdvanced} className="mt-3 text-sm text-primary underline">{advanced ? "Back to the form" : "Edit as text"}</button>
        </section>
        <section className={box}><h2 className="font-medium">Save and run</h2>
          <button onClick={save} disabled={!editable || busy || !check?.valid} className="mt-2 w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-text disabled:opacity-50">{isNew ? "Save scenario" : "Save changes"}</button>
          {!isNew && <button onClick={runIt} disabled={busy} className="mt-2 w-full rounded-lg border border-border px-3 py-2 text-sm hover:bg-border/40 disabled:opacity-50">Run it now (offline)</button>}
          {!isNew && editable && <button onClick={remove} className="mt-2 w-full rounded-lg border border-border px-3 py-2 text-sm text-[var(--bad)] hover:bg-border/40">Delete</button>}
          {!editable && <p className="mt-2 text-xs text-muted">{isNew ? "Your role cannot add scenarios." : "This scenario cannot be changed here: it comes from a file, or your role cannot edit."}</p>}
          {msg && <p role="alert" className="mt-2 text-sm text-[var(--bad)]">{msg}</p>}
          {r0 && <div role="status" className="mt-3 text-sm"><p className={r0.passed ? "text-[var(--ok)]" : "text-[var(--bad)]"}>{r0.passed ? "Passed" : "Failed"}</p>
            {!r0.passed && <ul className="mt-1 list-disc space-y-1 pl-5 text-xs">{r0.trials.flatMap((t) => t.failures).slice(0, 6).map((f, i) => <li key={i}>{f.where}: expected {String(f.expected)}, got {String(f.actual)}</li>)}</ul>}</div>}
        </section>
      </aside>
    </div>
  );
}

export default function ScenarioPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = use(params);
  const isNew = name === "new";
  const { can } = useMe();
  const detail = useLoad(() => (isNew ? Promise.resolve(null) : getScenario(decodeURIComponent(name))), [name]);
  if (detail.loading && !detail.data && !isNew) return <Loading />;
  if (detail.error) return <ErrorBox message={detail.error} onRetry={detail.reload} />;
  const d = detail.data;
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-primary underline" href="/simulations">← Simulations</Link></p>
      <PageHeader title={isNew ? "New scenario" : decodeURIComponent(name)} subtitle={isNew ? "Describe a conversation and what must be true afterwards. Scenarios are how an agent earns the right to go live." : d?.source === "file" ? "This scenario comes from a file. You can read it, not change it." : "Saved scenario"} />
      <Editor key={name} initial={d ? d.definition : BLANK} isNew={isNew} editable={isNew ? can("scenarios:write") : !!d?.editable && can("scenarios:write")} canRequire={can("scenarios:require")} />
    </>
  );
}
