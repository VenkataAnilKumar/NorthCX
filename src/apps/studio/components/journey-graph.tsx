"use client";
import type { Journey } from "@northcx/api-client";
import { addStep, moveStep, removeHandoff, removeStep } from "@/lib/journey-graph";

const card = "rounded-lg border border-border bg-surface px-3 py-2 text-sm";
const btn = "rounded border border-border px-2 py-0.5 text-xs hover:bg-border/40 disabled:opacity-40";
const Arrow = () => <div aria-hidden className="ml-6 h-4 w-px bg-border" />;

/** The journey as a line of cards: start, each step in order, then the "done" condition, with hand-over conditions branching off the start.
 *  It shows and edits the same journey as the list; nothing is stored separately. */
export function JourneyGraph({ journey: j, onChange }: { journey: Journey; onChange: (j: Journey) => void }) {
  const add = (after: number) => onChange(addStep(j, after, { purpose: "New step", required: true }));
  return (
    <div role="group" aria-label={`Graph of ${j.name}`} className="space-y-0">
      <div className={card}><strong>Start</strong> · {j.when || "when this journey applies"}<span className="block text-xs text-muted">Goal: {j.goal}</span></div>
      {j.steps.map((s, i) => (
        <div key={i}>
          <Arrow />
          <div className={card}>
            <span className="font-medium">{i + 1}. {s.purpose}</span>
            <span className="block text-xs text-muted">{s.tool ? `uses ${s.tool}` : "no tool"} · {s.required === false ? "optional" : "required"}</span>
            <div className="mt-1 flex gap-1">
              <button type="button" className={btn} aria-label={`Move step ${i + 1} up`} disabled={i === 0} onClick={() => onChange(moveStep(j, i, -1))}>Up</button>
              <button type="button" className={btn} aria-label={`Move step ${i + 1} down`} disabled={i === j.steps.length - 1} onClick={() => onChange(moveStep(j, i, 1))}>Down</button>
              <button type="button" className={btn} aria-label={`Add a step after step ${i + 1}`} onClick={() => add(i)}>Add after</button>
              <button type="button" className={btn} aria-label={`Remove step ${i + 1}`} onClick={() => onChange(removeStep(j, i))}>Remove</button>
            </div>
          </div>
        </div>
      ))}
      {j.steps.length === 0 && <><Arrow /><button type="button" className={btn} onClick={() => add(-1)}>Add the first step</button></>}
      {!!j.done_when?.length && <><Arrow /><div className={card}><strong>Done</strong> when {j.done_when.join(", ")} {j.done_when.length === 1 ? "has" : "have"} run</div></>}
      {!!j.handoff_if?.length && (
        <div className="mt-3 space-y-1">
          <p className="text-xs font-medium">Hand over to a person if</p>
          {j.handoff_if.map((h, i) => (
            <div key={i} className={`${card} flex items-center gap-2`}><span className="flex-1">{h}</span>
              <button type="button" className={btn} aria-label={`Remove hand-over condition ${i + 1}`} onClick={() => onChange(removeHandoff(j, i))}>Remove</button></div>
          ))}
        </div>
      )}
    </div>
  );
}
