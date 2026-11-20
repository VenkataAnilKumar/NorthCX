import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import { ReplayPlayer } from "../components/replay-player";
import { buildFrames } from "../lib/replay";

vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), rerunTurn: vi.fn() }));
const api = vi.mocked(client);

const ev = (t: number, type: string, data: Record<string, unknown>): client.TraceEvent => ({ t, type, data });
const traces: client.Trace[] = [
  { id: "t1", agent_id: "support", session_id: "s", agent_version: 1, events: [ev(1, "user", { message: "where is 1042?" }), ev(2, "tool_call", { name: "lookup_order", input: { order_id: "1042" } }),
    ev(3, "tool_result", { name: "lookup_order", output: { status: "shipped" } }), ev(4, "reply", { reply: "It shipped.", status: "completed" })] },
  { id: "t2", agent_id: "support", session_id: "s", agent_version: 1, events: [ev(10, "user", { message: "refund it" }), ev(11, "reply", { reply: "I can help with that.", status: "completed" })] },
];
const turns = [{ turn: 1, message: "where is 1042?" }, { turn: 2, message: "refund it" }];
const originals = { 1: "It shipped.", 2: "I can help with that." };
const frames = buildFrames(traces, turns);

function show(canRerun = true) { render(<ReplayPlayer sessionId="s" frames={frames} originals={originals} canRerun={canRerun} />); }
beforeEach(() => { vi.clearAllMocks(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("replay player", () => {
  it("starts at the first step and builds the conversation up as the person steps forward", () => {
    show();
    expect(screen.getByRole("status").textContent).toBe(`Step 1 of ${frames.length}`);
    expect(screen.getByLabelText("Conversation so far").textContent).toContain("where is 1042?");
    expect(screen.getByLabelText("Conversation so far").textContent).not.toContain("It shipped.");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByLabelText("Conversation so far").textContent).toContain("answered: status shipped");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByLabelText("Conversation so far").textContent).toContain("It shipped.");
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByLabelText("Conversation so far").textContent).not.toContain("It shipped.");
  });

  it("jumps to a step from the list or the slider and marks the current one", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "The customer wrote: refund it" }));
    expect(screen.getByRole("button", { name: "The customer wrote: refund it" }).getAttribute("aria-current")).toBe("step");
    expect(screen.getByRole("status").textContent).toBe(`Step 5 of ${frames.length}`);
    fireEvent.change(screen.getByRole("slider"), { target: { value: "0" } });
    expect(screen.getByRole("status").textContent).toBe(`Step 1 of ${frames.length}`);
  });

  it("plays one step at a time and stops at the end", async () => {
    vi.useFakeTimers();
    show();
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByRole("status").textContent).toBe(`Step 2 of ${frames.length}`);
    await act(async () => { await vi.advanceTimersByTimeAsync(900 * frames.length); });
    expect(screen.getByRole("status").textContent).toBe(`Step ${frames.length} of ${frames.length}`);
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();         // it paused itself
  });

  it("only reads: replaying makes no call to the agent", async () => {
    show();
    for (const b of ["Next", "Next", "Previous"]) fireEvent.click(screen.getByRole("button", { name: b }));
    expect(api.rerunTurn).not.toHaveBeenCalled();
  });

  it("edits a customer message, runs it in the sandbox and shows what happened beside what would happen", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "The customer wrote: refund it" }));
    api.rerunTurn.mockResolvedValue({ sessionId: "s", turn: 2, agent: "support", sandbox: true, note: "Nothing was saved or sent.", original: { message: "refund it", reply: "I can help with that." },
      rerun: { message: "refund order 1042 for 30", reply: "Done: a refund of 30 is on its way.", status: "completed", toolsCalled: ["issue_refund"],
        events: [ev(1, "tool_call", { name: "issue_refund", input: { order_id: "1042", amount: 30 } }), ev(2, "tool_result", { name: "issue_refund", output: { ok: true }, dry_run: true }), ev(3, "reply", { reply: "Done: a refund of 30 is on its way.", status: "completed" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Edit and run again: message 2" }));
    const panel = screen.getByRole("group", { name: "Edit and run again: message 2" });
    fireEvent.change(within(panel).getByLabelText(/What the customer would say instead/), { target: { value: "refund order 1042 for 30" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Run again" }));
    await waitFor(() => expect(api.rerunTurn).toHaveBeenCalledWith("s", 2, "refund order 1042 for 30"));
    const result = await within(panel).findByLabelText("Result");
    expect(result.textContent).toContain("I can help with that.");
    expect(result.textContent).toContain("Done: a refund of 30 is on its way.");
    expect(result.textContent).toContain("Used issue refund (order_id 1042, amount 30)");
    expect(result.textContent).toContain("Nothing was saved or sent.");
  });

  it("shows why a rerun was refused and keeps what was typed", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "The customer wrote: refund it" }));
    api.rerunTurn.mockRejectedValue(new client.ApiError(400, "This conversation has 1 customer message; choose a turn from 1 to 1"));
    fireEvent.click(screen.getByRole("button", { name: "Edit and run again: message 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Run again" }));
    expect(await screen.findByText(/choose a turn from 1 to 1/)).toBeTruthy();
    expect((screen.getByLabelText(/What the customer would say instead/) as HTMLTextAreaElement).value).toBe("refund it");
  });

  it("offers no editing to someone who may not run simulations", () => {
    show(false);
    fireEvent.click(screen.getByRole("button", { name: "The customer wrote: refund it" }));
    expect(screen.queryByRole("button", { name: /Edit and run again/ })).toBeNull();
  });

  it("says so when there is nothing to replay", () => {
    render(<ReplayPlayer sessionId="s" frames={[]} originals={{}} canRerun />);
    expect(screen.getByText(/no steps to replay/)).toBeTruthy();
  });
});
