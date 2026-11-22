import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import Compare from "../app/agents/[id]/compare/page";

let query = "candidate=3";
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(query) }));
vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), listVersions: vi.fn(), compareVersions: vi.fn(), useMe: vi.fn() }));
const api = vi.mocked(client);

const versions = [{ number: 3, live: false }, { number: 2, live: true }, { number: 1, live: false }] as never;
const result = (regressed: boolean): client.Comparison => ({ agent: "support", live: { number: 2, digest: "a" }, candidate: { number: 3, digest: "b" },
  counts: { live: { total: 3, passed: 3, failed: 0 }, candidate: { total: 3, passed: regressed ? 2 : 3, failed: regressed ? 1 : 0 } },
  scenarios: [{ name: "refund-small", required: true, live: true, candidate: true, change: "same" }, { name: "order-lookup", required: false, live: true, candidate: !regressed, change: regressed ? "regressed" : "same" },
    { name: "legal-topic", required: true, live: true, candidate: true, change: "same" }],
  verdict: regressed ? "The candidate fails 1 test that the live version passes: order-lookup." : "The candidate gives the same results as the live version on 3 tests.",
  differences: { from: 2, to: 3, identical: false, instructions: "-old\n+new", tools: { added: [], removed: [] }, guardrails: { added: [], removed: [], changed: [] }, input_guardrails: { added: [], removed: [], changed: [] }, forced_handoff: { added: ["orders"], removed: [], changed: [] }, other: {} } });

async function show(can = true) {
  api.useMe.mockReturnValue({ me: null, failed: false, can: () => can, askForName: false });
  api.listVersions.mockResolvedValue(versions);
  await act(async () => { render(<Suspense fallback="loading"><Compare params={Promise.resolve({ id: "support" })} /></Suspense>); });
}
beforeEach(() => { vi.clearAllMocks(); query = "candidate=3"; });
afterEach(cleanup);

describe("live and candidate side by side", () => {
  it("starts with the candidate from the address and runs the same tests on both when asked", async () => {
    await show();
    expect(((await screen.findByLabelText("Candidate version")) as HTMLSelectElement).value).toBe("3");
    api.compareVersions.mockResolvedValue(result(true));
    fireEvent.click(screen.getByRole("button", { name: "Run the same tests on both" }));
    await waitFor(() => expect(api.compareVersions).toHaveBeenCalledWith("support", 3));
    expect((await screen.findByRole("status")).textContent).toBe("The candidate fails 1 test that the live version passes: order-lookup.");
  });

  it("shows each test on both versions with what changed, the counts and what differs", async () => {
    await show();
    api.compareVersions.mockResolvedValue(result(true));
    fireEvent.click(await screen.findByRole("button", { name: "Run the same tests on both" }));
    const table = await screen.findByRole("table", { name: "Results on the same tests" });
    const row = within(table).getByText("order-lookup").closest("tr")!;
    expect(row.textContent).toContain("PassesFailsNow fails");
    expect(within(table).getByText("refund-small").closest("tr")!.textContent).toContain("required");
    expect(within(screen.getByLabelText("Live")).getByText("3 of 3 tests pass")).toBeTruthy();
    expect(within(screen.getByLabelText("Candidate")).getByText("2 of 3 tests pass")).toBeTruthy();
    expect(within(screen.getByLabelText("What differs")).getByText(/orders/)).toBeTruthy();
  });

  it("says plainly when nothing changed, and shows a refusal with its reason", async () => {
    await show();
    api.compareVersions.mockResolvedValueOnce(result(false));
    fireEvent.click(await screen.findByRole("button", { name: "Run the same tests on both" }));
    expect((await screen.findByRole("status")).textContent).toContain("same results");
    api.compareVersions.mockRejectedValueOnce(new client.ApiError(409, "Another test run is in progress. Wait for it to finish."));
    fireEvent.click(screen.getByRole("button", { name: "Run the same tests on both" }));
    expect(await screen.findByText(/Another test run is in progress/)).toBeTruthy();
  });

  it("offers no run to someone who may not run tests, and explains an agent with no versions", async () => {
    await show(false);
    expect((await screen.findByRole("button", { name: "Run the same tests on both" }) as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    api.listVersions.mockResolvedValue([] as never);
    await act(async () => { render(<Suspense fallback="loading"><Compare params={Promise.resolve({ id: "support" })} /></Suspense>); });
    expect(await screen.findByText(/no saved version yet/)).toBeTruthy();
  });
});
