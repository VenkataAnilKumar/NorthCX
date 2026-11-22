import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JourneyGraph } from "@/components/journey-graph";

const j = { name: "refund", goal: "Refund an order", when: "a customer wants a refund", steps: [{ purpose: "Find the order", tool: "lookup_order" }, { purpose: "Refund it", tool: "issue_refund", required: false }], done_when: ["issue_refund"], handoff_if: ["They mention a lawyer"] };

afterEach(cleanup);

describe("journey graph view", () => {
  it("shows the start, each step, the done condition and the hand-over branch", () => {
    render(<JourneyGraph journey={j} onChange={() => {}} />);
    expect(screen.getByText(/a customer wants a refund/)).toBeTruthy();
    expect(screen.getByText("1. Find the order")).toBeTruthy();
    expect(screen.getByText(/uses issue_refund · optional/)).toBeTruthy();
    expect(screen.getByText(/issue_refund has run/)).toBeTruthy();
    expect(screen.getByText("They mention a lawyer")).toBeTruthy();
  });
  it("moves a step and reports the changed journey", () => {
    const onChange = vi.fn();
    render(<JourneyGraph journey={j} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("Move step 2 up"));
    expect(onChange.mock.calls[0][0].steps.map((s: { purpose: string }) => s.purpose)).toEqual(["Refund it", "Find the order"]);
  });
  it("cannot move the first step up or the last down", () => {
    render(<JourneyGraph journey={j} onChange={() => {}} />);
    expect((screen.getByLabelText("Move step 1 up") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Move step 2 down") as HTMLButtonElement).disabled).toBe(true);
  });
  it("removes a hand-over condition", () => {
    const onChange = vi.fn();
    render(<JourneyGraph journey={j} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("Remove hand-over condition 1"));
    expect(onChange.mock.calls[0][0].handoff_if).toBeUndefined();
  });
  it("offers a first step on an empty journey", () => {
    const onChange = vi.fn();
    render(<JourneyGraph journey={{ name: "a", goal: "g", steps: [] }} onChange={onChange} />);
    fireEvent.click(screen.getByText("Add the first step"));
    expect(onChange.mock.calls[0][0].steps).toEqual([{ purpose: "New step", required: true }]);
  });
});
