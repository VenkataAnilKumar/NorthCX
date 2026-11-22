/** The canvas is a view of the same routine definition the server checks (E14): the definition becomes a graph for drawing and the graph becomes the definition again,
 *  unchanged. Nothing here knows how to run anything; the server's checks stay the only rules. */

export type StepKind = "report" | "assistant" | "person" | "tag" | "notify" | "output";
export interface Step { id: string; kind: StepKind | string; [field: string]: unknown }
export interface Trigger { type: string; everyHours?: number; event?: string; when?: string }
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
  tool: "Call a tool", branch: "Check a condition", foreach: "Do for each item", simulate: "Check an agent", criteria: "Judge conversations", alert: "Raise an alert",
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
    case "tool": return s(d.tool) || "choose a tool";
    case "branch": return s(d.when) ? `if ${s(d.when)}` : "write the condition";
    case "foreach": return s(d.over) ? `for each of ${s(d.over)}` : "choose the list";
    case "simulate": return s(d.agent) ? `${s(d.agent)}, ${s(d.mode) || "scripted"}` : "choose an agent";
    case "criteria": return Array.isArray(d.criteria) ? `${d.criteria.length} criteria on ${s(d.agent) || "an agent"}` : "write the criteria";
    case "alert": return s(d.text) || "write the alert";
    case "schedule": return `every ${d.everyHours ?? "?"} hours`;
    case "event": return s(d.event) || "choose an event";
    default: return "";
  }
}

export const DEFAULTS: Record<string, Record<string, unknown>> = {
  report: { report: "performance", days: 7 }, assistant: { assistant: "", prompt: "" }, person: { ask: "", maxWaitHours: 24 }, tag: { tag: "" }, notify: { to: "" }, output: { title: "" },
  tool: { tool: "", args: {} }, branch: { when: "", then: "continue", else: "stop" }, foreach: { over: "", max: 10, do: { kind: "tool", tool: "", args: {} } },
  simulate: { agent: "", mode: "scripted" }, criteria: { agent: "", criteria: [], sample: 10, days: 7 }, alert: { severity: "warning", text: "" },
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

type Next = "continue" | "stop" | { skip: number };

/** Where a step can lead: the next step, or for a branch whatever its two outcomes say. Mirrors the server's rule. */
function targets(steps: Step[], i: number): number[] {
  const s = steps[i];
  if (s.kind !== "branch") return [i + 1];
  return ([s.then ?? "continue", s.else ?? "stop"] as Next[]).flatMap((a) => (a === "continue" ? [i + 1] : typeof a === "object" && a ? [i + 1 + a.skip] : []));
}

/** For each step, whether every path that reaches it has passed a person step (a step no path reaches counts as approved). */
export function approved(def: Definition): boolean[] {
  const n = def.steps.length;
  const entering: boolean[][] = Array.from({ length: n + 1 }, () => []);
  entering[0].push(false);
  return def.steps.map((s, i) => {
    const got = entering[i].every(Boolean);
    for (const t of targets(def.steps, i)) if (t <= n) entering[t].push(got || s.kind === "person");
    return got;
  });
}

/** Quick checks to show next to the drawing. `readTools` names the tools that only read; any other tool changes something. The server's checks decide when you save. */
export function hints(def: Definition, readTools?: string[]): string[] {
  const out: string[] = [];
  const ids = def.steps.map((s) => s.id);
  if (new Set(ids).size !== ids.length) out.push("Two steps have the same id.");
  if (def.steps.length === 0) out.push("Add at least one step.");
  if (def.steps.length > 10) out.push("A routine has at most 10 steps.");
  const ok = approved(def);
  def.steps.forEach((s, i) => {
    const inner = (s.kind === "foreach" ? s.do : s) as Step | undefined;
    const changes = inner?.kind === "tool" && typeof inner.tool === "string" && inner.tool !== "" && readTools !== undefined && !readTools.includes(inner.tool);
    if (s.kind === "notify" && !ok[i]) out.push(`'${s.id}' sends something out, so an 'Ask a person' step must come before it.`);
    else if (changes && !ok[i]) out.push(`'${s.id}' changes something, so an 'Ask a person' step must come before it on every path.`);
  });
  return out;
}
