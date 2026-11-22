import { describe, expect, it } from "vitest";
import { guidedSteps, type Where } from "../lib/guided";

const base: Where = { agent: null, tools: 0, noTools: false, instructions: "", valid: null, problems: 0, saved: null, changed: false };
const states = (w: Where) => guidedSteps(w).map((s) => s.state);

describe("guidedSteps", () => {
  it("starts by choosing an agent and blocks everything after it", () => {
    expect(states(base)).toEqual(["next", "blocked", "blocked", "blocked", "blocked"]);
  });
  it("moves on step by step and never skips one: exactly one step is next", () => {
    const chosen = { ...base, agent: "support" };
    expect(states(chosen)).toEqual(["done", "next", "blocked", "blocked", "blocked"]);
    const withTools = { ...chosen, tools: 2 };
    expect(states(withTools)).toEqual(["done", "done", "next", "blocked", "blocked"]);
    const written = { ...withTools, instructions: "Help with orders." };
    expect(states(written)).toEqual(["done", "done", "done", "next", "blocked"]);
    const valid = { ...written, valid: true };
    expect(states(valid)).toEqual(["done", "done", "done", "done", "next"]);
    expect(states({ ...valid, saved: 3 })).toEqual(["done", "done", "done", "done", "done"]);
  });
  it("blocks the summary while the definition has problems and says how many", () => {
    const s = guidedSteps({ ...base, agent: "a", tools: 1, instructions: "x", valid: false, problems: 2 });
    expect(s[3]).toMatchObject({ state: "next", note: "2 things to fix first." });
    expect(s[4].state).toBe("blocked");
  });
  it("asks for a new save once the author changes something after saving", () => {
    expect(guidedSteps({ ...base, agent: "a", tools: 1, instructions: "x", valid: true, saved: 3, changed: true })[4].state).toBe("next");
  });
  it("holds the path at the tools step until tools are chosen or the author confirms none are needed", () => {
    expect(guidedSteps({ ...base, agent: "a", instructions: "x" })[1]).toMatchObject({ state: "next", note: "Choose the tools it may use, or confirm that it needs none." });
    const none = guidedSteps({ ...base, agent: "a", noTools: true, instructions: "x" });
    expect(none[1]).toMatchObject({ state: "done", note: "No tools: the agent answers from its instructions only." });
    expect(none[3].state).toBe("next");
  });
});
