"use client";
import { useState } from "react";
import type { AutomationCatalog } from "@northcx/api-client";
import type { Step } from "./flow";

type Patch = (p: Record<string, unknown>) => void;
const field = "field mt-1 w-full";

/** A JSON value edited as text; the step changes only while the text is valid, and the problem is shown beside it. */
function JsonField({ label, value, onValid, readOnly }: { label: string; value: unknown; onValid: (v: unknown) => void; readOnly: boolean }) {
  const [text, setText] = useState(JSON.stringify(value ?? {}, null, 1));
  const [bad, setBad] = useState(false);
  return (
    <label className="block">{label}
      <textarea className={`${field} h-20 font-mono text-xs`} disabled={readOnly} value={text} aria-invalid={bad} onChange={(e) => { setText(e.target.value); try { onValid(JSON.parse(e.target.value)); setBad(false); } catch { setBad(true); } }} />
      {bad && <span role="alert" className="text-xs text-[var(--bad)]">This is not valid JSON yet, so the step keeps its last valid value.</span>}
    </label>
  );
}

function Pick({ label, value, options, onChange, readOnly }: { label: string; value: string; options: string[]; onChange: (v: string) => void; readOnly: boolean }) {
  return <label className="block">{label}<select className={field} disabled={readOnly} value={value} onChange={(e) => onChange(e.target.value)}><option value="">Choose…</option>{options.map((o) => <option key={o}>{o}</option>)}</select></label>;
}

const str = (v: unknown) => (typeof v === "string" ? v : "");
const NEXT = ["continue", "stop", "skip steps"];
const nextOf = (v: unknown) => (typeof v === "object" && v !== null ? "skip steps" : str(v) || "continue");
const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);

function ToolFields({ step, catalog, readOnly, onPatch }: { step: Record<string, unknown>; catalog: AutomationCatalog | null; readOnly: boolean; onPatch: Patch }) {
  const tools = catalog?.tools ?? [];
  const effect = tools.find((t) => t.name === step.tool)?.effect;
  return (
    <>
      <Pick label="Tool" value={str(step.tool)} options={tools.map((t) => t.name)} readOnly={readOnly} onChange={(v) => onPatch({ tool: v })} />
      {effect && <p className="text-xs text-muted">{effect === "read" ? "This tool only reads." : "This tool changes something, so an ‘Ask a person’ step must come before it."}</p>}
      <JsonField label="Arguments (JSON). Use {{previous.field}}, {{input.field}} or, in a for-each step, {{item}}" value={step.args} readOnly={readOnly} onValid={(v) => onPatch({ args: v })} />
    </>
  );
}

export function NewKindFields({ step, catalog, readOnly, onPatch }: { step: Step; catalog: AutomationCatalog | null; readOnly: boolean; onPatch: Patch }) {
  const agents = catalog?.agents ?? [];
  if (step.kind === "tool") return <ToolFields step={step} catalog={catalog} readOnly={readOnly} onPatch={onPatch} />;
  if (step.kind === "branch") {
    const part = (k: "then" | "else") => (
      <div className="grid gap-2 md:grid-cols-2">
        <Pick label={k === "then" ? "If true" : "Otherwise"} value={nextOf(step[k])} options={NEXT} readOnly={readOnly}
          onChange={(v) => onPatch({ [k]: v === "skip steps" ? { skip: 1 } : v })} />
        {nextOf(step[k]) === "skip steps" && <label className="block">Skip how many steps<input type="number" min={1} max={9} className={field} disabled={readOnly} value={Number((step[k] as { skip?: number }).skip ?? 1)} onChange={(e) => onPatch({ [k]: { skip: Number(e.target.value) } })} /></label>}
      </div>
    );
    return (
      <>
        <label className="block">Condition. Read <code>previous</code> (the step before) or <code>input</code>, such as <code>previous.total &gt; 100</code>
          <input className={field} disabled={readOnly} value={str(step.when)} onChange={(e) => onPatch({ when: e.target.value })} /></label>
        {part("then")}{part("else")}
        <p className="text-xs text-muted">A condition can compare, and combine with and, or, not; it cannot call anything. Steps skipped never run.</p>
      </>
    );
  }
  if (step.kind === "foreach") {
    const inner = (step.do ?? { kind: "tool" }) as Record<string, unknown>;
    const setInner = (p: Record<string, unknown>) => onPatch({ do: { ...inner, ...p } });
    return (
      <>
        <label className="block">List to go through, such as <code>previous.orders</code><input className={field} disabled={readOnly} value={str(step.over)} onChange={(e) => onPatch({ over: e.target.value })} /></label>
        <label className="block">Most items (1 to 20)<input type="number" min={1} max={20} className={field} disabled={readOnly} value={Number(step.max ?? 10)} onChange={(e) => onPatch({ max: Number(e.target.value) })} /></label>
        <Pick label="For each item" value={str(inner.kind)} options={["tool", "assistant"]} readOnly={readOnly} onChange={(v) => onPatch({ do: v === "tool" ? { kind: "tool", tool: "", args: {} } : { kind: "assistant", assistant: "", prompt: "" } })} />
        {inner.kind === "tool" ? <ToolFields step={inner} catalog={catalog} readOnly={readOnly} onPatch={setInner} /> : <>
          <Pick label="Staff assistant" value={str(inner.assistant)} options={catalog?.assistants ?? []} readOnly={readOnly} onChange={(v) => setInner({ assistant: v })} />
          <label className="block">What to ask. <code>{"{{item}}"}</code> is the current item<textarea className={`${field} h-20`} disabled={readOnly} value={str(inner.prompt)} onChange={(e) => setInner({ prompt: e.target.value })} /></label></>}
        <p className="text-xs text-muted">If one item fails the run stops and says which; items already done stay done.</p>
      </>
    );
  }
  if (step.kind === "simulate") return (
    <>
      <Pick label="Agent to check" value={str(step.agent)} options={agents} readOnly={readOnly} onChange={(v) => onPatch({ agent: v })} />
      <Pick label="How" value={str(step.mode) || "scripted"} options={["scripted", "live"]} readOnly={readOnly} onChange={(v) => onPatch({ mode: v })} />
      <p className="text-xs text-muted">Runs the agent&rsquo;s test scenarios in a sandbox. Scripted uses no real model; live uses one and counts against the daily budget. Nothing reaches a customer.</p>
    </>
  );
  if (step.kind === "criteria") return (
    <>
      <Pick label="Agent whose conversations to judge" value={str(step.agent)} options={agents} readOnly={readOnly} onChange={(v) => onPatch({ agent: v })} />
      <label className="block">Criteria, one per line (1 to 5, each a plain sentence)
        <textarea className={`${field} h-24`} disabled={readOnly} value={((step.criteria as string[]) ?? []).join("\n")} onChange={(e) => onPatch({ criteria: lines(e.target.value) })} /></label>
      <div className="grid gap-2 md:grid-cols-2">
        <label className="block">Conversations (1 to 20)<input type="number" min={1} max={20} className={field} disabled={readOnly} value={Number(step.sample ?? 10)} onChange={(e) => onPatch({ sample: Number(e.target.value) })} /></label>
        <label className="block">From the last (days, 1 to 30)<input type="number" min={1} max={30} className={field} disabled={readOnly} value={Number(step.days ?? 7)} onChange={(e) => onPatch({ days: Number(e.target.value) })} /></label>
      </div>
      <p className="text-xs text-muted" role="note">Unverified: a model judges, and it has not been compared with people&rsquo;s judgements. Use it to find conversations worth a look, not to decide anything. Customer details are masked first.</p>
    </>
  );
  if (step.kind === "alert") return (
    <>
      <Pick label="How serious" value={str(step.severity) || "warning"} options={["warning", "critical"]} readOnly={readOnly} onChange={(v) => onPatch({ severity: v })} />
      <label className="block">What to say (5 to 200 characters, fixed wording)<input className={field} disabled={readOnly} value={str(step.text)} onChange={(e) => onPatch({ text: e.target.value })} /></label>
      <p className="text-xs text-muted">Goes to monitoring and the alert webhook. After a &lsquo;Check an agent&rsquo; step the names of failing scenarios are added. Put a condition before it so it fires only when something is wrong.</p>
    </>
  );
  return null;
}
