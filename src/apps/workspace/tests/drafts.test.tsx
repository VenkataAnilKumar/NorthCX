import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import Drafts from "../app/drafts/page";

vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), listShadowDrafts: vi.fn(), decideShadowDraft: vi.fn(), getShadowSummary: vi.fn(), useMe: vi.fn() }));
const api = vi.mocked(client);

const draft: client.ShadowDraft = { id: "d1", sessionId: "s1", agentId: "support", agentVersion: 1, traceId: "t1", customerMessage: "Where is order 1042?", draft: "Order 1042 shipped on Monday.",
  state: "pending", finalText: null, reasons: [], note: null, decidedBy: null, decidedAt: null, createdAt: 1700000000 };
const summary = (o: Partial<client.ShadowSummary> = {}): client.ShadowSummary => ({ days: 30, total: 0, pending: 1, sent: 0, edited: 0, rejected: 0, expired: 0, decided: 0,
  agreement: { value: null, numerator: 0, denominator: 0 }, rejectReasons: {}, note: "People may skim.", ...o });

function setup(can: (p: string) => boolean = () => true, drafts: client.ShadowDraft[] = [draft], sum = summary()) {
  api.useMe.mockReturnValue({ me: { name: "ann", role: "reviewer", permissions: [], openMode: false } as never, failed: false, can, askForName: false });
  api.listShadowDrafts.mockResolvedValue(drafts);
  api.getShadowSummary.mockResolvedValue(sum);
  api.decideShadowDraft.mockResolvedValue({ ...draft, state: "sent" });
  render(<Drafts />);
}
beforeEach(() => { vi.clearAllMocks(); });
afterEach(cleanup);

describe("drafts screen", () => {
  it("shows what the customer wrote and the agent's reply in a box a person can change", async () => {
    setup();
    const box = (await screen.findByLabelText(/The agent's reply/)) as HTMLTextAreaElement;
    expect(screen.getByText("Where is order 1042?")).toBeTruthy();
    expect(box.value).toBe("Order 1042 shipped on Monday.");
    expect(screen.getByText(/No drafts have been decided/)).toBeTruthy();
  });

  it("sends the draft as it is, naming the person, and reloads", async () => {
    setup();
    await screen.findByLabelText(/The agent's reply/);
    fireEvent.click(screen.getByRole("button", { name: "Send as is" }));
    await waitFor(() => expect(api.decideShadowDraft).toHaveBeenCalledWith("d1", { action: "send", by: "ann" }));
    await waitFor(() => expect(api.listShadowDrafts).toHaveBeenCalledTimes(2));
  });

  it("changes the button to Send my edit once the text differs, and sends the person's text with the reasons and note", async () => {
    setup();
    const box = await screen.findByLabelText(/The agent's reply/);
    fireEvent.change(box, { target: { value: "Order 1042 shipped Monday and arrives Wednesday." } });
    fireEvent.click(screen.getByLabelText("It leaves something out"));
    fireEvent.change(screen.getByLabelText(/Note/), { target: { value: "added the day" } });
    expect(screen.queryByRole("button", { name: "Send as is" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Send my edit" }));
    await waitFor(() => expect(api.decideShadowDraft).toHaveBeenCalledWith("d1", { action: "edit", text: "Order 1042 shipped Monday and arrives Wednesday.", reasons: ["incomplete"], note: "added the day", by: "ann" }));
  });

  it("rejects with a reason and sends nothing", async () => {
    setup();
    await screen.findByLabelText(/The agent's reply/);
    fireEvent.click(screen.getByLabelText("It is wrong"));
    fireEvent.click(screen.getByRole("button", { name: "Reject: send nothing" }));
    await waitFor(() => expect(api.decideShadowDraft).toHaveBeenCalledWith("d1", { action: "reject", reasons: ["wrong"], by: "ann" }));
  });

  it("will not send an empty reply", async () => {
    setup();
    fireEvent.change(await screen.findByLabelText(/The agent's reply/), { target: { value: "   " } });
    expect((screen.getByRole("button", { name: "Send my edit" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the server's reason when a decision is refused and keeps the text so it can be fixed", async () => {
    setup();
    api.decideShadowDraft.mockRejectedValue(new client.ApiError(400, "A check stopped this reply: never promise a delivery day. Change the text and try again"));
    const box = await screen.findByLabelText(/The agent's reply/);
    fireEvent.change(box, { target: { value: "We guarantee Monday." } });
    fireEvent.click(screen.getByRole("button", { name: "Send my edit" }));
    expect(await screen.findByText(/never promise a delivery day/)).toBeTruthy();
    expect((screen.getByLabelText(/The agent's reply/) as HTMLTextAreaElement).value).toBe("We guarantee Monday.");
  });

  it("tells someone who may not review that, and offers no sending", async () => {
    setup((p) => p !== "shadow:review");
    await screen.findByLabelText(/The agent's reply/);
    expect((screen.getByRole("button", { name: "Send as is" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Your role cannot review drafts/)).toBeTruthy();
  });

  it("shows the agreement with its numbers, and a decided draft with what was sent instead", async () => {
    setup(undefined, [{ ...draft, state: "edited", finalText: "Order 1042 arrives Wednesday.", decidedBy: "ann", reasons: ["incomplete"] }], summary({ decided: 4, sent: 2, edited: 1, rejected: 1, agreement: { value: 0.5, numerator: 2, denominator: 4 } }));
    expect(await screen.findByText(/4 drafts decided/)).toBeTruthy();
    expect(screen.getByText(/unchanged \(50%\)/)).toBeTruthy();
    const card = screen.getByText("Sent instead").closest("div")!;
    expect(within(card.parentElement!).getByText("Order 1042 arrives Wednesday.")).toBeTruthy();
    expect(screen.getByText(/Decided by ann · It leaves something out/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Send/ })).toBeNull();
  });

  it("explains an empty waiting list", async () => {
    setup(undefined, []);
    expect(await screen.findByText(/No drafts are waiting/)).toBeTruthy();
  });
});
