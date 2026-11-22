import { describe, expect, it } from "vitest";
import type { Journey } from "@northcx/api-client";
import { addStep, fromGraph, moveStep, normalize, removeHandoff, removeStep, toGraph } from "@/lib/journey-graph";

// A small seeded generator: the same 300 journeys on every run, so a failure can be reproduced.
function rng(seed: number) { let s = seed; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32); }
const pick = <T,>(r: () => number, xs: T[]) => xs[Math.floor(r() * xs.length)];
function journey(r: () => number): Journey {
  const n = Math.floor(r() * 6);
  const j: Journey = { name: `j${Math.floor(r() * 99)}`, goal: pick(r, ["Refund an order", "Track a parcel", "Change an address"]),
    steps: Array.from({ length: n }, (_, i) => ({ purpose: `Step ${i} ${Math.floor(r() * 9)}`, ...(r() < 0.5 ? { tool: pick(r, ["lookup_order", "issue_refund", null]) } : {}), ...(r() < 0.5 ? { required: r() < 0.5 } : {}) })) };
  if (r() < 0.5) j.when = "a customer asks";
  if (r() < 0.5) j.flexibility = pick(r, ["strict", "guided", "free"]);
  if (r() < 0.5) j.rules = Array.from({ length: Math.floor(r() * 3) }, (_, i) => `Rule ${i}`);
  if (r() < 0.5) j.handoff_if = Array.from({ length: Math.floor(r() * 3) }, (_, i) => `Hand over ${i}`);
  if (r() < 0.5) j.done_when = Array.from({ length: Math.floor(r() * 3) }, (_, i) => `tool_${i}`);
  if (r() < 0.3) j.samples = ["Hello"];
  return j;
}
const cases = (() => { const r = rng(7); return Array.from({ length: 300 }, () => journey(r)); })();

// The same edits made straight on the journey: what the graph must agree with.
const swap = <T,>(a: T[], i: number, k: number) => { const o = [...a]; [o[i], o[k]] = [o[k], o[i]]; return o; };

describe("a journey and its graph", () => {
  it("come back as the same journey", () => {
    for (const j of cases) expect(fromGraph(toGraph(j))).toEqual(normalize(j));
  });
  it("treat an empty list as no list", () => {
    expect(fromGraph(toGraph({ name: "a", goal: "g", steps: [], rules: [], handoff_if: [], done_when: [] }))).toEqual({ name: "a", goal: "g", steps: [] });
  });
  it("move a step the same way as moving it in the list", () => {
    for (const j of cases) for (const by of [-1, 1] as const) for (let i = 0; i < j.steps.length; i++) {
      const to = i + by;
      const want = to < 0 || to >= j.steps.length ? j.steps : swap(j.steps, i, to);
      expect(moveStep(j, i, by)).toEqual(normalize({ ...j, steps: want }));
    }
  });
  it("remove a step the same way as removing it from the list", () => {
    for (const j of cases) for (let i = 0; i < j.steps.length; i++) expect(removeStep(j, i)).toEqual(normalize({ ...j, steps: j.steps.filter((_, k) => k !== i) }));
  });
  it("add a step in the same place as adding it to the list", () => {
    const s = { purpose: "New step", required: true };
    for (const j of cases) for (let i = -1; i < j.steps.length; i++) expect(addStep(j, i, s)).toEqual(normalize({ ...j, steps: [...j.steps.slice(0, i + 1), s, ...j.steps.slice(i + 1)] }));
  });
  it("remove a hand-over condition the same way", () => {
    for (const j of cases) for (let i = 0; i < (j.handoff_if?.length ?? 0); i++) expect(removeHandoff(j, i)).toEqual(normalize({ ...j, handoff_if: j.handoff_if!.filter((_, k) => k !== i) }));
  });
  it("drops a step that is not on the line from the start", () => {
    const g = toGraph({ name: "a", goal: "g", steps: [{ purpose: "one" }, { purpose: "two" }] });
    g.edges = g.edges.filter((e) => e.to !== "step-2");
    expect(fromGraph(g).steps).toEqual([{ purpose: "one" }]);
  });
  it("needs a start", () => {
    expect(() => fromGraph({ nodes: [], edges: [] })).toThrow(/start/);
  });
});
