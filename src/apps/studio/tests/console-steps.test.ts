import { describe, expect, it } from "vitest";
import type { TraceEvent } from "@northcx/api-client";
import { plainSteps, toolCards, toolLabel } from "../lib/console-steps";

const ev = (type: string, data: Record<string, unknown>, t = 0): TraceEvent => ({ t, type, data });

describe("toolLabel", () => {
  it("writes a tool name as words, and an MCP tool as its name from its connection", () => {
    expect(toolLabel("lookup_order")).toBe("lookup order");
    expect(toolLabel("shop__orders_lookup")).toBe("orders lookup from shop");
  });
});

describe("toolCards", () => {
  const events = [ev("user", { message: "refund 240" }), ev("tool_call", { name: "lookup_order", input: { order_id: "2077" } }), ev("tool_result", { name: "lookup_order", output: { status: "delivered", total: 240 } }),
    ev("tool_call", { name: "issue_refund", input: { order_id: "2077", amount: 240 } }), ev("approval", { tool: "issue_refund", reason: "Refunds over 100 need a person" })];
  it("pairs each tool call with its result and marks the one held for a person", () => {
    const [a, b] = toolCards(events);
    expect(a).toMatchObject({ label: "lookup order", input: "order_id 2077", outcome: "done" });
    expect(a.detail).toContain("delivered");
    expect(b).toMatchObject({ label: "issue refund", input: "order_id 2077, amount 240", outcome: "held", detail: "Refunds over 100 need a person" });
  });
  it("shortens a long result instead of printing all of it", () => {
    const [c] = toolCards([ev("tool_call", { name: "x", input: {} }), ev("tool_result", { name: "x", output: { text: "a".repeat(500) } })]);
    expect(c.detail.length).toBeLessThanOrEqual(141);
    expect(c.input).toBe("no inputs");
  });
  it("shows a call that never got a result as not finished", () => {
    expect(toolCards([ev("tool_call", { name: "x", input: { a: 1 } })])[0].outcome).toBe("unfinished");
  });
});

describe("plainSteps", () => {
  it("tells what happened in order, in sentences, and leaves out the internal model steps", () => {
    const steps = plainSteps([ev("user", { message: "where is 1042?" }), ev("llm", { step: 1, stop_reason: "tool_use" }), ev("tool_call", { name: "lookup_order", input: { order_id: "1042" } }),
      ev("tool_result", { name: "lookup_order", output: { status: "shipped" } }), ev("guardrail", { guardrail: "pii_output", reason: "a card number was removed" }),
      ev("handoff", { reason: "asked for a person" }), ev("reply", { reply: "It shipped.", status: "completed" })]);
    expect(steps).toEqual(["The customer wrote: where is 1042?", "Used lookup order (order_id 1042).", "lookup order answered: status shipped.", "The check pii_output stepped in: a card number was removed.",
      "Passed to a person: asked for a person.", "Replied: It shipped."]);
  });
  it("tells what became of a held action once a person decided it", () => {
    expect(plainSteps([ev("approval_execution", { approval: "a1", tool: "issue_refund", outcome: "executed" })])).toEqual(["A person decided issue refund: executed."]);
  });
  it("says when an action was held and when a run failed", () => {
    expect(plainSteps([ev("approval", { tool: "issue_refund", reason: "over limit" }), ev("error", { error: "payment provider down" })]))
      .toEqual(["Held issue refund for a person: over limit.", "Something went wrong: payment provider down."]);
  });
});
