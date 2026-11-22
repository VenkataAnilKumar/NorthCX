import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import Releases from "../app/releases/page";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("") }));
vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), listReleaseRequests: vi.fn(), decideReleaseRequest: vi.fn(), cancelReleaseRequest: vi.fn(), useMe: vi.fn() }));
const api = vi.mocked(client);

const req: client.ReleaseRequestItem = { id: "r1", agent: "support", kind: "publish", environment: "production", version: 3, requestedBy: "ann", note: "Fixes the refund wording",
  status: "pending", decidedBy: null, decisionNote: null, createdAt: 1700000000, decidedAt: null };

function setup(opts: { can?: boolean; name?: string; required?: string[]; requests?: client.ReleaseRequestItem[] } = {}) {
  api.useMe.mockReturnValue({ me: { name: opts.name ?? "ben", role: "release_manager", permissions: [], openMode: false } as never, failed: false, can: () => opts.can ?? true, askForName: false });
  api.listReleaseRequests.mockResolvedValue({ required: opts.required ?? ["production"], requests: opts.requests ?? [req] });
  api.decideReleaseRequest.mockResolvedValue({ ...req, status: "approved" });
  render(<Releases />);
}
beforeEach(() => { vi.clearAllMocks(); });
afterEach(cleanup);

describe("release requests", () => {
  it("shows what is asked for, by whom and why, with a way to compare it with what is live", async () => {
    setup();
    expect(await screen.findByText("support: Version 3 to production")).toBeTruthy();
    expect(screen.getByText(/Asked for by ann/)).toBeTruthy();
    expect(screen.getByText("Fixes the refund wording")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Compare with what is live" }).getAttribute("href")).toBe("/agents/support/compare?candidate=3");
    expect(screen.getByText(/Two people are needed for: production/)).toBeTruthy();
  });

  it("approves with a note, and reloads", async () => {
    setup();
    fireEvent.change(await screen.findByLabelText(/Note/), { target: { value: "Looks right" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve and release" }));
    await waitFor(() => expect(api.decideReleaseRequest).toHaveBeenCalledWith("r1", true, "Looks right"));
    await waitFor(() => expect(api.listReleaseRequests).toHaveBeenCalledTimes(2));
  });

  it("rejects, and shows the server's reason when approving is refused (for example by the person who asked)", async () => {
    setup({ name: "ann" });
    api.decideReleaseRequest.mockRejectedValue(new client.ApiError(403, "You asked for this release, so someone else has to approve it."));
    fireEvent.click(await screen.findByRole("button", { name: "Approve and release" }));
    expect(await screen.findByText(/someone else has to approve it/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(api.decideReleaseRequest).toHaveBeenLastCalledWith("r1", false, undefined));
  });

  it("lets the person who asked withdraw the request", async () => {
    setup({ name: "ann" });
    api.cancelReleaseRequest.mockResolvedValue({ ...req, status: "cancelled" });
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw my request" }));
    await waitFor(() => expect(api.cancelReleaseRequest).toHaveBeenCalledWith("r1"));
  });

  it("offers no approval to someone who may not release, and says so", async () => {
    setup({ can: false });
    expect((await screen.findByRole("button", { name: "Approve and release" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Your role cannot approve releases/)).toBeTruthy();
  });

  it("explains when the two-person rule is off, and an empty list", async () => {
    setup({ required: [], requests: [] });
    expect(await screen.findByText(/two-person rule is off on this server/)).toBeTruthy();
    expect(screen.getByText("Nothing is waiting for approval.")).toBeTruthy();
  });

  it("shows a decided request with who decided it", async () => {
    setup({ requests: [{ ...req, status: "approved", decidedBy: "ben", decidedAt: 1700000100, decisionNote: "Checked" }] });
    expect(await screen.findByText(/Decided by ben/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve and release" })).toBeNull();
  });
});
