import { createElement, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FlowEditor } from "../components/FlowEditor";
import type { Definition } from "../components/flow";

afterEach(cleanup);
const catalog = { reports: ["performance", "quality"], events: ["handoff.created"], destinations: ["ops-chat"], assistants: ["shift-briefing"], kinds: ["report", "assistant", "person", "tag", "notify", "output"], triggers: ["manual", "schedule", "webhook", "event"] };
const START: Definition = { id: "r1", name: "R", trigger: { type: "manual" }, steps: [{ id: "a", kind: "report", report: "performance", days: 1 }, { id: "b", kind: "output", title: "Digest" }, { id: "c", kind: "tag", tag: "x" }] };

function Harness({ initial = START }: { initial?: Definition }) {
  const [d, setD] = useState(initial);
  return createElement("div", null, createElement(FlowEditor, { value: d, onChange: setD, catalog }), createElement("pre", { "data-testid": "json" }, JSON.stringify(d.steps.map((s) => s.id))));
}
const ids = () => JSON.parse(screen.getByTestId("json").textContent ?? "[]") as string[];
const card = (n: RegExp) => screen.getByRole("button", { name: n });

describe("the canvas editor", () => {
  it("shows the trigger and each step as a card, in order", () => {
    render(createElement(Harness));
    const list = screen.getByRole("list", { name: "Routine steps" });
    expect(list.querySelectorAll("li")).toHaveLength(4);
    expect(card(/Trigger: Starts by hand/)).toBeTruthy();
    expect(card(/Step 2: Save to Outputs/)).toBeTruthy();
  });

  it("moves between cards with the arrow keys and reorders with Alt and the arrows, from the keyboard alone", () => {
    render(createElement(Harness));
    const first = card(/Step 1/);
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement).toBe(card(/Step 2/));
    fireEvent.keyDown(card(/Step 2/), { key: "ArrowDown", altKey: true });
    expect(ids()).toEqual(["a", "c", "b"]);
    fireEvent.keyDown(card(/Step 1/), { key: "ArrowUp", altKey: true });
    expect(ids()).toEqual(["a", "c", "b"]);                       // the first step cannot go above itself
  });

  it("removes the focused step with Delete but never the trigger", () => {
    render(createElement(Harness));
    fireEvent.keyDown(card(/Step 2/), { key: "Delete" });
    expect(ids()).toEqual(["a", "c"]);
    fireEvent.keyDown(card(/Trigger/), { key: "Delete" });
    expect(ids()).toEqual(["a", "c"]);
  });

  it("adds a step of the chosen kind after the selected one and shows its form", () => {
    render(createElement(Harness));
    fireEvent.click(card(/Step 1/));
    fireEvent.change(screen.getByLabelText("Add a step"), { target: { value: "person" } });
    fireEvent.click(screen.getByRole("button", { name: /Add after 'a'/ }));
    expect(ids()).toEqual(["a", "person1", "b", "c"]);
    expect(screen.getByLabelText("Question for the person")).toBeTruthy();
  });

  it("edits a step's fields and warns about what the server would refuse", () => {
    render(createElement(Harness, { initial: { ...START, steps: [{ id: "send", kind: "notify", to: "" }] } }));
    expect(screen.getByRole("list", { name: "Things to fix" }).textContent).toContain("'Ask a person' step must come before it");
    fireEvent.click(card(/Step 1/));
    fireEvent.change(screen.getByLabelText("Send to"), { target: { value: "ops-chat" } });
    expect(card(/Step 1: Send out\. to ops-chat/)).toBeTruthy();
  });

  it("shows the same routine as a list, and the trigger form changes the trigger", () => {
    render(createElement(Harness));
    fireEvent.click(screen.getByRole("button", { name: "List" }));
    expect(screen.getByRole("list", { name: "Routine steps as a list" }).querySelectorAll("li")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "Starts by hand" }));
    fireEvent.change(screen.getByLabelText("Starts"), { target: { value: "schedule" } });
    expect(screen.getByLabelText("Every (hours)")).toBeTruthy();
  });

  it("is read-only when asked to be", () => {
    render(createElement(FlowEditor, { value: START, onChange: () => { throw new Error("changed"); }, catalog, readOnly: true }));
    fireEvent.keyDown(card(/Step 2/), { key: "Delete" });
    expect(screen.queryByRole("button", { name: /Add after/ })).toBeNull();
  });
});
