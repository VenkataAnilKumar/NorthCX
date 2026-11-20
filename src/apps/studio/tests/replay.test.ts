import { describe, expect, it } from "vitest";
import type { Trace, TraceEvent } from "@northcx/api-client";
import { buildFrames, conversationAt } from "../lib/replay";

const ev = (t: number, type: string, data: Record<string, unknown>): TraceEvent => ({ t, type, data });
const trace = (id: string, events: TraceEvent[]): Trace => ({ id, agent_id: "support", session_id: "s", agent_version: 1, events });
const first = trace("t1", [ev(10, "user", { message: "where is 1042?" }), ev(11, "llm", { step: 1 }), ev(12, "tool_call", { name: "lookup_order", input: { order_id: "1042" } }),
  ev(13, "tool_result", { name: "lookup_order", output: { status: "shipped" } }), ev(14, "reply", { reply: "It shipped.", status: "completed" })]);
const second = trace("t2", [ev(30, "user", { message: "refund it" }), ev(31, "approval", { tool: "issue_refund", reason: "over limit" }), ev(32, "reply", { reply: "Asked a teammate.", status: "needs_approval" })]);
const turns = [{ turn: 1, message: "where is 1042?" }, { turn: 2, message: "refund it" }];

describe("buildFrames", () => {
  it("puts the events of every trace in the order they happened and leaves out internal ones", () => {
    const frames = buildFrames([second, first], turns);                       // given out of order
    expect(frames.map((f) => f.event.type)).toEqual(["user", "tool_call", "tool_result", "reply", "user", "approval", "reply"]);
    expect(frames[0].sentence).toBe("The customer wrote: where is 1042?");
  });
  it("ties each customer message to its turn number by matching the words in order", () => {
    const frames = buildFrames([first, second], turns);
    expect(frames.filter((f) => f.event.type === "user").map((f) => f.turn)).toEqual([1, 2]);
    expect(buildFrames([first], [{ turn: 1, message: "something else" }])[0].turn).toBeNull();      // no match: no turn, so no edit button
  });
  it("copes with a conversation that has no traces", () => {
    expect(buildFrames([])).toEqual([]);
  });
});

describe("conversationAt", () => {
  const frames = buildFrames([first, second], turns);
  it("builds the conversation up to a step: customer, tool with its answer, agent, then notes", () => {
    expect(conversationAt(frames, 0)).toEqual([{ kind: "customer", text: "where is 1042?", turn: 1 }]);
    const lines = conversationAt(frames, 3);
    expect(lines.map((l) => l.kind)).toEqual(["customer", "tool", "agent"]);
    expect(lines[1].answer).toContain("answered: status shipped");
    expect(lines[2].text).toBe("It shipped.");
    const all = conversationAt(frames, frames.length - 1);
    expect(all.map((l) => l.kind)).toEqual(["customer", "tool", "agent", "customer", "note", "agent"]);
    expect(all[3].turn).toBe(2);
  });
  it("shows a tool that has not answered yet without an answer", () => {
    expect(conversationAt(frames, 1)[1].answer).toBeUndefined();
  });
});
