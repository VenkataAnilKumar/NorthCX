/** The canvas is a view of the same routine definition the server checks (E14): the definition becomes a graph for drawing and the graph becomes the definition again,
 *  unchanged. Nothing here knows how to run anything; the server's checks stay the only rules. */

export type StepKind = "report" | "assistant" | "person" | "tag" | "notify" | "output";
export interface Step { id: string; kind: StepKind | string; [field: string]: unknown }
export interface Trigger { type: string; everyHours?: number; event?: string }
export interface Definition { id?: string; name?: string; description?: string; trigger: Trigger; steps: Step[]; limits?: { maxSeconds?: number }; [extra: string]: unknown }

export interface GraphNode { id: string; type: "trigger" | "step"; kind: string; data: Record<string, unknown> }
export interface Graph { nodes: GraphNode[]; edges: { from: string; to: string }[]; meta: Record<string, unknown> }

const NODE_TRIGGER = "trigger";

/** A routine is a line: the trigger, then each step in order. */
export function toGraph(def: Definition): Graph {
  const { trigger, steps, ...meta } = def;
  const nodes: GraphNode[] = [{ id: NODE_TRIGGER, type: "trigger", kind: trigger.type, data: { ...trigger } }];
  const edges: { from: string; to: string }[] = [];
  let prev = NODE_TRIGGER;
  for (const s of steps) {
    const { id, kind, ...data } = s;
    nodes.push({ id, type: "step", kind: String(kind), data });
    edges.push({ from: prev, to: id });
    prev = id;
  }
  return { nodes, edges, meta };
}

/** Follow the edges from the trigger; a node not reached that way is not part of the routine. */
export function fromGraph(g: Graph): Definition {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const next = new Map(g.edges.map((e) => [e.from, e.to]));
  const root = byId.get(NODE_TRIGGER);
  if (!root) throw new Error("A routine needs a trigger");
  const steps: Step[] = [];
  const seen = new Set<string>([NODE_TRIGGER]);
  for (let at = next.get(NODE_TRIGGER); at !== undefined && !seen.has(at); at = next.get(at)) {
    seen.add(at);
    const n = byId.get(at);
    if (!n || n.type !== "step") break;
    steps.push({ id: n.id, kind: n.kind, ...n.data });
  }
  return { ...g.meta, trigger: { ...(root.data as unknown as Trigger), type: root.kind }, steps } as Definition;
}

export const KIND_LABEL: Record<string, string> = {
  report: "Get figures", assistant: "Ask an assistant", person: "Ask a person", tag: "Tag the conversation", notify: "Send out", output: "Save to Outputs",
  manual: "Starts by hand", schedule: "Starts on a schedule", webhook: "Starts by webhook", event: "Starts on an event",
};

/** What a step does, in a short line for its card. */
export function summary(kind: string, d: Record<string, unknown>): string {
  const s = (v: unknown) => (typeof v === "string" ? v : "");
  switch (kind) {
    case "report": return `${s(d.report) || "choose a report"}, last ${d.days ?? 7} day(s)`;
    case "assistant": return s(d.assistant) ? `${s(d.assistant)}: ${s(d.prompt).slice(0, 60)}` : "choose an assistant";
    case "person": return s(d.ask) || "write the question";
    case "tag": return s(d.tag) ? `auto-${s(d.tag)}` : "name the tag";
    case "notify": return s(d.to) ? `to ${s(d.to)}` : "choose a destination";
    case "output": return s(d.title) || "give it a title";
    case "schedule": return `every ${d.everyHours ?? "?"} hours`;
    case "event": return s(d.event) || "choose an event";
    default: return "";
  }
}

export const DEFAULTS: Record<string, Record<string, unknown>> = {
  report: { report: "performance", days: 7 }, assistant: { assistant: "", prompt: "" }, person: { ask: "", maxWaitHours: 24 }, tag: { tag: "" }, notify: { to: "" }, output: { title: "" },
};

export function newStepId(def: Definition, kind: string): string {
  const used = new Set(def.steps.map((s) => s.id));
  for (let n = 1; ; n++) if (!used.has(`${kind}${n}`)) return `${kind}${n}`;
}

export function addStep(def: Definition, kind: string, afterId?: string): Definition {
  const step: Step = { id: newStepId(def, kind), kind, ...(DEFAULTS[kind] ?? {}) };
  const at = afterId ? def.steps.findIndex((s) => s.id === afterId) + 1 : def.steps.length;
  return { ...def, steps: [...def.steps.slice(0, at), step, ...def.steps.slice(at)] };
}

export function moveStep(def: Definition, id: string, delta: -1 | 1): Definition {
  const i = def.steps.findIndex((s) => s.id === id);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= def.steps.length) return def;
  const steps = def.steps.slice();
  [steps[i], steps[j]] = [steps[j], steps[i]];
  return { ...def, steps };
}

export const removeStep = (def: Definition, id: string): Definition => ({ ...def, steps: def.steps.filter((s) => s.id !== id) });

export function updateStep(def: Definition, id: string, patch: Record<string, unknown>): Definition {
  return { ...def, steps: def.steps.map((s) => (s.id === id ? { ...s, ...patch } : s)) };
}

/** Quick checks to show next to the drawing. The server's checks decide when you save. */
export function hints(def: Definition): string[] {
  const out: string[] = [];
  const ids = def.steps.map((s) => s.id);
  if (new Set(ids).size !== ids.length) out.push("Two steps have the same id.");
  if (def.steps.length === 0) out.push("Add at least one step.");
  if (def.steps.length > 10) out.push("A routine has at most 10 steps.");
  let asked = false;
  for (const s of def.steps) {
    if (s.kind === "person") asked = true;
    if (s.kind === "notify" && !asked) out.push(`'${s.id}' sends something out, so an 'Ask a person' step must come before it.`);
  }
  return out;
}
