import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import { SaveTest } from "../components/try-panel";

vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), createScenario: vi.fn(), useMe: vi.fn() }));
const api = vi.mocked(client);
beforeEach(() => { vi.clearAllMocks(); api.useMe.mockReturnValue({ me: null, failed: false, can: () => true, askForName: false }); });
afterEach(cleanup);

describe("SaveTest", () => {
  it("turns a conversation into a test in one click and links to it", async () => {
    api.createScenario.mockResolvedValue({ name: "refund-question", revision: 1 } as never);
    render(<SaveTest yaml={async () => "name: refund-question\nagent: support\n"} label="Save as a test" />);
    fireEvent.click(screen.getByRole("button", { name: "Save as a test" }));
    await waitFor(() => expect(api.createScenario).toHaveBeenCalledWith({ yaml: "name: refund-question\nagent: support\n" }));
    expect((await screen.findByRole("link", { name: "refund-question" })).getAttribute("href")).toBe("/simulations/scenarios/refund-question");
  });
  it("shows what went wrong and offers the button again", async () => {
    api.createScenario.mockRejectedValue(new client.ApiError(400, "A test with that name already exists. Rename it and try again."));
    render(<SaveTest yaml={async () => "x"} label="Save as a test" />);
    fireEvent.click(screen.getByRole("button", { name: "Save as a test" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save as a test" })).toBeTruthy();
  });
  it("is not shown to someone who may not write tests", () => {
    api.useMe.mockReturnValue({ me: null, failed: false, can: (p: string) => p !== "scenarios:write", askForName: false });
    render(<SaveTest yaml={async () => "x"} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
