import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import TestConsole from "../app/chat/page";

vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), listAgents: vi.fn(), chatStream: vi.fn(), getTrace: vi.fn(), listOutbox: vi.fn(), listApprovals: vi.fn(),
  decideApproval: vi.fn(), useMe: vi.fn() }));
const api = vi.mocked(client);

const events = [{ t: 0, type: "user", data: { message: "refund 240" } }, { t: 1, type: "tool_call", data: { name: "issue_refund", input: { order_id: "2077", amount: 240 } } },
  { t: 2, type: "approval", data: { tool: "issue_refund", reason: "Refunds over 100 need a person" } }];
const held: client.ChatReply = { reply: "I have asked a person to approve this refund.", status: "needs_approval", traceId: "t1", handoffId: null, agentVersion: 1,
  pendingApprovals: [{ id: "ap1", tool: "issue_refund", reason: "Refunds over 100 need a person" }] };
const decided = (approved: boolean) => ({ id: "ap1", state: approved ? "executed" : "rejected", decided_by: "ann", resume: { reply: "done", status: "completed", traceId: "t2" } }) as never;

function setup(can: (p: string) => boolean = () => true) {
  api.useMe.mockReturnValue({ me: null, failed: false, can, askForName: false });
  api.listAgents.mockResolvedValue([{ id: "support" }] as never);
  api.chatStream.mockResolvedValue(held);
  api.getTrace.mockResolvedValue({ id: "t1", agent_id: "support", session_id: "s", agent_version: 1, events });
  api.listOutbox.mockResolvedValue([]);
  api.listApprovals.mockResolvedValue([{ id: "ap1" }] as never);
  render(<TestConsole />);
}
async function ask() {
  await screen.findByRole("option", { name: "support" });
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: "refund 240" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  return await screen.findByRole("group", { name: "Approval: issue refund" });
}

beforeEach(() => { vi.clearAllMocks(); });
afterEach(cleanup);

describe("test console", () => {
  it("shows what the agent used as a card, the held action with what it would do and why, and the trace in sentences", async () => {
    setup();
    const card = await ask();
    expect(within(card).getByText(/order_id 2077, amount 240/)).toBeTruthy();
    expect(within(card).getByText(/Refunds over 100 need a person/)).toBeTruthy();
    const tool = screen.getByRole("group", { name: "Tool: issue refund" });
    expect(within(tool).getByText(/Held for a person/)).toBeTruthy();
    const steps = screen.getByRole("list", { name: "What happened, in words" });
    expect(within(steps).getByText("Held issue refund for a person: Refunds over 100 need a person.")).toBeTruthy();
  });

  it("approves from the card, shows who decided, and fetches the follow-up the customer received", async () => {
    setup();
    let sent = false;                                              // the customer's message exists only once the decision was made
    api.decideApproval.mockImplementation(async () => { sent = true; return decided(true); });
    api.listOutbox.mockImplementation(async () => (sent ? [{ id: 7, reply: "Your refund went through.", status: "completed", traceId: "t2" }] : []) as never);
    await ask();
    fireEvent.click(screen.getByRole("button", { name: "Approve issue refund" }));
    expect(await screen.findByText(/Approved by ann/)).toBeTruthy();
    expect(api.decideApproval).toHaveBeenCalledWith("ap1", true);
    expect(await screen.findByText("Your refund went through.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve issue refund" })).toBeNull();
  });

  it("rejects from the card", async () => {
    setup();
    api.decideApproval.mockResolvedValue(decided(false));
    await ask();
    fireEvent.click(screen.getByRole("button", { name: "Reject issue refund" }));
    expect(await screen.findByText(/Rejected by ann/)).toBeTruthy();
    expect(api.decideApproval).toHaveBeenCalledWith("ap1", false);
  });

  it("says nothing ran when the action was decided elsewhere first (the server answers 409)", async () => {
    setup();
    api.decideApproval.mockRejectedValue(new client.ApiError(409, "already decided"));
    await ask();
    fireEvent.click(screen.getByRole("button", { name: "Approve issue refund" }));
    expect(await screen.findByText(/No longer waiting: it was decided somewhere else or it expired/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve issue refund" })).toBeNull();
  });

  it("notices an expired action without a click: the card stops offering buttons", async () => {
    setup();
    await ask();
    api.listApprovals.mockResolvedValue([]);                       // no longer pending
    expect(await screen.findByText(/No longer waiting/, {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve issue refund" })).toBeNull();
    expect(api.decideApproval).not.toHaveBeenCalled();
  });

  it("gives someone who cannot decide approvals no buttons and a next step", async () => {
    setup((p) => p !== "approvals:decide");
    const card = await ask();
    expect(within(card).queryByRole("button")).toBeNull();
    expect(within(card).getByText(/Your role cannot decide approvals/)).toBeTruthy();
  });

  it("shows a failed decision as an error and leaves the buttons so it can be retried", async () => {
    setup();
    api.decideApproval.mockRejectedValue(new client.ApiError(500, "The server could not run the action"));
    await ask();
    fireEvent.click(screen.getByRole("button", { name: "Approve issue refund" }));
    await waitFor(() => expect(screen.getByText(/The server could not run the action/)).toBeTruthy());
    expect(screen.getByRole("button", { name: "Approve issue refund" })).toBeTruthy();
  });
});
