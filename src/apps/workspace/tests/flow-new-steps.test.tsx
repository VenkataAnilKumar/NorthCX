import { createElement, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FlowEditor } from "../components/FlowEditor";
import type { Definition } from "../components/flow";

afterEach(cleanup);
const catalog = { reports: [], events: ["handoff.created"], destinations: [], assistants: ["shift-briefing"], tools: [{ name: "lookup_order", effect: "read" }, { name: "issue_refund", effect: "write" }], agents: ["support"],
  kinds: ["tool", "branch", "foreach", "simulate", "criteria", "alert", "person"], triggers: ["manual", "webhook", "event"], triggerInfo: [{ type: "manual", label: "Run by hand", description: "" }, { type: "webhook", label: "When a system calls", description: "" }] };

function Harness({ initial }: { initial: Definition }) {
  const [d, setD] = useState(initial);
  return createElement("div", null, createElement(FlowEditor, { value: d, onChange: setD, catalog }), createElement("pre", { "data-testid": "json" }, JSON.stringify(d)));
}
const def = () => JSON.parse(screen.getByTestId("json").textContent ?? "{}") as Definition;
const open = (re: RegExp) => fireEvent.click(screen.getByRole("button", { name: re }));
const base = (steps: Definition["steps"], trigger: Definition["trigger"] = { type: "manual" }): Definition => ({ id: "r1", name: "R", trigger, steps });

describe("the canvas edits the new step kinds", () => {
  it("shows each new kind as a card with a plain summary", () => {
    render(createElement(Harness, { initial: base([
      { id: "t", kind: "tool", tool: "lookup_order", args: {} }, { id: "b", kind: "branch", when: "previous.total > 100", then: "continue", else: "stop" },
      { id: "f", kind: "foreach", over: "input.orders", max: 5, do: { kind: "tool", tool: "lookup_order", args: {} } }, { id: "s", kind: "simulate", agent: "support", mode: "scripted" },
      { id: "c", kind: "criteria", agent: "support", criteria: ["Be kind to customers"], sample: 5, days: 7 }, { id: "a", kind: "alert", severity: "critical", text: "Something is wrong" }]) }));
    for (const re of [/Call a tool/, /Check a condition/, /Do for each item/, /Check an agent/, /Judge conversations/, /Raise an alert/]) expect(screen.getByRole("button", { name: re })).toBeTruthy();
    expect(screen.getByText("if previous.total > 100")).toBeTruthy();
    expect(screen.getByText("support, scripted")).toBeTruthy();
    expect(screen.getByText("1 criteria on support")).toBeTruthy();
  });

  it("sets a tool and its arguments, and keeps the last valid arguments while the text is not valid JSON", () => {
    render(createElement(Harness, { initial: base([{ id: "t", kind: "tool", tool: "", args: {} }]) }));
    open(/Step 1/);
    fireEvent.change(screen.getByLabelText("Tool"), { target: { value: "lookup_order" } });
    expect(screen.getByText("This tool only reads.")).toBeTruthy();
    const args = screen.getByLabelText(/Arguments/);
    fireEvent.change(args, { target: { value: '{"order_id": "{{input.order}}"}' } });
    expect(def().steps[0]).toMatchObject({ tool: "lookup_order", args: { order_id: "{{input.order}}" } });
    fireEvent.change(args, { target: { value: '{"order_id": ' } });
    expect(screen.getByRole("alert").textContent).toMatch(/not valid JSON/);
    expect(def().steps[0].args).toEqual({ order_id: "{{input.order}}" });
  });

  it("warns when a tool that changes something has no person step before it on every path", () => {
    render(createElement(Harness, { initial: base([{ id: "r", kind: "tool", tool: "issue_refund", args: {} }]) }));
    expect(screen.getByLabelText("Things to fix").textContent).toMatch(/'r' changes something/);
    open(/Step 1/);
    expect(screen.getByText(/This tool changes something/)).toBeTruthy();
  });

  it("edits a branch: the condition, and a skip with its number", () => {
    render(createElement(Harness, { initial: base([{ id: "b", kind: "branch", when: "", then: "continue", else: "stop" }, { id: "x", kind: "tag", tag: "a" }]) }));
    open(/Step 1/);
    fireEvent.change(screen.getByLabelText(/Condition/), { target: { value: "input.priority == 'urgent'" } });
    fireEvent.change(screen.getByLabelText("If true"), { target: { value: "skip steps" } });
    fireEvent.change(screen.getByLabelText(/Skip how many steps/), { target: { value: "2" } });
    expect(def().steps[0]).toMatchObject({ when: "input.priority == 'urgent'", then: { skip: 2 }, else: "stop" });
  });

  it("edits a for-each step and switches what it does for each item", () => {
    render(createElement(Harness, { initial: base([{ id: "f", kind: "foreach", over: "", max: 10, do: { kind: "tool", tool: "", args: {} } }]) }));
    open(/Step 1/);
    fireEvent.change(screen.getByLabelText(/List to go through/), { target: { value: "input.orders" } });
    fireEvent.change(screen.getByLabelText(/Most items/), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("For each item"), { target: { value: "assistant" } });
    fireEvent.change(screen.getByLabelText("Staff assistant"), { target: { value: "shift-briefing" } });
    expect(def().steps[0]).toMatchObject({ over: "input.orders", max: 20, do: { kind: "assistant", assistant: "shift-briefing", prompt: "" } });
  });

  it("says a judged result is unverified, and takes criteria one per line", () => {
    render(createElement(Harness, { initial: base([{ id: "c", kind: "criteria", agent: "", criteria: [], sample: 10, days: 7 }]) }));
    open(/Step 1/);
    expect(screen.getByRole("note").textContent).toMatch(/^Unverified/);
    fireEvent.change(screen.getByLabelText(/Criteria, one per line/), { target: { value: "Replies are polite\n\nNo refund promises" } });
    expect(def().steps[0].criteria).toEqual(["Replies are polite", "No refund promises"]);
  });

  it("offers a condition on webhook and event triggers only", () => {
    render(createElement(Harness, { initial: base([{ id: "t", kind: "tag", tag: "a" }], { type: "webhook" }) }));
    open(/Trigger/);
    fireEvent.change(screen.getByLabelText(/Only when/), { target: { value: "input.a == 1" } });
    expect(def().trigger).toEqual({ type: "webhook", when: "input.a == 1" });
    cleanup();
    render(createElement(Harness, { initial: base([{ id: "t", kind: "tag", tag: "a" }]) }));
    open(/Trigger/);
    expect(screen.queryByLabelText(/Only when/)).toBeNull();
  });
});
