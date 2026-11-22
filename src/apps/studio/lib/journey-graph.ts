import type { Journey } from "@northcx/api-client";

/** A journey drawn as a graph. The graph holds nothing the journey does not: `fromGraph(toGraph(j))` is the same journey, and each edit
 *  below changes the graph exactly as the same edit changes the journey. The server's checks stay the only rules. */
export type NodeKind = "start" | "step" | "handoff" | "done";
export interface GraphNode { id: string; kind: NodeKind; data: Record<string, unknown> }
export interface Graph { nodes: GraphNode[]; edges: { from: string; to: string }[] }

type Step = Journey["steps"][number];

/** The journey as the server stores it: empty lists and empty values are the same as absent ones. */
export function normalize(j: Journey): Journey {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(j)) {
    if (v === undefined || v === null || (Array.isArray(v) && v.length === 0)) continue;
    out[k] = k === "steps" ? (v as Step[]).map((s) => Object.fromEntries(Object.entries(s).filter(([, x]) => x !== undefined && x !== null))) : v;
  }
  if (!out.steps) out.steps = [];
  return out as unknown as Journey;
}

export function toGraph(journey: Journey): Graph {
  const { steps, handoff_if, done_when, ...rest } = normalize(journey);
  const nodes: GraphNode[] = [{ id: "start", kind: "start", data: rest }];
  const edges: Graph["edges"] = [];
  let prev = "start";
  steps.forEach((s, i) => {
    nodes.push({ id: `step-${i + 1}`, kind: "step", data: { ...s } });
    edges.push({ from: prev, to: `step-${i + 1}` });
    prev = `step-${i + 1}`;
  });
  if (done_when?.length) { nodes.push({ id: "done", kind: "done", data: { tools: done_when } }); edges.push({ from: prev, to: "done" }); }
  (handoff_if ?? []).forEach((text, i) => { nodes.push({ id: `handoff-${i + 1}`, kind: "handoff", data: { text } }); edges.push({ from: "start", to: `handoff-${i + 1}` }); });
  return { nodes, edges };
}

/** Steps are the nodes reached by following the line from the start; a step not on it is not part of the journey. */
export function fromGraph(g: Graph): Journey {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const start = byId.get("start");
  if (!start) throw new Error("A journey needs a start");
  const out: Record<string, unknown> = { ...start.data };
  const steps: Step[] = [];
  const seen = new Set<string>(["start"]);
  const nextOf = (id: string) => g.edges.find((e) => e.from === id && byId.get(e.to)?.kind !== "handoff")?.to;
  let done: string[] | undefined;
  for (let at = nextOf("start"); at !== undefined && !seen.has(at); at = nextOf(at)) {
    seen.add(at);
    const n = byId.get(at);
    if (!n) break;
    if (n.kind === "done") { done = n.data.tools as string[]; break; }
    if (n.kind !== "step") break;
    steps.push(n.data as Step);
  }
  const handoffs = g.edges.filter((e) => e.from === "start" && byId.get(e.to)?.kind === "handoff").map((e) => String(byId.get(e.to)!.data.text));
  return normalize({ ...out, steps, ...(handoffs.length ? { handoff_if: handoffs } : {}), ...(done?.length ? { done_when: done } : {}) } as unknown as Journey);
}

const stepIds = (g: Graph) => g.nodes.filter((n) => n.kind === "step").map((n) => n.id);

/** Move a step one place up (-1) or down (+1) along the line. */
export function moveStep(journey: Journey, index: number, by: -1 | 1): Journey {
  const g = toGraph(journey);
  const ids = stepIds(g);
  const to = index + by;
  if (index < 0 || to < 0 || to >= ids.length) return fromGraph(g);
  const order = [...ids];
  [order[index], order[to]] = [order[to], order[index]];
  return fromGraph(rewire(g, order));
}

export function removeStep(journey: Journey, index: number): Journey {
  const g = toGraph(journey);
  const ids = stepIds(g);
  if (index < 0 || index >= ids.length) return fromGraph(g);
  const gone = ids[index];
  return fromGraph(rewire({ ...g, nodes: g.nodes.filter((n) => n.id !== gone) }, ids.filter((id) => id !== gone)));
}

/** Add a step after the one at `index` (-1 puts it first). */
export function addStep(journey: Journey, index: number, step: Step): Journey {
  const g = toGraph(journey);
  const ids = stepIds(g);
  const id = `step-new`;
  const order = [...ids.slice(0, index + 1), id, ...ids.slice(index + 1)];
  return fromGraph(rewire({ ...g, nodes: [...g.nodes, { id, kind: "step", data: { ...step } }] }, order));
}

export function removeHandoff(journey: Journey, index: number): Journey {
  const g = toGraph(journey);
  const gone = `handoff-${index + 1}`;
  return fromGraph({ nodes: g.nodes.filter((n) => n.id !== gone), edges: g.edges.filter((e) => e.to !== gone) });
}

/** Lay the steps out in `order` between the start and the done node, leaving the handoff branches alone. */
function rewire(g: Graph, order: string[]): Graph {
  const done = g.nodes.find((n) => n.kind === "done");
  const line = ["start", ...order, ...(done ? [done.id] : [])];
  const branches = g.edges.filter((e) => g.nodes.find((n) => n.id === e.to)?.kind === "handoff");
  return { nodes: g.nodes, edges: [...line.slice(1).map((to, i) => ({ from: line[i], to })), ...branches] };
}
