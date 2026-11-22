import { describe, expect, it } from "vitest";
import { addStep, approved, fromGraph, hints, moveStep, removeStep, toGraph, updateStep, type Definition, type Step } from "../components/flow";

const KINDS = ["report", "assistant", "person", "tag", "notify", "output", "tool", "branch", "foreach", "simulate", "criteria", "alert"] as const;
const FIELDS: Record<string, () => Record<string, unknown>> = {
  report: () => ({ report: "performance", days: 7 }), assistant: () => ({ assistant: "shift-briefing", prompt: "Write it up: {{previous}}" }), person: () => ({ ask: "Ready?", maxWaitHours: 24 }),
  tag: () => ({ tag: "follow-up" }), notify: () => ({ to: "ops-chat" }), output: () => ({ title: "Digest {date}" }),
  tool: () => ({ tool: "lookup_order", args: { order_id: "{{input.order}}", nested: { list: [1, 2, "{{previous.id}}"] } } }),
  branch: () => ({ when: "previous.total > 100 and not input.skip", then: { skip: 2 }, else: "stop" }),
  foreach: () => ({ over: "previous.orders", max: 5, do: { kind: "tool", tool: "lookup_order", args: { order_id: "{{item}}" } } }),
  simulate: () => ({ agent: "support", mode: "scripted" }), criteria: () => ({ agent: "support", criteria: ["Replies are polite and short"], sample: 5, days: 7 }),
  alert: () => ({ severity: "critical", text: "The live agent fails its scenarios." }),
};

// a small deterministic generator, so the property runs the same way every time
function rng(seed: number) { let s = seed; return () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296; }

function randomDefinition(r: () => number): Definition {
  const n = 1 + Math.floor(r() * 10);
  const steps: Step[] = Array.from({ length: n }, (_, i) => { const kind = KINDS[Math.floor(r() * KINDS.length)]; return { id: `s${i}`, kind, ...FIELDS[kind]() }; });
  const triggers = [{ type: "manual" }, { type: "schedule", everyHours: 1 + Math.floor(r() * 100) }, { type: "webhook", when: "input.priority == 'urgent'" }, { type: "event", event: "handoff.created" }];
  const def: Definition = { id: `routine-${Math.floor(r() * 1000)}`, name: "Generated", trigger: triggers[Math.floor(r() * 4)], steps };
  if (r() > 0.5) def.description = "A description";
  if (r() > 0.5) def.limits = { maxSeconds: 30 + Math.floor(r() * 200) };
  return def;
}

describe("the canvas is a view of the definition, not a second format", () => {
  it("round trips: definition to graph to definition is the same definition (many generated cases)", () => {
    const r = rng(42);
    for (let i = 0; i < 300; i++) {
      const d = randomDefinition(r);
      expect(fromGraph(toGraph(d))).toEqual(d);
    }
  });

  it("round trips after any sequence of edits as well", () => {
    const r = rng(7);
    let d = randomDefinition(r);
    for (let i = 0; i < 200; i++) {
      const pick = Math.floor(r() * 4);
      const ids = d.steps.map((s) => s.id);
      if (pick === 0 && d.steps.length < 10) d = addStep(d, KINDS[Math.floor(r() * KINDS.length)], r() > 0.5 ? ids[Math.floor(r() * ids.length)] : undefined);
      else if (pick === 1 && ids.length) d = moveStep(d, ids[Math.floor(r() * ids.length)], r() > 0.5 ? 1 : -1);
      else if (pick === 2 && ids.length > 1) d = removeStep(d, ids[Math.floor(r() * ids.length)]);
      else if (ids.length) d = updateStep(d, ids[Math.floor(r() * ids.length)], { note: String(i) });
      expect(fromGraph(toGraph(d))).toEqual(d);
      expect(new Set(d.steps.map((s) => s.id)).size).toBe(d.steps.length);       // ids stay unique through every edit
    }
  });

  it("draws the trigger first and one edge between neighbours", () => {
    const d: Definition = { trigger: { type: "manual" }, steps: [{ id: "a", kind: "report", report: "performance", days: 1 }, { id: "b", kind: "output", title: "T" }] };
    const g = toGraph(d);
    expect(g.nodes.map((n) => n.id)).toEqual(["trigger", "a", "b"]);
    expect(g.edges).toEqual([{ from: "trigger", to: "a" }, { from: "a", to: "b" }]);
  });

  it("follows the edges, so an unconnected node is not part of the routine", () => {
    const g = toGraph({ trigger: { type: "manual" }, steps: [{ id: "a", kind: "report" }, { id: "b", kind: "output" }] });
    g.edges = [{ from: "trigger", to: "a" }];
    expect(fromGraph(g).steps.map((s) => s.id)).toEqual(["a"]);
    expect(() => fromGraph({ nodes: [], edges: [], meta: {} })).toThrow();
  });

  it("edits do what they say and never change the original", () => {
    const d: Definition = { trigger: { type: "manual" }, steps: [{ id: "a", kind: "report" }, { id: "b", kind: "output" }] };
    expect(moveStep(d, "b", -1).steps.map((s) => s.id)).toEqual(["b", "a"]);
    expect(moveStep(d, "a", -1)).toBe(d);
    expect(addStep(d, "person", "a").steps.map((s) => s.kind)).toEqual(["report", "person", "output"]);
    expect(addStep(d, "tag").steps.at(-1)).toMatchObject({ id: "tag1", kind: "tag" });
    expect(removeStep(d, "a").steps).toHaveLength(1);
    expect(updateStep(d, "a", { days: 3 }).steps[0]).toMatchObject({ days: 3 });
    expect(d.steps).toHaveLength(2);
  });

  it("warns about what the server would refuse", () => {
    const d: Definition = { trigger: { type: "manual" }, steps: [{ id: "a", kind: "report" }, { id: "send", kind: "notify", to: "x" }] };
    expect(hints(d).join(" ")).toContain("'Ask a person' step must come before it");
    expect(hints(addStep(d, "person", "a"))).toEqual([]);
    expect(hints({ trigger: { type: "manual" }, steps: [] })).toContain("Add at least one step.");
    expect(hints({ trigger: { type: "manual" }, steps: [{ id: "a", kind: "tag" }, { id: "a", kind: "tag" }] })).toContain("Two steps have the same id.");
  });

  it("knows which steps are approved on every path, like the server", () => {
    const step = (kind: string, extra: Record<string, unknown> = {}, id = kind): Step => ({ id, kind, ...extra });
    const skipOver = { trigger: { type: "manual" }, steps: [step("tool", { tool: "lookup_order" }, "find"), step("branch", { when: "previous.a > 1", then: { skip: 1 }, else: "continue" }), step("person"), step("tool", { tool: "issue_refund" }, "refund")] };
    expect(approved(skipOver)).toEqual([false, false, false, false]);             // the skip reaches the refund without the person
    const through = { ...skipOver, steps: [skipOver.steps[0], { ...skipOver.steps[1], then: "continue", else: "stop" }, skipOver.steps[2], skipOver.steps[3]] };
    expect(approved(through)).toEqual([false, false, false, true]);
    expect(hints(skipOver, ["lookup_order"]).join(" ")).toContain("'refund' changes something");
    expect(hints(through, ["lookup_order"])).toEqual([]);
    expect(hints(skipOver)).toEqual([]);                                          // with no list of reading tools nothing is claimed about a tool
  });

  it("checks a change made by the tool inside a for-each step too", () => {
    const d: Definition = { trigger: { type: "manual" }, steps: [{ id: "each", kind: "foreach", over: "input.l", do: { kind: "tool", tool: "issue_refund", args: {} } }] };
    expect(hints(d, ["lookup_order"]).join(" ")).toContain("'each' changes something");
  });
});
