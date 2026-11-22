/** The steps of the guided path and where the author stands in each. */
export type StepState = "done" | "next" | "blocked";
export interface GuidedStep { key: "start" | "connect" | "procedures" | "summary" | "try" | "save"; title: string; state: StepState; note: string }

export interface Where {
  agent: string | null; tools: number; noTools: boolean; instructions: string; valid: boolean | null; problems: number; tried: boolean; saved: number | null; changed: boolean;
}

export function guidedSteps(w: Where): GuidedStep[] {
  const start = w.agent !== null;
  const connect = start && (w.tools > 0 || w.noTools);
  const procedures = start && w.instructions.trim().length > 0;
  const summary = procedures && w.valid === true;
  const tried = summary && w.tried;
  const saved = w.saved !== null && !w.changed;
  const raw: [GuidedStep["key"], string, boolean, boolean, string][] = [
    ["start", "Choose the agent", start, true, start ? `Working on ${w.agent}.` : "Pick an agent, or start one from a template or your own material."],
    ["connect", "Connect what it can do", connect, start, !start ? "Choose an agent first." : connect ? (w.tools > 0 ? `${w.tools} tool${w.tools === 1 ? "" : "s"} chosen.` : "No tools: the agent answers from its instructions only.") : "Choose the tools it may use, or confirm that it needs none."],
    ["procedures", "Write its procedures", procedures, start, !start ? "Choose an agent first." : procedures ? "Instructions written." : "Write what the agent should do, in plain words."],
    ["summary", "Check what it will do", summary, procedures, !procedures ? "Write the procedures first." : w.valid === null ? "Checking…" : w.valid ? "Read the summary and make sure it is what you meant." : `${w.problems} thing${w.problems === 1 ? "" : "s"} to fix first.`],
    ["try", "Try it", tried, summary, !summary ? "Check what it will do first." : tried ? "Tried." : "Type a customer message and see how it answers. Nothing is saved or sent."],
    ["save", "Save it and get it ready to release", saved, tried, !tried ? "Try it first." : saved ? `Saved as version ${w.saved}.` : "Save a version, then run its tests and release it."],
  ];
  let nextGiven = false;
  return raw.map(([key, title, done, unlocked, note]) => {
    if (done) return { key, title, state: "done" as const, note };
    if (!unlocked || nextGiven) return { key, title, state: "blocked" as const, note };
    nextGiven = true;
    return { key, title, state: "next" as const, note };
  });
}
